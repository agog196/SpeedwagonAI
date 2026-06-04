from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Meeting:
    id: int
    title: str
    started_at: str
    ended_at: str | None = None
    audio_path: str | None = None
    transcript_path: str | None = None
    note_path: str | None = None
    summary: str | None = None
    source_type: str | None = None


@dataclass(frozen=True)
class ExtractedItem:
    text: str
    owner: str | None = None
    deadline: str | None = None
    status: str = "open"


@dataclass(frozen=True)
class ExtractionResult:
    summary: str = ""
    action_items: list[ExtractedItem] = field(default_factory=list)
    commitments: list[ExtractedItem] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    key_topics: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
