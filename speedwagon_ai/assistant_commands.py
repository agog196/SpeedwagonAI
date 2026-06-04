from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any

from speedwagon_ai.assistant_actions import CAPABILITIES, run_action
from speedwagon_ai.assistant_brain import interpret_command
from speedwagon_ai.config import Settings
from speedwagon_ai.dateparse import parse_date_phrase
from speedwagon_ai.storage import Repository


@dataclass(frozen=True)
class ParsedCommand:
    supported: bool
    action: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    category: str = "system_status"
    requires_confirmation: bool = False
    confidence: float | None = None
    explanation: str = ""
    safety_notes: list[str] = field(default_factory=list)
    pending_action_id: int | None = None
    source: str = "rules"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


CATEGORIES = {
    "list_capabilities": "system_status",
    "system_status": "system_status",
    "bot_status": "capture",
    "list_bot_sessions": "capture",
    "join_meeting_bot": "capture",
    "sync_bot_session": "capture",
    "process_bot_session": "meetings",
    "list_overdue_tasks": "tasks",
    "list_tasks_due_before": "tasks",
    "list_today_tasks": "tasks",
    "list_open_tasks": "tasks",
    "list_unscheduled_tasks": "tasks",
    "list_waiting_tasks": "commitments",
    "search_tasks": "tasks",
    "list_commitments_for_person": "commitments",
    "daily_brief": "brief",
    "calendar_status": "calendar",
    "sync_calendar": "calendar",
    "list_calendar_events": "calendar",
    "list_upcoming_calendar_events": "calendar",
    "prep_next_meeting": "calendar",
    "list_suggestions": "brief",
    "confirm_suggestion": "brief",
    "dismiss_suggestion": "brief",
    "snooze_suggestion": "brief",
    "add_task": "tasks",
    "complete_task": "tasks",
    "reopen_task": "tasks",
    "snooze_task": "tasks",
    "cancel_task": "tasks",
    "mark_task_waiting": "commitments",
    "mark_task_uncertain": "commitments",
    "search_context": "context",
    "search_context_graph": "context",
    "list_unprocessed_meetings": "meetings",
    "process_meeting": "meetings",
    "process_latest_meeting": "meetings",
    "start_meeting_recording": "capture",
    "finish_meeting_recording": "capture",
    "stop_meeting_recording": "capture",
    "draft_meeting_followup": "email",
    "draft_followup": "email",
    "draft_email_from_context": "email",
    "web_search": "context",
}


MUTATING_ACTIONS = {
    "add_task",
    "complete_task",
    "reopen_task",
    "snooze_task",
    "cancel_task",
    "mark_task_waiting",
    "mark_task_uncertain",
    "confirm_suggestion",
    "dismiss_suggestion",
    "snooze_suggestion",
    "process_meeting",
    "process_latest_meeting",
    "start_meeting_recording",
    "finish_meeting_recording",
    "stop_meeting_recording",
    "join_meeting_bot",
    "sync_bot_session",
    "process_bot_session",
}


