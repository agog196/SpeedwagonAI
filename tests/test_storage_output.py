from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from speedwagon_ai.config import Settings
from speedwagon_ai.extraction import parse_extraction
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
            record_cmd="",
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

    def test_commitments_markdown_handles_missing_owner_deadline(self) -> None:
        meeting = self.repo.create_meeting("Roadmap")
        self.repo.save_extraction(
            meeting.id,
            ExtractionResult(commitments=[ExtractedItem("Confirm scope")], raw={"commitments": [{"text": "Confirm scope"}]}),
        )
        markdown = render_commitments_markdown(self.repo.unresolved_work())
        self.assertIn("## Unassigned", markdown)
        self.assertIn("[commitment] Confirm scope", markdown)

    def test_writer_creates_files(self) -> None:
        meeting = self.repo.create_meeting("Demo")
        self.repo.save_extraction(meeting.id, ExtractionResult(summary="Demo summary", raw={"summary": "Demo summary"}))
        writer = MarkdownWriter(self.settings, self.repo)
        note_path = writer.write_meeting(meeting.id)
        commitments_path = writer.write_commitments()
        self.assertTrue(note_path.exists())
        self.assertTrue(commitments_path.exists())


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
