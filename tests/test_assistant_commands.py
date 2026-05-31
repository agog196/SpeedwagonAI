from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from speedwagon_ai.assistant_commands import execute_command, parse_command
from speedwagon_ai.config import Settings
from speedwagon_ai.storage import Repository


class AssistantCommandTests(unittest.TestCase):
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

    def test_parse_supported_commands(self) -> None:
        cases = {
            "what is overdue": ("list_overdue_tasks", {}),
            "what should I do today": ("list_today_tasks", {}),
            "show tasks": ("list_open_tasks", {}),
            "complete task 12": ("complete_task", {"task_id": 12}),
            "reopen task 12": ("reopen_task", {"task_id": 12}),
            "add task send notes due 2026-06-01": ("add_task", {"text": "send notes", "due_date": "2026-06-01"}),
            "search context for onboarding": ("search_context", {"topic": "onboarding"}),
        }
        for command, expected in cases.items():
            parsed = parse_command(command)
            self.assertTrue(parsed.supported, command)
            self.assertEqual((parsed.action, parsed.payload), expected)

    def test_unknown_command_is_unsupported(self) -> None:
        parsed = parse_command("please handle my life")
        self.assertFalse(parsed.supported)
        self.assertIn("Unsupported command", parsed.summary)

    def test_execute_command_updates_tasks(self) -> None:
        added = execute_command(self.settings, self.repo, "add task send notes due 2026-06-01")
        self.assertTrue(added["supported"])
        task_id = added["result"]["task"]["id"]

        completed = execute_command(self.settings, self.repo, f"complete task {task_id}")
        self.assertEqual(completed["result"]["task"]["status"], "done")

        reopened = execute_command(self.settings, self.repo, f"reopen task {task_id}")
        self.assertEqual(reopened["result"]["task"]["status"], "open")


if __name__ == "__main__":
    unittest.main()
