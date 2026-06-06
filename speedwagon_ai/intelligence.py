from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from datetime import date, timedelta
from typing import Any

from speedwagon_ai.config import Settings
from speedwagon_ai.model_router import choose_model
from speedwagon_ai.storage import Repository, notification_reason_for_suggestion
from speedwagon_ai.timeutil import utc_now_iso


SYNTHESIS_PROMPT = """You write compact daily intelligence for a local-first personal follow-through assistant.
Return only valid JSON with:
summary: string
risks: array of strings
dropped_threads: array of strings
followups: array of strings
recent_changes: array of strings
suggestion_narratives: object mapping suggestion id strings to concise notification messages
Use only the supplied compact data. Do not invent facts. Keep bullets short and actionable."""


def intelligence_status(repo: Repository, synthesis_date: str | None = None) -> dict[str, Any]:
    target_date = synthesis_date or date.today().isoformat()
    synthesis = repo.get_daily_synthesis(target_date)
    latest = repo.latest_daily_synthesis()
    return {
        "date": target_date,
        "cached": synthesis,
        "latest": latest,
        "manual_refresh_required": True,
        "note": "Daily intelligence is generated only when explicitly refreshed.",
    }


def refresh_daily_intelligence(
    settings: Settings,
    repo: Repository,
    synthesis_date: str | None = None,
    *,
    top_suggestion_limit: int = 8,
) -> dict[str, Any]:
    target_date = synthesis_date or date.today().isoformat()
    compact = build_daily_synthesis_input(repo, target_date, top_suggestion_limit=top_suggestion_limit)
    fingerprint = _fingerprint(compact)
    try:
        generated = _generate_openai(settings, compact)
    except Exception as exc:
        generated = fallback_synthesis(compact, reason=str(exc))
    synthesis = repo.save_daily_synthesis(
        synthesis_date=target_date,
        summary=str(generated.get("summary") or ""),
        risks=_strings(generated.get("risks")),
        dropped_threads=_strings(generated.get("dropped_threads")),
        followups=_strings(generated.get("followups")),
        recent_changes=_strings(generated.get("recent_changes")),
        provider=str(generated.get("provider") or "openai"),
        model=generated.get("model"),
        generated_at=str(generated.get("generated_at") or utc_now_iso()),
        input_fingerprint=fingerprint,
    )
    updated = update_top_suggestion_narratives(repo, compact.get("top_suggestions") or [], generated)
    return {
        "status": "refreshed",
        "date": target_date,
        "synthesis": synthesis,
        "updated_suggestions": updated,
        "input_fingerprint": fingerprint,
    }


def build_daily_synthesis_input(repo: Repository, synthesis_date: str, *, top_suggestion_limit: int = 8) -> dict[str, Any]:
    current = date.fromisoformat(synthesis_date)
    since = (current - timedelta(days=14)).isoformat()
    meetings = [
        {
            "id": meeting.id,
            "title": meeting.title,
            "started_at": meeting.started_at,
            "summary": meeting.summary,
            "source_type": meeting.source_type,
        }
        for meeting in repo.list_meetings(limit=30)
        if (meeting.started_at or "")[:10] >= since
    ]
    tasks = [
        {
            "id": task.get("id"),
            "text": task.get("text"),
            "status": task.get("status"),
            "owner": task.get("owner"),
            "owed_to": task.get("owed_to"),
            "project": task.get("project"),
            "due_date": task.get("due_date"),
            "updated_at": task.get("updated_at"),
            "contexts": [
                {"name": context.get("name"), "kind": context.get("kind")}
                for context in (task.get("contexts") or [])[:4]
            ],
        }
        for task in repo.list_tasks(status=None, include_done=False)[:80]
    ]
    suggestions = repo.notification_candidates(limit=max(top_suggestion_limit, 8))
    top_suggestions = [compact_suggestion(item) for item in suggestions[:top_suggestion_limit]]
    graph_contexts = repo.find_contexts(limit=30)
    relationships = []
    if graph_contexts:
        relationships = repo.relationships_for_contexts([int(context["id"]) for context in graph_contexts[:20]], limit=40)
    return {
        "date": synthesis_date,
        "tasks": tasks,
        "meetings": meetings,
        "contexts": [
            {"id": context.get("id"), "name": context.get("name"), "kind": context.get("kind")}
            for context in graph_contexts[:30]
        ],
        "relationships": [
            {
                "source": (relationship.get("source_context") or {}).get("name"),
                "target": (relationship.get("target_context") or {}).get("name"),
                "relationship_type": relationship.get("relationship_type"),
                "evidence": relationship.get("evidence"),
                "confidence": relationship.get("confidence"),
            }
            for relationship in relationships[:40]
        ],
        "calendar_today": repo.list_calendar_events(start_date=synthesis_date, end_date=(current + timedelta(days=1)).isoformat(), limit=20),
        "calendar_upcoming": repo.upcoming_calendar_events(limit=10, from_date=synthesis_date),
        "top_suggestions": top_suggestions,
    }


