from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from speedwagon_ai.cli import main


class CliFlowTests(unittest.TestCase):
    def test_process_uses_existing_transcript_and_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = {
                "SPEEDWAGON_DB_PATH": str(root / "data" / "speedwagon.db"),
                "SPEEDWAGON_NOTES_DIR": str(root / "notes"),
                "SPEEDWAGON_AUDIO_DIR": str(root / "audio"),
                "SPEEDWAGON_TRANSCRIPTS_DIR": str(root / "transcripts"),
                "SPEEDWAGON_STATE_PATH": str(root / "data" / "recording.json"),
            }
            with patch.dict(os.environ, env, clear=False):
                old_cwd = Path.cwd()
                os.chdir(root)
                try:
                    self.assertEqual(main(["init"]), 0)
                    from speedwagon_ai.config import Settings
                    from speedwagon_ai.storage import Repository

                    settings = Settings.load()
                    repo = Repository(settings.db_path)
                    meeting = repo.create_meeting("Fixture Meeting", audio_path=str(root / "audio" / "fixture.wav"))
                    transcript = root / "transcripts" / "meeting-1.txt"
                    transcript.parent.mkdir(parents=True, exist_ok=True)
                    transcript.write_text("Decision and action item.", encoding="utf-8")
                    repo.update_meeting(meeting.id, transcript_path=str(transcript))
                    fixture = root / "fixture.json"
                    fixture.write_text(
                        json.dumps(
                            {
                                "summary": "Fixture summary",
                                "action_items": [{"text": "Send notes", "owner": "Anish", "deadline": "tomorrow"}],
                                "commitments": [],
                                "decisions": ["Use fixture extraction"],
                                "open_questions": [],
                                "key_topics": ["fixtures"],
                                "entities": ["Anish"],
                            }
                        ),
                        encoding="utf-8",
                    )
                    self.assertEqual(main(["process", str(meeting.id), "--fixture", str(fixture)]), 0)
                    notes = list((root / "notes").glob("*.md"))
                    self.assertTrue(any(path.name == "commitments.md" for path in notes))
                    self.assertTrue(any("fixture-meeting" in path.name for path in notes))
                finally:
                    os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
