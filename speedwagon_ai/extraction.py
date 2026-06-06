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
from speedwagon_ai.models import ExtractedFollowup, ExtractedItem, ExtractedRelationship, ExtractionResult, Meeting
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
relationships: array of {source, source_kind, target, target_kind, relationship_type, evidence, confidence}
implicit_followups: array of {task_text, implied_by, owner, owed_to, project, due_date, confidence}
Use null for unknown owner/deadline. Use status "open" unless clearly completed."""


RELATIONSHIP_INFERENCE_PROMPT = """You infer compact relationship edges for a local personal context graph.
Return only valid JSON with these keys:
relationships: array of {source, source_kind, target, target_kind, relationship_type, evidence, confidence}
implicit_followups: array of {task_text, implied_by, owner, owed_to, project, due_date, confidence}
Use source_kind/target_kind as one of person, project, topic.
Only include relationships and follow-ups directly supported by the meeting summary, tasks, decisions, topics, entities, or transcript context.
Do not invent external facts."""


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
        if fixture_path is None:
            result = self._with_relationship_inference(meeting, transcript, result)
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

    def _with_relationship_inference(
        self,
        meeting: Meeting,
        transcript: str,
        result: ExtractionResult,
    ) -> ExtractionResult:
        if self.settings.llm_provider != "openai" or not self.settings.openai_api_key:
            return result
        try:
            raw = self._infer_relationships_openai(meeting, transcript, result)
            inferred = parse_relationship_payload(raw)
        except Exception as exc:
            merged_raw = dict(result.raw)
            merged_raw["relationship_inference_error"] = str(exc)
            return ExtractionResult(**{**result.__dict__, "raw": merged_raw})
        relationships = merge_relationships(result.relationships, inferred.relationships)
        implicit_followups = merge_followups(result.implicit_followups, inferred.implicit_followups)
        merged_raw = dict(result.raw)
        merged_raw["relationship_inference"] = raw
        return ExtractionResult(
            summary=result.summary,
            action_items=result.action_items,
            commitments=result.commitments,
            decisions=result.decisions,
            open_questions=result.open_questions,
            key_topics=result.key_topics,
            entities=result.entities,
            relationships=relationships,
            implicit_followups=implicit_followups,
            raw=merged_raw,
        )

    def _infer_relationships_openai(
        self,
        meeting: Meeting,
        transcript: str,
        result: ExtractionResult,
    ) -> dict[str, Any]:
        model = choose_model(self.settings, "relationship_inference")
        compact = {
            "meeting": {"id": meeting.id, "title": meeting.title, "started_at": meeting.started_at},
            "summary": result.summary,
            "action_items": [item.__dict__ for item in result.action_items],
            "commitments": [item.__dict__ for item in result.commitments],
            "decisions": result.decisions,
            "open_questions": result.open_questions,
            "key_topics": result.key_topics,
            "entities": result.entities,
            "transcript_excerpt": transcript[:4000],
        }
        payload = {
            "model": model.model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": RELATIONSHIP_INFERENCE_PROMPT},
                {"role": "user", "content": json.dumps(compact, indent=2, sort_keys=True)},
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
            with urllib.request.urlopen(request, timeout=45) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI relationship inference failed: HTTP {exc.code}: {body}") from exc
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
        relationships=[_parse_relationship(item) for item in _list(raw.get("relationships"))],
        implicit_followups=[_parse_followup(item) for item in _list(raw.get("implicit_followups"))],
        raw=raw,
    )


def parse_relationship_payload(raw: dict[str, Any]) -> ExtractionResult:
    return ExtractionResult(
        relationships=[_parse_relationship(item) for item in _list(raw.get("relationships"))],
        implicit_followups=[_parse_followup(item) for item in _list(raw.get("implicit_followups"))],
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
        "relationships": infer_relationships(meeting.title, text),
        "implicit_followups": [],
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


def infer_relationships(title: str, text: str) -> list[dict[str, Any]]:
    relationships: list[dict[str, Any]] = []
    topics = infer_topics(title, text)
    entities = infer_entities(text)
    if topics and entities:
        for entity in entities[:3]:
            relationships.append(
                {
                    "source": entity,
                    "source_kind": "person",
                    "target": topics[0],
                    "target_kind": "project" if looks_like_project(topics[0]) else "topic",
                    "relationship_type": "mentioned_with",
                    "evidence": "fallback co-mention",
                    "confidence": 0.45,
                }
            )
    return relationships


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


def _parse_relationship(value: Any) -> ExtractedRelationship:
    if not isinstance(value, dict):
        text = str(value).strip()
        return ExtractedRelationship(source=text, target=text, relationship_type="related")
    return ExtractedRelationship(
        source=str(value.get("source") or value.get("person") or "").strip(),
        source_kind=_context_kind(value.get("source_kind") or ("person" if value.get("person") else "topic")),
        target=str(value.get("target") or value.get("project_or_topic") or value.get("topic") or "").strip(),
        target_kind=_context_kind(value.get("target_kind") or ("project" if value.get("project_or_topic") else "topic")),
        relationship_type=str(value.get("relationship_type") or value.get("type") or "related").strip() or "related",
        evidence=_optional_str(value.get("evidence") or value.get("reason")),
        confidence=_confidence(value.get("confidence"), default=0.7),
    )


def _parse_followup(value: Any) -> ExtractedFollowup:
    if isinstance(value, str):
        return ExtractedFollowup(task_text=value.strip(), implied_by=value.strip())
    if not isinstance(value, dict):
        text = str(value).strip()
        return ExtractedFollowup(task_text=text, implied_by=text)
    return ExtractedFollowup(
        task_text=str(value.get("task_text") or value.get("text") or "").strip(),
        implied_by=str(value.get("implied_by") or value.get("reason") or "").strip(),
        owner=_optional_str(value.get("owner")),
        owed_to=_optional_str(value.get("owed_to")),
        project=_optional_str(value.get("project")),
        due_date=_optional_str(value.get("due_date") or value.get("deadline")),
        confidence=_confidence(value.get("confidence"), default=0.7),
    )


def merge_relationships(
    primary: list[ExtractedRelationship],
    inferred: list[ExtractedRelationship],
) -> list[ExtractedRelationship]:
    output: list[ExtractedRelationship] = []
    seen: set[tuple[str, str, str]] = set()
    for relationship in [*primary, *inferred]:
        if not relationship.source or not relationship.target:
            continue
        key = (
            relationship.source.strip().lower(),
            relationship.target.strip().lower(),
            relationship.relationship_type.strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(relationship)
    return output


def merge_followups(primary: list[ExtractedFollowup], inferred: list[ExtractedFollowup]) -> list[ExtractedFollowup]:
    output: list[ExtractedFollowup] = []
    seen: set[str] = set()
    for followup in [*primary, *inferred]:
        if not followup.task_text:
            continue
        key = followup.task_text.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(followup)
    return output


def _context_kind(value: Any) -> str:
    text = str(value or "topic").strip().lower().replace(" ", "_")
    if text in {"person", "people"}:
        return "person"
    if text in {"project", "product"}:
        return "project"
    return "topic"


def _confidence(value: Any, default: float = 0.7) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(0.0, min(1.0, number))


def looks_like_project(value: str) -> bool:
    return bool(re.search(r"[A-Z][a-z]+[A-Z]|\b[A-Z]{2,}\b", value or ""))


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