def compact_suggestion(suggestion: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": suggestion.get("id"),
        "title": suggestion.get("title"),
        "reason": suggestion.get("reason"),
        "notification_reason": suggestion.get("notification_reason"),
        "proposed_action": suggestion.get("proposed_action"),
        "confidence": suggestion.get("confidence"),
        "context": suggestion.get("context"),
        "task_ids": suggestion.get("task_ids") or [],
        "meeting_ids": suggestion.get("meeting_ids") or [],
    }


def fallback_synthesis(compact: dict[str, Any], reason: str = "") -> dict[str, Any]:
    tasks = compact.get("tasks") or []
    suggestions = compact.get("top_suggestions") or []
    overdue = [task for task in tasks if task.get("due_date") and str(task.get("due_date")) < str(compact.get("date"))]
    waiting = [task for task in tasks if task.get("status") in {"waiting", "uncertain"}]
    summary = f"{len(overdue)} overdue, {len(waiting)} waiting/uncertain, {len(suggestions)} notification candidates."
    narratives = {
        str(suggestion.get("id")): notification_reason_for_suggestion(
            str(suggestion.get("title") or ""),
            str(suggestion.get("reason") or ""),
            str(suggestion.get("proposed_action") or ""),
        )
        for suggestion in suggestions
        if suggestion.get("id")
    }
    return {
        "summary": summary,
        "risks": [f"{task.get('text')} is overdue." for task in overdue[:5]],
        "dropped_threads": [],
        "followups": [str(suggestion.get("title") or "") for suggestion in suggestions[:5] if suggestion.get("title")],
        "recent_changes": [],
        "suggestion_narratives": narratives,
        "provider": "fallback",
        "model": None,
        "generated_at": utc_now_iso(),
        "fallback_reason": reason,
    }


def update_top_suggestion_narratives(
    repo: Repository,
    top_suggestions: list[dict[str, Any]],
    generated: dict[str, Any],
) -> list[dict[str, Any]]:
    narratives = generated.get("suggestion_narratives") if isinstance(generated.get("suggestion_narratives"), dict) else {}
    updated: list[dict[str, Any]] = []
    for suggestion in top_suggestions:
        suggestion_id = suggestion.get("id")
        if not suggestion_id:
            continue
        narrative = str(narratives.get(str(suggestion_id)) or "").strip()
        if not narrative:
            narrative = notification_reason_for_suggestion(
                str(suggestion.get("title") or ""),
                str(suggestion.get("reason") or ""),
                str(suggestion.get("proposed_action") or ""),
            )
        updated.append(repo.update_suggestion_narrative(int(suggestion_id), narrative[:280]))
    return updated


def _generate_openai(settings: Settings, compact: dict[str, Any]) -> dict[str, Any]:
    if settings.llm_provider != "openai":
        raise RuntimeError(f"Unsupported LLM_PROVIDER: {settings.llm_provider}")
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    model = choose_model(settings, "deep_synthesis")
    payload = {
        "model": model.model,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYNTHESIS_PROMPT},
            {"role": "user", "content": json.dumps(compact, indent=2, sort_keys=True)},
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
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI daily synthesis failed: HTTP {exc.code}: {body}") from exc
    raw = json.loads(data["choices"][0]["message"]["content"])
    raw["provider"] = "openai"
    raw["model"] = model.model
    raw["generated_at"] = utc_now_iso()
    return raw


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    return [str(item).strip() for item in values if str(item).strip()][:12]


def _fingerprint(value: dict[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
