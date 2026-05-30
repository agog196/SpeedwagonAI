from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from speedwagon_ai.config import Settings
from speedwagon_ai.models import ExtractedItem, ExtractionResult, Meeting
from speedwagon_ai.storage import Repository


SYSTEM_PROMPT = """You extract durable meeting context for a local personal context engine.
Return only valid JSON with these keys:
summary: string
action_items: array of {text, owner, deadline, status}
commitments: array of {text, owner, deadline, status}
decisions: array of strings
open_questions: array of strings
key_topics: array of strings
entities: array of strings
Use null for unknown owner/deadline. Use status "open" unless clearly completed."""


class Extractor:
    def __init__(self, settings: Settings, repo: Repository):
        self.settings = settings
        self.repo = repo

    def extract(self, meeting_id: int, fixture_path: Path | None = None) -> ExtractionResult:
        meeting = self.repo.get_meeting(meeting_id)
        if not meeting.transcript_path:
            raise RuntimeError(f"Meeting {meeting_id} has no transcript path.")
        transcript = Path(meeting.transcript_path).read_text(encoding="utf-8")
        if fixture_path:
            raw = json.loads(fixture_path.read_text(encoding="utf-8"))
        elif self.settings.llm_provider == "openai":
            raw = self._extract_openai(meeting, transcript)
        else:
            raise RuntimeError(f"Unsupported LLM_PROVIDER: {self.settings.llm_provider}")
        result = parse_extraction(raw)
        self.repo.save_extraction(meeting_id, result)
        return result

    def _extract_openai(self, meeting: Meeting, transcript: str) -> dict[str, Any]:
        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured.")
        payload = {
            "model": self.settings.openai_model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Meeting title: {meeting.title}\n"
                        f"Started at: {meeting.started_at}\n\n"
                        f"Transcript:\n{transcript}"
                    ),
                },
            ],
        }
        request = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI extraction failed: HTTP {exc.code}: {body}") from exc
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)


def parse_extraction(raw: dict[str, Any]) -> ExtractionResult:
    return ExtractionResult(
        summary=str(raw.get("summary") or ""),
        action_items=[_parse_item(item) for item in _list(raw.get("action_items"))],
        commitments=[_parse_item(item) for item in _list(raw.get("commitments"))],
        decisions=[str(value) for value in _list(raw.get("decisions")) if str(value).strip()],
        open_questions=[str(value) for value in _list(raw.get("open_questions")) if str(value).strip()],
        key_topics=[str(value) for value in _list(raw.get("key_topics")) if str(value).strip()],
        entities=[str(value) for value in _list(raw.get("entities")) if str(value).strip()],
        raw=raw,
    )


def _parse_item(value: Any) -> ExtractedItem:
    if isinstance(value, str):
        return ExtractedItem(text=value)
    if not isinstance(value, dict):
        return ExtractedItem(text=str(value))
    return ExtractedItem(
        text=str(value.get("text") or "").strip(),
        owner=_optional_str(value.get("owner")),
        deadline=_optional_str(value.get("deadline")),
        status=str(value.get("status") or "open"),
    )


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "unknown"}:
        return None
    return text
