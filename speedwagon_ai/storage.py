from __future__ import annotations

import json
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
"""

ACTIVE_TASK_STATUSES = {"open", "waiting", "snoozed", "uncertain"}
FINAL_TASK_STATUSES = {"done", "canceled"}
TASK_STATUSES = ACTIVE_TASK_STATUSES | FINAL_TASK_STATUSES
SOURCE_TYPES = {"local_recording", "meeting_bot", "gmail", "calendar", "manual", "document", "action_item", "commitment"}


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
            self._ensure_column(conn, "email_drafts", "tone", "TEXT")
            self._ensure_column(conn, "email_drafts", "included_items_json", "TEXT")
            self._ensure_column(conn, "tasks", "owed_to", "TEXT")
            self._ensure_column(conn, "tasks", "project", "TEXT")
            self._ensure_column(conn, "tasks", "source_type", "TEXT NOT NULL DEFAULT 'manual'")
            self._ensure_column(conn, "tasks", "reminder_suggestion", "TEXT")
            self._ensure_column(conn, "tasks", "snoozed_until", "TEXT")
            self._ensure_column(conn, "tasks", "last_followed_up_at", "TEXT")
            self.sync_tasks_from_existing_work(conn)

    def create_meeting(self, title: str, audio_path: str | None = None) -> Meeting:
        now = utc_now_iso()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO meetings (title, started_at, audio_path, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (title, now, audio_path, now, now),
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
                WHERE audio_path IS NOT NULL
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
        allowed = {"ended_at", "audio_path", "transcript_path", "note_path", "summary", "raw_extraction_json"}
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
        return [self._task_dict(row) for row in rows]

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
        return [self._task_dict(row, today=today or date.today()) for row in rows]

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
        return self._task_dict(row)

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
        return self.get_task(task_id)

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
        return [self._task_dict(row) for row in rows]

    def daily_brief(self, today: date | None = None) -> dict[str, Any]:
        current = today or date.today()
        today_iso = current.isoformat()
        stale_before = (current - timedelta(days=7)).isoformat()
        tasks = self.list_commitments(include_final=False)
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
        brief["counts"] = {key: len(value) for key, value in brief.items() if isinstance(value, list)}
        return brief

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
