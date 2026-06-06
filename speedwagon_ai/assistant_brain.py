from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import date, datetime
from typing import Any

from speedwagon_ai.config import Settings
from speedwagon_ai.model_router import choose_model, web_search_enabled


COMMAND_PARSE_SYSTEM_PROMPT = """You are the conservative command interpreter for SpeedwagonAI.
Return only valid JSON.

You may choose exactly one action from the allowed action registry the user provides.
Never invent tools, APIs, shell commands, or side effects.
If the request is ambiguous, outside the registry, low confidence, or asks for irreversible/external work, return supported=false.

IMPORTANT: The current date is {current_date}. When the user refers to dates without specifying a year, always assume the current year ({current_year}). Never default to a past year.
Treat user-provided times as local wall-clock times unless the user explicitly says UTC, GMT, or a named timezone. Do not convert local times to UTC. If you emit ISO datetimes for local times, use the provided local UTC offset.

JSON schema:
{{
  "supported": boolean,
  "action": string or null,
  "category": string,
  "payload": object,
  "confidence": number from 0 to 1,
  "requires_confirmation": boolean,
  "explanation": string,
  "safety_notes": array of strings
}}"""

ASSISTANT_CHAT_SYSTEM_PROMPT = """You are SpeedwagonAI, a local-first follow-through assistant.
Answer the user from the provided local app snapshot only.
Be concise, specific, and action-oriented.
If the user asks for information, cite the relevant local tasks, meetings, suggestions, calendar events, or drafts from the snapshot.
You do have access to the provided local SpeedwagonAI snapshot. Do not say you lack access to tasks, calendar, meetings, profiles, or drafts when those items are present in the snapshot.
If the user asks to write/change something, do not claim it was done unless an action result is present. Say the app will ask for confirmation for writes.
Do not expose implementation errors, API errors, stack traces, secrets, or local file paths.
"""

MIN_CONFIDENCE = 0.55


def interpret_command(
    settings: Settings,
    command: str,
    *,
    allowed_actions: set[str],
    categories: dict[str, str],
    mutating_actions: set[str],
) -> dict[str, Any]:
    explicit_web = explicit_web_query(command)
    if explicit_web:
        return {
            "supported": True,
            "action": "web_search",
            "category": "context",
            "payload": {"query": explicit_web},
            "confidence": 1.0,
            "requires_confirmation": False,
            "explanation": "The request explicitly asked for web/current information.",
            "safety_notes": ["Web search is opt-in and gated by SPEEDWAGON_ENABLE_WEB_SEARCH."],
            "source": "explicit_web",
        }

    if not settings.openai_api_key:
        return unsupported_interpretation("OpenAI command parsing is not configured. Add OPENAI_API_KEY to enable flexible commands.")

    try:
        raw = _openai_interpret(settings, command, sorted(allowed_actions), categories, sorted(mutating_actions))
    except Exception as exc:
        return unsupported_interpretation(f"Could not interpret this with the LLM fallback: {exc}")
    return validate_interpretation(raw, allowed_actions=allowed_actions, categories=categories, mutating_actions=mutating_actions)


def explicit_web_query(command: str) -> str | None:
    text = re.sub(r"\s+", " ", command.strip())
    lowered = text.lower()
    patterns = [
        r"^search the web (?:for|about) (.+)$",
        r"^web search (?:for|about) (.+)$",
        r"^look up (?:the latest|current)?\s*(.+)$",
        r"^(?:latest|current) (.+)$",
    ]
    for pattern in patterns:
        match = re.fullmatch(pattern, lowered)
        if match:
            return match.group(1).strip()
    return None


def validate_interpretation(
    raw: dict[str, Any],
    *,
    allowed_actions: set[str],
    categories: dict[str, str],
    mutating_actions: set[str],
) -> dict[str, Any]:
    supported = bool(raw.get("supported"))
    action = _optional_str(raw.get("action"))
    confidence = _float(raw.get("confidence"))
    explanation = str(raw.get("explanation") or "").strip()
    safety_notes = [str(note).strip() for note in _as_list(raw.get("safety_notes")) if str(note).strip()]

    if not supported:
        return unsupported_interpretation(explanation or "The request is outside the current SpeedwagonAI action registry.")
    if not action or action not in allowed_actions:
        return unsupported_interpretation("The LLM suggested an unsupported action, so SpeedwagonAI did not run it.")
    if confidence < MIN_CONFIDENCE:
        return unsupported_interpretation("I am not confident enough to safely map that request. Try a more specific command.")

    payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}
    requires_confirmation = action in mutating_actions or bool(raw.get("requires_confirmation"))
    category = categories.get(action, str(raw.get("category") or "system_status"))
    return {
        "supported": True,
        "action": action,
        "category": category,
        "payload": _json_safe_object(payload),
        "confidence": confidence,
        "requires_confirmation": requires_confirmation,
        "explanation": explanation,
        "safety_notes": safety_notes,
        "source": "llm",
    }


