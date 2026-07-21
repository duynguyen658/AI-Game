from __future__ import annotations

import io
import re
import zipfile
from datetime import UTC, datetime

from docx import Document
from pypdf import PdfReader

from app.core.config import Settings
from app.core.exceptions import M7ValidationError
from app.database.models import PromptVersionModel
from app.llm.base import LLMClient
from app.llm.capabilities import CompletionRequest
from app.prompt_management.renderer import PromptRenderer
from app.schemas.document_processing import (
    DocumentConsistencyAnalysis,
    DocumentInconsistency,
    DocumentProcessingResult,
    DocumentType,
)

INJECTION_PATTERN = re.compile(
    r"(?i)(ignore (all|previous) instructions|system prompt|developer message|reveal secrets)"
)
SECTION_REQUIREMENTS = {
    DocumentType.MARKETING_BRIEF: [
        "objective",
        "audience",
        "message",
        "budget",
        "timeline",
    ],
    DocumentType.CAMPAIGN_REPORT: ["summary", "results", "metrics", "learnings"],
    DocumentType.GAME_DESIGN_DOCUMENT: ["gameplay", "mechanics", "progression", "art"],
    DocumentType.PRODUCT_REQUIREMENT_DOCUMENT: [
        "problem",
        "requirements",
        "acceptance",
        "risks",
    ],
    DocumentType.MEETING_NOTES: ["attendees", "decisions", "actions"],
    DocumentType.UNKNOWN: [],
}


async def process_document(
    content: bytes,
    *,
    filename: str,
    content_type: str,
    settings: Settings,
    llm_client: LLMClient,
    prompt_version: PromptVersionModel,
) -> DocumentProcessingResult:
    if len(content) > settings.max_upload_bytes:
        raise M7ValidationError("Document exceeds the configured size limit")
    extension = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if extension == "pdf":
        if not content.startswith(b"%PDF") or content_type not in {
            "application/pdf",
            "application/octet-stream",
        }:
            raise M7ValidationError(
                "PDF extension, MIME type, and signature do not match"
            )
        text, pages = _extract_pdf(content, settings.max_document_pages)
    elif extension == "docx":
        if not content.startswith(b"PK") or content_type not in {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/octet-stream",
        }:
            raise M7ValidationError(
                "DOCX extension, MIME type, and signature do not match"
            )
        _validate_docx_archive(content)
        text, pages = _extract_docx(content)
    elif extension == "txt":
        if b"\x00" in content or content_type not in {
            "text/plain",
            "application/octet-stream",
        }:
            raise M7ValidationError("TXT file type is invalid")
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise M7ValidationError("TXT documents must be UTF-8 encoded") from exc
        pages = 1
    else:
        raise M7ValidationError("Supported document types are PDF, DOCX, and TXT")
    if not text.strip():
        raise M7ValidationError(
            "Document contains no extractable text; OCR is disabled"
        )
    text = text.replace("\x00", " ")[:200_000]
    document_type, confidence = _classify(text)
    lower = text.lower()
    missing = [
        section
        for section in SECTION_REQUIREMENTS[document_type]
        if section not in lower
    ]
    warning = bool(INJECTION_PATTERN.search(text))
    safe_excerpt = INJECTION_PATTERN.sub("[UNTRUSTED_INSTRUCTION]", text[:20_000])
    completion = await llm_client.complete(
        CompletionRequest(
            system_prompt=prompt_version.system_prompt,
            user_prompt=PromptRenderer().render(
                prompt_version.user_prompt_template,
                {"document": safe_excerpt},
                allowed_variables={
                    key for key in prompt_version.variables if not key.startswith("__")
                },
                allow_unknown=bool(
                    prompt_version.variables.get("__allow_unknown__", False)
                ),
            ),
            model=settings.llm_model or "mock-applied-ai",
            max_output_tokens=1000,
        )
    )
    consistency_completion = await llm_client.complete_structured(
        CompletionRequest(
            system_prompt=prompt_version.system_prompt,
            user_prompt=(
                PromptRenderer().render(
                    prompt_version.user_prompt_template,
                    {"document": safe_excerpt},
                    allowed_variables={
                        key
                        for key in prompt_version.variables
                        if not key.startswith("__")
                    },
                    allow_unknown=bool(
                        prompt_version.variables.get("__allow_unknown__", False)
                    ),
                )
                + "\nReturn only structured consistency findings. Label model-assisted "
                "findings and do not include hidden reasoning."
            ),
            model=settings.llm_model or "mock-applied-ai",
            max_output_tokens=1500,
        ),
        DocumentConsistencyAnalysis,
    )
    model_findings = DocumentConsistencyAnalysis.model_validate(
        consistency_completion.structured
    ).findings
    for finding in model_findings:
        finding.detection_method = "MODEL_ASSISTED"
    lines = [line.strip(" -\t") for line in text.splitlines() if line.strip()]
    actions = [
        line[:500]
        for line in lines
        if re.search(r"(?i)\b(action|todo|owner|due)\b", line)
    ][:30]
    questions = [line[:500] for line in lines if line.endswith("?")][:30]
    risks = [
        line[:500] for line in lines if re.search(r"(?i)\b(risk|blocker|issue)\b", line)
    ][:30]
    return DocumentProcessingResult(
        document_type=document_type,
        executive_summary=(completion.content or "Document extracted successfully.")[
            :5000
        ],
        key_points=lines[:10],
        missing_sections=missing,
        inconsistencies=_deterministic_inconsistencies(text) + model_findings,
        risks=risks,
        action_items=actions,
        open_questions=questions,
        confidence=confidence,
        limitations=[
            "Document content is treated as untrusted data.",
            "No OCR, macro execution, attachment execution, or external link fetching was performed.",
        ],
        prompt_injection_warning=warning,
        page_count=pages,
        character_count=len(text),
        generated_at=datetime.now(UTC),
    )


