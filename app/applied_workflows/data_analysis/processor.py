from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from statistics import mean, pstdev
from typing import Any

from app.core.config import Settings
from app.core.exceptions import M7ValidationError
from app.database.models import PromptVersionModel
from app.llm.base import LLMClient
from app.llm.capabilities import CompletionRequest
from app.prompt_management.renderer import PromptRenderer
from app.schemas.data_analysis import DataAnalysisReport, DataQualityReport

SUPPORTED_COLUMNS = {
    "date",
    "platform",
    "country",
    "campaign",
    "impressions",
    "clicks",
    "spend",
    "conversions",
    "retention",
    "sessions",
    "revenue",
}
NUMERIC_COLUMNS = {
    "impressions",
    "clicks",
    "spend",
    "conversions",
    "retention",
    "sessions",
    "revenue",
}


async def analyze_csv(
    content: bytes,
    *,
    filename: str,
    settings: Settings,
    llm_client: LLMClient,
    prompt_version: PromptVersionModel,
) -> DataAnalysisReport:
    if len(content) > settings.max_upload_bytes:
        raise M7ValidationError("CSV exceeds the configured size limit")
    if not filename.lower().endswith(".csv"):
        raise M7ValidationError("Only CSV files are supported")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise M7ValidationError("CSV must be UTF-8 encoded") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames is None:
        raise M7ValidationError("CSV header is required")
    columns = [column.strip().lower() for column in reader.fieldnames]
    if len(columns) != len(set(columns)) or len(columns) > settings.max_csv_columns:
        raise M7ValidationError(
            "CSV columns are duplicated or exceed the configured limit"
        )
    reader.fieldnames = columns
    rows: list[dict[str, str]] = []
    for index, raw in enumerate(reader):
        if index >= settings.max_csv_rows:
            raise M7ValidationError("CSV row count exceeds the configured limit")
        rows.append(
            {
                key: (value or "").strip()
                for key, value in raw.items()
                if key is not None
            }
        )
    if not rows:
        raise M7ValidationError("CSV must contain at least one data row")
    parsed = [_numeric_row(row, index + 2) for index, row in enumerate(rows)]
    metrics = _metrics(parsed)
    segments = _segments(parsed)
    anomalies = _anomalies(parsed)
    trends = _trends(parsed)
    quality = DataQualityReport(
        row_count=len(rows),
        column_count=len(columns),
        columns=columns,
        missing_value_rate=_decimal_string(
            Decimal(sum(not value for row in rows for value in row.values()))
            / Decimal(max(len(rows) * len(columns), 1))
        ),
        duplicate_row_count=len(rows)
        - len({tuple(sorted(row.items())) for row in rows}),
        unsupported_columns=sorted(set(columns) - SUPPORTED_COLUMNS),
        preview=[
            {key: _safe_cell(value) for key, value in row.items()} for row in rows[:5]
        ],
    )
    prompt_values = {
        "metrics": str(
            {"metrics": metrics, "anomalies": anomalies[:10], "trends": trends[:10]}
        )
    }
    explanation_request = CompletionRequest(
        system_prompt=prompt_version.system_prompt,
        user_prompt=PromptRenderer().render(
            prompt_version.user_prompt_template,
            prompt_values,
            allowed_variables={
                key for key in prompt_version.variables if not key.startswith("__")
            },
            allow_unknown=bool(
                prompt_version.variables.get("__allow_unknown__", False)
            ),
        ),
        model=settings.llm_model or "mock-applied-ai",
        max_output_tokens=800,
    )
    completion = await llm_client.complete(explanation_request)
    explanation = (
        completion.content or "Deterministic metrics were computed successfully."
    )
    recommendations = [
        "Review flagged anomalies with the campaign owner.",
        "Validate source completeness before making budget changes.",
    ]
    return DataAnalysisReport(
        data_quality=quality,
        summary_metrics=metrics,
        segment_performance=segments,
        anomalies=anomalies,
        trends=trends,
        explanation=explanation[:5000],
        recommendations=recommendations,
        limitations=[
            "Metrics are limited to columns present in the uploaded CSV.",
            "Anomalies are statistical indicators and require human validation.",
        ],
        generated_at=datetime.now(UTC),
    )


