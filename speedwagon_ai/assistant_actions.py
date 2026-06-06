from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from datetime import date
from typing import Any

from speedwagon_ai.context import render_context
from speedwagon_ai.capture import Recorder
from speedwagon_ai.integrations.calendar import GoogleCalendarService
from speedwagon_ai.email_composer import compose_context_email, ensure_email_signature
from speedwagon_ai.integrations.gmail import preview_followup_email
from speedwagon_ai.config import Settings
from speedwagon_ai.meeting_bot import MeetingBotService
from speedwagon_ai.model_router import web_search_enabled
from speedwagon_ai.processing import process_meeting
from speedwagon_ai.storage import Repository


CAPABILITIES = [
    {"category": "brief", "command": "daily brief", "description": "Show overdue, due-today, waiting, uncertain, and stale work."},
    {"category": "tasks", "command": "what is overdue", "description": "List overdue tasks and commitments."},
    {"category": "tasks", "command": "what is due before June 7", "description": "List open tasks due before or by a date."},
    {"category": "tasks", "command": "what tasks have no due date", "description": "List open tasks that do not have a due date."},
    {"category": "commitments", "command": "what do I owe Alex", "description": "Find commitments related to a person."},
    {"category": "context", "command": "what did I say about onboarding", "description": "Search meeting history and decisions."},
    {"category": "context", "command": "what did we decide about onboarding", "description": "Show decisions, meetings, and graph links for a topic."},
    {"category": "context", "command": "everything related to Alex", "description": "Traverse one-hop context graph relationships for a person, project, or topic."},
    {"category": "brief", "command": "who should I follow up with", "description": "Show suggested follow-ups and waiting/uncertain commitments."},
    {"category": "context", "command": "what changed on DairyMGT", "description": "Show recent related meetings, decisions, tasks, and graph links."},
    {"category": "meetings", "command": "show unprocessed meetings", "description": "List meetings missing transcript, extraction, or notes."},
    {"category": "meetings", "command": "process latest meeting", "description": "Process the newest meeting that still needs notes/tasks."},
    {"category": "capture", "command": "start meeting recording called weekly planning", "description": "Start local mic recording for a meeting."},
    {"category": "capture", "command": "finish meeting", "description": "Stop active meeting recording and process it."},
    {"category": "email", "command": "draft follow-up for meeting 8", "description": "Preview a follow-up email draft for a meeting."},
    {"category": "tasks", "command": "search tasks for DairyMGT", "description": "Search local tasks by text, project, source meeting, or context."},
    {"category": "context", "command": "search context graph for onboarding", "description": "Show contexts, linked tasks, meetings, and suggestions."},
    {"category": "brief", "command": "show suggestions", "description": "List Speedwagon's local follow-through suggestions."},
    {"category": "brief", "command": "confirm suggestion 3", "description": "Accept an in-app suggestion after reviewing it."},
    {"category": "capture", "command": "show bot sessions", "description": "List optional managed meeting-bot sessions."},
    {"category": "capture", "command": "send bot to meeting <url>", "description": "Send the configured meeting bot to a meeting link after explicit consent."},
    {"category": "capture", "command": "sync bot session 3", "description": "Pull transcript/status for a meeting-bot session."},
    {"category": "meetings", "command": "process bot session 3", "description": "Turn a bot transcript into notes, tasks, context, and suggestions."},
    {"category": "calendar", "command": "sync calendar", "description": "Sync the configured Google Calendar window."},
    {"category": "calendar", "command": "show upcoming meetings", "description": "List upcoming synced Calendar events."},
    {"category": "calendar", "command": "when is my meeting with Alex", "description": "Search upcoming synced Calendar events by person, title, location, or attendees."},
    {"category": "calendar", "command": "prep for my next meeting", "description": "Show local context for the next Calendar event."},
    {"category": "calendar", "command": "what is on my calendar today", "description": "List today's synced Calendar events."},
    {"category": "calendar", "command": "create calendar event for June 10 at 10am to call Raj", "description": "Create a Google Calendar event after explicit confirmation."},
    {"category": "email", "command": "draft an email to John asking for v8 files", "description": "Retrieve local context, preview a draft, then create a local draft after confirmation."},
    {"category": "context", "command": "search the web for current pricing", "description": "Explicit web search request; disabled unless opted in."},
]


