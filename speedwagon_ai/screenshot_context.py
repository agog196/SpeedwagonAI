from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
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
Do not infer sensitive personal data beyond what is visibly necessary for the user's requested context."""

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

    for task in suggested_tasks:
        if not task.get("text"):
            continue
        pending_actions.append(
            repo.create_pending_action(
                command=command or "screenshot analysis",
                action="add_task",
                category="tasks",
                payload={
                    "text": task["text"],
                    "owner": task.get("owner"),
                    "due_date": task.get("due_date"),
                    "project": task.get("project"),
                },
                confidence=task.get("confidence"),
                source="screenshot",
                explanation="Suggested from screenshot context. Confirm before creating.",
                safety_notes=["Screenshots are analyzed only after you explicitly request analysis."],
            )
        )

    for suggestion in suggested_actions:
        action = suggestion.get("action")
        if action not in SUGGESTED_ACTION_CATEGORIES or action not in MUTATING_SUGGESTED_ACTIONS:
            continue
        pending_actions.append(
            repo.create_pending_action(
                command=command or "screenshot analysis",
                action=action,
                category=SUGGESTED_ACTION_CATEGORIES[action],
                payload=suggestion.get("payload") or {},
                confidence=suggestion.get("confidence"),
                source="screenshot",
                explanation=suggestion.get("explanation") or "Suggested from screenshot context. Confirm before running.",
                safety_notes=["Screenshot-suggested actions require confirmation."],
            )
        )

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
        "due_date": _optional_str(value.get("due_date")),
        "owner": _optional_str(value.get("owner")),
        "project": _optional_str(value.get("project")),
        "confidence": _float(value.get("confidence")),
    }


def _action_suggestion(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"action": None, "payload": {}, "confidence": 0.0, "explanation": str(value)}
    payload = value.get("payload") if isinstance(value.get("payload"), dict) else {}
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


def _float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))