def parse_command(command: str) -> ParsedCommand:
    original = command.strip()
    text = normalize_command(original)
    if not text:
        return unsupported("Enter a command.")

    if re.fullmatch(r"(what can you do|help|show capabilities|list capabilities)", text):
        return supported("list_capabilities", {}, "Showing SpeedwagonAI capabilities.")

    if re.fullmatch(r"(status|system status|speedwagon status)", text):
        return supported("system_status", {}, "Showing SpeedwagonAI status.")

    if re.fullmatch(r"(bot status|meeting bot status)", text):
        return supported("bot_status", {}, "Showing meeting bot beta status.")

    if re.fullmatch(r"(show bot sessions|list bot sessions|show meeting bot sessions|list meeting bot sessions)", text):
        return supported("list_bot_sessions", {}, "Showing meeting bot sessions.")

    if re.fullmatch(r"(what is overdue|what's overdue|show overdue tasks|list overdue tasks|overdue)", text):
        return supported("list_overdue_tasks", {}, "Showing overdue tasks.")

    match = re.fullmatch(
        r"(?:what(?:'s| is)? due|show tasks due|show tasks|list tasks|what do i have(?: to do)?(?: due)?|what should i do) (before|by|on or before) (.+)",
        text,
    )
    if match:
        due_date = parse_date_phrase(match.group(2).strip())
        if due_date:
            inclusive = match.group(1) in {"by", "on or before"}
            label = "by" if inclusive else "before"
            return supported(
                "list_tasks_due_before",
                {"due_before": due_date, "inclusive": inclusive},
                f"Showing tasks due {label} {due_date}.",
            )

    if re.fullmatch(r"(what should i do today|show today'?s tasks|show tasks for today|today'?s tasks|today)", text):
        return supported("list_today_tasks", {}, "Showing tasks due today.")

    match = re.fullmatch(
        r"(?:what(?:'s| is)? due|show tasks due|show tasks for|what do i have(?: to do)?(?: on)?|what should i do on) (.+)",
        text,
    )
    if match:
        due_date = parse_date_phrase(match.group(1).strip())
        if due_date:
            return supported("list_today_tasks", {"date": due_date}, f"Showing tasks due {due_date}.")

    if re.fullmatch(r"(show open tasks|list open tasks|show tasks|list tasks|what tasks)", text):
        return supported("list_open_tasks", {}, "Showing open tasks.")

    if re.fullmatch(
        r"(?:what|which|show|list).*(?:tasks?|work).*(?:without|with no|that do not have|that don't have|missing).*(?:due dates?|deadlines?)",
        text,
    ) or re.fullmatch(r"(?:unscheduled tasks?|tasks? without due dates?|tasks? with no due dates?)", text):
        return supported("list_unscheduled_tasks", {}, "Showing open tasks without due dates.")

    if re.fullmatch(r"(daily brief|show daily brief|summarize today|what should i follow up on|what needs follow up|what needs my attention)", text):
        return supported("daily_brief", {}, "Showing your daily follow-through brief.")

    if re.fullmatch(r"(calendar status|google calendar status)", text):
        return supported("calendar_status", {}, "Showing Google Calendar status.")

    if re.fullmatch(r"(sync calendar|sync google calendar|refresh calendar|refresh google calendar)", text):
        return supported("sync_calendar", {}, "Syncing Google Calendar.")

    if re.fullmatch(r"(show upcoming meetings|show upcoming calendar|upcoming meetings|upcoming calendar events)", text):
        return supported("list_upcoming_calendar_events", {"limit": 10}, "Showing upcoming calendar events.")

    if re.fullmatch(r"(prep for my next meeting|prepare for my next meeting|next meeting prep|meeting prep)", text):
        return supported("prep_next_meeting", {}, "Preparing context for your next meeting.")

    if re.fullmatch(r"(what is on my calendar today|what's on my calendar today|show my calendar today|calendar today)", text):
        today = date.today().isoformat()
        return supported(
            "list_calendar_events",
            {"from": today, "to": today_next_day(today), "limit": 20},
            "Showing today's calendar events.",
        )

    if re.fullmatch(r"(show suggestions|list suggestions|what are your suggestions|suggestions)", text):
        return supported("list_suggestions", {}, "Showing follow-through suggestions.")

    match = re.fullmatch(r"(?:confirm|accept|run) suggestion (\d+)", text)
    if match:
        suggestion_id = int(match.group(1))
        return supported("confirm_suggestion", {"suggestion_id": suggestion_id}, f"Confirming suggestion {suggestion_id}.")

    match = re.fullmatch(r"(?:dismiss|ignore) suggestion (\d+)", text)
    if match:
        suggestion_id = int(match.group(1))
        return supported("dismiss_suggestion", {"suggestion_id": suggestion_id}, f"Dismissing suggestion {suggestion_id}.")

    match = re.fullmatch(r"snooze suggestion (\d+)(?: until (\d{4}-\d{2}-\d{2}))?", text)
    if match:
        suggestion_id = int(match.group(1))
        payload: dict[str, Any] = {"suggestion_id": suggestion_id}
        if match.group(2):
            payload["until"] = match.group(2)
        return supported("snooze_suggestion", payload, f"Snoozing suggestion {suggestion_id}.")

    if re.fullmatch(r"(what am i waiting on|show waiting tasks|list waiting tasks|waiting on others)", text):
        return supported("list_waiting_tasks", {}, "Showing work waiting on others.")

    match = re.fullmatch(r"(?:what do i owe|show commitments for|show work for) (.+)", text)
    if match:
        person = match.group(1).strip()
        if not person:
            return unsupported("Person is required.")
        return supported("list_commitments_for_person", {"person": person}, f"Showing commitments related to {person}.")

    if re.fullmatch(r"show unprocessed meetings", text):
        return supported("list_unprocessed_meetings", {}, "Showing unprocessed meetings.")

    if re.fullmatch(r"process latest meeting", text):
        return supported("process_latest_meeting", {}, "Processing the latest unprocessed meeting.")

    match = re.fullmatch(r"process meeting (\d+)", text)
    if match:
        meeting_id = int(match.group(1))
        return supported("process_meeting", {"meeting_id": meeting_id}, f"Processing meeting {meeting_id}.")

    match = re.fullmatch(r"sync bot session (\d+)", text)
    if match:
        session_id = int(match.group(1))
        return supported("sync_bot_session", {"session_id": session_id}, f"Syncing bot session {session_id}.")

    match = re.fullmatch(r"process bot session (\d+)", text)
    if match:
        session_id = int(match.group(1))
        return supported("process_bot_session", {"session_id": session_id}, f"Processing bot session {session_id}.")

    join_match = re.fullmatch(r"(?:send|join|add) (?:a )?(?:meeting )?bot (?:to|for) (?:meeting )?(.+)", original, re.IGNORECASE)
    if join_match:
        meeting_url = join_match.group(1).strip()
        return supported(
            "join_meeting_bot",
            {"meeting_url": meeting_url, "title": "Bot meeting", "consent_confirmed": True},
            "Sending the configured meeting bot to the meeting link.",
        )

    match = re.fullmatch(r"start meeting recording called (.+)", text)
    if match:
        title = match.group(1).strip()
        return supported("start_meeting_recording", {"title": title}, f"Starting meeting recording: {title}.")

    if re.fullmatch(r"(finish meeting|finish recording|stop and process meeting)", text):
        return supported("finish_meeting_recording", {}, "Finishing and processing the active meeting.")

    if re.fullmatch(r"stop meeting without processing", text):
        return supported("stop_meeting_recording", {}, "Stopping the active meeting without processing.")

    match = re.fullmatch(r"draft follow-?up for meeting (\d+)", text)
    if match:
        meeting_id = int(match.group(1))
        return supported(
            "draft_meeting_followup",
            {"meeting_id": meeting_id, "instruction": "Draft a concise, useful follow-up email."},
            f"Drafting a follow-up for meeting {meeting_id}.",
        )

    match = re.fullmatch(r"draft (?:an )?(?:email|follow-?up) (?:for|about) context (.+)", text)
    if match:
        query = match.group(1).strip()
        if not query:
            return unsupported("Context name is required.")
        return supported(
            "draft_email_from_context",
            {"query": query, "instruction": f"Draft a concise follow-up about {query}."},
            f"Drafting a follow-up from context: {query}.",
        )

    match = re.fullmatch(r"(?:complete|confirm) task (\d+)", text)
    if match:
        task_id = int(match.group(1))
        return supported("complete_task", {"task_id": task_id}, f"Completing task {task_id}.")

    match = re.fullmatch(r"reopen task (\d+)", text)
    if match:
        task_id = int(match.group(1))
        return supported("reopen_task", {"task_id": task_id}, f"Reopening task {task_id}.")

    match = re.fullmatch(r"snooze task (\d+)(?: until (\d{4}-\d{2}-\d{2}))?", text)
    if match:
        task_id = int(match.group(1))
        payload: dict[str, Any] = {"task_id": task_id}
        if match.group(2):
            payload["until"] = match.group(2)
        return supported("snooze_task", payload, f"Snoozing task {task_id}.")

    match = re.fullmatch(r"cancel task (\d+)", text)
    if match:
        task_id = int(match.group(1))
        return supported("cancel_task", {"task_id": task_id}, f"Canceling task {task_id}.")

    match = re.fullmatch(r"(?:mark )?task (\d+) waiting", text)
    if match:
        task_id = int(match.group(1))
        return supported("mark_task_waiting", {"task_id": task_id}, f"Marking task {task_id} as waiting.")

    match = re.fullmatch(r"(?:mark )?task (\d+) uncertain", text)
    if match:
        task_id = int(match.group(1))
        return supported("mark_task_uncertain", {"task_id": task_id}, f"Marking task {task_id} as uncertain.")

    match = re.fullmatch(r"add task (.+?)(?: due (\d{4}-\d{2}-\d{2}))?", text)
    if match:
        task_text = match.group(1).strip()
        due_date = match.group(2)
        if not task_text:
            return unsupported("Task text is required.")
        payload = {"text": task_text}
        if due_date:
            payload["due_date"] = due_date
        return supported("add_task", payload, f"Adding task: {task_text}.")

    match = re.fullmatch(r"(?:search|find) tasks? (?:for|about) (.+)", text)
    if match:
        query = match.group(1).strip()
        if not query:
            return unsupported("Task search query is required.")
        return supported("search_tasks", {"query": query}, f"Searching tasks for {query}.")

    match = re.fullmatch(r"(?:search|show|find) context graph (?:for|about) (.+)", text)
    if match:
        query = match.group(1).strip()
        if not query:
            return unsupported("Context graph query is required.")
        return supported("search_context_graph", {"query": query}, f"Searching the context graph for {query}.")

    match = re.fullmatch(r"(?:search|find) context (?:for|about) (.+)", text)
    if not match:
        match = re.fullmatch(r"what did i say about (.+)", text)
    if match:
        topic = match.group(1).strip()
        if not topic:
            return unsupported("Context topic is required.")
        return supported("search_context", {"topic": topic}, f"Searching context for {topic}.")

    return unsupported(
        "Unsupported command. Try: daily brief, what do I owe Alex, show overdue tasks, complete task 12, "
        "snooze task 12 until 2026-06-05, add task send notes due 2026-06-01, or search context for onboarding."
    )