def _extract_pdf(content: bytes, max_pages: int) -> tuple[str, int]:
    try:
        reader = PdfReader(io.BytesIO(content), strict=True)
        if len(reader.pages) > max_pages:
            raise M7ValidationError("PDF page count exceeds the configured limit")
        return "\n".join(page.extract_text() or "" for page in reader.pages), len(
            reader.pages
        )
    except M7ValidationError:
        raise
    except Exception as exc:
        raise M7ValidationError("PDF could not be extracted safely") from exc


def _validate_docx_archive(content: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            if len(infos) > 2000:
                raise M7ValidationError("DOCX archive contains too many entries")
            compressed = sum(info.compress_size for info in infos)
            uncompressed = sum(info.file_size for info in infos)
            if uncompressed > 50_000_000 or uncompressed > max(compressed, 1) * 100:
                raise M7ValidationError("DOCX archive expansion is unsafe")
            if any("vbaProject.bin" in info.filename for info in infos):
                raise M7ValidationError("Macro-enabled documents are not supported")
    except zipfile.BadZipFile as exc:
        raise M7ValidationError("DOCX archive is invalid") from exc


def _extract_docx(content: bytes) -> tuple[str, int]:
    try:
        document = Document(io.BytesIO(content))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        return text, max(1, len(text) // 3000 + 1)
    except Exception as exc:
        raise M7ValidationError("DOCX could not be extracted safely") from exc


def _classify(text: str) -> tuple[DocumentType, float]:
    lower = text.lower()
    signals = {
        DocumentType.MARKETING_BRIEF: (
            "marketing brief",
            "target audience",
            "campaign objective",
            "key message",
        ),
        DocumentType.CAMPAIGN_REPORT: (
            "campaign results",
            "impressions",
            "conversion rate",
        ),
        DocumentType.GAME_DESIGN_DOCUMENT: (
            "gameplay",
            "game mechanics",
            "level design",
        ),
        DocumentType.PRODUCT_REQUIREMENT_DOCUMENT: (
            "product requirement",
            "acceptance criteria",
            "user story",
        ),
        DocumentType.MEETING_NOTES: ("meeting notes", "attendees", "action items"),
    }
    scores = {
        kind: sum(signal in lower for signal in items)
        for kind, items in signals.items()
    }
    winner = max(scores, key=lambda item: scores[item])
    score = scores[winner]
    if score == 0:
        return DocumentType.UNKNOWN, 0.25
    return winner, min(0.5 + score * 0.15, 0.95)


def _deterministic_inconsistencies(text: str) -> list[DocumentInconsistency]:
    aliases = {
        "DATE": {"date", "launch date", "start date"},
        "DEADLINE": {"deadline", "due date"},
        "BUDGET": {"budget", "campaign budget"},
        "PRODUCT_NAME": {"product", "product name", "campaign", "campaign name"},
        "PRIORITY": {"priority", "priority level"},
        "TOTAL": {"total", "grand total"},
    }
    values: dict[str, list[tuple[str, int]]] = {key: [] for key in aliases}
    repeated: dict[str, list[tuple[str, int]]] = {}
    requirements: dict[str, list[tuple[str, int]]] = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        match = re.match(r"^([^:]{1,80}):\s*(.+)$", line)
        if match is None:
            continue
        label = re.sub(r"\s+", " ", match.group(1).strip().lower())
        value = re.sub(r"\s+", " ", match.group(2).strip())
        repeated.setdefault(label, []).append((value, line_number))
        for kind, names in aliases.items():
            if label in names:
                values[kind].append((value, line_number))
        requirement_match = re.match(r"requirements?\s+(.+)", label)
        if requirement_match:
            requirements.setdefault(requirement_match.group(1), []).append(
                (value, line_number)
            )

    findings: list[DocumentInconsistency] = []
    for kind, entries in values.items():
        finding = _conflict_finding(kind, entries)
        if finding is not None:
            findings.append(finding)
    for label, entries in repeated.items():
        if label not in {name for names in aliases.values() for name in names}:
            finding = _conflict_finding("DUPLICATED_SECTION", entries, label=label)
            if finding is not None:
                findings.append(finding)
    for requirement, entries in requirements.items():
        finding = _conflict_finding(
            "CONTRADICTORY_REQUIREMENT", entries, label=requirement
        )
        if finding is not None:
            findings.append(finding)
    return findings[:50]


def _conflict_finding(
    kind: str, entries: list[tuple[str, int]], *, label: str | None = None
) -> DocumentInconsistency | None:
    normalized = {value.casefold() for value, _ in entries}
    if len(normalized) < 2:
        return None
    evidence = "; ".join(f"line {line}: {value[:120]}" for value, line in entries)
    subject = label or kind.lower().replace("_", " ")
    return DocumentInconsistency(
        type=kind,
        severity="HIGH" if kind in {"BUDGET", "DEADLINE", "TOTAL"} else "MEDIUM",
        source_locations=[f"line {line}" for _, line in entries],
        description=f"Conflicting values were declared for {subject}.",
        evidence_summary=evidence[:1000],
        detection_method="DETERMINISTIC",
        confidence=1.0,
        suggested_resolution=f"Confirm one authoritative {subject} value and update duplicates.",
    )
