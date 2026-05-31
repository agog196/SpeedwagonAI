from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from speedwagon_ai.assistant_actions import run_action
from speedwagon_ai.config import Settings
from speedwagon_ai.storage import Repository


@dataclass(frozen=True)
class ParsedCommand:
    supported: bool
    action: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_command(command: str) -> ParsedCommand:
    original = command.strip()
    text = normalize_command(original)
    if not text:
        return unsupported("Enter a command.")

    if re.fullmatch(r"(what is overdue|what's overdue|show overdue tasks|list overdue tasks|overdue)", text):
        return ParsedCommand(True, "list_overdue_tasks", {}, "Showing overdue tasks.")

    if re.fullmatch(r"(what should i do today|show today'?s tasks|show tasks for today|today'?s tasks|today)", text):
        return ParsedCommand(True, "list_today_tasks", {}, "Showing tasks due today.")

    if re.fullmatch(r"(show open tasks|list open tasks|show tasks|list tasks|what tasks)", text):
        return ParsedCommand(True, "list_open_tasks", {}, "Showing open tasks.")

    match = re.fullmatch(r"complete task (\d+)", text)
    if match:
        task_id = int(match.group(1))
        return ParsedCommand(True, "complete_task", {"task_id": task_id}, f"Completing task {task_id}.")

    match = re.fullmatch(r"reopen task (\d+)", text)
    if match:
        task_id = int(match.group(1))
        return ParsedCommand(True, "reopen_task", {"task_id": task_id}, f"Reopening task {task_id}.")

    match = re.fullmatch(r"add task (.+?)(?: due (\d{4}-\d{2}-\d{2}))?", text)
    if match:
        task_text = match.group(1).strip()
        due_date = match.group(2)
        if not task_text:
            return unsupported("Task text is required.")
        payload = {"text": task_text}
        if due_date:
            payload["due_date"] = due_date
        return ParsedCommand(True, "add_task", payload, f"Adding task: {task_text}.")

    match = re.fullmatch(r"(?:search|find) context (?:for|about) (.+)", text)
    if match:
        topic = match.group(1).strip()
        if not topic:
            return unsupported("Context topic is required.")
        return ParsedCommand(True, "search_context", {"topic": topic}, f"Searching context for {topic}.")

    return unsupported(
        "Unsupported command. Try: show overdue tasks, what should I do today, complete task 12, "
        "add task send notes due 2026-06-01, or search context for onboarding."
    )


def execute_command(settings: Settings, repo: Repository, command: str) -> dict[str, Any]:
    parsed = parse_command(command)
    if not parsed.supported:
        return {
            **parsed.to_dict(),
            "command": command,
            "result": None,
        }
    result = run_action(settings, repo, parsed.action or "", parsed.payload)
    return {
        **parsed.to_dict(),
        "command": command,
        "result": result,
        "summary": summarize_result(parsed, result),
    }


def summarize_result(parsed: ParsedCommand, result: dict[str, Any]) -> str:
    if parsed.action in {"list_overdue_tasks", "list_today_tasks", "list_open_tasks"}:
        tasks = result.get("tasks", [])
        if not tasks:
            if parsed.action == "list_overdue_tasks":
                return "No overdue tasks."
            if parsed.action == "list_today_tasks":
                return "No tasks due today."
            return "No open tasks."
        label = "task" if len(tasks) == 1 else "tasks"
        return f"Found {len(tasks)} {label}."
    if parsed.action == "complete_task":
        task = result.get("task", {})
        return f"Completed task {task.get('id')}: {task.get('text')}"
    if parsed.action == "reopen_task":
        task = result.get("task", {})
        return f"Reopened task {task.get('id')}: {task.get('text')}"
    if parsed.action == "add_task":
        task = result.get("task", {})
        return f"Added task {task.get('id')}: {task.get('text')}"
    if parsed.action == "search_context":
        topic = result.get("topic", "")
        return f"Found context for {topic}."
    return parsed.summary


def normalize_command(command: str) -> str:
    return re.sub(r"\s+", " ", command.strip().lower())


def unsupported(summary: str) -> ParsedCommand:
    return ParsedCommand(False, None, {}, summary)