def run_action(settings: Settings, repo: Repository, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    if action == "list_capabilities":
        return {"capabilities": CAPABILITIES}
    if action == "list_overdue_tasks":
        due_before = payload.get("due_before") or payload.get("before")
        if due_before:
            return tasks_due_before(repo, str(due_before), inclusive=bool(payload.get("inclusive")))
        return {"tasks": repo.overdue_tasks()}
    if action == "list_tasks_due_before":
        due_before = str(payload.get("due_before") or payload.get("date") or "")
        return tasks_due_before(repo, due_before, inclusive=bool(payload.get("inclusive", True)))
    if action == "list_today_tasks":
        requested_date = str(payload.get("date") or payload.get("due_date") or date.today().isoformat())
        return {
            "date": requested_date,
            "tasks": [task for task in active_tasks(repo) if task.get("due_date") == requested_date],
        }
    if action == "list_open_tasks":
        return {"tasks": repo.list_tasks(status="open")}
    if action == "list_unscheduled_tasks":
        return {"tasks": [task for task in active_tasks(repo) if not task.get("due_date")]}
    if action == "list_waiting_tasks":
        return {"tasks": repo.list_commitments(status="waiting")}
    if action == "show_tasks_by_id":
        task_ids = payload.get("task_ids") or []
        if isinstance(task_ids, str):
            task_ids = [int(x.strip()) for x in task_ids.split(",") if x.strip().isdigit()]
        task_ids = [int(x) for x in task_ids if str(x).strip()]
        return {"task_ids": task_ids, "tasks": repo.get_tasks_by_ids(task_ids)}
    if action == "search_tasks":
        return {
            "query": str(payload.get("query") or ""),
            "tasks": repo.search_tasks(
                query=str(payload.get("query") or ""),
                status=payload.get("status"),
            ),
        }
    if action == "daily_brief":
        return repo.daily_brief()
    if action == "calendar_status":
        return GoogleCalendarService(settings, repo).status()
    if action == "sync_calendar":
        return GoogleCalendarService(settings, repo).sync()
    if action == "create_calendar_event":
        return GoogleCalendarService(settings, repo).create_event(
            title=str(payload.get("title") or ""),
            start_at=str(payload.get("start_at") or ""),
            end_at=str(payload.get("end_at") or ""),
            calendar_id=str(payload.get("calendar_id") or "primary"),
            timezone_name=payload.get("timezone"),
            description=payload.get("description"),
            location=payload.get("location"),
            attendees=payload.get("attendees") if isinstance(payload.get("attendees"), list) else [],
            send_updates=str(payload.get("send_updates") or "none"),
        )
    if action == "list_calendar_events":
        return GoogleCalendarService(settings, repo).events(
            start_date=payload.get("from") or payload.get("start_date"),
            end_date=payload.get("to") or payload.get("end_date"),
            limit=int(payload.get("limit") or 50),
        )
    if action == "list_upcoming_calendar_events":
        return GoogleCalendarService(settings, repo).upcoming(limit=int(payload.get("limit") or 10))
    if action == "search_calendar_events":
        query = str(payload.get("query") or payload.get("person") or payload.get("topic") or "")
        return {
            "query": query,
            "events": search_calendar_events(repo, query, limit=int(payload.get("limit") or 10)),
        }
    if action == "prep_next_meeting":
        events = repo.upcoming_calendar_events(limit=1)
        if not events:
            return {"event": None, "prep": None, "message": "No upcoming calendar events are synced."}
        return {"event": events[0], "prep": repo.meeting_prep_for_event(events[0])}
    if action == "search_context_graph":
        query = str(payload.get("query") or payload.get("topic") or payload.get("context") or "")
        return repo.context_graph(query)
    if action == "decisions_about_context":
        query = str(payload.get("query") or payload.get("topic") or payload.get("context") or "")
        graph = repo.context_graph(query)
        context = repo.context_for_topic(query)
        return {
            "query": query,
            "contexts": graph.get("contexts", []),
            "relationships": graph.get("relationships", []),
            "meetings": graph.get("meetings", []),
            "tasks": graph.get("tasks", []),
            "decisions": context.get("decisions", []),
        }
    if action == "everything_related":
        query = str(payload.get("query") or payload.get("topic") or payload.get("context") or "")
        return repo.context_graph(query)
    if action == "followup_targets":
        brief = repo.daily_brief()
        suggestions = repo.list_suggestions(status="open", limit=30)
        followup_suggestions = [
            suggestion
            for suggestion in suggestions
            if suggestion.get("proposed_action") in {"draft_email_from_context", "add_task"}
            or "follow" in str(suggestion.get("title") or suggestion.get("reason") or "").lower()
        ]
        return {
            "suggestions": followup_suggestions[:10],
            "tasks": [*brief.get("waiting", [])[:5], *brief.get("uncertain", [])[:5], *brief.get("overdue", [])[:5]],
            "counts": brief.get("counts", {}),
        }
    if action == "context_changes":
        query = str(payload.get("query") or payload.get("topic") or payload.get("context") or "")
        graph = repo.context_graph(query)
        context = repo.context_for_topic(query)
        return {
            "query": query,
            "contexts": graph.get("contexts", []),
            "relationships": graph.get("relationships", []),
            "meetings": graph.get("meetings", [])[:8],
            "tasks": graph.get("tasks", [])[:12],
            "decisions": context.get("decisions", [])[:8],
            "suggestions": graph.get("suggestions", [])[:8],
        }
    if action == "list_suggestions":
        return {"suggestions": repo.list_suggestions(status=payload.get("status") or "open")}
    if action == "confirm_suggestion":
        suggestion_id = int(payload["suggestion_id"])
        suggestion = repo.get_suggestion(suggestion_id)
        result: dict[str, Any] = {}
        proposed_action = str(suggestion.get("proposed_action") or "")
        if proposed_action == "draft_email_from_context":
            result = create_local_followup_draft(settings, repo, suggestion)
        elif proposed_action == "add_task":
            result = create_or_reuse_task_from_suggestion(repo, suggestion)
        elif proposed_action:
            result = run_action(settings, repo, proposed_action, suggestion.get("payload") or {})
            result.setdefault("created", False)
            result.setdefault("reused", False)
            result.setdefault("next_step", "Review the result.")
        updated = repo.update_suggestion_status(suggestion_id, "accepted")
        return {"suggestion": updated, "action_result": result}
    if action == "dismiss_suggestion":
        return {"suggestion": repo.update_suggestion_status(int(payload["suggestion_id"]), "dismissed")}
    if action == "snooze_suggestion":
        suggestion_id = int(payload["suggestion_id"])
        until = payload.get("until") or payload.get("snoozed_until")
        return {"suggestion": repo.update_suggestion_status(suggestion_id, "snoozed", snoozed_until=until)}
    if action == "system_status":
        return {
            "db_path": str(settings.db_path),
            "openai_key_present": bool(settings.openai_api_key),
            "active_recording": active_recording(settings),
            "unprocessed_meetings": len(repo.list_unprocessed_meetings()),
        }
    if action == "bot_status":
        return MeetingBotService(settings, repo).status()
    if action == "list_bot_sessions":
        return {"sessions": MeetingBotService(settings, repo).sessions(limit=int(payload.get("limit") or 20))}
    if action == "join_meeting_bot":
        return MeetingBotService(settings, repo).join(
            meeting_url=str(payload.get("meeting_url") or payload.get("url") or ""),
            title=str(payload.get("title") or "Bot meeting"),
            join_at=payload.get("join_at"),
            bot_name=payload.get("bot_name"),
            consent_confirmed=bool(payload.get("consent_confirmed")),
        )
    if action == "sync_bot_session":
        return MeetingBotService(settings, repo).sync(int(payload["session_id"]))
    if action == "process_bot_session":
        return MeetingBotService(settings, repo).process(int(payload["session_id"]))
    if action == "list_unprocessed_meetings":
        return {"meetings": [meeting_to_dict(meeting) for meeting in repo.list_unprocessed_meetings()]}
    if action == "process_meeting":
        meeting_id = int(payload["meeting_id"])
        return process_result_to_dict(process_meeting(settings, repo, meeting_id))
    if action == "process_latest_meeting":
        meeting = repo.latest_unprocessed_meeting()
        if meeting is None:
            return {"meeting": None, "message": "No unprocessed meetings."}
        return process_result_to_dict(process_meeting(settings, repo, meeting.id))
    if action == "start_meeting_recording":
        title = str(payload.get("title") or "").strip()
        if not title:
            raise ValueError("Meeting title is required")
        meeting_id = Recorder(settings, repo).start(title)
        return {"meeting_id": meeting_id, "recording": active_recording(settings)}
    if action == "finish_meeting_recording":
        meeting_id = Recorder(settings, repo).stop()
        result = process_meeting(settings, repo, meeting_id)
        return process_result_to_dict(result)
    if action == "stop_meeting_recording":
        meeting_id = Recorder(settings, repo).stop()
        return {"meeting_id": meeting_id, "message": "Stopped recording without processing."}
    if action == "list_commitments_for_person":
        person = str(payload.get("person") or "")
        return {"person": person, "tasks": repo.list_commitments(person=person)}
    if action == "add_task":
        return {
            "task": repo.create_task(
                str(payload.get("text") or ""),
                owner=payload.get("owner"),
                due_date=payload.get("due_date"),
                owed_to=payload.get("owed_to"),
                project=payload.get("project"),
                source=str(payload.get("source") or "manual"),
                source_type=payload.get("source_type"),
                source_meeting_id=payload.get("source_meeting_id"),
            )
        }
    if action == "complete_task":
        task_ids = _task_ids_from_payload(payload)
        tasks = [repo.complete_task(task_id) for task_id in task_ids]
        return {"task": tasks[0], "tasks": tasks}
    if action == "reopen_task":
        task_ids = _task_ids_from_payload(payload)
        tasks = [repo.reopen_task(task_id) for task_id in task_ids]
        return {"task": tasks[0], "tasks": tasks}
    if action == "snooze_task":
        task_ids = _task_ids_from_payload(payload)
        tasks = [repo.snooze_task(task_id, until=payload.get("until")) for task_id in task_ids]
        return {"task": tasks[0], "tasks": tasks}
    if action == "cancel_task":
        task_ids = _task_ids_from_payload(payload)
        tasks = [repo.cancel_task(task_id) for task_id in task_ids]
        return {"task": tasks[0], "tasks": tasks}
    if action == "mark_task_waiting":
        task_ids = _task_ids_from_payload(payload)
        tasks = [repo.update_task_status(task_id, "waiting") for task_id in task_ids]
        return {"task": tasks[0], "tasks": tasks}
    if action == "mark_task_uncertain":
        task_ids = _task_ids_from_payload(payload)
        tasks = [repo.update_task_status(task_id, "uncertain") for task_id in task_ids]
        return {"task": tasks[0], "tasks": tasks}
    if action in {"draft_followup", "draft_meeting_followup"}:
        meeting_id = int(payload["meeting_id"])
        return {
            "draft": preview_followup_email(
                settings,
                repo,
                meeting_id,
                to=str(payload.get("to") or ""),
                subject=payload.get("subject"),
                instruction=str(payload.get("instruction") or ""),
            )
        }
    if action == "draft_email_from_context":
        return create_local_draft_from_context(settings, repo, payload)
    if action == "create_local_email_draft":
        return create_local_email_draft(repo, payload)
    if action == "search_context":
        topic = str(payload.get("topic") or "")
        return {"topic": topic, "markdown": render_context(repo, topic)}
    if action == "web_search":
        query = str(payload.get("query") or "").strip()
        if not web_search_enabled():
            return {
                "query": query,
                "enabled": False,
                "message": "Web search is disabled. Set SPEEDWAGON_ENABLE_WEB_SEARCH=true to opt in.",
            }
        return {
            "query": query,
            "enabled": True,
            "message": "Web search is enabled, but V12 has not configured a search provider yet.",
            "results": [],
        }
    raise ValueError(f"Unknown assistant action: {action}")


def search_calendar_events(repo: Repository, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    terms = calendar_search_terms(query)
    if not terms:
        return []
    scored: list[tuple[int, str, dict[str, Any]]] = []
    for event in repo.upcoming_calendar_events(limit=120):
        haystack = calendar_event_search_blob(event)
        if not haystack:
            continue
        score = sum(1 for term in terms if term in haystack)
        if score == 0:
            continue
        if len(terms) > 1 and score < max(1, len(terms) - 1):
            continue
        title_blob = normalize_calendar_search_text(str(event.get("title") or ""))
        if any(term in title_blob for term in terms):
            score += 2
        scored.append((score, str(event.get("start_at") or ""), event))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [event for _, _, event in scored[:limit]]


def calendar_search_terms(query: str) -> list[str]:
    normalized = normalize_calendar_search_text(query)
    stop_words = {
        "a",
        "an",
        "about",
        "and",
        "calendar",
        "call",
        "event",
        "for",
        "meeting",
        "my",
        "on",
        "prof",
        "professor",
        "schedule",
        "the",
        "with",
    }
    return [term for term in normalized.split() if len(term) > 1 and term not in stop_words]


def calendar_event_search_blob(event: dict[str, Any]) -> str:
    pieces = [
        event.get("title"),
        event.get("description_snippet"),
        event.get("location"),
        event.get("meeting_url"),
    ]
    for attendee in event.get("attendees") or []:
        if isinstance(attendee, dict):
            pieces.append(attendee.get("email"))
            pieces.append(attendee.get("display_name"))
    return normalize_calendar_search_text(" ".join(str(piece or "") for piece in pieces))


def normalize_calendar_search_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


def _coerce_int_id(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        id_value = int(text)
    except (TypeError, ValueError):
        return None
    return id_value if id_value > 0 else None


def _iter_id_candidates(*candidates: Any) -> list[Any]:
    values: list[Any] = []
    for candidate in candidates:
        if isinstance(candidate, (list, tuple, set)):
            values.extend(candidate)
        else:
            values.append(candidate)
    return values


def _existing_task_id(repo: Repository, value: Any) -> int | None:
    task_id = _coerce_int_id(value)
    if task_id is None:
        return None
    try:
        repo.get_task(task_id)
    except KeyError:
        return None
    return task_id


def _existing_meeting_id(repo: Repository, value: Any) -> int | None:
    meeting_id = _coerce_int_id(value)
    if meeting_id is None:
        return None
    try:
        repo.get_meeting(meeting_id)
    except KeyError:
        return None
    return meeting_id


def _existing_context_id(repo: Repository, value: Any) -> int | None:
    context_id = _coerce_int_id(value)
    if context_id is None:
        return None
    try:
        repo.get_context(context_id)
    except KeyError:
        return None
    return context_id


def _first_existing_task_id(repo: Repository, *candidates: Any) -> int | None:
    for candidate in _iter_id_candidates(*candidates):
        task_id = _existing_task_id(repo, candidate)
        if task_id is not None:
            return task_id
    return None


def _first_existing_meeting_id(repo: Repository, *candidates: Any) -> int | None:
    for candidate in _iter_id_candidates(*candidates):
        meeting_id = _existing_meeting_id(repo, candidate)
        if meeting_id is not None:
            return meeting_id
    return None


def _first_existing_context_id(repo: Repository, *candidates: Any) -> int | None:
    for candidate in _iter_id_candidates(*candidates):
        context_id = _existing_context_id(repo, candidate)
        if context_id is not None:
            return context_id
    return None


def _task_ids_from_payload(payload: dict[str, Any]) -> list[int]:
    values = _iter_id_candidates(payload.get("task_id"), payload.get("task_ids"))
    task_ids: list[int] = []
    for value in values:
        if isinstance(value, str) and "," in value:
            values.extend(value.split(","))
            continue
        task_id = _coerce_int_id(value)
        if task_id is not None and task_id not in task_ids:
            task_ids.append(task_id)
    if not task_ids:
        raise ValueError("task_id is required")
    return task_ids


def draft_from_context(settings: Settings, repo: Repository, payload: dict[str, Any]) -> dict[str, Any]:
    context_id = _existing_context_id(repo, payload.get("context_id"))
    if not context_id:
        query = str(payload.get("query") or payload.get("context") or "")
        contexts = repo.find_contexts(query, limit=1)
        if not contexts:
            return {"draft": fallback_context_draft(query or "that context", [], None), "context": None, "tasks": []}
        context_id = _existing_context_id(repo, contexts[0].get("id"))
        if not context_id:
            return {"draft": fallback_context_draft(query or "that context", [], None), "context": None, "tasks": []}
    detail = repo.context_detail(context_id, limit=24)
    context = detail.get("context") or repo.get_context(context_id)
    tasks = detail.get("tasks") or repo.tasks_for_context(context_id, include_done=True)
    meetings = detail.get("meetings") or []
    decisions = detail.get("decisions") or []
    related_contexts = detail.get("related_contexts") or []
    meeting_ids = [
        meeting_id
        for meeting_id in (_existing_meeting_id(repo, task.get("meeting_id")) for task in tasks)
        if meeting_id is not None
    ]
    payload_meeting_id = _existing_meeting_id(repo, payload.get("meeting_id"))
    if payload_meeting_id:
        meeting_ids.insert(0, payload_meeting_id)
    if meeting_ids:
        draft = preview_followup_email(
            settings,
            repo,
            meeting_ids[0],
            to=context_recipient(context, payload),
            subject=payload.get("subject") or f"Follow-up on {context['name']}",
            instruction=str(payload.get("instruction") or f"Draft a concise follow-up about {context['name']} and next steps."),
        )
    else:
        recipient = context_recipient(context, payload)
        draft = compose_context_email(
            settings,
            recipient=recipient,
            subject=payload.get("subject"),
            instruction=str(payload.get("instruction") or f"Draft a concise follow-up about {context['name']}."),
            context=context,
            tasks=tasks,
            meetings=meetings,
            decisions=decisions,
            related_contexts=related_contexts,
        ).to_dict()
        if recipient:
            draft["to"] = recipient
    return {
        "draft": draft,
        "context": context,
        "tasks": tasks,
        "meetings": meetings,
        "decisions": decisions,
        "related_contexts": related_contexts,
    }


def create_local_draft_from_context(settings: Settings, repo: Repository, payload: dict[str, Any]) -> dict[str, Any]:
    result = draft_from_context(settings, repo, payload)
    draft = result.get("draft") or {}
    context = result.get("context") or {}
    tasks = result.get("tasks") or []
    meeting_id = _first_existing_meeting_id(repo, payload.get("meeting_id"), [task.get("meeting_id") for task in tasks])
    task_id = _first_existing_task_id(
        repo,
        payload.get("task_id"),
        [task.get("id") for task in tasks if task.get("status") not in {"done", "canceled"}],
    )
    context_id = _existing_context_id(repo, context.get("id"))
    local = repo.create_followup_draft(
        suggestion_id=None,
        task_id=task_id,
        context_id=context_id,
        meeting_id=meeting_id,
        recipient=str(draft.get("to") or context_recipient(context, payload) or ""),
        subject=str(draft.get("subject") or payload.get("subject") or "Follow-up"),
        body=str(draft.get("body") or ""),
        source="assistant",
    )
    return {
        **result,
        "followup_draft": local,
        "draft": local,
        "created": True,
        "reused": False,
        "next_step": "Review the local draft before creating it in Gmail.",
    }


def create_local_email_draft(repo: Repository, payload: dict[str, Any]) -> dict[str, Any]:
    recipient = str(payload.get("to") or payload.get("recipient") or "").strip()
    subject = str(payload.get("subject") or "").strip()
    body = ensure_email_signature(str(payload.get("body") or "").strip())
    if not recipient:
        raise ValueError("recipient is required")
    if not subject:
        raise ValueError("subject is required")
    if not body:
        raise ValueError("body is required")
    task_id = _existing_task_id(repo, payload.get("task_id"))
    context_id = _existing_context_id(repo, payload.get("context_id"))
    meeting_id = _existing_meeting_id(repo, payload.get("meeting_id"))
    local = repo.create_followup_draft(
        suggestion_id=_coerce_int_id(payload.get("suggestion_id")),
        task_id=task_id,
        context_id=context_id,
        meeting_id=meeting_id,
        recipient=recipient,
        subject=subject,
        body=body,
        source=str(payload.get("source") or "assistant"),
    )
    return {
        "followup_draft": local,
        "draft": local,
        "created": True,
        "reused": False,
        "next_step": "Review the local draft before creating it in Gmail.",
    }


def context_recipient(context: dict[str, Any], payload: dict[str, Any]) -> str:
    explicit = str(payload.get("to") or payload.get("recipient") or "").strip()
    if "@" in explicit:
        return explicit
    profile_email = str(context.get("profile_email") or "").strip()
    if profile_email:
        return profile_email
    return explicit


def create_local_followup_draft(settings: Settings, repo: Repository, suggestion: dict[str, Any]) -> dict[str, Any]:
    existing = repo.followup_draft_for_suggestion(int(suggestion["id"]))
    if existing:
        return {
            "followup_draft": existing,
            "draft": existing,
            "created": False,
            "reused": True,
            "next_step": "Review the existing local draft before creating it in Gmail.",
        }
    payload = suggestion.get("payload") or {}
    result = draft_from_context(settings, repo, payload)
    draft = result.get("draft") or {}
    tasks = result.get("tasks") or []
    context = result.get("context") or suggestion.get("context") or {}
    task_id = _first_existing_task_id(
        repo,
        payload.get("task_id"),
        suggestion.get("task_ids") or [],
        [task.get("id") for task in tasks if task.get("status") not in {"done", "canceled"}],
    )
    context_id = _first_existing_context_id(repo, context.get("id"), suggestion.get("context_id"), payload.get("context_id"))
    meeting_id = _first_existing_meeting_id(
        repo,
        payload.get("meeting_id"),
        suggestion.get("meeting_ids") or [],
        [task.get("meeting_id") for task in tasks],
    )
    local = repo.create_followup_draft(
        suggestion_id=int(suggestion["id"]),
        task_id=task_id,
        context_id=context_id,
        meeting_id=meeting_id,
        recipient=str(draft.get("to") or ""),
        subject=str(draft.get("subject") or suggestion.get("title") or "Follow-up"),
        body=str(draft.get("body") or ""),
        source="suggestion",
    )
    return {
        "followup_draft": local,
        "draft": local,
        "context": context,
        "tasks": tasks,
        "created": True,
        "reused": False,
        "next_step": "Review the local draft before creating it in Gmail.",
    }


def create_or_reuse_task_from_suggestion(repo: Repository, suggestion: dict[str, Any]) -> dict[str, Any]:
    payload = suggestion.get("payload") or {}
    existing = find_existing_suggestion_task(repo, payload)
    if existing:
        return {
            "task": existing,
            "created": False,
            "reused": True,
            "next_step": "Review the existing task.",
        }
    task = repo.create_task(
        str(payload.get("text") or ""),
        owner=payload.get("owner"),
        due_date=payload.get("due_date"),
        owed_to=payload.get("owed_to"),
        project=payload.get("project"),
        source=str(payload.get("source") or "manual"),
        source_type=payload.get("source_type"),
        source_meeting_id=payload.get("source_meeting_id"),
    )
    return {
        "task": task,
        "created": True,
        "reused": False,
        "next_step": "Review the created task.",
    }


def find_existing_suggestion_task(repo: Repository, payload: dict[str, Any]) -> dict[str, Any] | None:
    text = str(payload.get("text") or "").strip()
    if not text:
        return None
    source_meeting_id = payload.get("source_meeting_id")
    for task in repo.list_tasks(status=None, include_done=True):
        if str(task.get("text") or "").strip() != text:
            continue
        if _optional_match(task.get("due_date"), payload.get("due_date")) is False:
            continue
        if _optional_match(task.get("owner"), payload.get("owner")) is False:
            continue
        if _optional_match(task.get("owed_to"), payload.get("owed_to")) is False:
            continue
        if _optional_match(task.get("project"), payload.get("project")) is False:
            continue
        if source_meeting_id is not None and int(task.get("source_meeting_id") or 0) != int(source_meeting_id):
            continue
        return task
    return None


def _optional_match(left: Any, right: Any) -> bool:
    return (left or None) == (right or None)


def tasks_due_before(repo: Repository, due_before: str, inclusive: bool = False) -> dict[str, Any]:
    if not due_before:
        return {"date": "", "due_before": "", "inclusive": inclusive, "tasks": []}
    tasks = []
    for task in active_tasks(repo):
        due = task.get("due_date")
        if not due:
            continue
        if due < due_before or (inclusive and due == due_before):
            tasks.append(task)
    return {"date": due_before, "due_before": due_before, "inclusive": inclusive, "tasks": tasks}


def active_tasks(repo: Repository) -> list[dict[str, Any]]:
    return [
        task
        for task in repo.list_tasks(status=None, include_done=False)
        if task.get("status") not in {"done", "canceled", "snoozed"}
    ]


def fallback_context_draft(context_name: str, tasks: list[dict[str, Any]], subject: str | None) -> dict[str, Any]:
    open_tasks = [task for task in tasks if task.get("status") not in {"done", "canceled"}]
    lines = [
        "Hi,",
        "",
        f"Quick follow-up on {context_name}.",
    ]
    if open_tasks:
        lines.extend(["", "Current next steps:"])
        for task in open_tasks[:6]:
            due = f" due {task['due_date']}" if task.get("due_date") else ""
            lines.append(f"- {task.get('text')}{due}")
    lines.extend(["", "Thanks,"])
    return {
        "subject": subject or f"Follow-up on {context_name}",
        "body": ensure_email_signature("\n".join(lines)),
        "tone": "concise",
        "included_items": [str(task.get("id")) for task in open_tasks[:6]],
        "provider": "fallback",
    }


def active_recording(settings: Settings) -> dict[str, Any]:
    if not settings.state_path.exists():
        return {"active": False}
    return {"active": True, **json.loads(settings.state_path.read_text(encoding="utf-8"))}


def meeting_to_dict(meeting: Any) -> dict[str, Any]:
    if is_dataclass(meeting):
        return asdict(meeting)
    return dict(meeting)


def process_result_to_dict(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "meeting": meeting_to_dict(result["meeting"]),
        "transcript_path": str(result["transcript_path"]),
        "note_path": str(result["note_path"]),
        "commitments_path": str(result["commitments_path"]),
        "action_items": len(result["extraction"].action_items),
        "commitments": len(result["extraction"].commitments),
    }
