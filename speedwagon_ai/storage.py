from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from speedwagon_ai.models import ExtractedItem, ExtractionResult, Meeting
from speedwagon_ai.timeutil import utc_now_iso


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meetings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    audio_path TEXT,
    transcript_path TEXT,
    note_path TEXT,
    summary TEXT,
    source_type TEXT NOT NULL DEFAULT 'local_recording',
    raw_extraction_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS action_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    owner TEXT,
    deadline TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS commitments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    owner TEXT,
    deadline TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS open_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS key_topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    topic TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS email_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    provider_draft_id TEXT,
    recipient TEXT,
    subject TEXT NOT NULL,
    instruction TEXT,
    tone TEXT,
    included_items_json TEXT,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    owner TEXT,
    owed_to TEXT,
    project TEXT,
    due_date TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    source TEXT NOT NULL DEFAULT 'manual',
    source_type TEXT NOT NULL DEFAULT 'manual',
    source_table TEXT,
    source_id INTEGER,
    source_meeting_id INTEGER REFERENCES meetings(id) ON DELETE SET NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    reminder_suggestion TEXT,
    snoozed_until TEXT,
    last_followed_up_at TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
    channel TEXT NOT NULL DEFAULT 'local',
    remind_at TEXT,
    status TEXT NOT NULL DEFAULT 'suggested',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assistant_pending_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    command TEXT NOT NULL,
    action TEXT NOT NULL,
    category TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    confidence REAL,
    source TEXT NOT NULL DEFAULT 'llm',
    explanation TEXT,
    safety_notes_json TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT
);

CREATE TABLE IF NOT EXISTS contexts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL DEFAULT 'topic',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS context_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    context_id INTEGER NOT NULL REFERENCES contexts(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,
    source_table TEXT,
    source_id INTEGER,
    task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
    meeting_id INTEGER REFERENCES meetings(id) ON DELETE CASCADE,
    confidence REAL NOT NULL DEFAULT 0.7,
    reason TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    confidence REAL NOT NULL DEFAULT 0.7,
    context_id INTEGER REFERENCES contexts(id) ON DELETE SET NULL,
    proposed_action TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    task_ids_json TEXT NOT NULL DEFAULT '[]',
    meeting_ids_json TEXT NOT NULL DEFAULT '[]',
    source_fingerprint TEXT,
    retired_at TEXT,
    next_notify_at TEXT,
    last_notified_at TEXT,
    notification_reason TEXT,
    notification_status TEXT,
    snoozed_until TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS suggestion_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    suggestion_id INTEGER NOT NULL REFERENCES suggestions(id) ON DELETE CASCADE,
    source_fingerprint TEXT,
    scheduled_at TEXT,
    delivered_at TEXT,
    status TEXT NOT NULL DEFAULT 'candidate',
    reason TEXT,
    action_taken TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bot_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    provider_bot_id TEXT,
    meeting_id INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    meeting_url_display TEXT,
    meeting_url_hash TEXT,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'created',
    join_at TEXT,
    transcript_path TEXT,
    raw_metadata_path TEXT,
    last_sync_at TEXT,
    error TEXT,
    consent_confirmed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS calendar_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL DEFAULT 'google',
    provider_event_id TEXT NOT NULL,
    calendar_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description_snippet TEXT,
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL,
    timezone TEXT,
    location TEXT,
    meeting_url TEXT,
    attendees_json TEXT NOT NULL DEFAULT '[]',
    status TEXT,
    html_link TEXT,
    raw_json_path TEXT,
    last_synced_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(provider, calendar_id, provider_event_id)
);

