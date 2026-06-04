from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from speedwagon_ai.assistant_actions import CAPABILITIES, run_action
from speedwagon_ai.assistant_brain import interpret_command
from speedwagon_ai.config import Settings
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
    "list_overdue_tasks": "tasks",
    "list_today_tasks": "tasks",
    "list_open_tasks": "tasks",
    "list_unscheduled_tasks": "tasks",
    "list_waiting_tasks": "commitments",
    "list_commitments_for_person": "commitments",
    "daily_brief": "brief",
    "add_task": "tasks",
    "complete_task": "tasks",
    "reopen_task": "tasks",
    "snooze_task": "tasks",
    "cancel_task": "tasks",
    "mark_task_waiting": "commitments",
    "mark_task_uncertain": "commitments",
    "search_context": "context",
    "list_unprocessed_meetings": "meetings",
    "process_meeting": "meetings",
    "process_latest_meeting": "meetings",
    "start_meeting_recording": "capture",
    "finish_meeting_recording": "capture",
    "stop_meeting_recording": "capture",
    "draft_meeting_followup": "email",
    "draft_followup": "email",
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
    "process_meeting",
    "process_latest_meeting",
    "start_meeting_recording",
    "finish_meeting_recording",
    "stop_meeting_recording",
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

    if re.fullmatch(r"(what is overdue|what's overdue|show overdue tasks|list overdue tasks|overdue)", text):
        return supported("list_overdue_tasks", {}, "Showing overdue tasks.")

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
    if parsed.action in {
        "list_overdue_tasks",
        "list_today_tasks",
        "list_open_tasks",
        "list_unscheduled_tasks",
        "list_waiting_tasks",
        "list_commitments_for_person",
    }:
        tasks = result.get("tasks", [])
        due_date = result.get("date")
        due_label = "today" if due_date in {None, date.today().isoformat()} else f"on {due_date}"
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
            return "No open tasks."
        label = "task" if len(tasks) == 1 else "tasks"
        if parsed.action == "list_today_tasks":
            return f"Found {len(tasks)} {label} due {due_label}."
        if parsed.action == "list_unscheduled_tasks":
            return f"Found {len(tasks)} open {label} without due dates."
        return f"Found {len(tasks)} {label}."
    if parsed.action == "daily_brief":
        counts = result.get("counts", {})
        return (
            f"Daily brief: {counts.get('overdue', 0)} overdue, "
            f"{counts.get('today', 0)} due today, {counts.get('waiting', 0)} waiting, "
            f"{counts.get('uncertain', 0)} uncertain."
        )
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
    if parsed.action == "search_context":
        topic = result.get("topic", "")
        return f"Found context for {topic}."
    if parsed.action == "web_search":
        return result.get("message") or f"Web search request received for {result.get('query') or 'that topic'}."
    return parsed.summary


def normalize_command(command: str) -> str:
    return re.sub(r"\s+", " ", command.strip().lower())


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


def parse_date_phrase(value: str) -> str | None:
    text = value.strip().lower()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    if text == "today":
        return date.today().isoformat()
    if text == "tomorrow":
        return date.fromordinal(date.today().toordinal() + 1).isoformat()
    match = re.fullmatch(
        r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?",
        text,
    )
    if not match:
        return None
    months = {
        "jan": 1,
        "january": 1,
        "feb": 2,
        "february": 2,
        "mar": 3,
        "march": 3,
        "apr": 4,
        "april": 4,
        "may": 5,
        "jun": 6,
        "june": 6,
        "jul": 7,
        "july": 7,
        "aug": 8,
        "august": 8,
        "sep": 9,
        "september": 9,
        "oct": 10,
        "october": 10,
        "nov": 11,
        "november": 11,
        "dec": 12,
        "december": 12,
    }
    month = months[match.group(1)]
    day = int(match.group(2))
    year = int(match.group(3) or date.today().year)
    try:
        parsed = date(year, month, day)
    except ValueError:
        return None
    return parsed.isoformat()
