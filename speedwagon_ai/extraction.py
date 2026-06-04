from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from speedwagon_ai.config import Settings
from speedwagon_ai.model_router import choose_model
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
            try:
                raw = self._extract_openai(meeting, transcript)
            except Exception as exc:
                raw = fallback_extract(meeting, transcript, reason=str(exc))
        else:
            raise RuntimeError(f"Unsupported LLM_PROVIDER: {self.settings.llm_provider}")
        result = parse_extraction(raw)
        self.repo.save_extraction(meeting_id, result)
        return result

    def _extract_openai(self, meeting: Meeting, transcript: str) -> dict[str, Any]:
        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured.")
        model = choose_model(self.settings, "extraction")
        payload = {
            "model": model.model,
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


def fallback_extract(meeting: Meeting, transcript: str, reason: str = "") -> dict[str, Any]:
    text = " ".join(line.strip() for line in transcript.splitlines() if line.strip())
    action_items = []
    commitments = []
    if text:
        action = infer_action_item(text)
        action_items.append(action)
        commitments.append(action)
    return {
        "summary": text[:500],
        "action_items": action_items,
        "commitments": commitments,
        "decisions": [],
        "open_questions": [],
        "key_topics": infer_topics(meeting.title, text),
        "entities": infer_entities(text),
        "provider": "fallback",
        "fallback_reason": reason,
    }


def infer_action_item(text: str) -> dict[str, Any]:
    cleaned = text.strip().rstrip(".")
    deadline = infer_deadline(cleaned)
    owner = infer_owner(cleaned)
    task_text = cleaned
    match = re.search(r"\b(?:we|i)\s+want\s+(?:an?\s+)?(.+?)(?:\s+by\s+.+)?$", cleaned, flags=re.IGNORECASE)
    if match:
        task_text = match.group(1).strip()
    task_text = re.sub(r"\bemail\s+sent\s+to\b", "send email to", task_text, flags=re.IGNORECASE)
    if task_text and task_text[0].islower():
        task_text = task_text[0].upper() + task_text[1:]
    return {"text": task_text or cleaned, "owner": owner, "deadline": deadline, "status": "open"}


def infer_deadline(text: str) -> str | None:
    match = re.search(r"\bby\s+([A-Z][a-z]+\s+\d{1,2}(?:st|nd|rd|th)?)\b", text, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"\bby\s+(today|tomorrow|friday|monday|tuesday|wednesday|thursday|saturday|sunday)\b", text, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def infer_owner(text: str) -> str | None:
    match = re.search(r"\b([A-Z][a-z]+)\s+will\s+", text)
    if match:
        return match.group(1)
    return None


def infer_topics(title: str, text: str) -> list[str]:
    topics = [title.strip()] if title.strip() else []
    match = re.search(r"\bfor\s+([^,.]+?)(?:,|\s+we\s+|\s+i\s+|\s+by\s+|$)", text, flags=re.IGNORECASE)
    if match:
        topic = match.group(1).strip()
        if topic and topic.lower() not in {value.lower() for value in topics}:
            topics.append(topic)
    return topics[:5]


def infer_entities(text: str) -> list[str]:
    values = []
    for value in re.findall(r"\b[A-Z][a-z]+\b", text):
        if value.lower() in {"so", "for", "we", "i"}:
            continue
        if value not in values:
            values.append(value)
    return values[:8]


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
