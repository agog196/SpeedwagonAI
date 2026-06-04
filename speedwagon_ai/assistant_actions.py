from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date
from typing import Any

from speedwagon_ai.context import render_context
from speedwagon_ai.capture import Recorder
from speedwagon_ai.integrations.gmail import preview_followup_email
from speedwagon_ai.config import Settings
from speedwagon_ai.model_router import web_search_enabled
from speedwagon_ai.processing import process_meeting
from speedwagon_ai.storage import Repository


CAPABILITIES = [
    {"category": "brief", "command": "daily brief", "description": "Show overdue, due-today, waiting, uncertain, and stale work."},
    {"category": "tasks", "command": "what is overdue", "description": "List overdue tasks and commitments."},
    {"category": "tasks", "command": "what tasks have no due date", "description": "List open tasks that do not have a due date."},
    {"category": "commitments", "command": "what do I owe Alex", "description": "Find commitments related to a person."},
    {"category": "context", "command": "what did I say about onboarding", "description": "Search meeting history and decisions."},
    {"category": "meetings", "command": "show unprocessed meetings", "description": "List meetings missing transcript, extraction, or notes."},
    {"category": "meetings", "command": "process latest meeting", "description": "Process the newest meeting that still needs notes/tasks."},
    {"category": "capture", "command": "start meeting recording called weekly planning", "description": "Start local mic recording for a meeting."},
    {"category": "capture", "command": "finish meeting", "description": "Stop active meeting recording and process it."},
    {"category": "email", "command": "draft follow-up for meeting 8", "description": "Preview a follow-up email draft for a meeting."},
    {"category": "context", "command": "search the web for current pricing", "description": "Explicit web search request; disabled unless opted in."},
]


def run_action(settings: Settings, repo: Repository, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    if action == "list_capabilities":
        return {"capabilities": CAPABILITIES}
    if action == "list_overdue_tasks":
        return {"tasks": repo.overdue_tasks()}
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
    if action == "daily_brief":
        return repo.daily_brief()
    if action == "system_status":
        return {
            "db_path": str(settings.db_path),
            "openai_key_present": bool(settings.openai_api_key),
            "active_recording": active_recording(settings),
            "unprocessed_meetings": len(repo.list_unprocessed_meetings()),
        }
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