def execute_command(settings: Settings, repo: Repository, command: str) -> dict[str, Any]:
    parsed = parse_command(command)
    if not parsed.supported:
        interpreted = interpret_command(
            settings,
            command,
            allowed_actions=set(CATEGORIES),
            categories=CATEGORIES,
            mutating_actions=MUTATING_ACTIONS,
        )
        if interpreted.get("supported"):
            return execute_interpreted_command(settings, repo, command, interpreted)
        return {
            **parsed.to_dict(),
            "command": command,
            "result": None,
            "explanation": interpreted.get("explanation") or parsed.summary,
            "safety_notes": interpreted.get("safety_notes") or [],
            "confidence": interpreted.get("confidence"),
            "source": interpreted.get("source") or "rules",
        }
    result = run_action(settings, repo, parsed.action or "", parsed.payload)
    return {
        **parsed.to_dict(),
        "command": command,
        "result": result,
        "summary": summarize_result(parsed, result),
    }


def execute_interpreted_command(settings: Settings, repo: Repository, command: str, interpreted: dict[str, Any]) -> dict[str, Any]:
    action = str(interpreted["action"])
    parsed = ParsedCommand(
        True,
        action=action,
        payload=interpreted.get("payload") or {},
        summary=str(interpreted.get("explanation") or f"Interpreted as {action}."),
        category=str(interpreted.get("category") or CATEGORIES.get(action, "system_status")),
        requires_confirmation=bool(interpreted.get("requires_confirmation")),
        confidence=interpreted.get("confidence"),
        explanation=str(interpreted.get("explanation") or ""),
        safety_notes=list(interpreted.get("safety_notes") or []),
        source=str(interpreted.get("source") or "llm"),
    )
    if parsed.requires_confirmation:
        pending = repo.create_pending_action(
            command=command,
            action=action,
            category=parsed.category,
            payload=parsed.payload,
            confidence=parsed.confidence,
            source=parsed.source,
            explanation=parsed.explanation,
            safety_notes=parsed.safety_notes,
        )
        return {
            **parsed.to_dict(),
            "command": command,
            "pending_action_id": pending["id"],
            "result": {"pending_action": pending},
            "summary": f"Ready to run {action}. Confirm pending action {pending['id']} to continue.",
        }
    result = run_action(settings, repo, action, parsed.payload)
    return {
        **parsed.to_dict(),
        "command": command,
        "result": result,
        "summary": summarize_result(parsed, result),
    }


