from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from speedwagon_ai.config import Settings
from speedwagon_ai.model_router import choose_model, web_search_enabled


COMMAND_PARSE_SYSTEM_PROMPT = """You are the conservative command interpreter for SpeedwagonAI.
Return only valid JSON.

You may choose exactly one action from the allowed action registry the user provides.
Never invent tools, APIs, shell commands, or side effects.
If the request is ambiguous, outside the registry, low confidence, or asks for irreversible/external work, return supported=false.

JSON schema:
{
  "supported": boolean,
  "action": string or null,
  "category": string,
  "payload": object,
  "confidence": number from 0 to 1,
  "requires_confirmation": boolean,
  "explanation": string,
  "safety_notes": array of strings
}"""

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
    model = choose_model(settings, "command_parse")
    payload = {
        "model": model.model,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": COMMAND_PARSE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "command": command,
                        "allowed_actions": allowed_actions,
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
