from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime, timedelta
from typing import Any

from speedwagon_ai.assistant_actions import CAPABILITIES, meeting_to_dict, run_action
from speedwagon_ai.assistant_brain import compose_assistant_reply, interpret_command
from speedwagon_ai.assistant_pipeline import execute_tool_assisted_turn
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
    "show_tasks_by_id": "tasks",
    "search_tasks": "tasks",
    "list_commitments_for_person": "commitments",
    "daily_brief": "brief",
    "calendar_status": "calendar",
    "sync_calendar": "calendar",
    "create_calendar_event": "calendar",
    "list_calendar_events": "calendar",
    "list_upcoming_calendar_events": "calendar",
    "search_calendar_events": "calendar",
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
    "decisions_about_context": "context",
    "everything_related": "context",
    "followup_targets": "brief",
    "context_changes": "context",
    "list_unprocessed_meetings": "meetings",
    "process_meeting": "meetings",
    "process_latest_meeting": "meetings",
    "start_meeting_recording": "capture",
    "finish_meeting_recording": "capture",
    "stop_meeting_recording": "capture",
    "draft_meeting_followup": "email",
    "draft_followup": "email",
    "draft_email_from_context": "email",
    "create_local_email_draft": "email",
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
    "draft_meeting_followup",
    "draft_followup",
    "draft_email_from_context",
    "create_local_email_draft",
    "join_meeting_bot",
    "sync_bot_session",
    "process_bot_session",
    "create_calendar_event",
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

    if re.fullmatch(r"(who should i follow up with|who needs follow up|who do i need to follow up with)", text):
        return supported("followup_targets", {}, "Showing people and work that look ready for follow-up.")

    if re.fullmatch(r"(calendar status|google calendar status)", text):
        return supported("calendar_status", {}, "Showing Google Calendar status.")

    if re.fullmatch(r"(sync calendar|sync google calendar|refresh calendar|refresh google calendar)", text):
        return supported("sync_calendar", {}, "Syncing Google Calendar.")

    calendar_create = parse_calendar_create_command(original)
    if calendar_create:
        return supported(
            "create_calendar_event",
            calendar_create,
            f"Ready to create Calendar event: {calendar_create['title']}.",
            requires_confirmation=True,
        )

    if re.fullmatch(r"(show upcoming meetings|show upcoming calendar|upcoming meetings|upcoming calendar events)", text):
        return supported("list_upcoming_calendar_events", {"limit": 10}, "Showing upcoming calendar events.")

    if re.fullmatch(r"(prep for my next meeting|prepare for my next meeting|next meeting prep|meeting prep)", text):
        return supported("prep_next_meeting", {}, "Preparing context for your next meeting.")

    match = re.fullmatch(
        r"(?:when(?:'s| is)?|what time is|find|show|list).*(?:meeting|calendar event|event).*(?:with|for|about) (.+)",
        text,
    )
    if match:
        query = strip_calendar_query_noise(match.group(1))
        if query:
            return supported(
                "search_calendar_events",
                {"query": query, "limit": 10},
                f"Searching calendar events for {query}.",
            )

    if re.fullmatch(r"(what is on my calendar today|what's on my calendar today|show my calendar today|calendar today)", text):
        today = date.today().isoformat()
        return supported(
            "list_calendar_events",
            {"from": today, "to": today_next_day(today), "limit": 20},
            "Showing today's calendar events.",
        )

    calendar_range = parse_calendar_range_command(original)
    if calendar_range:
        return supported(
            "list_calendar_events",
            calendar_range,
            f"Showing calendar events for the next {calendar_range['days']} days.",
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
            requires_confirmation=True,
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
            requires_confirmation=True,
        )

    email_match = re.fullmatch(
        r"(?:can you\s+)?(?:please\s+)?(?:send|write|draft)(?: an)? email to ([a-zA-Z0-9 ._@+-]+?) about (.+)",
        original,
        flags=re.IGNORECASE,
    )
    if email_match:
        recipient = email_match.group(1).strip()
        topic = email_match.group(2).strip()
        if recipient and topic:
            return supported(
                "draft_email_from_context",
                {
                    "query": recipient,
                    "recipient": recipient,
                    "subject": clean_email_subject(topic),
                    "instruction": f"Draft an email to {recipient} about {topic}. User request: {original.strip()}",
                },
                f"Ready to draft an email to {recipient}.",
                requires_confirmation=True,
            )
    email_match = re.fullmatch(
        r"(?:can you\s+)?(?:please\s+)?email ([a-zA-Z0-9 ._@+-]+?) about (.+)",
        original,
        flags=re.IGNORECASE,
    )
    if email_match:
        recipient = email_match.group(1).strip()
        topic = email_match.group(2).strip()
        if recipient and topic:
            return supported(
                "draft_email_from_context",
                {
                    "query": recipient,
                    "recipient": recipient,
                    "subject": clean_email_subject(topic),
                    "instruction": f"Draft an email to {recipient} about {topic}. User request: {original.strip()}",
                },
                f"Ready to draft an email to {recipient}.",
                requires_confirmation=True,
            )

    match = re.search(r"\b(?:complete|finish|confirm)(?: task)?\s*#?(\d+)\b", text)
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

    task_id_match = re.findall(r"\b(\d+)\b", text)
    if task_id_match and re.search(r"(?:show|get|display|find|list|give|what(?:'s| is| are))(?: me)? tasks?(?: number| #| id)?", text):
        task_ids = [int(x) for x in task_id_match]
        if task_ids:
            return supported("show_tasks_by_id", {"task_ids": task_ids}, f"Showing tasks {', '.join(str(x) for x in task_ids)}.")

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

    match = re.fullmatch(r"(?:what did (?:we|i) decide about|show decisions (?:for|about)) (.+)", text)
    if match:
        query = match.group(1).strip()
        if not query:
            return unsupported("Decision topic is required.")
        return supported("decisions_about_context", {"query": query}, f"Showing decisions about {query}.")

    match = re.fullmatch(r"(?:everything related to|show everything related to|what is related to|show related context for) (.+)", text)
    if match:
        query = match.group(1).strip()
        if not query:
            return unsupported("Context query is required.")
        return supported("everything_related", {"query": query}, f"Showing everything related to {query}.")

    match = re.fullmatch(r"(?:what changed on|what changed about|show changes (?:for|about)) (.+)", text)
    if match:
        query = match.group(1).strip()
        if not query:
            return unsupported("Context query is required.")
        return supported("context_changes", {"query": query}, f"Showing recent changes for {query}.")

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
        planned = execute_tool_assisted_turn(settings, repo, command, suggested_commands=suggested_commands)
        if planned:
            return planned
        interpreted = interpret_command(
            settings,
            command,
            allowed_actions=set(CATEGORIES),
            categories=CATEGORIES,
            mutating_actions=MUTATING_ACTIONS,
        )
        if interpreted.get("supported"):
            return execute_interpreted_command(settings, repo, command, interpreted)
        fallback = conversational_fallback(settings, repo, command, interpreted)
        if fallback:
            return fallback
        explanation = friendly_interpretation_explanation(interpreted.get("explanation") or parsed.summary)
        return {
            **parsed.to_dict(),
            "command": command,
            "result": {"suggested_commands": suggested_commands(command)},
            "summary": "I could not safely turn that into an app action yet.",
            "explanation": explanation,
            "safety_notes": interpreted.get("safety_notes") or [],
            "confidence": interpreted.get("confidence"),
            "source": interpreted.get("source") or "rules",
            "suggested_commands": suggested_commands(command),
        }
    if parsed.requires_confirmation:
        pending = repo.create_pending_action(
            command=command,
            action=parsed.action or "",
            category=parsed.category,
            payload=parsed.payload,
            confidence=parsed.confidence,
            source=parsed.source,
            explanation=parsed.summary,
            safety_notes=parsed.safety_notes,
        )
        return {
            **parsed.to_dict(),
            "command": command,
            "pending_action_id": pending["id"],
            "result": {"pending_action": pending},
            "summary": f"Ready to run {parsed.action}. Confirm pending action {pending['id']} to continue.",
        }
    result = run_action(settings, repo, parsed.action or "", parsed.payload)
    return {
        **parsed.to_dict(),
        "command": command,
        "result": result,
        "summary": summarize_result(parsed, result),
    }


