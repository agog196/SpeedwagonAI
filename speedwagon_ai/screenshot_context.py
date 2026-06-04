from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from datetime import date
from typing import Any

from speedwagon_ai.config import Settings
from speedwagon_ai.model_router import choose_model
from speedwagon_ai.storage import Repository


VISION_SYSTEM_PROMPT = """You analyze a user-approved full-screen screenshot for a local personal assistant.
Return only valid JSON with these keys:
summary: string
visible_text: array of strings
suggested_tasks: array of objects with text, due_date, owner, project, confidence
suggested_context_topics: array of strings
suggested_actions: array of objects with action, payload, confidence, explanation
confidence: number from 0 to 1

Do not create tasks, emails, calendar events, or reminders. Only suggest them.
Do not infer sensitive personal data beyond what is visibly necessary for the user's requested context.
For dates without a visible year, use the current year supplied by the user message.
Do not return past years for future-looking tasks unless that year is explicitly visible in the screenshot."""

SUGGESTED_ACTION_CATEGORIES = {
    "add_task": "tasks",
    "search_context": "context",
    "draft_meeting_followup": "email",
}
MUTATING_SUGGESTED_ACTIONS = {"add_task"}


def analyze_screenshot(
    settings: Settings,
    repo: Repository,
    *,
    image_base64: str,
    instruction: str = "",
) -> dict[str, Any]:
    image_base64 = normalize_base64_png(image_base64)
    if settings.openai_api_key:
        try:
            raw = _openai_analyze(settings, image_base64, instruction)
        except Exception as exc:
            raw = fallback_analysis(reason=str(exc))
    else:
        raw = fallback_analysis(reason="OPENAI_API_KEY is not configured.")
    return build_analysis_response(repo, raw, command=instruction)


def build_analysis_response(repo: Repository, raw: dict[str, Any], *, command: str = "") -> dict[str, Any]:
    suggested_tasks = [_task_suggestion(item) for item in _as_list(raw.get("suggested_tasks"))]
    suggested_actions = [_action_suggestion(item) for item in _as_list(raw.get("suggested_actions"))]
    pending_actions: list[dict[str, Any]] = []
    seen_pending = {
        pending_action_key(action.get("action"), action.get("payload") or {})
        for action in repo.list_pending_actions(status="pending")
        if action.get("source") == "screenshot"
    }

    for task in suggested_tasks:
        if not task.get("text"):
            continue
        pending = create_screenshot_pending_action(
            repo,
            seen_pending,
            command=command,
            action="add_task",
            category="tasks",
            payload={
                "text": task["text"],
                "owner": task.get("owner"),
                "due_date": task.get("due_date"),
                "project": task.get("project"),
                "source": "screenshot",
                "source_type": "screenshot",
            },
            confidence=task.get("confidence"),
            explanation="Suggested from screenshot context. Confirm before creating.",
        )
        if pending:
            pending_actions.append(pending)

    for suggestion in suggested_actions:
        action = suggestion.get("action")
        if action not in SUGGESTED_ACTION_CATEGORIES or action not in MUTATING_SUGGESTED_ACTIONS:
            continue
        payload = suggestion.get("payload") or {}
        if action == "add_task":
            payload = {
                **payload,
                "due_date": normalize_screenshot_due_date(payload.get("due_date")),
                "source": payload.get("source") or "screenshot",
                "source_type": payload.get("source_type") or "screenshot",
            }
        pending = create_screenshot_pending_action(
            repo,
            seen_pending,
            command=command,
            action=action,
            category=SUGGESTED_ACTION_CATEGORIES[action],
            payload=payload,
            confidence=suggestion.get("confidence"),
            explanation=suggestion.get("explanation") or "Suggested from screenshot context. Confirm before running.",
        )
        if pending:
            pending_actions.append(pending)

    return {
        "summary": str(raw.get("summary") or "Screenshot analyzed."),
        "visible_text": [str(value) for value in _as_list(raw.get("visible_text")) if str(value).strip()],
        "suggested_tasks": suggested_tasks,
        "suggested_context_topics": [str(value).strip() for value in _as_list(raw.get("suggested_context_topics")) if str(value).strip()],
        "suggested_actions": suggested_actions,
        "pending_actions": pending_actions,
        "confidence": _float(raw.get("confidence")),
        "provider": str(raw.get("provider") or "openai"),
    }