def unsupported_interpretation(summary: str) -> dict[str, Any]:
    return {
        "supported": False,
        "action": None,
        "category": "system_status",
        "payload": {},
        "confidence": 0.0,
        "requires_confirmation": False,
        "explanation": summary,
        "safety_notes": [],
        "source": "llm",
    }


def _openai_interpret(
    settings: Settings,
    command: str,
    allowed_actions: list[str],
    categories: dict[str, str],
    mutating_actions: list[str],
) -> dict[str, Any]:
    today = date.today()
    local_now = datetime.now().astimezone()
    local_offset = local_now.strftime("%z")
    if local_offset:
        local_offset = f"{local_offset[:3]}:{local_offset[3:]}"
    system_prompt = COMMAND_PARSE_SYSTEM_PROMPT.format(
        current_date=today.isoformat(),
        current_year=today.year,
    )
    model = choose_model(settings, "command_parse")
    payload = {
        "model": model.model,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "command": command,
                        "current_date": today.isoformat(),
                        "current_year": today.year,
                        "local_timezone_name": local_now.tzname(),
                        "local_utc_offset": local_offset or "local",
                        "allowed_actions": allowed_actions,
                        "payload_hints": payload_hints(),
                        "categories": categories,
                        "mutating_actions_require_confirmation": mutating_actions,
                        "web_search_enabled": web_search_enabled(),
                    },
                    indent=2,
                    sort_keys=True,
                ),
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
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI command parse failed: HTTP {exc.code}: {body}") from exc
    return json.loads(data["choices"][0]["message"]["content"])


def compose_assistant_reply(settings: Settings, command: str, snapshot: dict[str, Any]) -> str | None:
    if not settings.openai_api_key:
        return None
    try:
        return _openai_assistant_reply(settings, command, snapshot)
    except Exception:
        return None


def _openai_assistant_reply(settings: Settings, command: str, snapshot: dict[str, Any]) -> str:
    model = choose_model(settings, "assistant_chat")
    payload = {
        "model": model.model,
        "messages": [
            {"role": "system", "content": ASSISTANT_CHAT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": command,
                        "local_snapshot": snapshot,
                    },
                    indent=2,
                    sort_keys=True,
                    default=str,
                ),
            },
        ],
        "temperature": 0.2,
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
    with urllib.request.urlopen(request, timeout=45) as response:
        data = json.loads(response.read().decode("utf-8"))
    return str(data["choices"][0]["message"]["content"]).strip()


def payload_hints() -> dict[str, Any]:
    return {
        "create_calendar_event": {
            "title": "Short event title.",
            "start_at": "Required ISO-8601 datetime. For ordinary user times, preserve the local wall-clock time and attach the provided local UTC offset, e.g. 2026-06-10T10:00:00-07:00.",
            "end_at": "Required ISO-8601 datetime. Default to 30 minutes after start when duration is not specified. Do not convert to UTC unless the user explicitly requested UTC/GMT/a timezone.",
            "calendar_id": "Optional, default primary.",
            "timezone": "Optional IANA timezone, e.g. America/Los_Angeles.",
            "description": "Optional event description.",
            "location": "Optional location or meeting URL.",
            "attendees": "Optional array of attendee email strings.",
            "send_updates": "Use none unless the user explicitly asks to email attendees.",
        },
        "show_tasks_by_id": {
            "task_ids": "Required array of integer task IDs, e.g. [26, 27, 28].",
        },
        "add_task": {
            "text": "Required task text.",
            "due_date": "Optional YYYY-MM-DD.",
            "owner": "Optional owner/person.",
            "project": "Optional project.",
        },
        "draft_email_from_context": {
            "query": "Required person/project/topic/context search query. For 'email John about v6', use John here so the app can load John's profile and local context.",
            "recipient": "Optional recipient name or email from the user's request.",
            "to": "Optional recipient email only if explicitly provided or known from the request.",
            "subject": "Optional concise subject/title for the local draft.",
            "instruction": "Drafting instruction. Include the user's requested message, reminders, and topic. This creates a local editable draft after confirmation; it never sends email.",
        },
        "search_calendar_events": {
            "query": "Required search query such as a person, professor, project, event title, location, or attendee.",
            "limit": "Optional maximum number of matching upcoming events.",
        },
    }


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


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _json_safe_object(value: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(json.dumps(value))
    except (TypeError, ValueError):
        return {}