CREATE INDEX IF NOT EXISTS idx_calendar_events_start_at ON calendar_events(start_at);
CREATE INDEX IF NOT EXISTS idx_calendar_events_provider_event ON calendar_events(provider, calendar_id, provider_event_id);
"""

ACTIVE_TASK_STATUSES = {"open", "waiting", "snoozed", "uncertain"}
FINAL_TASK_STATUSES = {"done", "canceled"}
TASK_STATUSES = ACTIVE_TASK_STATUSES | FINAL_TASK_STATUSES
SOURCE_TYPES = {
    "local_recording",
    "meeting_bot",
    "gmail",
    "calendar",
    "manual",
    "document",
    "action_item",
    "commitment",
    "screenshot",
}


class Repository:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            self._ensure_column(conn, "meetings", "source_type", "TEXT NOT NULL DEFAULT 'local_recording'")
            self._ensure_column(conn, "email_drafts", "tone", "TEXT")
            self._ensure_column(conn, "email_drafts", "included_items_json", "TEXT")
            self._ensure_column(conn, "tasks", "owed_to", "TEXT")
            self._ensure_column(conn, "tasks", "project", "TEXT")
            self._ensure_column(conn, "tasks", "source_type", "TEXT NOT NULL DEFAULT 'manual'")
            self._ensure_column(conn, "tasks", "reminder_suggestion", "TEXT")
            self._ensure_column(conn, "tasks", "snoozed_until", "TEXT")
            self._ensure_column(conn, "tasks", "last_followed_up_at", "TEXT")
            self._ensure_column(conn, "calendar_events", "description_snippet", "TEXT")
            self._ensure_column(conn, "calendar_events", "meeting_url", "TEXT")
            self._ensure_column(conn, "calendar_events", "attendees_json", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(conn, "calendar_events", "raw_json_path", "TEXT")
            self._ensure_column(conn, "suggestions", "source_fingerprint", "TEXT")
            self._ensure_column(conn, "suggestions", "retired_at", "TEXT")
            self._ensure_column(conn, "suggestions", "next_notify_at", "TEXT")
            self._ensure_column(conn, "suggestions", "last_notified_at", "TEXT")
            self._ensure_column(conn, "suggestions", "notification_reason", "TEXT")
            self._ensure_column(conn, "suggestions", "notification_status", "TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_suggestions_source_fingerprint ON suggestions(source_fingerprint)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_suggestions_notification_status ON suggestions(notification_status)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_suggestion_notifications_suggestion "
                "ON suggestion_notifications(suggestion_id)"
            )
            self.sync_tasks_from_existing_work(conn)
        self.refresh_all_contexts()

    def create_meeting(
        self,
        title: str,
        audio_path: str | None = None,
        *,
        source_type: str = "local_recording",
    ) -> Meeting:
        now = utc_now_iso()
        source_type = normalize_source_type(source_type)
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO meetings (title, started_at, audio_path, source_type, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (title, now, audio_path, source_type, now, now),
            )
            meeting_id = int(cur.lastrowid)
        return self.get_meeting(meeting_id)

    def get_meeting(self, meeting_id: int) -> Meeting:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
        if row is None:
            raise KeyError(f"Meeting {meeting_id} not found")
        return self._meeting_from_row(row)

    def list_meetings(self, limit: int = 20) -> list[Meeting]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM meetings ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._meeting_from_row(row) for row in rows]

    def list_unprocessed_meetings(self, limit: int = 20) -> list[Meeting]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM meetings
                WHERE (audio_path IS NOT NULL OR source_type = 'meeting_bot')
                  AND (
                    transcript_path IS NULL
                    OR summary IS NULL
                    OR note_path IS NULL
                  )
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._meeting_from_row(row) for row in rows]

    def latest_unprocessed_meeting(self) -> Meeting | None:
        meetings = self.list_unprocessed_meetings(limit=1)
        return meetings[0] if meetings else None

    def update_meeting(self, meeting_id: int, **fields: Any) -> Meeting:
        allowed = {"ended_at", "audio_path", "transcript_path", "note_path", "summary", "raw_extraction_json", "source_type"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Unknown meeting fields: {', '.join(sorted(unknown))}")
        if not fields:
            return self.get_meeting(meeting_id)
        fields["updated_at"] = utc_now_iso()
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [meeting_id]
        with self.connect() as conn:
            conn.execute(f"UPDATE meetings SET {assignments} WHERE id = ?", values)
        return self.get_meeting(meeting_id)

    def save_extraction(self, meeting_id: int, result: ExtractionResult) -> None:
        now = utc_now_iso()
        with self.connect() as conn:
            for table in ["action_items", "commitments", "decisions", "open_questions", "key_topics", "entities"]:
                conn.execute(f"DELETE FROM {table} WHERE meeting_id = ?", (meeting_id,))
            conn.execute(
                """
                UPDATE meetings
                SET summary = ?, raw_extraction_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (result.summary, json.dumps(result.raw, indent=2, sort_keys=True), now, meeting_id),
            )
            conn.execute(
                """
                DELETE FROM tasks
                WHERE source_meeting_id = ?
                  AND source IN ('action_item', 'commitment')
                  AND status NOT IN ('done', 'canceled')
                """,
                (meeting_id,),
            )
            action_ids = self._insert_items(conn, "action_items", meeting_id, result.action_items, now)
            commitment_ids = self._insert_items(conn, "commitments", meeting_id, result.commitments, now)
            for item, source_id in zip(result.action_items, action_ids):
                self._insert_task_from_item(conn, meeting_id, "action_item", "action_items", source_id, item, now)
            for item, source_id in zip(result.commitments, commitment_ids):
                self._insert_task_from_item(conn, meeting_id, "commitment", "commitments", source_id, item, now)
            self._insert_text_rows(conn, "decisions", "text", meeting_id, result.decisions, now)
            self._insert_text_rows(conn, "open_questions", "text", meeting_id, result.open_questions, now)
            self._insert_text_rows(conn, "key_topics", "topic", meeting_id, result.key_topics, now)
            self._insert_text_rows(conn, "entities", "name", meeting_id, result.entities, now)
        self.refresh_meeting_contexts(meeting_id)
        for task in self.list_tasks_for_meeting(meeting_id):
            self.refresh_task_contexts(int(task["id"]))
            self.generate_suggestions_for_task(int(task["id"]))

    def meeting_bundle(self, meeting_id: int) -> dict[str, Any]:
        meeting = self.get_meeting(meeting_id)
        with self.connect() as conn:
            return {
                "meeting": meeting,
                "action_items": self._rows(conn, "action_items", meeting_id),
                "commitments": self._rows(conn, "commitments", meeting_id),
                "decisions": self._rows(conn, "decisions", meeting_id),
                "open_questions": self._rows(conn, "open_questions", meeting_id),
                "key_topics": self._rows(conn, "key_topics", meeting_id),
                "entities": self._rows(conn, "entities", meeting_id),
            }

    def unresolved_work(self) -> list[dict[str, Any]]:
        return self.list_commitments()

    def list_tasks(self, status: str | None = "open", include_done: bool = False) -> list[dict[str, Any]]:
        conditions = []
        params: list[Any] = []
        if status:
            conditions.append("tasks.status = ?")
            params.append(status)
        elif not include_done:
            conditions.append("tasks.status NOT IN ('done', 'canceled')")
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"""
        SELECT
            tasks.*,
            tasks.source AS kind,
            tasks.due_date AS deadline,
            tasks.source_meeting_id AS meeting_id,
            meetings.title AS meeting_title,
            meetings.started_at,
            tasks.owner IS NULL AS owner_missing,
            tasks.due_date IS NULL AS deadline_missing
        FROM tasks
        LEFT JOIN meetings ON meetings.id = tasks.source_meeting_id
        {where}
        ORDER BY
            tasks.status = 'done',
            deadline_missing,
            tasks.due_date,
            owner_missing,
            tasks.owner,
            tasks.created_at DESC
        """
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._task_with_contexts(row) for row in rows]

    def list_tasks_for_meeting(self, meeting_id: int) -> list[dict[str, Any]]:
        query = """
        SELECT
            tasks.*,
            tasks.source AS kind,
            tasks.due_date AS deadline,
            tasks.source_meeting_id AS meeting_id,
            meetings.title AS meeting_title,
            meetings.started_at
        FROM tasks
        LEFT JOIN meetings ON meetings.id = tasks.source_meeting_id
        WHERE tasks.source_meeting_id = ?
        ORDER BY tasks.created_at DESC
        """
        with self.connect() as conn:
            rows = conn.execute(query, (meeting_id,)).fetchall()
        return [self._task_with_contexts(row) for row in rows]

    def overdue_tasks(self, today: date | None = None) -> list[dict[str, Any]]:
        today_iso = (today or date.today()).isoformat()
        query = """
        SELECT
            tasks.*,
            tasks.source AS kind,
            tasks.due_date AS deadline,
            tasks.source_meeting_id AS meeting_id,
            meetings.title AS meeting_title,
            meetings.started_at
        FROM tasks
        LEFT JOIN meetings ON meetings.id = tasks.source_meeting_id
        WHERE tasks.status NOT IN ('done', 'canceled', 'snoozed')
          AND tasks.due_date IS NOT NULL
          AND tasks.due_date < ?
        ORDER BY tasks.due_date, tasks.created_at DESC
        """
        with self.connect() as conn:
            rows = conn.execute(query, (today_iso,)).fetchall()
        return [self._task_with_contexts(row, today=today or date.today()) for row in rows]

    def create_task(
        self,
        text: str,
        owner: str | None = None,
        due_date: str | None = None,
        source: str = "manual",
        source_meeting_id: int | None = None,
        confidence: float = 1.0,
        owed_to: str | None = None,
        project: str | None = None,
        status: str = "open",
        source_type: str | None = None,
    ) -> dict[str, Any]:
        if not text.strip():
            raise ValueError("Task text is required")
        status = normalize_task_status(status)
        source_type = normalize_source_type(source_type or source)
        now = utc_now_iso()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO tasks (
                    text, owner, owed_to, project, due_date, status, source, source_type,
                    source_meeting_id, confidence, reminder_suggestion, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    text.strip(),
                    _optional(owner),
                    _optional(owed_to),
                    _optional(project),
                    _optional(due_date),
                    status,
                    source,
                    source_type,
                    source_meeting_id,
                    confidence,
                    reminder_suggestion(_optional(due_date), status=status),
                    now,
                    now,
                ),
            )
            task_id = int(cur.lastrowid)
        self.refresh_task_contexts(task_id)
        self.generate_suggestions_for_task(task_id)
        return self.get_task(task_id)

    def get_task(self, task_id: int) -> dict[str, Any]:
        query = """
        SELECT
            tasks.*,
            tasks.source AS kind,
            tasks.due_date AS deadline,
            tasks.source_meeting_id AS meeting_id,
            meetings.title AS meeting_title,
            meetings.started_at
        FROM tasks
        LEFT JOIN meetings ON meetings.id = tasks.source_meeting_id
        WHERE tasks.id = ?
        """
        with self.connect() as conn:
            row = conn.execute(query, (task_id,)).fetchone()
        if row is None:
            raise KeyError(f"Task {task_id} not found")
        return self._task_with_contexts(row)

    def complete_task(self, task_id: int) -> dict[str, Any]:
        now = utc_now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE tasks
                SET status = 'done', completed_at = ?, snoozed_until = NULL, updated_at = ?
                WHERE id = ?
                """,
                (now, now, task_id),
            )
        self.retire_suggestions_for_task(task_id, reason="Source task was completed.")
        task = self.get_task(task_id)
        for context in task.get("contexts") or []:
            self.generate_context_suggestions(int(context["id"]))
        return task

    def reopen_task(self, task_id: int) -> dict[str, Any]:
        now = utc_now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE tasks
                SET status = 'open', completed_at = NULL, snoozed_until = NULL, updated_at = ?
                WHERE id = ?
                """,
                (now, task_id),
            )
        self.refresh_task_contexts(task_id)
        self.generate_suggestions_for_task(task_id)
        return self.get_task(task_id)

    def update_task_status(
        self,
        task_id: int,
        status: str,
        *,
        snoozed_until: str | None = None,
    ) -> dict[str, Any]:
        status = normalize_task_status(status)
        now = utc_now_iso()
        completed_at = now if status == "done" else None
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE tasks
                SET status = ?, completed_at = ?, snoozed_until = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, completed_at, _optional(snoozed_until), now, task_id),
            )
        self.refresh_task_contexts(task_id)
        if status in FINAL_TASK_STATUSES:
            self.retire_suggestions_for_task(task_id, reason=f"Source task was marked {status}.")
        elif status == "snoozed":
            self.retire_suggestions_for_task(task_id, reason="Source task was snoozed.")
        self.generate_suggestions_for_task(task_id)
        return self.get_task(task_id)

    def snooze_task(self, task_id: int, until: str | None = None) -> dict[str, Any]:
        if not until:
            until = (date.today() + timedelta(days=1)).isoformat()
        return self.update_task_status(task_id, "snoozed", snoozed_until=until)

    def cancel_task(self, task_id: int) -> dict[str, Any]:
        return self.update_task_status(task_id, "canceled")

    def list_commitments(
        self,
        status: str | None = None,
        include_final: bool = False,
        person: str | None = None,
        project: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions = []
        params: list[Any] = []
        if status:
            conditions.append("tasks.status = ?")
            params.append(normalize_task_status(status))
        elif not include_final:
            conditions.append("tasks.status NOT IN ('done', 'canceled')")
        if person:
            needle = f"%{person.lower()}%"
            conditions.append(
                "(lower(coalesce(tasks.owner, '')) LIKE ? OR lower(coalesce(tasks.owed_to, '')) LIKE ? OR lower(tasks.text) LIKE ?)"
            )
            params.extend([needle, needle, needle])
        if project:
            needle = f"%{project.lower()}%"
            conditions.append("(lower(coalesce(tasks.project, '')) LIKE ? OR lower(tasks.text) LIKE ?)")
            params.extend([needle, needle])
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"""
        SELECT
            tasks.*,
            tasks.source AS kind,
            tasks.due_date AS deadline,
            tasks.source_meeting_id AS meeting_id,
            meetings.title AS meeting_title,
            meetings.started_at,
            tasks.owner IS NULL AS owner_missing,
            tasks.due_date IS NULL AS deadline_missing
        FROM tasks
        LEFT JOIN meetings ON meetings.id = tasks.source_meeting_id
        {where}
        ORDER BY
            tasks.status = 'done',
            tasks.status = 'canceled',
            deadline_missing,
            tasks.due_date,
            tasks.updated_at DESC
        """
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._task_with_contexts(row) for row in rows]

    def daily_brief(self, today: date | None = None) -> dict[str, Any]:
        current = today or date.today()
        today_iso = current.isoformat()
        stale_before = (current - timedelta(days=7)).isoformat()
        tasks = self.list_commitments(include_final=False)
        tomorrow_iso = (current + timedelta(days=1)).isoformat()
        brief = {
            "date": today_iso,
            "overdue": [],
            "today": [],
            "upcoming": [],
            "waiting": [],
            "snoozed": [],
            "uncertain": [],
            "stale": [],
            "unscheduled": [],
            "recommended_followups": [],
            "calendar_today": self.list_calendar_events(start_date=today_iso, end_date=tomorrow_iso, limit=20),
            "calendar_upcoming": self.upcoming_calendar_events(limit=10, from_date=today_iso),
            "meeting_prep": [],
        }
        for task in tasks:
            due = task.get("due_date")
            status = task.get("status")
            if status == "waiting":
                brief["waiting"].append(task)
            elif status == "snoozed":
                brief["snoozed"].append(task)
            elif status == "uncertain":
                brief["uncertain"].append(task)

            if due and due < today_iso and status != "snoozed":
                brief["overdue"].append(task)
            elif due == today_iso:
                brief["today"].append(task)
            elif due and due > today_iso:
                brief["upcoming"].append(task)
            elif not due and status in ACTIVE_TASK_STATUSES:
                brief["unscheduled"].append(task)

            updated_day = str(task.get("updated_at") or "")[:10]
            if status in {"open", "waiting", "uncertain"} and not due and updated_day and updated_day <= stale_before:
                brief["stale"].append(task)

        brief["recommended_followups"] = [
            *brief["overdue"][:5],
            *brief["waiting"][:3],
            *brief["uncertain"][:3],
            *brief["stale"][:3],
        ]
        brief["meeting_prep"] = [self.meeting_prep_for_event(event) for event in brief["calendar_upcoming"][:5]]
        brief["notification_candidates"] = self.notification_candidates(limit=10)
        brief["counts"] = {key: len(value) for key, value in brief.items() if isinstance(value, list)}
        return brief

    def upsert_calendar_event(self, event: dict[str, Any]) -> dict[str, Any]:
        now = utc_now_iso()
        provider = str(event.get("provider") or "google")
        provider_event_id = str(event.get("provider_event_id") or "").strip()
        calendar_id = str(event.get("calendar_id") or "primary").strip()
        if not provider_event_id:
            raise ValueError("Calendar event provider_event_id is required")
        if not event.get("start_at") or not event.get("end_at"):
            raise ValueError("Calendar event start_at and end_at are required")
        attendees_json = json.dumps(event.get("attendees") or [], sort_keys=True)
        values = (
            provider,
            provider_event_id,
            calendar_id,
            str(event.get("title") or "Untitled event"),
            _optional(event.get("description_snippet")),
            str(event.get("start_at")),
            str(event.get("end_at")),
            _optional(event.get("timezone")),
            _optional(event.get("location")),
            _optional(event.get("meeting_url")),
            attendees_json,
            _optional(event.get("status")),
            _optional(event.get("html_link")),
            _optional(event.get("raw_json_path")),
            now,
            now,
            now,
        )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO calendar_events (
                    provider, provider_event_id, calendar_id, title, description_snippet,
                    start_at, end_at, timezone, location, meeting_url, attendees_json,
                    status, html_link, raw_json_path, last_synced_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, calendar_id, provider_event_id)
                DO UPDATE SET
                    title = excluded.title,
                    description_snippet = excluded.description_snippet,
                    start_at = excluded.start_at,
                    end_at = excluded.end_at,
                    timezone = excluded.timezone,
                    location = excluded.location,
                    meeting_url = excluded.meeting_url,
                    attendees_json = excluded.attendees_json,
                    status = excluded.status,
                    html_link = excluded.html_link,
                    raw_json_path = excluded.raw_json_path,
                    last_synced_at = excluded.last_synced_at,
                    updated_at = excluded.updated_at
                """,
                values,
            )
            row = conn.execute(
                """
                SELECT * FROM calendar_events
                WHERE provider = ? AND calendar_id = ? AND provider_event_id = ?
                """,
                (provider, calendar_id, provider_event_id),
            ).fetchone()
        if row is None:
            raise RuntimeError("Calendar event upsert failed")
        return self._calendar_event_dict(row)

    def list_calendar_events(
        self,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if start_date:
            conditions.append("start_at >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("start_at < ?")
            params.append(end_date)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM calendar_events
                {where}
                ORDER BY start_at ASC
                LIMIT ?
                """,
                [*params, limit],
            ).fetchall()
        return [self._calendar_event_dict(row) for row in rows]

    def upcoming_calendar_events(self, *, limit: int = 10, from_date: str | None = None) -> list[dict[str, Any]]:
        start = from_date or date.today().isoformat()
        return self.list_calendar_events(start_date=start, limit=limit)

    def meeting_prep_for_event(self, event: dict[str, Any], *, limit: int = 5) -> dict[str, Any]:
        query = calendar_event_query(event)
        tasks = self.search_tasks(query=query, status=None, limit=limit) if query else []
        contexts = self.find_contexts(query, limit=limit) if query else []
        context = self.context_for_topic(query, limit=limit) if query else {"meetings": [], "decisions": []}
        return {
            "event": event,
            "query": query,
            "contexts": contexts,
            "tasks": tasks[:limit],
            "meetings": [as_meeting_dict(meeting) for meeting in context.get("meetings", [])[:limit]],
            "decisions": context.get("decisions", [])[:limit],
        }

    def context_for_topic(self, topic: str, limit: int = 8) -> dict[str, Any]:
        needle = f"%{topic.lower()}%"
        with self.connect() as conn:
            meetings = conn.execute(
                """
                SELECT DISTINCT meetings.*
                FROM meetings
                LEFT JOIN key_topics ON key_topics.meeting_id = meetings.id
                LEFT JOIN decisions ON decisions.meeting_id = meetings.id
                WHERE lower(meetings.title) LIKE ?
                   OR lower(coalesce(meetings.summary, '')) LIKE ?
                   OR lower(coalesce(key_topics.topic, '')) LIKE ?
                   OR lower(coalesce(decisions.text, '')) LIKE ?
                ORDER BY meetings.started_at DESC
                LIMIT ?
                """,
                (needle, needle, needle, needle, limit),
            ).fetchall()
            decisions = conn.execute(
                """
                SELECT decisions.*, meetings.title AS meeting_title, meetings.started_at
                FROM decisions
                JOIN meetings ON meetings.id = decisions.meeting_id
                WHERE lower(decisions.text) LIKE ? OR lower(meetings.title) LIKE ?
                ORDER BY meetings.started_at DESC
                LIMIT ?
                """,
                (needle, needle, limit),
            ).fetchall()
        return {
            "meetings": [self._meeting_from_row(row) for row in meetings],
            "decisions": [dict(row) for row in decisions],
            "unresolved": self.unresolved_work(),
        }

    def save_email_draft(
        self,
        meeting_id: int,
        provider: str,
        provider_draft_id: str | None,
        recipient: str,
        subject: str,
        instruction: str | None,
        body: str,
        tone: str | None = None,
        included_items: list[str] | None = None,
    ) -> int:
        now = utc_now_iso()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO email_drafts (
                    meeting_id, provider, provider_draft_id, recipient, subject,
                    instruction, tone, included_items_json, body, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    meeting_id,
                    provider,
                    provider_draft_id,
                    recipient,
                    subject,
                    instruction,
                    tone,
                    json.dumps(included_items or []),
                    body,
                    now,
                ),
            )
            return int(cur.lastrowid)

    def email_drafts_for_meeting(self, meeting_id: int) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM email_drafts
                WHERE meeting_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (meeting_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_bot_session(
        self,
        *,
        provider: str,
        provider_bot_id: str | None,
        meeting_id: int,
        meeting_url_display: str | None,
        meeting_url_hash: str | None,
        title: str,
        status: str = "created",
        join_at: str | None = None,
        transcript_path: str | None = None,
        raw_metadata_path: str | None = None,
        error: str | None = None,
        consent_confirmed: bool = False,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO bot_sessions (
                    provider, provider_bot_id, meeting_id, meeting_url_display, meeting_url_hash,
                    title, status, join_at, transcript_path, raw_metadata_path, error,
                    consent_confirmed, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    provider,
                    _optional(provider_bot_id),
                    meeting_id,
                    _optional(meeting_url_display),
                    _optional(meeting_url_hash),
                    title,
                    status,
                    _optional(join_at),
                    _optional(transcript_path),
                    _optional(raw_metadata_path),
                    _optional(error),
                    1 if consent_confirmed else 0,
                    now,
                    now,
                ),
            )
            session_id = int(cur.lastrowid)
        return self.get_bot_session(session_id)

    def get_bot_session(self, session_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT bot_sessions.*, meetings.title AS meeting_title, meetings.summary AS meeting_summary,
                       meetings.transcript_path AS meeting_transcript_path, meetings.note_path AS meeting_note_path
                FROM bot_sessions
                JOIN meetings ON meetings.id = bot_sessions.meeting_id
                WHERE bot_sessions.id = ?
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Bot session {session_id} not found")
        return self._bot_session_dict(row)

    def get_bot_session_by_provider_id(self, provider: str, provider_bot_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT bot_sessions.*, meetings.title AS meeting_title, meetings.summary AS meeting_summary,
                       meetings.transcript_path AS meeting_transcript_path, meetings.note_path AS meeting_note_path
                FROM bot_sessions
                JOIN meetings ON meetings.id = bot_sessions.meeting_id
                WHERE bot_sessions.provider = ? AND bot_sessions.provider_bot_id = ?
                """,
                (provider, provider_bot_id),
            ).fetchone()
        return self._bot_session_dict(row) if row else None

    def list_bot_sessions(self, limit: int = 20, status: str | None = None) -> list[dict[str, Any]]:
        params: list[Any] = []
        where = ""
        if status:
            where = "WHERE bot_sessions.status = ?"
            params.append(status)
        query_limit = limit * 3 if status in {"open", "snoozed"} else limit
        params.append(query_limit)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT bot_sessions.*, meetings.title AS meeting_title, meetings.summary AS meeting_summary,
                       meetings.transcript_path AS meeting_transcript_path, meetings.note_path AS meeting_note_path
                FROM bot_sessions
                JOIN meetings ON meetings.id = bot_sessions.meeting_id
                {where}
                ORDER BY bot_sessions.created_at DESC, bot_sessions.id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._bot_session_dict(row) for row in rows]

    def update_bot_session(self, session_id: int, **fields: Any) -> dict[str, Any]:
        allowed = {
            "provider_bot_id",
            "status",
            "join_at",
            "transcript_path",
            "raw_metadata_path",
            "last_sync_at",
            "error",
            "consent_confirmed",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Unknown bot session fields: {', '.join(sorted(unknown))}")
        if not fields:
            return self.get_bot_session(session_id)
        normalized: dict[str, Any] = {}
        for key, value in fields.items():
            if key == "consent_confirmed":
                normalized[key] = 1 if value else 0
            else:
                normalized[key] = value
        normalized["updated_at"] = utc_now_iso()
        assignments = ", ".join(f"{key} = ?" for key in normalized)
        values = list(normalized.values()) + [session_id]
        with self.connect() as conn:
            conn.execute(f"UPDATE bot_sessions SET {assignments} WHERE id = ?", values)
        return self.get_bot_session(session_id)

    def create_pending_action(
        self,
        *,
        command: str,
        action: str,
        category: str,
        payload: dict[str, Any],
        confidence: float | None = None,
        source: str = "llm",
        explanation: str | None = None,
        safety_notes: list[str] | None = None,
        expires_at: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO assistant_pending_actions (
                    command, action, category, payload_json, confidence, source,
                    explanation, safety_notes_json, status, created_at, updated_at, expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
                """,
                (
                    command,
                    action,
                    category,
                    json.dumps(payload, sort_keys=True),
                    confidence,
                    source,
                    explanation,
                    json.dumps(safety_notes or []),
                    now,
                    now,
                    expires_at,
                ),
            )
            action_id = int(cur.lastrowid)
        return self.get_pending_action(action_id)

    def get_pending_action(self, action_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM assistant_pending_actions WHERE id = ?", (action_id,)).fetchone()
        if row is None:
            raise KeyError(f"Pending assistant action {action_id} not found")
        return self._pending_action_dict(row)

    def list_pending_actions(self, status: str | None = "pending") -> list[dict[str, Any]]:
        params: list[Any] = []
        where = ""
        if status:
            where = "WHERE status = ?"
            params.append(status)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM assistant_pending_actions
                {where}
                ORDER BY created_at DESC, id DESC
                """,
                params,
            ).fetchall()
        return [self._pending_action_dict(row) for row in rows]

    def update_pending_action_status(self, action_id: int, status: str) -> dict[str, Any]:
        normalized = status.strip().lower()
        if normalized not in {"pending", "confirmed", "canceled", "expired"}:
            raise ValueError(f"Unsupported pending action status: {status}")
        now = utc_now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE assistant_pending_actions
                SET status = ?, updated_at = ?
                WHERE id = ?
                """,
                (normalized, now, action_id),
            )
        return self.get_pending_action(action_id)

    def ensure_context(self, name: str, kind: str = "topic") -> dict[str, Any]:
        cleaned = clean_context_name(name)
        if not cleaned:
            raise ValueError("Context name is required")
        normalized = normalize_context_name(cleaned)
        now = utc_now_iso()
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM contexts WHERE normalized_name = ?", (normalized,)).fetchone()
            if row:
                conn.execute(
                    "UPDATE contexts SET name = ?, kind = ?, updated_at = ? WHERE id = ?",
                    (cleaned, kind, now, row["id"]),
                )
                context_id = int(row["id"])
            else:
                cur = conn.execute(
                    """
                    INSERT INTO contexts (name, normalized_name, kind, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (cleaned, normalized, kind, now, now),
                )
                context_id = int(cur.lastrowid)
        return self.get_context(context_id)

    def get_context(self, context_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM contexts WHERE id = ?", (context_id,)).fetchone()
        if row is None:
            raise KeyError(f"Context {context_id} not found")
        return dict(row)

    def find_contexts(self, query: str = "", limit: int = 20) -> list[dict[str, Any]]:
        params: list[Any] = []
        where = ""
        if query.strip():
            needle = f"%{query.strip().lower()}%"
            where = "WHERE lower(name) LIKE ? OR normalized_name LIKE ?"
            params.extend([needle, needle])
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM contexts
                {where}
                ORDER BY updated_at DESC, name
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def link_context(
        self,
        context_id: int,
        *,
        source_type: str,
        source_table: str | None = None,
        source_id: int | None = None,
        task_id: int | None = None,
        meeting_id: int | None = None,
        confidence: float = 0.7,
        reason: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM context_links
                WHERE context_id = ?
                  AND source_type = ?
                  AND coalesce(source_table, '') = ?
                  AND coalesce(source_id, -1) = ?
                  AND coalesce(task_id, -1) = ?
                  AND coalesce(meeting_id, -1) = ?
                """,
                (
                    context_id,
                    source_type,
                    source_table or "",
                    source_id if source_id is not None else -1,
                    task_id if task_id is not None else -1,
                    meeting_id if meeting_id is not None else -1,
                ),
            ).fetchone()
            if row:
                return self._context_link_dict(row)
            cur = conn.execute(
                """
                INSERT INTO context_links (
                    context_id, source_type, source_table, source_id, task_id, meeting_id,
                    confidence, reason, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (context_id, source_type, source_table, source_id, task_id, meeting_id, confidence, reason, now),
            )
            link_id = int(cur.lastrowid)
            row = conn.execute("SELECT * FROM context_links WHERE id = ?", (link_id,)).fetchone()
        return self._context_link_dict(row)

    def contexts_for_task(self, task_id: int) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT contexts.*, context_links.confidence, context_links.reason
                FROM context_links
                JOIN contexts ON contexts.id = context_links.context_id
                WHERE context_links.task_id = ?
                ORDER BY confidence DESC, contexts.name
                """,
                (task_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def refresh_meeting_contexts(self, meeting_id: int) -> None:
        meeting = self.get_meeting(meeting_id)
        candidates: list[tuple[str, str, float, str]] = []
        candidates.extend((value, "topic", 0.65, "meeting title") for value in context_candidates_from_text(meeting.title))
        with self.connect() as conn:
            topics = conn.execute("SELECT topic FROM key_topics WHERE meeting_id = ?", (meeting_id,)).fetchall()
            entities = conn.execute("SELECT name FROM entities WHERE meeting_id = ?", (meeting_id,)).fetchall()
        candidates.extend((row["topic"], "topic", 0.9, "meeting topic") for row in topics)
        candidates.extend((row["name"], "person", 0.65, "meeting entity") for row in entities)
        for name, kind, confidence, reason in dedupe_context_candidates(candidates):
            context = self.ensure_context(name, kind=kind)
            self.link_context(
                int(context["id"]),
                source_type="meeting",
                source_table="meetings",
                source_id=meeting_id,
                meeting_id=meeting_id,
                confidence=confidence,
                reason=reason,
            )

    def refresh_task_contexts(self, task_id: int) -> None:
        task = self._raw_task(task_id)
        candidates: list[tuple[str, str, float, str]] = []
        if task.get("project"):
            candidates.append((str(task["project"]), "project", 1.0, "explicit task project"))
        for person_key in ["owner", "owed_to"]:
            if task.get(person_key):
                candidates.append((str(task[person_key]), "person", 0.65, f"task {person_key}"))
        candidates.extend((value, "topic", 0.72, "task text") for value in context_candidates_from_text(str(task.get("text") or "")))
        meeting_id = task.get("source_meeting_id")
        if meeting_id:
            self.refresh_meeting_contexts(int(meeting_id))
            for context in self.contexts_for_meeting(int(meeting_id)):
                candidates.append((context["name"], context["kind"], min(float(context.get("confidence") or 0.7), 0.85), "source meeting context"))
        for name, kind, confidence, reason in dedupe_context_candidates(candidates):
            context = self.ensure_context(name, kind=kind)
            self.link_context(
                int(context["id"]),
                source_type=str(task.get("source_type") or task.get("source") or "manual"),
                source_table="tasks",
                source_id=task_id,
                task_id=task_id,
                meeting_id=int(meeting_id) if meeting_id else None,
                confidence=confidence,
                reason=reason,
            )

    def contexts_for_meeting(self, meeting_id: int) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    contexts.*,
                    max(context_links.confidence) AS confidence,
                    min(context_links.reason) AS reason
                FROM context_links
                JOIN contexts ON contexts.id = context_links.context_id
                WHERE context_links.meeting_id = ?
                GROUP BY contexts.id
                ORDER BY confidence DESC, contexts.name
                """,
                (meeting_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def refresh_all_contexts(self) -> None:
        with self.connect() as conn:
            meeting_ids = [int(row["id"]) for row in conn.execute("SELECT id FROM meetings").fetchall()]
            task_ids = [int(row["id"]) for row in conn.execute("SELECT id FROM tasks").fetchall()]
        for meeting_id in meeting_ids:
            self.refresh_meeting_contexts(meeting_id)
        for task_id in task_ids:
            self.refresh_task_contexts(task_id)
            self.generate_suggestions_for_task(task_id)

    def context_graph(self, query: str, limit: int = 20) -> dict[str, Any]:
        contexts = self.find_contexts(query, limit=limit)
        if not contexts and query.strip():
            needle = query.strip().lower()
            contexts = [context for context in self.find_contexts(limit=50) if needle in context["name"].lower()]
        context_ids = [int(context["id"]) for context in contexts]
        tasks: list[dict[str, Any]] = []
        meetings: list[dict[str, Any]] = []
        if context_ids:
            placeholders = ",".join("?" for _ in context_ids)
            with self.connect() as conn:
                task_rows = conn.execute(
                    f"""
                    SELECT DISTINCT
                        tasks.*,
                        tasks.source AS kind,
                        tasks.due_date AS deadline,
                        tasks.source_meeting_id AS meeting_id,
                        meetings.title AS meeting_title,
                        meetings.started_at
                    FROM context_links
                    JOIN tasks ON tasks.id = context_links.task_id
                    LEFT JOIN meetings ON meetings.id = tasks.source_meeting_id
                    WHERE context_links.context_id IN ({placeholders})
                    ORDER BY tasks.status = 'done', tasks.due_date IS NULL, tasks.due_date, tasks.updated_at DESC
                    LIMIT ?
                    """,
                    [*context_ids, limit],
                ).fetchall()
                meeting_rows = conn.execute(
                    f"""
                    SELECT DISTINCT meetings.*
                    FROM context_links
                    JOIN meetings ON meetings.id = context_links.meeting_id
                    WHERE context_links.context_id IN ({placeholders})
                    ORDER BY meetings.started_at DESC
                    LIMIT ?
                    """,
                    [*context_ids, limit],
                ).fetchall()
            tasks = [self._task_with_contexts(row) for row in task_rows]
            meetings = [as_meeting_dict(self._meeting_from_row(row)) for row in meeting_rows]
        return {
            "query": query,
            "contexts": contexts,
            "tasks": tasks,
            "meetings": meetings,
            "suggestions": self.list_suggestions(status="open"),
        }

    def create_suggestion(
        self,
        *,
        title: str,
        reason: str,
        proposed_action: str,
        payload: dict[str, Any],
        confidence: float = 0.7,
        context_id: int | None = None,
        task_ids: list[int] | None = None,
        meeting_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        payload_json = json.dumps(payload, sort_keys=True)
        task_ids_json = json.dumps(sorted(set(task_ids or [])))
        meeting_ids_json = json.dumps(sorted(set(meeting_ids or [])))
        source_fingerprint = suggestion_fingerprint(
            proposed_action=proposed_action,
            payload=payload,
            context_id=context_id,
            task_ids=task_ids or [],
            meeting_ids=meeting_ids or [],
        )
        notification_reason = notification_reason_for_suggestion(title, reason, proposed_action)
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM suggestions
                WHERE status IN ('open', 'snoozed')
                  AND source_fingerprint = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (source_fingerprint,),
            ).fetchone()
            if row:
                return self._suggestion_dict(row)
            cur = conn.execute(
                """
                INSERT INTO suggestions (
                    title, reason, status, confidence, context_id, proposed_action, payload_json,
                    task_ids_json, meeting_ids_json, source_fingerprint, next_notify_at,
                    notification_reason, notification_status, created_at, updated_at
                )
                VALUES (?, ?, 'open', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'candidate', ?, ?)
                """,
                (
                    title,
                    reason,
                    confidence,
                    context_id,
                    proposed_action,
                    payload_json,
                    task_ids_json,
                    meeting_ids_json,
                    source_fingerprint,
                    now,
                    notification_reason,
                    now,
                    now,
                ),
            )
            suggestion_id = int(cur.lastrowid)
        return self.get_suggestion(suggestion_id)

    def get_suggestion(self, suggestion_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT suggestions.*, contexts.name AS context_name, contexts.kind AS context_kind
                FROM suggestions
                LEFT JOIN contexts ON contexts.id = suggestions.context_id
                WHERE suggestions.id = ?
                """,
                (suggestion_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Suggestion {suggestion_id} not found")
        return self._suggestion_dict(row)

    def list_suggestions(self, status: str | None = "open", limit: int = 20) -> list[dict[str, Any]]:
        params: list[Any] = []
        where = ""
        if status:
            where = "WHERE suggestions.status = ?"
            params.append(status)
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT suggestions.*, contexts.name AS context_name, contexts.kind AS context_kind
                FROM suggestions
                LEFT JOIN contexts ON contexts.id = suggestions.context_id
                {where}
                ORDER BY suggestions.created_at DESC, suggestions.id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        suggestions = [self._suggestion_dict(row) for row in rows]
        if status in {"open", "snoozed"}:
            suggestions = self._dedupe_followup_suggestions(suggestions)
        return suggestions[:limit]

    def update_suggestion_status(self, suggestion_id: int, status: str, snoozed_until: str | None = None) -> dict[str, Any]:
        normalized = status.strip().lower()
        if normalized not in {"open", "accepted", "dismissed", "snoozed", "retired"}:
            raise ValueError(f"Unsupported suggestion status: {status}")
        now = utc_now_iso()
        retired_at = now if normalized == "retired" else None
        notification_status = {
            "accepted": "accepted",
            "dismissed": "dismissed",
            "snoozed": "snoozed",
            "retired": "retired",
        }.get(normalized)
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE suggestions
                SET status = ?,
                    snoozed_until = ?,
                    retired_at = coalesce(?, retired_at),
                    notification_status = coalesce(?, notification_status),
                    next_notify_at = CASE WHEN ? IN ('accepted', 'dismissed', 'retired') THEN NULL ELSE next_notify_at END,
                    updated_at = ?
                WHERE id = ?
                """,
                (normalized, _optional(snoozed_until), retired_at, notification_status, normalized, now, suggestion_id),
            )
        return self.get_suggestion(suggestion_id)

    def retire_suggestions_for_task(self, task_id: int, *, reason: str) -> list[dict[str, Any]]:
        now = utc_now_iso()
        updated: list[int] = []
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, task_ids_json FROM suggestions
                WHERE status IN ('open', 'snoozed')
                """
            ).fetchall()
            for row in rows:
                try:
                    task_ids = json.loads(row["task_ids_json"] or "[]")
                except json.JSONDecodeError:
                    task_ids = []
                if task_id not in {int(value) for value in task_ids if str(value).isdigit()}:
                    continue
                conn.execute(
                    """
                    UPDATE suggestions
                    SET status = 'retired',
                        retired_at = ?,
                        notification_status = 'retired',
                        notification_reason = ?,
                        next_notify_at = NULL,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (now, reason, now, int(row["id"])),
                )
                updated.append(int(row["id"]))
        return [self.get_suggestion(suggestion_id) for suggestion_id in updated]

    def notification_status(self) -> dict[str, Any]:
        candidates = self.notification_candidates(limit=50)
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    sum(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) AS delivered,
                    sum(CASE WHEN status = 'dismissed' THEN 1 ELSE 0 END) AS dismissed,
                    sum(CASE WHEN status = 'snoozed' THEN 1 ELSE 0 END) AS snoozed
                FROM suggestion_notifications
                """
            ).fetchone()
        return {
            "enabled": True,
            "delivery": "native_app",
            "runtime": "while_app_running",
            "permission_owner": "native",
            "candidate_count": len(candidates),
            "delivered_count": int(row["delivered"] or 0) if row else 0,
            "dismissed_count": int(row["dismissed"] or 0) if row else 0,
            "snoozed_count": int(row["snoozed"] or 0) if row else 0,
            "note": "Native notifications are scheduled by the Mac app while it is running.",
        }

    def notification_candidates(self, limit: int = 20) -> list[dict[str, Any]]:
        today = date.today().isoformat()
        rows = self.list_suggestions(status="open", limit=max(limit * 3, 20))
        candidates: list[dict[str, Any]] = []
        for suggestion in rows:
            if suggestion.get("retired_at"):
                continue
            last_notified = suggestion.get("last_notified_at")
            if last_notified and str(last_notified)[:10] >= today:
                continue
            next_notify = suggestion.get("next_notify_at")
            if next_notify and str(next_notify)[:10] > today:
                continue
            task_ids = [int(value) for value in suggestion.get("task_ids") or []]
            if not self._notification_source_active(task_ids):
                continue
            item = dict(suggestion)
            item["notification_reason"] = item.get("notification_reason") or notification_reason_for_suggestion(
                str(item.get("title") or ""),
                str(item.get("reason") or ""),
                str(item.get("proposed_action") or ""),
            )
            item["notification_status"] = item.get("notification_status") or "candidate"
            candidates.append(item)
            if len(candidates) >= limit:
                break
        return candidates

    def mark_notification_delivered(self, suggestion_id: int) -> dict[str, Any]:
        now = utc_now_iso()
        suggestion = self.get_suggestion(suggestion_id)
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE suggestions
                SET last_notified_at = ?,
                    notification_status = 'delivered',
                    updated_at = ?
                WHERE id = ?
                """,
                (now, now, suggestion_id),
            )
            conn.execute(
                """
                INSERT INTO suggestion_notifications (
                    suggestion_id, source_fingerprint, scheduled_at, delivered_at,
                    status, reason, action_taken, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 'delivered', ?, 'delivered', ?, ?)
                """,
                (
                    suggestion_id,
                    suggestion.get("source_fingerprint"),
                    suggestion.get("next_notify_at") or now,
                    now,
                    suggestion.get("notification_reason") or suggestion.get("reason"),
                    now,
                    now,
                ),
            )
        return {"suggestion": self.get_suggestion(suggestion_id), "notification": self.latest_notification_for_suggestion(suggestion_id)}

    def dismiss_notification(self, suggestion_id: int) -> dict[str, Any]:
        suggestion = self.update_suggestion_status(suggestion_id, "dismissed")
        self._record_notification_action(suggestion, "dismissed")
        return {"suggestion": suggestion}

    def snooze_notification(self, suggestion_id: int, until: str | None = None) -> dict[str, Any]:
        if not until:
            until = (date.today() + timedelta(days=1)).isoformat()
        now = utc_now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE suggestions
                SET status = 'snoozed',
                    snoozed_until = ?,
                    next_notify_at = ?,
                    notification_status = 'snoozed',
                    updated_at = ?
                WHERE id = ?
                """,
                (until, until, now, suggestion_id),
            )
        suggestion = self.get_suggestion(suggestion_id)
        self._record_notification_action(suggestion, "snoozed")
        return {"suggestion": suggestion}

    def latest_notification_for_suggestion(self, suggestion_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM suggestion_notifications
                WHERE suggestion_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (suggestion_id,),
            ).fetchone()
        return dict(row) if row else None

    def _record_notification_action(self, suggestion: dict[str, Any], action: str) -> None:
        now = utc_now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO suggestion_notifications (
                    suggestion_id, source_fingerprint, scheduled_at, delivered_at,
                    status, reason, action_taken, created_at, updated_at
                )
                VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?)
                """,
                (
                    int(suggestion["id"]),
                    suggestion.get("source_fingerprint"),
                    suggestion.get("next_notify_at"),
                    action,
                    suggestion.get("notification_reason") or suggestion.get("reason"),
                    action,
                    now,
                    now,
                ),
            )

    def _notification_source_active(self, task_ids: list[int]) -> bool:
        for task_id in task_ids:
            try:
                task = self.get_task(task_id)
            except KeyError:
                return False
            status = str(task.get("status") or "")
            if status in FINAL_TASK_STATUSES:
                return False
            if status == "snoozed":
                until = task.get("snoozed_until")
                if until and str(until)[:10] > date.today().isoformat():
                    return False
        return True

    def generate_suggestions_for_task(self, task_id: int) -> list[dict[str, Any]]:
        task = self.get_task(task_id)
        suggestions: list[dict[str, Any]] = []
        status = task.get("status")
        if status not in FINAL_TASK_STATUSES:
            due = task.get("due_date")
            if not due:
                suggestions.append(
                    self.create_suggestion(
                        title=f"Schedule task #{task_id}",
                        reason="This task has no due date, so it can slip without a reminder.",
                        proposed_action="search_tasks",
                        payload={"task_id": task_id, "query": task.get("text")},
                        confidence=0.75,
                        task_ids=[task_id],
                    )
                )
            elif is_past_iso_date(str(due)) and status != "snoozed":
                suggestions.append(
                    self.create_suggestion(
                        title=f"Review overdue task #{task_id}",
                        reason="This task is overdue. Confirm complete, snooze it, or follow up.",
                        proposed_action="search_tasks",
                        payload={"task_id": task_id, "query": task.get("text")},
                        confidence=0.85,
                        task_ids=[task_id],
                    )
                )
            if status in {"waiting", "uncertain"}:
                suggestions.append(
                    self.create_suggestion(
                        title=f"Resolve {status} task #{task_id}",
                        reason=f"This task is marked {status}; Speedwagon should bring it back into view.",
                        proposed_action="search_tasks",
                        payload={"task_id": task_id, "query": task.get("text")},
                        confidence=0.8,
                        task_ids=[task_id],
                    )
                )
        for context in task.get("contexts") or []:
            context_id = int(context["id"])
            suggestions.extend(self.generate_context_suggestions(context_id))
        return suggestions

    def generate_context_suggestions(self, context_id: int) -> list[dict[str, Any]]:
        context = self.get_context(context_id)
        tasks = self.tasks_for_context(context_id, include_done=True)
        active = [task for task in tasks if task.get("status") not in FINAL_TASK_STATUSES]
        all_email_tasks = [task for task in active if is_followup_task(str(task.get("text") or ""))]
        email_tasks = [
            task
            for task in all_email_tasks
            if self._preferred_followup_context_id(task) == context_id
        ]
        blockers = [task for task in active if task not in all_email_tasks and task.get("status") not in {"done", "canceled"}]
        if not email_tasks or blockers:
            return []
        task_ids = [int(task["id"]) for task in tasks]
        meeting_ids = sorted({int(task["meeting_id"]) for task in tasks if task.get("meeting_id")})
        email_task = email_tasks[0]
        return [
            self.create_suggestion(
                title=f"Draft follow-up for {context['name']}",
                reason=(
                    f"All other open work linked to {context['name']} appears resolved, "
                    f"and task #{email_task['id']} is still a follow-up/email task."
                ),
                proposed_action="draft_email_from_context",
                payload={"context_id": context_id, "task_id": int(email_task["id"])},
                confidence=0.82,
                context_id=context_id,
                task_ids=task_ids,
                meeting_ids=meeting_ids,
            )
        ]

    def _preferred_followup_context_id(self, task: dict[str, Any]) -> int | None:
        contexts = task.get("contexts") or []
        if not contexts:
            return None
        task_text = str(task.get("text") or "").lower()

        def score(context: dict[str, Any]) -> tuple[float, int]:
            name = str(context.get("name") or "").lower()
            kind = str(context.get("kind") or "topic")
            kind_score = {"project": 50, "topic": 40, "person": 30}.get(kind, 20)
            text_score = 25 if name and name in task_text else 0
            confidence_score = float(context.get("confidence") or 0.0) * 10
            return (kind_score + text_score + confidence_score, int(context.get("id") or 0))

        return int(max(contexts, key=score)["id"])

    def _dedupe_followup_suggestions(self, suggestions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        best_by_task: dict[int, dict[str, Any]] = {}
        output: list[dict[str, Any]] = []
        task_texts: dict[int, str] = {}
        for suggestion in suggestions:
            if suggestion.get("proposed_action") != "draft_email_from_context":
                output.append(suggestion)
                continue
            payload = suggestion.get("payload") or {}
            try:
                task_id = int(payload.get("task_id") or 0)
            except (TypeError, ValueError):
                output.append(suggestion)
                continue
            if not task_id:
                output.append(suggestion)
                continue
            if task_id not in task_texts:
                try:
                    task_texts[task_id] = str(self.get_task(task_id).get("text") or "").lower()
                except KeyError:
                    task_texts[task_id] = ""
            existing = best_by_task.get(task_id)
            if existing is None or self._followup_suggestion_score(suggestion, task_texts[task_id]) > self._followup_suggestion_score(existing, task_texts[task_id]):
                best_by_task[task_id] = suggestion
        output.extend(best_by_task.values())
        output.sort(key=lambda item: (str(item.get("created_at") or ""), int(item.get("id") or 0)), reverse=True)
        return output

    @staticmethod
    def _followup_suggestion_score(suggestion: dict[str, Any], task_text: str) -> tuple[float, int]:
        context = suggestion.get("context") or {}
        context_name = str(context.get("name") or suggestion.get("context_name") or "").lower()
        context_kind = str(context.get("kind") or suggestion.get("context_kind") or "topic")
        kind_score = {"project": 50, "topic": 40, "person": 30}.get(context_kind, 20)
        text_score = 25 if context_name and context_name in task_text else 0
        confidence_score = float(suggestion.get("confidence") or 0.0) * 10
        return (kind_score + text_score + confidence_score, int(suggestion.get("id") or 0))

    def tasks_for_context(self, context_id: int, include_done: bool = False) -> list[dict[str, Any]]:
        where = "" if include_done else "AND tasks.status NOT IN ('done', 'canceled')"
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT DISTINCT
                    tasks.*,
                    tasks.source AS kind,
                    tasks.due_date AS deadline,
                    tasks.source_meeting_id AS meeting_id,
                    meetings.title AS meeting_title,
                    meetings.started_at
                FROM context_links
                JOIN tasks ON tasks.id = context_links.task_id
                LEFT JOIN meetings ON meetings.id = tasks.source_meeting_id
                WHERE context_links.context_id = ?
                {where}
                ORDER BY tasks.status = 'done', tasks.due_date IS NULL, tasks.due_date, tasks.updated_at DESC
                """,
                (context_id,),
            ).fetchall()
        return [self._task_with_contexts(row) for row in rows]

    def search_tasks(self, query: str = "", status: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        conditions = []
        params: list[Any] = []
        if status:
            conditions.append("tasks.status = ?")
            params.append(status)
        if query.strip():
            needle = f"%{query.strip().lower()}%"
            conditions.append(
                "(lower(tasks.text) LIKE ? OR lower(coalesce(tasks.project, '')) LIKE ? OR lower(coalesce(meetings.title, '')) LIKE ?)"
            )
            params.extend([needle, needle, needle])
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    tasks.*,
                    tasks.source AS kind,
                    tasks.due_date AS deadline,
                    tasks.source_meeting_id AS meeting_id,
                    meetings.title AS meeting_title,
                    meetings.started_at
                FROM tasks
                LEFT JOIN meetings ON meetings.id = tasks.source_meeting_id
                {where}
                ORDER BY tasks.status = 'done', tasks.due_date IS NULL, tasks.due_date, tasks.updated_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._task_with_contexts(row) for row in rows]

    def sync_tasks_from_existing_work(self, conn: sqlite3.Connection | None = None) -> None:
        owns_connection = conn is None
        active_conn = conn or self.connect()
        now = utc_now_iso()
        try:
            for source, table in [("action_item", "action_items"), ("commitment", "commitments")]:
                rows = active_conn.execute(
                    f"""
                    SELECT * FROM {table}
                    WHERE status NOT IN ('done', 'canceled')
                      AND NOT EXISTS (
                        SELECT 1 FROM tasks
                        WHERE tasks.source_table = ?
                          AND tasks.source_id = {table}.id
                      )
                    """,
                    (table,),
                ).fetchall()
                for row in rows:
                    active_conn.execute(
                        """
                        INSERT INTO tasks (
                            text, owner, due_date, status, source, source_type, source_table, source_id,
                            source_meeting_id, confidence, reminder_suggestion, created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0.85, ?, ?, ?)
                        """,
                        (
                            row["text"],
                            row["owner"],
                            row["deadline"],
                            row["status"],
                            source,
                            source,
                            table,
                            row["id"],
                            row["meeting_id"],
                            reminder_suggestion(row["deadline"], status=row["status"]),
                            now,
                            now,
                        ),
                    )
        finally:
            if owns_connection:
                active_conn.close()

    def _raw_task(self, task_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(f"Task {task_id} not found")
        return dict(row)

    def _task_with_contexts(self, row: sqlite3.Row, today: date | None = None) -> dict[str, Any]:
        item = self._task_dict(row, today=today)
        item["contexts"] = self.contexts_for_task(int(item["id"]))
        return item

    @staticmethod
    def _meeting_from_row(row: sqlite3.Row) -> Meeting:
        return Meeting(
            id=int(row["id"]),
            title=row["title"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            audio_path=row["audio_path"],
            transcript_path=row["transcript_path"],
            note_path=row["note_path"],
            summary=row["summary"],
            source_type=row["source_type"],
        )

    @staticmethod
    def _insert_items(conn: sqlite3.Connection, table: str, meeting_id: int, items: list[ExtractedItem], now: str) -> list[int]:
        ids = []
        for item in items:
            cur = conn.execute(
                f"""
                INSERT INTO {table} (meeting_id, text, owner, deadline, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (meeting_id, item.text, item.owner, item.deadline, item.status, now, now),
            )
            ids.append(int(cur.lastrowid))
        return ids

    @staticmethod
    def _insert_task_from_item(
        conn: sqlite3.Connection,
        meeting_id: int,
        source: str,
        source_table: str,
        source_id: int,
        item: ExtractedItem,
        now: str,
    ) -> None:
        if item.status == "done":
            return
        conn.execute(
            """
            INSERT INTO tasks (
                text, owner, due_date, status, source, source_type, source_table, source_id,
                source_meeting_id, confidence, reminder_suggestion, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0.9, ?, ?, ?)
            """,
            (
                item.text,
                item.owner,
                item.deadline,
                item.status,
                source,
                source,
                source_table,
                source_id,
                meeting_id,
                reminder_suggestion(item.deadline, status=item.status),
                now,
                now,
            ),
        )

    @staticmethod
    def _insert_text_rows(
        conn: sqlite3.Connection,
        table: str,
        column: str,
        meeting_id: int,
        values: list[str],
        now: str,
    ) -> None:
        for value in values:
            conn.execute(
                f"INSERT INTO {table} (meeting_id, {column}, created_at) VALUES (?, ?, ?)",
                (meeting_id, value, now),
            )

    @staticmethod
    def _rows(conn: sqlite3.Connection, table: str, meeting_id: int) -> list[dict[str, Any]]:
        rows = conn.execute(f"SELECT * FROM {table} WHERE meeting_id = ? ORDER BY id", (meeting_id,)).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _pending_action_dict(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        try:
            item["payload"] = json.loads(item.pop("payload_json") or "{}")
        except json.JSONDecodeError:
            item["payload"] = {}
        try:
            item["safety_notes"] = json.loads(item.pop("safety_notes_json") or "[]")
        except json.JSONDecodeError:
            item["safety_notes"] = []
        return item

    @staticmethod
    def _context_link_dict(row: sqlite3.Row) -> dict[str, Any]:
        return dict(row)

    @staticmethod
    def _suggestion_dict(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        try:
            item["payload"] = json.loads(item.pop("payload_json") or "{}")
        except json.JSONDecodeError:
            item["payload"] = {}
        try:
            item["task_ids"] = json.loads(item.pop("task_ids_json") or "[]")
        except json.JSONDecodeError:
            item["task_ids"] = []
        try:
            item["meeting_ids"] = json.loads(item.pop("meeting_ids_json") or "[]")
        except json.JSONDecodeError:
            item["meeting_ids"] = []
        if item.get("context_id") and item.get("context_name"):
            item["context"] = {
                "id": item["context_id"],
                "name": item.get("context_name"),
                "kind": item.get("context_kind"),
            }
        else:
            item["context"] = None
        return item

    @staticmethod
    def _bot_session_dict(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["consent_confirmed"] = bool(item.get("consent_confirmed"))
        item["transcript_ready"] = bool(item.get("transcript_path") or item.get("meeting_transcript_path"))
        item["processed"] = bool(item.get("meeting_summary") and item.get("meeting_note_path"))
        return item

    @staticmethod
    def _calendar_event_dict(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        try:
            item["attendees"] = json.loads(item.pop("attendees_json") or "[]")
        except json.JSONDecodeError:
            item["attendees"] = []
        return item

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def _task_dict(row: sqlite3.Row, today: date | None = None) -> dict[str, Any]:
        item = dict(row)
        due = item.get("due_date")
        current = today or date.today()
        item["deadline"] = due
        item["kind"] = item.get("source")
        item["meeting_id"] = item.get("source_meeting_id")
        item["is_overdue"] = bool(item.get("status") not in FINAL_TASK_STATUSES and due and due < current.isoformat())
        if item.get("status") not in FINAL_TASK_STATUSES:
            item["reminder_suggestion"] = reminder_suggestion(due, today=current, status=item.get("status"))
        return item


def _optional(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_task_status(status: str) -> str:
    normalized = (status or "open").strip().lower().replace("-", "_")
    if normalized == "complete":
        normalized = "done"
    if normalized not in TASK_STATUSES:
        raise ValueError(f"Unsupported task status: {status}")
    return normalized


def normalize_source_type(source_type: str) -> str:
    normalized = (source_type or "manual").strip().lower().replace("-", "_")
    if normalized not in SOURCE_TYPES:
        return "manual"
    return normalized


def reminder_suggestion(due_date: str | None, today: date | None = None, status: str | None = None) -> str | None:
    if status == "waiting":
        return "Waiting on someone else. Consider a gentle follow-up."
    if status == "uncertain":
        return "Speedwagon is unsure whether this is resolved. Confirm, snooze, or follow up."
    if status == "snoozed":
        return "Snoozed. Review when it comes back into focus."
    if not due_date:
        return None
    current = today or date.today()
    try:
        due = date.fromisoformat(due_date)
    except ValueError:
        return None
    delta = (current - due).days
    if delta > 0:
        unit = "day" if delta == 1 else "days"
        return f"This was due {delta} {unit} ago. Confirm complete or follow up."
    if delta == 0:
        return "This is due today. Confirm status or follow up."
    return None


def as_meeting_dict(meeting: Meeting) -> dict[str, Any]:
    return {
        "id": meeting.id,
        "title": meeting.title,
        "started_at": meeting.started_at,
        "ended_at": meeting.ended_at,
        "audio_path": meeting.audio_path,
        "transcript_path": meeting.transcript_path,
        "note_path": meeting.note_path,
        "summary": meeting.summary,
        "source_type": meeting.source_type,
    }


def calendar_event_query(event: dict[str, Any]) -> str:
    parts = [
        str(event.get("title") or ""),
        str(event.get("description_snippet") or ""),
        str(event.get("location") or ""),
    ]
    for attendee in event.get("attendees") or []:
        if isinstance(attendee, dict):
            parts.append(str(attendee.get("display_name") or attendee.get("email") or ""))
    text = " ".join(part.strip() for part in parts if part and part.strip())
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9@._-]{2,}", text)
    stop = {"meeting", "calendar", "https", "com", "with", "the", "and", "for", "about"}
    values: list[str] = []
    seen: set[str] = set()
    for word in words:
        cleaned = word.strip(".,;:")
        key = cleaned.lower()
        if key in stop or key in seen:
            continue
        seen.add(key)
        values.append(cleaned)
        if len(values) >= 8:
            break
    return " ".join(values)


def suggestion_fingerprint(
    *,
    proposed_action: str,
    payload: dict[str, Any],
    context_id: int | None = None,
    task_ids: list[int] | None = None,
    meeting_ids: list[int] | None = None,
) -> str:
    payload_json = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"))
    task_part = ",".join(str(value) for value in sorted(set(task_ids or [])))
    meeting_part = ",".join(str(value) for value in sorted(set(meeting_ids or [])))
    return f"{proposed_action}|context:{context_id or ''}|tasks:{task_part}|meetings:{meeting_part}|payload:{payload_json}"


def notification_reason_for_suggestion(title: str, reason: str, proposed_action: str) -> str:
    action = proposed_action.replace("_", " ")
    lowered = f"{title} {reason}".lower()
    if "overdue" in lowered:
        return "This work is overdue and needs a decision."
    if "schedule task" in lowered or "no due date" in lowered:
        return "This task has no due date, so it can slip."
    if "follow-up" in lowered or "email" in action:
        return "Related work looks ready for follow-up."
    if "waiting" in lowered or "uncertain" in lowered:
        return "This commitment needs confirmation."
    return reason


def is_past_iso_date(value: str, today: date | None = None) -> bool:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return False
    return parsed < (today or date.today())


def clean_context_name(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip(" \t\n\r,.;:()[]{}")).strip()


def normalize_context_name(value: str) -> str:
    text = clean_context_name(value).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def context_candidates_from_text(text: str) -> list[str]:
    candidates: list[str] = []
    stop = {
        "add",
        "ask",
        "can",
        "email",
        "fix",
        "put",
        "remove",
        "send",
        "task",
        "the",
        "this",
        "with",
    }
    for value in re.findall(r"\b[A-Za-z][A-Za-z0-9]*(?:[A-Z][A-Za-z0-9]*)+\b|\b[A-Z]{2,}[A-Za-z0-9]*\b", text or ""):
        cleaned = clean_context_name(value)
        if cleaned and cleaned.lower() not in stop and len(cleaned) >= 3:
            candidates.append(cleaned)
    for value in re.findall(r"\b([A-Za-z][A-Za-z0-9]+(?:MGT|AI|CRM|API|MVP|UX|UI))\b", text or "", flags=re.IGNORECASE):
        cleaned = clean_context_name(value)
        if cleaned and cleaned.lower() not in stop:
            candidates.append(cleaned)
    return candidates[:8]


def dedupe_context_candidates(candidates: list[tuple[str, str, float, str]]) -> list[tuple[str, str, float, str]]:
    seen: set[str] = set()
    values: list[tuple[str, str, float, str]] = []
    for name, kind, confidence, reason in candidates:
        cleaned = clean_context_name(name)
        normalized = normalize_context_name(cleaned)
        if not cleaned or normalized in seen:
            continue
        seen.add(normalized)
        values.append((cleaned, kind, confidence, reason))
    return values


def is_followup_task(text: str) -> bool:
    return bool(re.search(r"\b(email|mail|follow[- ]?up|send .*update|send .*recap)\b", text or "", flags=re.IGNORECASE))