def confirm_pending_action(settings: Settings, repo: Repository, action_id: int) -> dict[str, Any]:
    pending = repo.get_pending_action(action_id)
    if pending["status"] != "pending":
        return {
            "supported": False,
            "action": pending.get("action"),
            "category": pending.get("category"),
            "requires_confirmation": False,
            "payload": pending.get("payload") or {},
            "summary": f"Pending action {action_id} is already {pending['status']}.",
            "command": pending.get("command"),
            "result": {"pending_action": pending},
            "pending_action_id": action_id,
            "confidence": pending.get("confidence"),
            "explanation": pending.get("explanation") or "",
            "safety_notes": pending.get("safety_notes") or [],
            "source": pending.get("source") or "llm",
        }
    parsed = ParsedCommand(
        True,
        action=pending["action"],
        payload=pending.get("payload") or {},
        summary=pending.get("explanation") or f"Confirmed pending action {action_id}.",
        category=pending.get("category") or CATEGORIES.get(pending["action"], "system_status"),
        requires_confirmation=False,
        confidence=pending.get("confidence"),
        explanation=pending.get("explanation") or "",
        safety_notes=pending.get("safety_notes") or [],
        pending_action_id=action_id,
        source=pending.get("source") or "llm",
    )
    result = run_action(settings, repo, parsed.action or "", parsed.payload)
    updated = repo.update_pending_action_status(action_id, "confirmed")
    return {
        **parsed.to_dict(),
        "command": pending.get("command"),
        "result": {**result, "pending_action": updated},
        "summary": summarize_result(parsed, result),
    }


