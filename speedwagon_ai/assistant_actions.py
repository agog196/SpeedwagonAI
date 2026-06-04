from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date
from typing import Any

from speedwagon_ai.context import render_context
from speedwagon_ai.capture import Recorder
from speedwagon_ai.integrations.calendar import GoogleCalendarService
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
    {"category": "calendar", "command": "prep for my next meeting", "description": "Show local context for the next Calendar event."},
    {"category": "calendar", "command": "what is on my calendar today", "description": "List today's synced Calendar events."},
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
            "tasks": [task for task in repo.list_tasks(status="open") if task.get("due_date") == requested_date],
        }
    if action == "list_open_tasks":
        return {"tasks": repo.list_tasks(status="open")}
    if action == "list_unscheduled_tasks":
        return {"tasks": [task for task in repo.list_tasks(status="open") if not task.get("due_date")]}
    if action == "list_waiting_tasks":
        return {"tasks": repo.list_commitments(status="waiting")}
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
    if action == "list_calendar_events":
        return GoogleCalendarService(settings, repo).events(
            start_date=payload.get("from") or payload.get("start_date"),
            end_date=payload.get("to") or payload.get("end_date"),
            limit=int(payload.get("limit") or 50),
        )
    if action == "list_upcoming_calendar_events":
        return GoogleCalendarService(settings, repo).upcoming(limit=int(payload.get("limit") or 10))
    if action == "prep_next_meeting":
        events = repo.upcoming_calendar_events(limit=1)
        if not events:
            return {"event": None, "prep": None, "message": "No upcoming calendar events are synced."}
        return {"event": events[0], "prep": repo.meeting_prep_for_event(events[0])}
    if action == "search_context_graph":
        query = str(payload.get("query") or payload.get("topic") or payload.get("context") or "")
        return repo.context_graph(query)
    if action == "list_suggestions":
        return {"suggestions": repo.list_suggestions(status=payload.get("status") or "open")}
    if action == "confirm_suggestion":
        suggestion_id = int(payload["suggestion_id"])
        suggestion = repo.get_suggestion(suggestion_id)
        result: dict[str, Any] = {}
        proposed_action = str(suggestion.get("proposed_action") or "")
        if proposed_action:
            result = run_action(settings, repo, proposed_action, suggestion.get("payload") or {})
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
        return {"task": repo.complete_task(int(payload["task_id"]))}
    if action == "reopen_task":
        return {"task": repo.reopen_task(int(payload["task_id"]))}
    if action == "snooze_task":
        return {"task": repo.snooze_task(int(payload["task_id"]), until=payload.get("until"))}
    if action == "cancel_task":
        return {"task": repo.cancel_task(int(payload["task_id"]))}
    if action == "mark_task_waiting":
        return {"task": repo.update_task_status(int(payload["task_id"]), "waiting")}
    if action == "mark_task_uncertain":
        return {"task": repo.update_task_status(int(payload["task_id"]), "uncertain")}
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
        return draft_from_context(settings, repo, payload)
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


def draft_from_context(settings: Settings, repo: Repository, payload: dict[str, Any]) -> dict[str, Any]:
    context_id = int(payload.get("context_id") or 0)
    if not context_id:
        query = str(payload.get("query") or payload.get("context") or "")
        contexts = repo.find_contexts(query, limit=1)
        if not contexts:
            return {"draft": fallback_context_draft(query or "that context", [], None), "context": None, "tasks": []}
        context_id = int(contexts[0]["id"])
    context = repo.get_context(context_id)
    tasks = repo.tasks_for_context(context_id, include_done=True)
    meeting_ids = [int(task["meeting_id"]) for task in tasks if task.get("meeting_id")]
    if payload.get("meeting_id"):
        meeting_ids.insert(0, int(payload["meeting_id"]))
    if meeting_ids:
        draft = preview_followup_email(
            settings,
            repo,
            meeting_ids[0],
            to=str(payload.get("to") or ""),
            subject=payload.get("subject") or f"Follow-up on {context['name']}",
            instruction=str(payload.get("instruction") or f"Draft a concise follow-up about {context['name']} and next steps."),
        )
    else:
        draft = fallback_context_draft(str(context["name"]), tasks, payload.get("subject"))
    return {"draft": draft, "context": context, "tasks": tasks}


def tasks_due_before(repo: Repository, due_before: str, inclusive: bool = False) -> dict[str, Any]:
    if not due_before:
        return {"date": "", "due_before": "", "inclusive": inclusive, "tasks": []}
    tasks = []
    for task in repo.list_tasks(status="open"):
        due = task.get("due_date")
        if not due:
            continue
        if due < due_before or (inclusive and due == due_before):
            tasks.append(task)
    return {"date": due_before, "due_before": due_before, "inclusive": inclusive, "tasks": tasks}


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
        "body": "\n".join(lines),
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