def normalize_base64_png(value: str) -> str:
    text = (value or "").strip()
    if text.startswith("data:image/png;base64,"):
        text = text.split(",", 1)[1]
    if not text:
        raise ValueError("image_base64 is required")
    base64.b64decode(text, validate=True)
    return text


def fallback_analysis(reason: str = "") -> dict[str, Any]:
    return {
        "summary": "Screenshot received, but vision analysis is not configured.",
        "visible_text": [],
        "suggested_tasks": [],
        "suggested_context_topics": [],
        "suggested_actions": [],
        "confidence": 0.0,
        "provider": "fallback",
        "fallback_reason": reason,
    }


def _openai_analyze(settings: Settings, image_base64: str, instruction: str) -> dict[str, Any]:
    model = choose_model(settings, "vision_context")
    payload = {
        "model": model.model,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": VISION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "instruction": instruction,
                                "current_date": date.today().isoformat(),
                                "allowed_suggested_actions": sorted(SUGGESTED_ACTION_CATEGORIES),
                            },
                            indent=2,
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                    },
                ],
            },
        ],
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI screenshot analysis failed: HTTP {exc.code}: {body}") from exc
    return json.loads(data["choices"][0]["message"]["content"])


def _task_suggestion(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return {"text": value, "due_date": None, "owner": None, "project": None, "confidence": 0.5}
    if not isinstance(value, dict):
        return {"text": str(value), "due_date": None, "owner": None, "project": None, "confidence": 0.3}
    return {
        "text": str(value.get("text") or "").strip(),
        "due_date": normalize_screenshot_due_date(value.get("due_date")),
        "owner": _optional_str(value.get("owner")),
        "project": _optional_str(value.get("project")),
        "confidence": _float(value.get("confidence")),
    }


def _action_suggestion(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"action": None, "payload": {}, "confidence": 0.0, "explanation": str(value)}
    payload = value.get("payload") if isinstance(value.get("payload"), dict) else {}
    if _optional_str(value.get("action")) == "add_task" and payload.get("due_date"):
        payload = {**payload, "due_date": normalize_screenshot_due_date(payload.get("due_date"))}
    return {
        "action": _optional_str(value.get("action")),
        "payload": payload,
        "confidence": _float(value.get("confidence")),
        "explanation": str(value.get("explanation") or "").strip(),
    }


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def create_screenshot_pending_action(
    repo: Repository,
    seen_pending: set[tuple[str, str, str | None]],
    *,
    command: str,
    action: str,
    category: str,
    payload: dict[str, Any],
    confidence: float | None,
    explanation: str,
) -> dict[str, Any] | None:
    key = pending_action_key(action, payload)
    if key in seen_pending:
        return None
    seen_pending.add(key)
    return repo.create_pending_action(
        command=command or "screenshot analysis",
        action=action,
        category=category,
        payload=payload,
        confidence=confidence,
        source="screenshot",
        explanation=explanation,
        safety_notes=["Screenshots are analyzed only after you explicitly request analysis."],
    )


def pending_action_key(action: Any, payload: dict[str, Any]) -> tuple[str, str, str | None]:
    action_text = str(action or "")
    text = str(payload.get("text") or "").strip().lower()
    text = " ".join(text.split())
    if action_text == "add_task":
        return (action_text, text, None)
    return (action_text, text, _optional_str(payload.get("due_date")))


def normalize_screenshot_due_date(value: Any) -> str | None:
    text = _optional_str(value)
    if not text:
        return None
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        return text
    current = date.today()
    if parsed.year < current.year:
        try:
            candidate = parsed.replace(year=current.year)
        except ValueError:
            return parsed.isoformat()
        if candidate >= current:
            return candidate.isoformat()
    return parsed.isoformat()


def _float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))
