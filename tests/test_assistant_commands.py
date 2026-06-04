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
            google_calendar_token_path=root / "data" / "google_calendar_token.json",
        )
        self.repo = Repository(self.settings.db_path)
        self.repo.init()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_parse_supported_commands(self) -> None:
        cases = {
            "what is overdue": ("list_overdue_tasks", {}),
            "what do I have to do before June 7 2026": ("list_tasks_due_before", {"due_before": "2026-06-07", "inclusive": False}),
            "show tasks due by June 7 2026": ("list_tasks_due_before", {"due_before": "2026-06-07", "inclusive": True}),
            "what should I do today": ("list_today_tasks", {}),
            "what do I have to do on June 5 2026": ("list_today_tasks", {"date": "2026-06-05"}),
            "show tasks due 2026-06-05": ("list_today_tasks", {"date": "2026-06-05"}),
            "what tasks do I have that do not have due dates": ("list_unscheduled_tasks", {}),
            "tasks without due dates": ("list_unscheduled_tasks", {}),
            "daily brief": ("daily_brief", {}),
            "summarize today": ("daily_brief", {}),
            "what needs my attention": ("daily_brief", {}),
            "calendar status": ("calendar_status", {}),
            "sync calendar": ("sync_calendar", {}),
            "show upcoming meetings": ("list_upcoming_calendar_events", {"limit": 10}),
            "prep for my next meeting": ("prep_next_meeting", {}),
            "show suggestions": ("list_suggestions", {}),
            "confirm suggestion 3": ("confirm_suggestion", {"suggestion_id": 3}),
            "dismiss suggestion 3": ("dismiss_suggestion", {"suggestion_id": 3}),
            "snooze suggestion 3 until 2026-06-08": ("snooze_suggestion", {"suggestion_id": 3, "until": "2026-06-08"}),
            "what can you do": ("list_capabilities", {}),
            "bot status": ("bot_status", {}),
            "show bot sessions": ("list_bot_sessions", {}),
            "sync bot session 4": ("sync_bot_session", {"session_id": 4}),
            "process bot session 4": ("process_bot_session", {"session_id": 4}),
            "send bot to meeting https://meet.google.com/abc-defg-hij": (
                "join_meeting_bot",
                {
                    "meeting_url": "https://meet.google.com/abc-defg-hij",
                    "title": "Bot meeting",
                    "consent_confirmed": True,
                },
            ),
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
            "search tasks for onboarding": ("search_tasks", {"query": "onboarding"}),
            "search context for onboarding": ("search_context", {"topic": "onboarding"}),
            "search context graph for onboarding": ("search_context_graph", {"query": "onboarding"}),
            "draft email for context onboarding": (
                "draft_email_from_context",
                {"query": "onboarding", "instruction": "Draft a concise follow-up about onboarding."},
            ),
        }
        for command, expected in cases.items():
            parsed = parse_command(command)
            self.assertTrue(parsed.supported, command)
            self.assertEqual((parsed.action, parsed.payload), expected)
            self.assertIn(parsed.category, {"tasks", "commitments", "meetings", "email", "capture", "context", "brief", "calendar", "system_status"})

    def test_parse_calendar_today_command(self) -> None:
        parsed = parse_command("what is on my calendar today")
        self.assertEqual(parsed.action, "list_calendar_events")
        self.assertIn("from", parsed.payload)
        self.assertIn("to", parsed.payload)

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

    def test_execute_command_lists_tasks_due_before_date(self) -> None:
        self.repo.create_task("June fifth task", due_date="2026-06-05")
        self.repo.create_task("June seventh task", due_date="2026-06-07")
        self.repo.create_task("June eighth task", due_date="2026-06-08")

        before = execute_command(self.settings, self.repo, "what do I have to do before June 7 2026")
        by = execute_command(self.settings, self.repo, "show tasks due by June 7 2026")

        self.assertEqual(before["action"], "list_tasks_due_before")
        self.assertEqual([task["text"] for task in before["result"]["tasks"]], ["June fifth task"])
        self.assertIn("due before 2026-06-07", before["summary"])
        self.assertEqual([task["text"] for task in by["result"]["tasks"]], ["June fifth task", "June seventh task"])
        self.assertIn("due by 2026-06-07", by["summary"])

    def test_llm_overdue_action_with_due_before_payload_lists_future_deadlines(self) -> None:
        self.repo.create_task("June fifth task", due_date="2026-06-05")
        self.repo.create_task("June eighth task", due_date="2026-06-08")
        interpreted = {
            "supported": True,
            "action": "list_overdue_tasks",
            "category": "tasks",
            "payload": {"due_before": "2026-06-07"},
            "confidence": 0.95,
            "requires_confirmation": False,
            "explanation": "Mapped to tasks due before a date.",
            "safety_notes": [],
            "source": "llm",
        }

        with patch("speedwagon_ai.assistant_commands.interpret_command", return_value=interpreted):
            response = execute_command(self.settings, self.repo, "which deadlines are earlier than June 7")

        self.assertEqual(response["action"], "list_overdue_tasks")
        self.assertEqual([task["text"] for task in response["result"]["tasks"]], ["June fifth task"])
        self.assertIn("due before 2026-06-07", response["summary"])

    def test_execute_command_lists_unscheduled_tasks_only(self) -> None:
        self.repo.create_task("No due date task")
        self.repo.create_task("Scheduled task", due_date="2026-06-06")

        response = execute_command(self.settings, self.repo, "what tasks do I have that do not have due dates")

        self.assertEqual(response["action"], "list_unscheduled_tasks")
        self.assertEqual([task["text"] for task in response["result"]["tasks"]], ["No due date task"])
        self.assertIn("without due dates", response["summary"])

    def test_execute_command_searches_graph_and_suggestions(self) -> None:
        blocker = self.repo.create_task("Finish DairyMGT graph polish", project="DairyMGT")
        self.repo.create_task("Email Megan about DairyMGT updates", project="DairyMGT")
        self.repo.complete_task(blocker["id"])

        task_search = execute_command(self.settings, self.repo, "search tasks for DairyMGT")
        graph = execute_command(self.settings, self.repo, "search context graph for DairyMGT")
        suggestions = execute_command(self.settings, self.repo, "show suggestions")

        self.assertEqual(task_search["action"], "search_tasks")
        self.assertTrue(task_search["result"]["tasks"])
        self.assertEqual(graph["action"], "search_context_graph")
        self.assertTrue(graph["result"]["contexts"])
        self.assertEqual(suggestions["action"], "list_suggestions")
        self.assertTrue(suggestions["result"]["suggestions"])

    def test_execute_command_lists_bot_sessions(self) -> None:
        meeting = self.repo.create_meeting("Bot Command Meeting", source_type="meeting_bot")
        self.repo.create_bot_session(
            provider="fake",
            provider_bot_id="fake-1",
            meeting_id=meeting.id,
            meeting_url_display="https://meet.google.com/abc-defg-hij",
            meeting_url_hash="hash",
            title="Bot Command Meeting",
            status="transcript_ready",
            consent_confirmed=True,
        )

        response = execute_command(self.settings, self.repo, "show bot sessions")

        self.assertEqual(response["action"], "list_bot_sessions")
        self.assertEqual(response["result"]["sessions"][0]["title"], "Bot Command Meeting")

    def test_execute_command_lists_calendar_events_and_prep(self) -> None:
        self.repo.upsert_calendar_event(
            {
                "provider_event_id": "event-1",
                "calendar_id": "primary",
                "title": "DairyMGT review",
                "start_at": "2026-06-08T10:00:00-07:00",
                "end_at": "2026-06-08T10:30:00-07:00",
            }
        )

        upcoming = execute_command(self.settings, self.repo, "show upcoming meetings")
        prep = execute_command(self.settings, self.repo, "prep for my next meeting")

        self.assertEqual(upcoming["action"], "list_upcoming_calendar_events")
        self.assertEqual(upcoming["result"]["events"][0]["title"], "DairyMGT review")
        self.assertEqual(prep["action"], "prep_next_meeting")
        self.assertEqual(prep["result"]["event"]["title"], "DairyMGT review")

    def test_execute_command_can_dismiss_suggestion(self) -> None:
        suggestion = self.repo.create_suggestion(
            title="Schedule task",
            reason="No due date.",
            proposed_action="search_tasks",
            payload={"query": "demo"},
        )

        response = execute_command(self.settings, self.repo, f"dismiss suggestion {suggestion['id']}")

        self.assertEqual(response["action"], "dismiss_suggestion")
        self.assertEqual(response["result"]["suggestion"]["status"], "dismissed")

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