def _numeric_row(row: dict[str, str], row_number: int) -> dict[str, Any]:
    result: dict[str, Any] = dict(row)
    for column in NUMERIC_COLUMNS & row.keys():
        value = row[column]
        if not value:
            result[column] = None
            continue
        try:
            result[column] = Decimal(value.replace(",", ""))
        except InvalidOperation as exc:
            raise M7ValidationError(
                f"Column {column} contains a non-numeric value at row {row_number}"
            ) from exc
    return result


def _sum(rows: list[dict[str, Any]], column: str) -> Decimal | None:
    values: list[Decimal] = []
    for row in rows:
        value = row.get(column)
        if isinstance(value, Decimal):
            values.append(value)
    return sum(values, Decimal(0)) if values else None


def _rate(numerator: Decimal | None, denominator: Decimal | None) -> str | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return _decimal_string(numerator / denominator)


def _metrics(rows: list[dict[str, Any]]) -> dict[str, str | int | None]:
    impressions = _sum(rows, "impressions")
    clicks = _sum(rows, "clicks")
    spend = _sum(rows, "spend")
    conversions = _sum(rows, "conversions")
    sessions = _sum(rows, "sessions")
    revenue = _sum(rows, "revenue")
    retention_values = [
        row["retention"] for row in rows if isinstance(row.get("retention"), Decimal)
    ]
    return {
        "rows": len(rows),
        "impressions": _optional_decimal(impressions),
        "clicks": _optional_decimal(clicks),
        "spend": _optional_decimal(spend),
        "conversions": _optional_decimal(conversions),
        "revenue": _optional_decimal(revenue),
        "ctr": _rate(clicks, impressions),
        "cpc": _rate(spend, clicks),
        "cpa": _rate(spend, conversions),
        "conversion_rate": _rate(conversions, clicks or sessions),
        "roas": _rate(revenue, spend),
        "retention_average": (
            _decimal_string(
                sum(retention_values, Decimal(0)) / Decimal(len(retention_values))
            )
            if retention_values
            else None
        ),
    }


def _segments(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    segment_column = next(
        (name for name in ("platform", "country", "campaign") if name in rows[0]), None
    )
    if segment_column is None:
        return []
    groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row.get(segment_column) or "unknown")].append(row)
    return [
        {"segment_by": segment_column, "segment": key, "metrics": _metrics(group)}
        for key, group in sorted(groups.items())
    ]


def _anomalies(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    anomalies: list[dict[str, Any]] = []
    for column in sorted(NUMERIC_COLUMNS):
        values = [
            float(row[column]) for row in rows if isinstance(row.get(column), Decimal)
        ]
        if len(values) < 3:
            continue
        deviation = pstdev(values)
        if deviation == 0:
            continue
        center = mean(values)
        for index, row in enumerate(rows):
            value = row.get(column)
            if (
                isinstance(value, Decimal)
                and abs(float(value) - center) > 2 * deviation
            ):
                anomalies.append(
                    {
                        "row": index + 2,
                        "column": column,
                        "value": str(value),
                        "method": "zscore_gt_2",
                    }
                )
    return anomalies[:100]


def _trends(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if "date" not in rows[0]:
        return []
    ordered = sorted(rows, key=lambda row: str(row.get("date", "")))
    trends = []
    for column in sorted(NUMERIC_COLUMNS):
        values = [
            row[column] for row in ordered if isinstance(row.get(column), Decimal)
        ]
        if len(values) >= 2 and values[0] != 0:
            trends.append(
                {
                    "metric": column,
                    "first": str(values[0]),
                    "last": str(values[-1]),
                    "delta_rate": _decimal_string(
                        (values[-1] - values[0]) / abs(values[0])
                    ),
                }
            )
    return trends


def _decimal_string(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def _optional_decimal(value: Decimal | None) -> str | None:
    return _decimal_string(value) if value is not None else None


def _safe_cell(value: str) -> str:
    if value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value[:500]
