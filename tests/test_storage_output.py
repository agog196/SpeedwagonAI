from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from speedwagon_ai.config import Settings
from speedwagon_ai.email_composer import fallback_compose, parse_email_content
from speedwagon_ai.extraction import parse_extraction
from speedwagon_ai.integrations.gmail import preview_followup_email
from speedwagon_ai.models import ExtractionResult, ExtractedItem
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
        )
        self.repo = Repository(self.settings.db_path)
        self.repo.init()

    def tearDown(self) -> None:
        self.tmp.cleanup()

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

    def test_commitments_markdown_uses_unified_tasks(self) -> None:
        self.repo.create_task("Manual reminder", owner="Anish", due_date="2026-06-01")
        markdown = render_commitments_markdown(self.repo.list_tasks(status="open"))
        self.assertIn("[manual] Manual reminder due 2026-06-01", markdown)
        self.assertIn("[[Manual task]]", markdown)

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


if __name__ == "__main__":
    unittest.main()