def cancel_pending_action(repo: Repository, action_id: int) -> dict[str, Any]:
    updated = repo.update_pending_action_status(action_id, "canceled")
    return {
        "supported": True,
        "action": updated.get("action"),
        "category": updated.get("category"),
        "requires_confirmation": False,
        "payload": updated.get("payload") or {},
        "summary": f"Canceled pending action {action_id}.",
        "command": updated.get("command"),
        "result": {"pending_action": updated},
        "pending_action_id": action_id,
        "confidence": updated.get("confidence"),
        "explanation": updated.get("explanation") or "",
        "safety_notes": updated.get("safety_notes") or [],
        "source": updated.get("source") or "llm",
    }


def summarize_result(parsed: ParsedCommand, result: dict[str, Any]) -> str:
    if parsed.action == "list_capabilities":
        return f"SpeedwagonAI can help with {len(result.get('capabilities', CAPABILITIES))} local action types."
    if parsed.action == "system_status":
        active = "active" if result.get("active_recording", {}).get("active") else "inactive"
        return f"Status: recording {active}, {result.get('unprocessed_meetings', 0)} unprocessed meetings."
    if parsed.action == "bot_status":
        state = result.get("status") or "unknown"
        return f"Meeting bot beta is {state}."
    if parsed.action == "list_bot_sessions":
        sessions = result.get("sessions", [])
        if not sessions:
            return "No meeting bot sessions yet."
        label = "session" if len(sessions) == 1 else "sessions"
        return f"Found {len(sessions)} meeting bot {label}."
    if parsed.action in {
        "list_overdue_tasks",
        "list_tasks_due_before",
        "list_today_tasks",
        "list_open_tasks",
        "list_unscheduled_tasks",
        "list_waiting_tasks",
        "list_commitments_for_person",
        "search_tasks",
    }:
        tasks = result.get("tasks", [])
        due_date = result.get("date")
        due_label = "today" if due_date in {None, date.today().isoformat()} else f"on {due_date}"
        if parsed.action == "list_tasks_due_before" or (parsed.action == "list_overdue_tasks" and result.get("due_before")):
            relation = "by" if result.get("inclusive") else "before"
            if not tasks:
                return f"No open tasks due {relation} {result.get('due_before') or result.get('date')}."
            label = "task" if len(tasks) == 1 else "tasks"
            return f"Found {len(tasks)} open {label} due {relation} {result.get('due_before') or result.get('date')}."
        if not tasks:
            if parsed.action == "list_overdue_tasks":
                return "No overdue tasks."
            if parsed.action == "list_today_tasks":
                return f"No tasks due {due_label}."
            if parsed.action == "list_unscheduled_tasks":
                return "No open tasks without due dates."
            if parsed.action == "list_waiting_tasks":
                return "No tasks are waiting on others."
            if parsed.action == "list_commitments_for_person":
                return f"No commitments found for {result.get('person') or 'that person'}."
            if parsed.action == "search_tasks":
                return f"No tasks found for {result.get('query') or 'that search'}."
            return "No open tasks."
        label = "task" if len(tasks) == 1 else "tasks"
        if parsed.action == "list_today_tasks":
            return f"Found {len(tasks)} {label} due {due_label}."
        if parsed.action == "list_unscheduled_tasks":
            return f"Found {len(tasks)} open {label} without due dates."
        if parsed.action == "search_tasks":
            return f"Found {len(tasks)} matching {label}."
        return f"Found {len(tasks)} {label}."
    if parsed.action == "daily_brief":
        counts = result.get("counts", {})
        return (
            f"Daily brief: {counts.get('overdue', 0)} overdue, "
            f"{counts.get('today', 0)} due today, {counts.get('waiting', 0)} waiting, "
            f"{counts.get('uncertain', 0)} uncertain."
        )
    if parsed.action == "calendar_status":
        return f"Google Calendar: {result.get('status')}."
    if parsed.action == "sync_calendar":
        return f"Synced {result.get('synced_count', 0)} calendar events."
    if parsed.action in {"list_calendar_events", "list_upcoming_calendar_events"}:
        events = result.get("events", [])
        if not events:
            return "No calendar events found."
        label = "event" if len(events) == 1 else "events"
        return f"Found {len(events)} calendar {label}."
    if parsed.action == "prep_next_meeting":
        event = result.get("event")
        if not event:
            return result.get("message") or "No upcoming meeting found."
        prep = result.get("prep") or {}
        return f"Prep for {event.get('title')}: {len(prep.get('tasks') or [])} related tasks, {len(prep.get('meetings') or [])} related meetings."
    if parsed.action == "list_suggestions":
        suggestions = result.get("suggestions", [])
        if not suggestions:
            return "No open follow-through suggestions."
        label = "suggestion" if len(suggestions) == 1 else "suggestions"
        return f"Found {len(suggestions)} open {label}."
    if parsed.action == "confirm_suggestion":
        suggestion = result.get("suggestion", {})
        return f"Accepted suggestion {suggestion.get('id')}: {suggestion.get('title')}"
    if parsed.action == "dismiss_suggestion":
        suggestion = result.get("suggestion", {})
        return f"Dismissed suggestion {suggestion.get('id')}: {suggestion.get('title')}"
    if parsed.action == "snooze_suggestion":
        suggestion = result.get("suggestion", {})
        return f"Snoozed suggestion {suggestion.get('id')}: {suggestion.get('title')}"
    if parsed.action == "list_unprocessed_meetings":
        meetings = result.get("meetings", [])
        if not meetings:
            return "No unprocessed meetings."
        label = "meeting" if len(meetings) == 1 else "meetings"
        return f"Found {len(meetings)} unprocessed {label}."
    if parsed.action in {"process_meeting", "process_latest_meeting"}:
        meeting = result.get("meeting")
        if not meeting:
            return result.get("message") or "No meeting processed."
        return f"Processed meeting {meeting.get('id')}: {meeting.get('title')}"
    if parsed.action == "join_meeting_bot":
        session = result.get("session", {})
        return f"Joined meeting bot session {session.get('id')} for meeting {session.get('meeting_id')}."
    if parsed.action == "sync_bot_session":
        session = result.get("session", {})
        if result.get("transcript_path"):
            return f"Synced bot session {session.get('id')}; transcript is ready."
        return f"Synced bot session {session.get('id')}; transcript is not ready yet."
    if parsed.action == "process_bot_session":
        meeting = result.get("meeting", {})
        return f"Processed bot meeting {meeting.get('id')}: {meeting.get('title')}"
    if parsed.action == "start_meeting_recording":
        return f"Recording meeting {result.get('meeting_id')}."
    if parsed.action == "finish_meeting_recording":
        meeting = result.get("meeting", {})
        return f"Finished and processed meeting {meeting.get('id')}: {meeting.get('title')}"
    if parsed.action == "stop_meeting_recording":
        return f"Stopped meeting {result.get('meeting_id')} without processing."
    if parsed.action == "complete_task":
        task = result.get("task", {})
        return f"Completed task {task.get('id')}: {task.get('text')}"
    if parsed.action == "reopen_task":
        task = result.get("task", {})
        return f"Reopened task {task.get('id')}: {task.get('text')}"
    if parsed.action == "snooze_task":
        task = result.get("task", {})
        return f"Snoozed task {task.get('id')}: {task.get('text')}"
    if parsed.action == "cancel_task":
        task = result.get("task", {})
        return f"Canceled task {task.get('id')}: {task.get('text')}"
    if parsed.action == "mark_task_waiting":
        task = result.get("task", {})
        return f"Marked waiting: {task.get('id')}: {task.get('text')}"
    if parsed.action == "mark_task_uncertain":
        task = result.get("task", {})
        return f"Marked uncertain: {task.get('id')}: {task.get('text')}"
    if parsed.action == "add_task":
        task = result.get("task", {})
        return f"Added task {task.get('id')}: {task.get('text')}"
    if parsed.action in {"draft_meeting_followup", "draft_followup"}:
        draft = result.get("draft", {})
        return f"Draft preview ready: {draft.get('subject')}"
    if parsed.action == "draft_email_from_context":
        draft = result.get("draft", {})
        context = result.get("context") or {}
        return f"Draft preview ready for {context.get('name') or 'that context'}: {draft.get('subject')}"
    if parsed.action == "search_context":
        topic = result.get("topic", "")
        return f"Found context for {topic}."
    if parsed.action == "search_context_graph":
        contexts = result.get("contexts", [])
        tasks = result.get("tasks", [])
        meetings = result.get("meetings", [])
        return f"Found {len(contexts)} contexts, {len(tasks)} tasks, and {len(meetings)} meetings."
    if parsed.action == "web_search":
        return result.get("message") or f"Web search request received for {result.get('query') or 'that topic'}."
    return parsed.summary


def normalize_command(command: str) -> str:
    return re.sub(r"\s+", " ", command.strip().lower())


def today_next_day(today_iso: str) -> str:
    return (date.fromisoformat(today_iso) + timedelta(days=1)).isoformat()


def unsupported(summary: str) -> ParsedCommand:
    return ParsedCommand(False, None, {}, summary)


def supported(action: str, payload: dict[str, Any], summary: str) -> ParsedCommand:
    return ParsedCommand(
        True,
        action,
        payload,
        summary,
        category=CATEGORIES.get(action, "system_status"),
        requires_confirmation=False,
    )
