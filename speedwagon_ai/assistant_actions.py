from __future__ import annotations

from datetime import date
from typing import Any

from speedwagon_ai.context import render_context
from speedwagon_ai.integrations.gmail import preview_followup_email
from speedwagon_ai.config import Settings
from speedwagon_ai.storage import Repository


def run_action(settings: Settings, repo: Repository, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    if action == "list_overdue_tasks":
        return {"tasks": repo.overdue_tasks()}
    if action == "list_today_tasks":
        today = date.today().isoformat()
        return {"tasks": [task for task in repo.list_tasks(status="open") if task.get("due_date") == today]}
    if action == "list_open_tasks":
        return {"tasks": repo.list_tasks(status="open")}
    if action == "add_task":
        return {
            "task": repo.create_task(
                str(payload.get("text") or ""),
                owner=payload.get("owner"),
                due_date=payload.get("due_date"),
            )
        }
    if action == "complete_task":
        return {"task": repo.complete_task(int(payload["task_id"]))}
    if action == "reopen_task":
        return {"task": repo.reopen_task(int(payload["task_id"]))}
    if action == "draft_followup":
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
    raise ValueError(f"Unknown assistant action: {action}")
