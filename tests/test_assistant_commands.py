from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from speedwagon_ai.assistant_commands import confirm_pending_action, execute_command, parse_command
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
            "what do I have to do on June 5 2026": ("list_today_tasks", {"date": "2026-06-05"}),
            "show tasks due 2026-06-05": ("list_today_tasks", {"date": "2026-06-05"}),
            "what tasks do I have that do not have due dates": ("list_unscheduled_tasks", {}),
            "tasks without due dates": ("list_unscheduled_tasks", {}),
            "daily brief": ("daily_brief", {}),
            "summarize today": ("daily_brief", {}),
            "what needs my attention": ("daily_brief", {}),
            "what can you do": ("list_capabilities", {}),
            "what am I waiting on": ("list_waiting_tasks", {}),
            "what do I owe Alex": ("list_commitments_for_person", {"person": "alex"}),
            "what did I say about onboarding": ("search_context", {"topic": "onboarding"}),
            "show unprocessed meetings": ("list_unprocessed_meetings", {}),
            "process latest meeting": ("process_latest_meeting", {}),
            "process meeting 12": ("process_meeting", {"meeting_id": 12}),
            "draft follow-up for meeting 8": ("draft_meeting_followup", {"meeting_id": 8, "instruction": "Draft a concise, useful follow-up email."}),
            "start meeting recording called weekly planning": ("start_meeting_recording", {"title": "weekly planning"}),
            "finish meeting": ("finish_meeting_recording", {}),
            "stop meeting without processing": ("stop_meeting_recording", {}),
            "show tasks": ("list_open_tasks", {}),
            "complete task 12": ("complete_task", {"task_id": 12}),
            "confirm task 12": ("complete_task", {"task_id": 12}),
            "reopen task 12": ("reopen_task", {"task_id": 12}),
            "snooze task 12 until 2026-06-05": ("snooze_task", {"task_id": 12, "until": "2026-06-05"}),
            "cancel task 12": ("cancel_task", {"task_id": 12}),
            "task 12 waiting": ("mark_task_waiting", {"task_id": 12}),
            "task 12 uncertain": ("mark_task_uncertain", {"task_id": 12}),
            "add task send notes due 2026-06-01": ("add_task", {"text": "send notes", "due_date": "2026-06-01"}),
            "search context for onboarding": ("search_context", {"topic": "onboarding"}),
        }
        for command, expected in cases.items():
            parsed = parse_command(command)
            self.assertTrue(parsed.supported, command)
            self.assertEqual((parsed.action, parsed.payload), expected)
            self.assertIn(parsed.category, {"tasks", "commitments", "meetings", "email", "capture", "context", "brief", "system_status"})

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

        waiting = execute_command(self.settings, self.repo, f"task {task_id} waiting")
        self.assertEqual(waiting["result"]["task"]["status"], "waiting")

        snoozed = execute_command(self.settings, self.repo, f"snooze task {task_id} until 2026-06-05")
        self.assertEqual(snoozed["result"]["task"]["status"], "snoozed")
        self.assertEqual(snoozed["result"]["task"]["snoozed_until"], "2026-06-05")

        brief = execute_command(self.settings, self.repo, "daily brief")
        self.assertEqual(brief["action"], "daily_brief")
        self.assertEqual(brief["category"], "brief")
        self.assertIn("counts", brief["result"])

    def test_execute_command_lists_tasks_for_requested_date(self) -> None:
        self.repo.create_task("June fifth task", due_date="2026-06-05")
        self.repo.create_task("Different day task", due_date="2026-06-06")

        response = execute_command(self.settings, self.repo, "what do I have to do on June 5 2026")

        self.assertEqual(response["action"], "list_today_tasks")
        self.assertEqual(response["result"]["date"], "2026-06-05")
        self.assertEqual([task["text"] for task in response["result"]["tasks"]], ["June fifth task"])
        self.assertIn("due on 2026-06-05", response["summary"])

    def test_execute_command_lists_unscheduled_tasks_only(self) -> None:
        self.repo.create_task("No due date task")
        self.repo.create_task("Scheduled task", due_date="2026-06-06")

        response = execute_command(self.settings, self.repo, "what tasks do I have that do not have due dates")

        self.assertEqual(response["action"], "list_unscheduled_tasks")
        self.assertEqual([task["text"] for task in response["result"]["tasks"]], ["No due date task"])
        self.assertIn("without due dates", response["summary"])

    def test_capabilities_command_returns_structured_result(self) -> None:
        response = execute_command(self.settings, self.repo, "what can you do")
        self.assertTrue(response["supported"])
        self.assertEqual(response["action"], "list_capabilities")
        self.assertEqual(response["category"], "system_status")
        self.assertTrue(response["result"]["capabilities"])

    def test_unprocessed_meeting_command(self) -> None:
        meeting = self.repo.create_meeting("Raw Meeting", audio_path="audio/raw.wav")
        response = execute_command(self.settings, self.repo, "show unprocessed meetings")
        self.assertEqual(response["action"], "list_unprocessed_meetings")
        self.assertEqual(response["result"]["meetings"][0]["id"], meeting.id)

    def test_rules_parser_wins_before_llm_fallback(self) -> None:
        with patch("speedwagon_ai.assistant_commands.interpret_command") as interpret:
            response = execute_command(self.settings, self.repo, "what is overdue")

        interpret.assert_not_called()
        self.assertEqual(response["action"], "list_overdue_tasks")

    def test_llm_fallback_mutating_action_requires_confirmation(self) -> None:
        interpreted = {
            "supported": True,
            "action": "add_task",
            "category": "tasks",
            "payload": {"text": "send flexible recap", "due_date": "2026-06-01"},
            "confidence": 0.82,
            "requires_confirmation": True,
            "explanation": "Mapped to a task creation request.",
            "safety_notes": ["Mutating interpreted actions require confirmation."],
            "source": "llm",
        }

        with patch("speedwagon_ai.assistant_commands.interpret_command", return_value=interpreted):
            response = execute_command(self.settings, self.repo, "please remind me to send the flexible recap by monday")

        self.assertTrue(response["requires_confirmation"])
        self.assertIsNotNone(response["pending_action_id"])
        self.assertEqual(self.repo.list_tasks(status="open"), [])

        confirmed = confirm_pending_action(self.settings, self.repo, response["pending_action_id"])
        self.assertEqual(confirmed["action"], "add_task")
        self.assertEqual(confirmed["result"]["task"]["text"], "send flexible recap")
        self.assertEqual(self.repo.get_pending_action(response["pending_action_id"])["status"], "confirmed")

    def test_ambiguous_llm_fallback_stays_unsupported(self) -> None:
        interpreted = {
            "supported": False,
            "action": None,
            "category": "system_status",
            "payload": {},
            "confidence": 0.2,
            "requires_confirmation": False,
            "explanation": "This is too ambiguous.",
            "safety_notes": [],
            "source": "llm",
        }

        with patch("speedwagon_ai.assistant_commands.interpret_command", return_value=interpreted):
            response = execute_command(self.settings, self.repo, "handle the thing")

        self.assertFalse(response["supported"])
        self.assertEqual(response["explanation"], "This is too ambiguous.")

    def test_explicit_web_search_is_gated(self) -> None:
        response = execute_command(self.settings, self.repo, "search the web for latest local assistant tools")

        self.assertTrue(response["supported"])
        self.assertEqual(response["action"], "web_search")
        self.assertFalse(response["result"]["enabled"])
        self.assertIn("disabled", response["summary"].lower())


if __name__ == "__main__":
    unittest.main()
