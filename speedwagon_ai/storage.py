from __future__ import annotations

import json
import sqlite3
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
    body TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


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
            self._insert_items(conn, "action_items", meeting_id, result.action_items, now)
            self._insert_items(conn, "commitments", meeting_id, result.commitments, now)
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
        query = """
        SELECT *
        FROM (
            SELECT
                'action_item' AS kind,
                action_items.*,
                meetings.title AS meeting_title,
                meetings.started_at,
                owner IS NULL AS owner_missing,
                deadline IS NULL AS deadline_missing
            FROM action_items
            JOIN meetings ON meetings.id = action_items.meeting_id
            WHERE action_items.status != 'done'
            UNION ALL
            SELECT
                'commitment' AS kind,
                commitments.*,
                meetings.title AS meeting_title,
                meetings.started_at,
                owner IS NULL AS owner_missing,
                deadline IS NULL AS deadline_missing
            FROM commitments
            JOIN meetings ON meetings.id = commitments.meeting_id
            WHERE commitments.status != 'done'
        )
        ORDER BY owner_missing, owner, deadline_missing, deadline, started_at DESC
        """
        with self.connect() as conn:
            rows = conn.execute(query).fetchall()
        return [dict(row) for row in rows]

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
    ) -> int:
        now = utc_now_iso()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO email_drafts (
                    meeting_id, provider, provider_draft_id, recipient, subject, instruction, body, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (meeting_id, provider, provider_draft_id, recipient, subject, instruction, body, now),
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
    def _insert_items(conn: sqlite3.Connection, table: str, meeting_id: int, items: list[ExtractedItem], now: str) -> None:
        for item in items:
            conn.execute(
                f"""
                INSERT INTO {table} (meeting_id, text, owner, deadline, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (meeting_id, item.text, item.owner, item.deadline, item.status, now, now),
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
