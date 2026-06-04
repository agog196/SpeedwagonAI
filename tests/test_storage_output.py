from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from speedwagon_ai.config import Settings
from speedwagon_ai.email_composer import fallback_compose, parse_email_content
from speedwagon_ai.extraction import fallback_extract, parse_extraction
from speedwagon_ai.integrations.gmail import preview_followup_email
from speedwagon_ai.models import ExtractionResult, ExtractedItem, Meeting
from speedwagon_ai.output import MarkdownWriter, render_commitments_markdown, render_meeting_markdown
from speedwagon_ai.storage import Repository


class StorageOutputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.settings = Settings(
            db_path=root / "data" / "speedwagon.db",
            notes_dir=root / "notes",
            audio_dir=root / "audio",
            transcripts_dir=root / "transcripts",
            state_path=root / "data" / "recording.json",
            app_host="127.0.0.1",
            app_port=8765,
            record_cmd="",
            capture_profile="mic",
            input_device="",
            whisper_cpp_bin="",
            whisper_cpp_model="",
            llm_provider="openai",
            openai_api_key="",
            openai_model="gpt-4.1-mini",
            anthropic_api_key="",
            gmail_credentials_path=root / "data" / "google_credentials.json",
            gmail_token_path=root / "data" / "google_token.json",
            google_calendar_token_path=root / "data" / "google_calendar_token.json",
        )
        self.repo = Repository(self.settings.db_path)
        self.repo.init()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_init_migrates_old_suggestion_lifecycle_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "data" / "speedwagon.db"
            db_path.parent.mkdir(parents=True)
            with sqlite3.connect(db_path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE contexts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        normalized_name TEXT NOT NULL UNIQUE,
                        kind TEXT NOT NULL DEFAULT 'topic',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE suggestions (
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
                        snoozed_until TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    """
                )

            repo = Repository(db_path)
            repo.init()

            with sqlite3.connect(db_path) as conn:
                suggestion_columns = {
                    row[1] for row in conn.execute("PRAGMA table_info(suggestions)").fetchall()
                }
                self.assertIn("source_fingerprint", suggestion_columns)
                self.assertIn("notification_status", suggestion_columns)
                indexes = {row[1] for row in conn.execute("PRAGMA index_list(suggestions)").fetchall()}
                self.assertIn("idx_suggestions_source_fingerprint", indexes)
                conn.execute("SELECT 1 FROM suggestion_notifications LIMIT 1").fetchall()

    def test_schema_crud_and_markdown(self) -> None:
        meeting = self.repo.create_meeting("Weekly Planning", audio_path="audio/meeting-1.wav")
        transcript = self.settings.transcripts_dir / "meeting-1.txt"
        transcript.parent.mkdir(parents=True)
        transcript.write_text("We decided to ship the CLI. Anish will write tests by Friday.", encoding="utf-8")
        self.repo.update_meeting(meeting.id, transcript_path=str(transcript))
        result = ExtractionResult(
            summary="Team planned the first SpeedwagonAI CLI.",
            action_items=[ExtractedItem("Write tests", owner="Anish", deadline="Friday")],
            commitments=[ExtractedItem("Ship the CLI", owner=None, deadline=None)],
            decisions=["Use CLI first"],
            open_questions=["Which UI comes next?"],
            key_topics=["CLI", "meeting context"],
            entities=["Anish"],
            raw={"summary": "Team planned the first SpeedwagonAI CLI."},
        )
        self.repo.save_extraction(meeting.id, result)

        bundle = self.repo.meeting_bundle(meeting.id)
        markdown = render_meeting_markdown(bundle)

        self.assertIn("meeting_id: 1", markdown)
        self.assertIn("- [ ] Write tests", markdown)
        self.assertIn("- [[commitments]]", markdown)
        self.assertEqual(len(bundle["action_items"]), 1)
        self.assertEqual(len(self.repo.unresolved_work()), 2)
        tasks = self.repo.list_tasks(status="open")
        self.assertEqual(len(tasks), 2)
        self.assertTrue(any(task["source"] == "action_item" for task in tasks))

    def test_commitments_markdown_handles_missing_owner_deadline(self) -> None:
        meeting = self.repo.create_meeting("Roadmap")
        self.repo.save_extraction(
            meeting.id,
            ExtractionResult(commitments=[ExtractedItem("Confirm scope")], raw={"commitments": [{"text": "Confirm scope"}]}),
        )
        markdown = render_commitments_markdown(self.repo.unresolved_work())
        self.assertIn("## Unassigned", markdown)
        self.assertIn("[commitment] Confirm scope", markdown)

    def test_task_lifecycle_and_overdue_logic(self) -> None:
        task = self.repo.create_task("Follow up on launch", owner="Anish", due_date="2026-05-29")
        self.assertEqual(task["status"], "open")
        overdue = self.repo.overdue_tasks(today=date(2026, 5, 31))
        self.assertEqual(overdue[0]["id"], task["id"])
        self.assertIn("2 days ago", overdue[0]["reminder_suggestion"])

        done = self.repo.complete_task(task["id"])
        self.assertEqual(done["status"], "done")
        self.assertIsNotNone(done["completed_at"])
        self.assertEqual(self.repo.overdue_tasks(today=date(2026, 5, 31)), [])

        reopened = self.repo.reopen_task(task["id"])
        self.assertEqual(reopened["status"], "open")
        self.assertIsNone(reopened["completed_at"])

    def test_commitment_statuses_and_daily_brief(self) -> None:
        overdue = self.repo.create_task("Send overdue notes", owner="Anish", due_date="2026-05-29")
        today = self.repo.create_task("Prep launch brief", owner="Anish", due_date="2026-05-31")
        waiting = self.repo.create_task("Get design approval", owner="Maya", status="waiting")
        uncertain = self.repo.create_task("Confirm whether beta shipped", status="uncertain")
        snoozed = self.repo.snooze_task(today["id"], until="2026-06-03")
        self.repo.cancel_task(uncertain["id"])

        brief = self.repo.daily_brief(today=date(2026, 5, 31))

        self.assertTrue(any(task["id"] == overdue["id"] for task in brief["overdue"]))
        self.assertTrue(any(task["id"] == waiting["id"] for task in brief["waiting"]))
        self.assertTrue(any(task["id"] == snoozed["id"] for task in brief["snoozed"]))
        self.assertFalse(any(task["id"] == uncertain["id"] for task in self.repo.list_commitments()))
        self.assertEqual(self.repo.get_task(uncertain["id"])["status"], "canceled")

    def test_list_commitments_can_filter_by_person_and_project(self) -> None:
        self.repo.create_task("Send Alex notes", owner="Anish", owed_to="Alex", project="Onboarding")
        self.repo.create_task("Review finance doc", owner="Maya", project="Finance")

        alex = self.repo.list_commitments(person="Alex")
        onboarding = self.repo.list_commitments(project="Onboarding")

        self.assertEqual([task["text"] for task in alex], ["Send Alex notes"])
        self.assertEqual([task["text"] for task in onboarding], ["Send Alex notes"])

    def test_unprocessed_meetings_detect_missing_outputs(self) -> None:
        raw = self.repo.create_meeting("Raw Meeting", audio_path="audio/raw.wav")
        done = self.repo.create_meeting("Done Meeting", audio_path="audio/done.wav")
        self.repo.update_meeting(
            done.id,
            transcript_path="transcripts/done.txt",
            note_path="notes/done.md",
            summary="Done",
            raw_extraction_json="{}",
        )

        meetings = self.repo.list_unprocessed_meetings()

        self.assertEqual([meeting.id for meeting in meetings], [raw.id])
        self.assertEqual(self.repo.latest_unprocessed_meeting().id, raw.id)

    def test_commitments_markdown_uses_unified_tasks(self) -> None:
        self.repo.create_task("Manual reminder", owner="Anish", due_date="2026-06-01")
        markdown = render_commitments_markdown(self.repo.list_tasks(status="open"))
        self.assertIn("[manual] Manual reminder due 2026-06-01", markdown)
        self.assertIn("[[Manual task]]", markdown)

    def test_context_graph_links_tasks_and_creates_followup_suggestion(self) -> None:
        blocker = self.repo.create_task("Finish DairyMGT Repro tab graphs", project="DairyMGT", due_date="2026-06-07")
        email = self.repo.create_task("Email Megan about DairyMGT updates", project="DairyMGT")

        graph = self.repo.context_graph("DairyMGT")
        self.assertTrue(any(context["name"] == "DairyMGT" for context in graph["contexts"]))
        self.assertEqual({task["id"] for task in graph["tasks"]}, {blocker["id"], email["id"]})
        self.assertTrue(self.repo.get_task(email["id"])["contexts"])

        self.repo.complete_task(blocker["id"])
        suggestions = self.repo.list_suggestions(status="open")

        self.assertTrue(any(item["proposed_action"] == "draft_email_from_context" for item in suggestions))
        followup = next(item for item in suggestions if item["proposed_action"] == "draft_email_from_context")
        self.assertEqual(followup["context"]["name"], "DairyMGT")
        self.assertIn(email["id"], followup["task_ids"])

    def test_followup_suggestions_are_deduped_per_email_task(self) -> None:
        meeting = self.repo.create_meeting("testMeet")
        self.repo.save_extraction(
            meeting.id,
            ExtractionResult(
                summary="Discussed sending a project update and reviewing next steps.",
                action_items=[
                    ExtractedItem("Send project update email to Megan"),
                    ExtractedItem("Review the next steps"),
                ],
                key_topics=["project update", "next steps"],
                raw={"summary": "Discussed sending a project update and reviewing next steps."},
            ),
        )
        tasks = self.repo.list_tasks_for_meeting(meeting.id)
        blocker = next(task for task in tasks if task["text"] == "Review the next steps")
        email = next(task for task in tasks if task["text"] == "Send project update email to Megan")

        self.repo.complete_task(blocker["id"])
        suggestions = [
            item
            for item in self.repo.list_suggestions(status="open", limit=20)
            if item["proposed_action"] == "draft_email_from_context"
            and (item.get("payload") or {}).get("task_id") == email["id"]
        ]

        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["context"]["name"], "project update")

    def test_extracted_meeting_tasks_inherit_meeting_context(self) -> None:
        meeting = self.repo.create_meeting("DairyMGT planning")
        self.repo.save_extraction(
            meeting.id,
            ExtractionResult(
                summary="Discussed DairyMGT release follow-through.",
                action_items=[ExtractedItem("Email Clara with the DairyMGT release notes")],
                key_topics=["DairyMGT"],
                entities=["Clara"],
                raw={"summary": "Discussed DairyMGT release follow-through."},
            ),
        )

        task = self.repo.list_tasks_for_meeting(meeting.id)[0]
        contexts = {context["name"] for context in task["contexts"]}

        self.assertIn("DairyMGT", contexts)
        self.assertIn("Clara", contexts)
        self.assertTrue(any(context["name"] == "DairyMGT" for context in self.repo.contexts_for_meeting(meeting.id)))

    def test_suggestion_status_lifecycle(self) -> None:
        suggestion = self.repo.create_suggestion(
            title="Review stale work",
            reason="A task looks stale.",
            proposed_action="search_tasks",
            payload={"query": "stale"},
            confidence=0.7,
        )

        snoozed = self.repo.update_suggestion_status(suggestion["id"], "snoozed", snoozed_until="2026-06-08")
        dismissed = self.repo.update_suggestion_status(suggestion["id"], "dismissed")

        self.assertEqual(snoozed["snoozed_until"], "2026-06-08")
        self.assertEqual(dismissed["status"], "dismissed")

    def test_notification_candidates_and_lifecycle_retirement(self) -> None:
        overdue = self.repo.create_task("Send overdue update", due_date="2026-06-01")
        unscheduled = self.repo.create_task("Plan launch follow-up")

        candidates = self.repo.notification_candidates()
        candidate_ids = {item["id"] for item in candidates}
        self.assertTrue(any(overdue["id"] in item["task_ids"] for item in candidates))
        self.assertTrue(any(unscheduled["id"] in item["task_ids"] for item in candidates))
        self.assertTrue(all(item["notification_reason"] for item in candidates))

        delivered = self.repo.mark_notification_delivered(next(iter(candidate_ids)))
        self.assertEqual(delivered["suggestion"]["notification_status"], "delivered")
        self.assertIsNotNone(delivered["suggestion"]["last_notified_at"])

        self.repo.complete_task(overdue["id"])
        self.assertFalse(any(overdue["id"] in item["task_ids"] for item in self.repo.notification_candidates()))

    def test_duplicate_suggestion_fingerprint_reuses_active_suggestion(self) -> None:
        first = self.repo.create_suggestion(
            title="Schedule task #99",
            reason="This task has no due date.",
            proposed_action="search_tasks",
            payload={"task_id": 99, "query": "demo"},
            task_ids=[99],
        )
        second = self.repo.create_suggestion(
            title="Schedule task #99 again",
            reason="This task has no due date.",
            proposed_action="search_tasks",
            payload={"query": "demo", "task_id": 99},
            task_ids=[99],
        )

        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["source_fingerprint"], second["source_fingerprint"])

    def test_notification_snooze_and_dismiss_update_status(self) -> None:
        task = self.repo.create_task("Review notification controls")
        suggestion = next(item for item in self.repo.notification_candidates() if task["id"] in item["task_ids"])

        snoozed = self.repo.snooze_notification(suggestion["id"], "2026-06-09")["suggestion"]
        self.assertEqual(snoozed["status"], "snoozed")
        self.assertEqual(snoozed["notification_status"], "snoozed")
        self.assertEqual(snoozed["next_notify_at"], "2026-06-09")

        dismissed = self.repo.dismiss_notification(suggestion["id"])["suggestion"]
        self.assertEqual(dismissed["status"], "dismissed")
        self.assertEqual(dismissed["notification_status"], "dismissed")

    def test_writer_creates_files(self) -> None:
        meeting = self.repo.create_meeting("Demo")
        self.repo.save_extraction(meeting.id, ExtractionResult(summary="Demo summary", raw={"summary": "Demo summary"}))
        writer = MarkdownWriter(self.settings, self.repo)
        note_path = writer.write_meeting(meeting.id)
        commitments_path = writer.write_commitments()
        self.assertTrue(note_path.exists())
        self.assertTrue(commitments_path.exists())

    def test_instruction_based_email_preview_and_audit_storage(self) -> None:
        meeting = self.repo.create_meeting("Partner Sync")
        self.repo.save_extraction(
            meeting.id,
            ExtractionResult(
                summary="Discussed launch next steps.",
                action_items=[ExtractedItem("Send launch notes", owner="Anish", deadline="Monday")],
                decisions=["Launch next week"],
                raw={"summary": "Discussed launch next steps."},
            ),
        )
        preview = preview_followup_email(
            self.settings,
            self.repo,
            meeting.id,
            to="person@example.com",
            instruction="Make it warm and focus on next steps.",
        )
        self.assertEqual(preview["to"], "person@example.com")
        self.assertNotIn("Make it warm and focus on next steps.", preview["body"])
        self.assertIn("Send launch notes", preview["body"])
        self.assertEqual(preview["provider"], "fallback")

        draft_id = self.repo.save_email_draft(
            meeting_id=meeting.id,
            provider="gmail",
            provider_draft_id="draft-123",
            recipient="person@example.com",
            subject=preview["subject"],
            instruction="Make it warm and focus on next steps.",
            body=preview["body"],
            tone=preview["tone"],
            included_items=preview["included_items"],
        )
        drafts = self.repo.email_drafts_for_meeting(meeting.id)
        self.assertEqual(drafts[0]["id"], draft_id)
        self.assertEqual(drafts[0]["provider_draft_id"], "draft-123")
        self.assertEqual(drafts[0]["tone"], "warm")

    def test_fallback_email_instruction_is_private(self) -> None:
        meeting = self.repo.create_meeting("Design Review")
        self.repo.save_extraction(
            meeting.id,
            ExtractionResult(
                summary="Reviewed dashboard and email draft flows.",
                action_items=[ExtractedItem("Send revised draft", owner="Anish")],
                decisions=["Keep Gmail draft-only"],
                open_questions=["Should reminders be next?"],
                raw={"summary": "Reviewed dashboard and email draft flows."},
            ),
        )
        bundle = self.repo.meeting_bundle(meeting.id)
        instruction = "Make it concise and focus on the decision."
        draft = fallback_compose(bundle, instruction=instruction)
        self.assertNotIn(instruction, draft.body)
        self.assertEqual(draft.tone, "concise")
        self.assertIn("Keep Gmail draft-only", draft.body)

    def test_parse_email_content_from_llm_fixture(self) -> None:
        draft = parse_email_content(
            {
                "subject": "Next steps from design review",
                "body": "Hi,\n\nThanks for the discussion. I will send the revised draft today.\n\nBest,",
                "tone": "warm",
                "included_items": ["summary", "action_items"],
            },
            fallback_subject="Follow-up",
            provider="openai",
        )
        self.assertEqual(draft.subject, "Next steps from design review")
        self.assertEqual(draft.tone, "warm")
        self.assertEqual(draft.included_items, ["summary", "action_items"])


class ExtractionParsingTests(unittest.TestCase):
    def test_parse_extraction_normalizes_missing_fields(self) -> None:
        raw = {
            "summary": "Summary",
            "action_items": [{"text": "Do thing", "owner": "unknown", "deadline": None}],
            "commitments": ["Follow up"],
            "decisions": ["Decision"],
            "open_questions": ["Question"],
            "key_topics": ["Topic"],
            "entities": ["Person"],
        }
        result = parse_extraction(raw)
        self.assertIsNone(result.action_items[0].owner)
        self.assertEqual(result.action_items[0].status, "open")
        self.assertEqual(result.commitments[0].text, "Follow up")
        self.assertEqual(result.raw, raw)

    def test_fallback_extract_creates_obvious_action_item(self) -> None:
        meeting = Meeting(id=1, title="DairyMGT", started_at="2026-06-03T21:18:16+00:00")
        raw = fallback_extract(meeting, "So, for DairyMGT, we want an email sent to Megan by June 5th.", reason="no key")
        result = parse_extraction(raw)

        self.assertEqual(raw["provider"], "fallback")
        self.assertEqual(result.action_items[0].deadline, "June 5th")
        self.assertIn("send email to megan", result.action_items[0].text.lower())
        self.assertIn("Megan", result.entities)


if __name__ == "__main__":
    unittest.main()
