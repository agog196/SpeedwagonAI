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

                    self.assertEqual(main(["tasks", "add", "Manual CLI task", "--due", "2026-06-01"]), 0)
                    cli_task = next(task for task in repo.list_tasks(status="open") if task["text"] == "Manual CLI task")
                    self.assertEqual(main(["tasks", "complete", str(cli_task["id"])]), 0)
                    self.assertEqual(repo.get_task(cli_task["id"])["status"], "done")
                    self.assertEqual(main(["ask", "add task ask cli task due 2026-06-02"]), 0)
                    ask_task = next(task for task in repo.list_tasks(status="open") if task["text"] == "ask cli task")
                    self.assertEqual(main(["ask", f"complete task {ask_task['id']}"]), 0)
                    self.assertEqual(repo.get_task(ask_task["id"])["status"], "done")
                    self.assertEqual(main(["ask", "what can you do"]), 0)
                    self.assertEqual(main(["assistant", "capabilities"]), 0)

                    raw = repo.create_meeting("Second Fixture", audio_path=str(root / "audio" / "second.wav"))
                    second_transcript = root / "transcripts" / "meeting-2.txt"
                    second_transcript.write_text("We need to send a launch email by Friday.", encoding="utf-8")
                    repo.update_meeting(raw.id, transcript_path=str(second_transcript))
                    self.assertEqual(main(["ask", "process latest meeting"]), 0)
                    self.assertIsNotNone(repo.get_meeting(raw.id).note_path)

                    self.assertEqual(main(["calendar", "status"]), 0)
                    repo.upsert_calendar_event(
                        {
                            "provider_event_id": "cli-event",
                            "calendar_id": "primary",
                            "title": "CLI Calendar Event",
                            "start_at": "2026-06-08T10:00:00-07:00",
                            "end_at": "2026-06-08T10:30:00-07:00",
                        }
                    )
                    self.assertEqual(main(["calendar", "upcoming"]), 0)
                    with patch(
                        "speedwagon_ai.cli.GoogleCalendarService.sync",
                        return_value={
                            "synced_count": 0,
                            "time_min": "2026-05-21T00:00:00Z",
                            "time_max": "2026-07-04T00:00:00Z",
                        },
                    ):
                        self.assertEqual(main(["calendar", "sync"]), 0)

                    notify_task = repo.create_task("CLI notification task", due_date="2026-06-01")
                    notify_suggestion = next(
                        item for item in repo.notification_candidates() if notify_task["id"] in item["task_ids"]
                    )
                    self.assertEqual(main(["notifications", "status"]), 0)
                    self.assertEqual(main(["notifications", "candidates"]), 0)
                    self.assertEqual(
                        main(["notifications", "snooze", str(notify_suggestion["id"]), "--until", "2026-06-09"]),
                        0,
                    )
                    self.assertEqual(main(["notifications", "dismiss", str(notify_suggestion["id"])]), 0)
                finally:
                    os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