def conversational_fallback(
    settings: Settings,
    repo: Repository,
    command: str,
    interpreted: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if likely_write_request(command):
        return None

    topic = suggested_graph_topic(command) or inferred_topic(command)
    suggestions = suggested_commands(command)
    brief = repo.daily_brief()
    result: dict[str, Any] = {
        "message": "Answered from local SpeedwagonAI data. No action was run.",
        "counts": brief.get("counts", {}),
        "suggested_commands": suggestions,
        "calendar_today": brief.get("calendar_today", []),
        "calendar_upcoming": brief.get("calendar_upcoming", [])[:10],
        "meeting_prep": brief.get("meeting_prep", [])[:5],
    }

    if topic:
        graph = repo.context_graph(topic, limit=12)
        context = repo.context_for_topic(topic, limit=8)
        tasks = graph.get("tasks", [])[:8]
        meetings = graph.get("meetings", [])[:6]
        decisions = context.get("decisions", [])[:6]
        relationships = graph.get("relationships", [])[:8]
        result.update(
            {
                "query": topic,
                "contexts": graph.get("contexts", [])[:12],
                "relationships": relationships,
                "tasks": tasks,
                "meetings": meetings,
                "decisions": decisions,
                "suggestions": graph.get("suggestions", [])[:8],
            }
        )
        summary = local_topic_summary(topic, tasks, meetings, decisions, relationships)
    else:
        tasks = [
            *brief.get("overdue", [])[:4],
            *brief.get("today", [])[:4],
            *brief.get("waiting", [])[:4],
            *brief.get("uncertain", [])[:4],
            *brief.get("unscheduled", [])[:4],
        ]
        meetings = [meeting_to_dict(meeting) for meeting in repo.list_meetings(limit=5)]
        result.update(
            {
                "tasks": dedupe_items_by_id(tasks)[:10],
                "meetings": meetings,
                "suggestions": repo.list_suggestions(status="open", limit=6),
                "followup_drafts": repo.list_followup_drafts(status=None, limit=5),
            }
        )
        counts = brief.get("counts", {})
        summary = (
            "Here is the current local picture: "
            f"{counts.get('overdue', 0)} overdue, {counts.get('today', 0)} due today, "
            f"{counts.get('waiting', 0)} waiting, {counts.get('uncertain', 0)} uncertain, "
            f"and {counts.get('unscheduled', 0)} unscheduled."
        )

    snapshot = assistant_snapshot(result)
    if ai_summary := compose_assistant_reply(settings, command, snapshot):
        summary = ai_summary
        result["message"] = ai_summary
        source = "llm_local_snapshot"
        confidence = 0.72
        safety_notes = ["Answered from the local SpeedwagonAI snapshot. No writes or external sends were performed."]
    else:
        source = "local_chat_fallback"
        confidence = 0.45
        safety_notes = ["Read-only fallback. No writes or external sends were performed."]

    explanation = "This is a read-only local assistant answer because the request did not map to a specific action."
    if interpreted and interpreted.get("explanation") and not settings.openai_api_key:
        explanation = f"{explanation} Configure OPENAI_API_KEY to let the assistant interpret more write requests."
    return {
        "supported": True,
        "action": "answer_question",
        "category": "assistant",
        "payload": {"query": command},
        "summary": summary,
        "command": command,
        "result": json_safe(result),
        "requires_confirmation": False,
        "confidence": confidence,
        "explanation": explanation,
        "safety_notes": safety_notes,
        "source": source,
        "suggested_commands": suggestions,
    }


def execute_interpreted_command(settings: Settings, repo: Repository, command: str, interpreted: dict[str, Any]) -> dict[str, Any]:
    action = str(interpreted["action"])
    payload = interpreted.get("payload") or {}
    if action == "create_calendar_event":
        payload = normalize_calendar_event_payload(command, payload)
    parsed = ParsedCommand(
        True,
        action=action,
        payload=payload,
        summary=str(interpreted.get("explanation") or f"Interpreted as {action}."),
        category=str(interpreted.get("category") or CATEGORIES.get(action, "system_status")),
        requires_confirmation=action in MUTATING_ACTIONS or bool(interpreted.get("requires_confirmation")),
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
    summary = summarize_result(parsed, result)

    # For LLM-interpreted read-only questions, refine the summary with the AI
    # so answers like "when is my meeting with X?" get a direct answer.
    if (
        parsed.source == "llm"
        and action not in MUTATING_ACTIONS
        and _is_question(command)
    ):
        snapshot = {"question": command, "action": action, "action_result": json_safe(result)}
        refined = compose_assistant_reply(settings, command, snapshot)
        if refined:
            summary = refined

    return {
        **parsed.to_dict(),
        "command": command,
        "result": result,
        "summary": summary,
    }


def _is_question(command: str) -> bool:
    text = command.strip().lower()
    return (
        text.endswith("?")
        or text.startswith(("when ", "where ", "what ", "who ", "is there ", "do i ", "does ", "how ", "which "))
    )


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
    if parsed.action == "show_tasks_by_id":
        tasks = result.get("tasks", [])
        task_ids = result.get("task_ids", [])
        if not tasks:
            return f"No tasks found with IDs {', '.join(str(x) for x in task_ids)}."
        label = "task" if len(tasks) == 1 else "tasks"
        return f"Found {len(tasks)} {label}."
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
        explicit_date = parsed.action == "list_today_tasks" and bool(parsed.payload.get("date"))
        due_label = (
            f"on {due_date}"
            if explicit_date and due_date
            else "today" if due_date in {None, date.today().isoformat()} else f"on {due_date}"
        )
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
    if parsed.action == "followup_targets":
        suggestions = result.get("suggestions", [])
        tasks = result.get("tasks", [])
        if not suggestions and not tasks:
            return "No follow-up targets found right now."
        return f"Found {len(suggestions)} follow-up suggestions and {len(tasks)} related tasks."
    if parsed.action == "calendar_status":
        return f"Google Calendar: {result.get('status')}."
    if parsed.action == "sync_calendar":
        removed = int(result.get("removed_count") or 0)
        if removed:
            return f"Synced {result.get('synced_count', 0)} calendar events and removed {removed} deleted event(s)."
        return f"Synced {result.get('synced_count', 0)} calendar events."
    if parsed.action == "create_calendar_event":
        event = result.get("event", {})
        return f"Created Calendar event {event.get('id')}: {event.get('title')}"
    if parsed.action in {"list_calendar_events", "list_upcoming_calendar_events", "search_calendar_events"}:
        events = result.get("events", [])
        if not events:
            return "No calendar events found."
        if parsed.action == "search_calendar_events" and len(events) == 1:
            event = events[0]
            return f"{event.get('title') or 'That calendar event'} is scheduled for {format_calendar_event_time(event)}."
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
        draft = result.get("followup_draft") or result.get("draft", {})
        context = result.get("context") or {}
        if result.get("created"):
            return f"Created local draft {draft.get('id')}: {draft.get('subject')}"
        return f"Draft ready for {context.get('name') or 'that context'}: {draft.get('subject')}"
    if parsed.action == "create_local_email_draft":
        draft = result.get("followup_draft") or result.get("draft", {})
        return f"Created local draft {draft.get('id')}: {draft.get('subject')}"
    if parsed.action == "search_context":
        topic = result.get("topic", "")
        return f"Found context for {topic}."
    if parsed.action in {"search_context_graph", "everything_related"}:
        contexts = result.get("contexts", [])
        tasks = result.get("tasks", [])
        meetings = result.get("meetings", [])
        return f"Found {len(contexts)} contexts, {len(tasks)} tasks, and {len(meetings)} meetings."
    if parsed.action == "decisions_about_context":
        decisions = result.get("decisions", [])
        contexts = result.get("contexts", [])
        return f"Found {len(decisions)} decisions and {len(contexts)} related contexts."
    if parsed.action == "context_changes":
        meetings = result.get("meetings", [])
        tasks = result.get("tasks", [])
        decisions = result.get("decisions", [])
        return f"Found {len(meetings)} meetings, {len(tasks)} tasks, and {len(decisions)} decisions for recent context."
    if parsed.action == "web_search":
        return result.get("message") or f"Web search request received for {result.get('query') or 'that topic'}."
    return parsed.summary


def parse_calendar_range_command(command: str) -> dict[str, Any] | None:
    text = normalize_command(command)
    if "calendar" not in text and "schedule" not in text:
        return None
    patterns = [
        r"(?:what(?:'s| is)?|show|list|give me|tell me).*(?:calendar|schedule).*(?:next|coming) (\d{1,2}) days?",
        r"(?:calendar|schedule).*(?:next|coming) (\d{1,2}) days?",
    ]
    for pattern in patterns:
        match = re.fullmatch(pattern, text)
        if not match:
            continue
        days = max(1, min(31, int(match.group(1))))
        start = date.today()
        end = start + timedelta(days=days)
        return {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "limit": min(max(days * 8, 20), 120),
            "days": days,
        }
    if re.fullmatch(r"(?:what(?:'s| is)?|show|list|give me|tell me).*(?:calendar|schedule).*(?:next|coming) week", text):
        start = date.today()
        end = start + timedelta(days=7)
        return {"from": start.isoformat(), "to": end.isoformat(), "limit": 80, "days": 7}
    return None


def parse_calendar_create_command(command: str) -> dict[str, Any] | None:
    cleaned = re.sub(r"\s+", " ", command.strip()).strip()
    patterns = [
        r"(?:please\s+)?(?:create|add|schedule)(?: a| an)?(?: google)? calendar event (?:for|on) (?P<date>.+?) at (?P<time>.+?) (?:to|called|titled|for) (?P<title>.+)",
        r"(?:please\s+)?(?:create|add|schedule)(?: a| an)?(?: google)? calendar event (?:called|titled|for) (?P<title>.+?) (?:on|for) (?P<date>.+?) at (?P<time>.+)",
    ]
    for pattern in patterns:
        match = re.fullmatch(pattern, cleaned, flags=re.IGNORECASE)
        if not match:
            continue
        date_iso = parse_date_phrase(match.group("date").strip())
        parsed_time = parse_time_phrase(match.group("time").strip())
        title = clean_calendar_title(match.group("title"))
        if not date_iso or not parsed_time or not title:
            return None
        start = datetime.fromisoformat(f"{date_iso}T{parsed_time}:00")
        end = start + timedelta(minutes=30)
        offset = local_timezone_offset()
        return {
            "title": title,
            "start_at": start.strftime(f"%Y-%m-%dT%H:%M:%S{offset}"),
            "end_at": end.strftime(f"%Y-%m-%dT%H:%M:%S{offset}"),
            "calendar_id": "primary",
            "send_updates": "none",
            "description": f"Created from assistant command: {command.strip()}",
        }
    return None


def parse_time_phrase(value: str) -> str | None:
    text = value.strip().lower().rstrip(".,!?")
    text = re.sub(r"\s+", "", text)
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?(am|pm)?", text)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or "0")
    suffix = match.group(3)
    if minute > 59:
        return None
    if suffix:
        if hour < 1 or hour > 12:
            return None
        if suffix == "pm" and hour != 12:
            hour += 12
        if suffix == "am" and hour == 12:
            hour = 0
    elif hour > 23:
        return None
    return f"{hour:02d}:{minute:02d}"


def clean_calendar_title(value: str) -> str:
    title = value.strip().strip(".,!?")
    title = re.sub(r"^(?:a|an|the)\s+", "", title, flags=re.IGNORECASE)
    if title.lower().startswith("wish "):
        title = title[0].upper() + title[1:]
    return title[:140]


def clean_email_subject(value: str) -> str:
    subject = re.split(r"\b(?:and remind|and tell|and ask|please remind)\b", value.strip(), maxsplit=1, flags=re.IGNORECASE)[0]
    subject = subject.strip(" .,!?:;")
    if not subject:
        subject = value.strip(" .,!?:;")
    return subject[:110] or "Follow-up"


def strip_calendar_query_noise(value: str) -> str:
    cleaned = re.sub(r"[?!.,]", " ", value).strip()
    cleaned = re.sub(r"\b(?:professor|prof)\b\.?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:meeting|calendar|event|call)\b", "", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip()


def normalize_calendar_event_payload(command: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    explicit_year = bool(re.search(r"\b(?:19|20)\d{2}\b", command))
    explicit_timezone = command_mentions_timezone(command)
    offset = local_timezone_offset()
    for key in ("start_at", "end_at"):
        value = normalized.get(key)
        if not isinstance(value, str):
            continue
        adjusted = normalize_calendar_datetime_value(
            value,
            explicit_year=explicit_year,
            explicit_timezone=explicit_timezone,
            offset=offset,
        )
        if adjusted:
            normalized[key] = adjusted
    if not explicit_timezone:
        normalized.pop("timezone", None)
    return normalized


def normalize_calendar_datetime_value(
    value: str,
    *,
    explicit_year: bool,
    explicit_timezone: bool,
    offset: str,
) -> str | None:
    match = re.fullmatch(
        r"(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})[T ](?P<time>\d{2}:\d{2}(?::\d{2})?)(?:\.\d+)?(?P<zone>Z|[+-]\d{2}:?\d{2})?",
        value.strip(),
    )
    if not match:
        return None
    year = int(match.group("year"))
    month = int(match.group("month"))
    day = int(match.group("day"))
    if not explicit_year:
        today = date.today()
        try:
            candidate = date(today.year, month, day)
        except ValueError:
            return None
        year = today.year + (1 if candidate < today else 0)
    time_value = match.group("time")
    if len(time_value) == 5:
        time_value = f"{time_value}:00"
    zone = match.group("zone")
    if explicit_timezone and zone:
        if zone != "Z" and re.fullmatch(r"[+-]\d{4}", zone):
            zone = f"{zone[:3]}:{zone[3:]}"
        return f"{year:04d}-{month:02d}-{day:02d}T{time_value}{zone}"
    return f"{year:04d}-{month:02d}-{day:02d}T{time_value}{offset}"


def command_mentions_timezone(command: str) -> bool:
    text = command.lower()
    return bool(
        re.search(r"\b(?:utc|gmt|pst|pdt|est|edt|cst|cdt|mst|mdt|timezone|time zone)\b", text)
        or re.search(r"\b[+-]\d{2}:?\d{2}\b", text)
    )


def format_calendar_event_time(event: dict[str, Any]) -> str:
    start = str(event.get("start_at") or "").replace("T", " ")
    end = str(event.get("end_at") or "")
    if len(start) >= 16 and len(end) >= 16 and start[:10] == end[:10]:
        return f"{start[:16]} to {end[11:16]}"
    return start[:16] if len(start) >= 16 else start


def local_timezone_offset() -> str:
    offset = datetime.now().astimezone().strftime("%z")
    if not offset:
        return "Z"
    return f"{offset[:3]}:{offset[3:]}"


def normalize_command(command: str) -> str:
    return re.sub(r"\s+", " ", command.strip().lower())


def today_next_day(today_iso: str) -> str:
    return (date.fromisoformat(today_iso) + timedelta(days=1)).isoformat()


def unsupported(summary: str) -> ParsedCommand:
    return ParsedCommand(False, None, {}, summary)


def supported(
    action: str,
    payload: dict[str, Any],
    summary: str,
    *,
    requires_confirmation: bool = False,
) -> ParsedCommand:
    return ParsedCommand(
        True,
        action,
        payload,
        summary,
        category=CATEGORIES.get(action, "system_status"),
        requires_confirmation=requires_confirmation,
    )


def likely_write_request(command: str) -> bool:
    text = normalize_command(command)
    write_verbs = {
        "add",
        "book",
        "cancel",
        "change",
        "complete",
        "create",
        "delete",
        "dismiss",
        "draft",
        "handle",
        "invite",
        "join",
        "mark",
        "move",
        "process",
        "record",
        "remember",
        "remove",
        "reschedule",
        "schedule",
        "send",
        "snooze",
        "start",
        "stop",
        "sync",
        "update",
        "write",
    }
    words = set(re.findall(r"[a-z0-9-]+", text))
    return bool(words & write_verbs)


def friendly_interpretation_explanation(explanation: str) -> str:
    text = str(explanation or "").strip()
    if not text:
        return "Try asking a more specific question or use one of the suggested app actions."
    lowered = text.lower()
    if "openai" in lowered or "http" in lowered or "model parameter" in lowered or "traceback" in lowered:
        return "The AI action interpreter could not run cleanly, so SpeedwagonAI did not make any changes. Try a standard action chip or a more specific request."
    if "not configured" in lowered:
        return text
    if text.startswith("Unsupported command"):
        return "Try asking a broader question, or use one of the suggested app actions."
    return text


def inferred_topic(command: str) -> str | None:
    cleaned = re.sub(r"[?!.,]", " ", command).strip()
    lowered = normalize_command(cleaned)
    patterns = [
        r"(?:about|with|for|on|regarding|related to) ([a-zA-Z0-9 _-]{2,})$",
        r"(?:summarize|explain|tell me about|what happened with|what is going on with) ([a-zA-Z0-9 _-]{2,})$",
    ]
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            topic = strip_topic_noise(match.group(1))
            if topic:
                return topic
    words = [
        word
        for word in re.findall(r"[a-zA-Z0-9_-]+", cleaned)
        if word.lower()
        not in {
            "a",
            "about",
            "all",
            "and",
            "are",
            "can",
            "did",
            "for",
            "going",
            "happened",
            "is",
            "me",
            "my",
            "of",
            "on",
            "our",
            "please",
            "show",
            "summarize",
            "tell",
            "the",
            "this",
            "to",
            "was",
            "what",
            "with",
            "work",
            "you",
        }
    ]
    if words:
        return strip_topic_noise(" ".join(words[-2:]))
    return None


def strip_topic_noise(topic: str) -> str | None:
    cleaned = re.sub(r"\b(decisions?|tasks?|meetings?|projects?|people|person|stuff|things?)\b", " ", topic, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -_")
    return cleaned or None


def local_topic_summary(
    topic: str,
    tasks: list[dict[str, Any]],
    meetings: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
) -> str:
    pieces = []
    if decisions:
        pieces.append(f"{len(decisions)} decision{'s' if len(decisions) != 1 else ''}")
    if tasks:
        pieces.append(f"{len(tasks)} task{'s' if len(tasks) != 1 else ''}")
    if meetings:
        pieces.append(f"{len(meetings)} meeting{'s' if len(meetings) != 1 else ''}")
    if relationships:
        pieces.append(f"{len(relationships)} relationship{'s' if len(relationships) != 1 else ''}")
    if not pieces:
        return f"I did not find much local context for {topic}. Try a narrower person, project, or meeting topic."
    return f"Here is what I found for {topic}: " + ", ".join(pieces) + "."


def dedupe_items_by_id(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[Any] = set()
    output: list[dict[str, Any]] = []
    for item in items:
        item_id = item.get("id")
        if item_id in seen:
            continue
        seen.add(item_id)
        output.append(item)
    return output


def json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    try:
        return json.loads(json.dumps(value, default=str))
    except (TypeError, ValueError):
        return {}


def assistant_snapshot(result: dict[str, Any]) -> dict[str, Any]:
    safe = json_safe(result)
    if not isinstance(safe, dict):
        return {}
    return {
        "counts": safe.get("counts", {}),
        "tasks": safe.get("tasks", [])[:12],
        "calendar_today": safe.get("calendar_today", [])[:12],
        "calendar_upcoming": safe.get("calendar_upcoming", [])[:12],
        "meeting_prep": safe.get("meeting_prep", [])[:5],
        "meetings": safe.get("meetings", [])[:8],
        "decisions": safe.get("decisions", [])[:8],
        "relationships": safe.get("relationships", [])[:8],
        "contexts": safe.get("contexts", [])[:8],
        "suggestions": safe.get("suggestions", [])[:8],
        "followup_drafts": safe.get("followup_drafts", [])[:5],
        "suggested_commands": safe.get("suggested_commands", [])[:5],
        "query": safe.get("query"),
    }


def suggested_commands(command: str) -> list[str]:
    text = normalize_command(command)
    topic = suggested_graph_topic(command)
    graph_cues = {"people", "person", "project", "projects", "decision", "decisions", "follow", "followup", "follow-up", "related", "changed", "change"}
    if topic and graph_cues & set(re.findall(r"[a-z0-9-]+", text)):
        dynamic = [
            f"everything related to {topic}",
            f"what did we decide about {topic}",
            f"what changed on {topic}",
            "who should I follow up with",
        ]
        return dedupe_suggestions(dynamic)[:3]
    options = [
        "daily brief",
        "who should I follow up with",
        "what did we decide about onboarding",
        "everything related to Alex",
        "what changed on DairyMGT",
        "show overdue tasks",
        "show tasks due by June 7 2026",
        "search context graph for onboarding",
        "show suggestions",
        "what can you do",
    ]
    scored: list[tuple[int, str]] = []
    words = {word for word in re.findall(r"[a-z0-9]+", text) if len(word) > 2}
    for option in options:
        option_words = {word for word in re.findall(r"[a-z0-9]+", option.lower()) if len(word) > 2}
        overlap = len(words & option_words)
        if overlap:
            scored.append((overlap, option))
    if not scored:
        return options[:3]
    scored.sort(key=lambda item: (-item[0], options.index(item[1])))
    return [option for _, option in scored[:3]]


def suggested_graph_topic(command: str) -> str | None:
    cleaned = re.sub(r"[?!.,]", " ", command).strip()
    capitalized = [
        token
        for token in re.findall(r"\b[A-Z][A-Za-z0-9_-]+\b", cleaned)
        if token.lower() not in {"i", "what", "who", "show", "please"}
    ]
    if capitalized:
        return capitalized[-1]
    words = [
        word
        for word in re.findall(r"[a-zA-Z0-9_-]+", cleaned)
        if word.lower()
        not in {
            "what",
            "who",
            "when",
            "where",
            "why",
            "how",
            "did",
            "we",
            "with",
            "about",
            "for",
            "the",
            "and",
            "all",
            "everything",
            "related",
            "decision",
            "decisions",
            "changed",
            "change",
            "happened",
            "follow",
            "followup",
            "up",
            "project",
            "person",
            "people",
            "please",
        }
    ]
    return words[-1] if words else None


def dedupe_suggestions(commands: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for command in commands:
        normalized = command.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        output.append(command)
    return output
