from __future__ import annotations

from app.core.sanitization import sanitize_text


class DeterministicMemorySummarizer:
    def summarize(self, event_type: object, detail: object) -> str:
        event = sanitize_text(event_type, max_characters=100)
        safe_detail = sanitize_text(detail, max_characters=2800)
        return f"{event}: {safe_detail}"
