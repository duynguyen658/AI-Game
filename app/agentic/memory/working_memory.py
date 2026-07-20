from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.core.sanitization import sanitize_text


class WorkingMemoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str = Field(min_length=1, max_length=50)
    summary: str = Field(min_length=1, max_length=2000)


class WorkingMemory(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    max_items: int = Field(default=20, ge=1, le=50)
    max_characters: int = Field(default=12_000, ge=100, le=50_000)
    items: list[WorkingMemoryItem] = Field(default_factory=list)

    def add(self, kind: str, summary: object) -> None:
        item = WorkingMemoryItem(
            kind=sanitize_text(kind, max_characters=50),
            summary=sanitize_text(summary, max_characters=2000),
        )
        self.items.append(item)
        while (
            len(self.items) > self.max_items
            or self.total_characters > self.max_characters
        ):
            self.items.pop(0)

    @property
    def total_characters(self) -> int:
        return sum(len(item.kind) + len(item.summary) for item in self.items)
