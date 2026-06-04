from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from datetime import date
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from speedwagon_ai.app import make_handler
from speedwagon_ai.config import Settings
from speedwagon_ai.models import ExtractionResult, ExtractedItem
from speedwagon_ai.meeting_bot import FakeMeetingBotProvider
from speedwagon_ai.screenshot_context import build_analysis_response
from speedwagon_ai.storage import Repository


class AppApiTests(unittest.TestCase):
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
            app_port=0,
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
        meeting = self.repo.create_meeting("API Meeting")
        self.repo.save_extraction(
            meeting.id,
            ExtractionResult(
                summary="API test summary.",
                action_items=[ExtractedItem("Review API")],
                decisions=["Use local HTTP API"],
                key_topics=["API"],
                raw={"summary": "API test summary."},
            ),
        )
        handler = make_handler(self.settings, self.repo)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.daemon = True
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.tmp.cleanup()

    def test_meetings_and_detail_api(self) -> None:
        meetings = self.get_json("/api/meetings")
        self.assertEqual(meetings["meetings"][0]["title"], "API Meeting")

        detail = self.get_json("/api/meetings/1")
        self.assertEqual(detail["meeting"]["summary"], "API test summary.")
        self.assertEqual(detail["decisions"][0]["text"], "Use local HTTP API")

    def test_email_preview_api(self) -> None:
        preview = self.post_json(
            "/api/meetings/1/email/preview",
            {"to": "person@example.com", "instruction": "Focus on the decision."},
        )
        self.assertEqual(preview["to"], "person@example.com")
        self.assertNotIn("Focus on the decision.", preview["body"])
        self.assertEqual(preview["provider"], "fallback")

    def test_email_draft_api_uses_edited_body(self) -> None:
        with patch("speedwagon_ai.app.create_gmail_draft", return_value="draft-1") as create_draft:
            response = self.post_json(
                "/api/meetings/1/email/draft",
                {
                    "to": "person@example.com",
                    "subject": "Edited subject",
                    "instruction": "Make it shorter.",
                    "body": "Hi,\n\nThis is the edited body.\n\nThanks,",
                },
            )
        self.assertEqual(response["draft_id"], "draft-1")
        self.assertEqual(create_draft.call_args.kwargs["body"], "Hi,\n\nThis is the edited body.\n\nThanks,")

    def test_context_and_settings_api(self) -> None:
        context = self.get_json("/api/context?topic=API")
        self.assertIn("API Meeting", context["markdown"])

        settings = self.get_json("/api/settings")
        self.assertFalse(settings["openai_key_present"])
        self.assertIn("recorder_status", settings)

    def test_capture_status_and_diagnostics_api(self) -> None:
        status = self.get_json("/api/capture/status")
        self.assertFalse(status["active"])

        diagnostics = self.get_json("/api/capture/diagnostics")
        self.assertIn("recorder_status", diagnostics)
        self.assertIn("warnings", diagnostics)

    def test_capture_start_and_stop_meeting_api(self) -> None:
        class FakeProcess:
            pid = 99999

            def poll(self) -> None:
                return None

        with patch("speedwagon_ai.capture.subprocess.Popen", return_value=FakeProcess()), patch("speedwagon_ai.capture.os.kill"):
            started = self.post_json("/api/capture/local/start", {"kind": "meeting", "title": "Capture API"})
            audio_path = Path(started["session"]["audio_path"])
            audio_path.write_bytes(b"0" * 5000)
            stopped = self.post_json("/api/capture/local/stop", {"process": False})

        self.assertEqual(started["session"]["kind"], "meeting")
        self.assertEqual(stopped["meeting_id"], started["session"]["meeting_id"])
        self.assertEqual(stopped["session"]["file_size"], 5000)

    def test_capture_stop_process_meeting_api(self) -> None:
        class FakeProcess:
            pid = 99998

            def poll(self) -> None:
                return None

        with patch("speedwagon_ai.capture.subprocess.Popen", return_value=FakeProcess()), patch("speedwagon_ai.capture.os.kill"):
            started = self.post_json("/api/capture/local/start", {"kind": "meeting", "title": "Process Capture API"})
            audio_path = Path(started["session"]["audio_path"])
            audio_path.write_bytes(b"0" * 5000)
            meeting = self.repo.get_meeting(started["session"]["meeting_id"])
            with patch(
                "speedwagon_ai.app.process_meeting",
                return_value={
                    "meeting": meeting,
                    "transcript_path": self.settings.transcripts_dir / "meeting.txt",
                    "note_path": self.settings.notes_dir / "meeting.md",
                    "commitments_path": self.settings.notes_dir / "commitments.md",
                },
            ):
                stopped = self.post_json("/api/capture/local/stop", {"process": True})

        self.assertEqual(stopped["meeting_id"], started["session"]["meeting_id"])
        self.assertEqual(stopped["transcript_path"], str(self.settings.transcripts_dir / "meeting.txt"))

    def test_native_capture_prepare_complete_and_fail_api(self) -> None:
        prepared = self.post_json(
            "/api/capture/native/prepare",
            {"kind": "meeting", "title": "Native Meeting", "mode": "system_mic"},
        )
        session = prepared["session"]
        self.assertTrue(session["active"])
        self.assertTrue(session["native"])
        self.assertEqual(session["capture_profile"], "native_screencapturekit")
        self.assertTrue(session["audio_path"].endswith(f"meeting-{session['meeting_id']}.wav"))
        self.assertTrue(session["system_audio_path"].endswith(f"meeting-{session['meeting_id']}-system.wav"))
        self.assertTrue(session["microphone_audio_path"].endswith(f"meeting-{session['meeting_id']}-mic.wav"))

        status = self.get_json("/api/capture/status")
        self.assertEqual(status["session_id"], session["session_id"])

        final_audio = Path(session["audio_path"])
        final_audio.write_bytes(b"RIFFWAVE" + b"0" * 5000)
        completed = self.post_json(
            "/api/capture/native/complete",
            {
                "session_id": session["session_id"],
                "audio_path": session["audio_path"],
                "process": False,
                "warnings": ["mic unavailable, captured system audio only"],
            },
        )
        self.assertFalse(completed["session"]["active"])
        self.assertEqual(completed["meeting_id"], session["meeting_id"])
        self.assertEqual(completed["session"]["warnings"], ["mic unavailable, captured system audio only"])
        meeting = self.repo.get_meeting(session["meeting_id"])
        self.assertEqual(meeting.audio_path, session["audio_path"])
        self.assertIsNotNone(meeting.ended_at)

        failed_prepare = self.post_json(
            "/api/capture/native/prepare",
            {"kind": "meeting", "title": "Native Failure", "mode": "system_mic"},
        )
        failed = self.post_json(
            "/api/capture/native/fail",
            {"session_id": failed_prepare["session"]["session_id"], "error": "permission denied"},
        )
        self.assertFalse(failed["session"]["active"])
        self.assertEqual(failed["session"]["status"], "failed")
        self.assertEqual(failed["session"]["last_error"], "permission denied")

    def test_native_capture_complete_process_calls_existing_pipeline(self) -> None:
        prepared = self.post_json(
            "/api/capture/native/prepare",
            {"kind": "meeting", "title": "Native Process", "mode": "system_mic"},
        )
        session = prepared["session"]
        Path(session["audio_path"]).write_bytes(b"RIFFWAVE" + b"1" * 5000)
        meeting = self.repo.get_meeting(session["meeting_id"])
        with patch(
            "speedwagon_ai.app.process_meeting",
            return_value={
                "meeting": meeting,
                "transcript_path": self.settings.transcripts_dir / "native.txt",
                "note_path": self.settings.notes_dir / "native.md",
                "commitments_path": self.settings.notes_dir / "commitments.md",
            },
        ) as process:
            completed = self.post_json(
                "/api/capture/native/complete",
                {
                    "session_id": session["session_id"],
                    "audio_path": session["audio_path"],
                    "process": True,
                    "warnings": [],
                },
            )

        process.assert_called_once_with(self.settings, self.repo, session["meeting_id"])
        self.assertEqual(completed["transcript_path"], str(self.settings.transcripts_dir / "native.txt"))

    def test_assistant_voice_start_stop_runs_transcribed_command(self) -> None:
        class FakeProcess:
            pid = 99997

            def poll(self) -> None:
                return None

        def fake_transcribe(settings: Settings, audio_path: Path, output_base: Path) -> Path:
            transcript_path = settings.transcripts_dir / "assistant-voice.txt"
            transcript_path.parent.mkdir(parents=True, exist_ok=True)
            transcript_path.write_text("add task send voice recap due 2026-06-01", encoding="utf-8")
            return transcript_path

        with patch("speedwagon_ai.capture.subprocess.Popen", return_value=FakeProcess()), patch("speedwagon_ai.capture.os.kill"):
            started = self.post_json("/api/assistant/voice/start", {})
            Path(started["session"]["audio_path"]).write_bytes(b"0" * 5000)
            with patch("speedwagon_ai.capture.transcribe_audio", side_effect=fake_transcribe):
                stopped = self.post_json("/api/assistant/voice/stop", {})

        self.assertEqual(started["session"]["kind"], "assistant_voice")
        self.assertEqual(stopped["transcript"], "add task send voice recap due 2026-06-01")
        self.assertEqual(stopped["assistant_response"]["action"], "add_task")
        self.assertEqual(stopped["assistant_response"]["result"]["task"]["text"], "send voice recap")

    def test_assistant_voice_unsupported_transcript_is_visible(self) -> None:
        class FakeProcess:
            pid = 99996

            def poll(self) -> None:
                return None

        def fake_transcribe(settings: Settings, audio_path: Path, output_base: Path) -> Path:
            transcript_path = settings.transcripts_dir / "assistant-voice-unsupported.txt"
            transcript_path.parent.mkdir(parents=True, exist_ok=True)
            transcript_path.write_text("please handle my life", encoding="utf-8")
            return transcript_path

        with patch("speedwagon_ai.capture.subprocess.Popen", return_value=FakeProcess()), patch("speedwagon_ai.capture.os.kill"):
            started = self.post_json("/api/assistant/voice/start", {})
            Path(started["session"]["audio_path"]).write_bytes(b"0" * 5000)
            with patch("speedwagon_ai.capture.transcribe_audio", side_effect=fake_transcribe):
                stopped = self.post_json("/api/assistant/voice/stop", {})

        self.assertEqual(stopped["transcript"], "please handle my life")
        self.assertFalse(stopped["assistant_response"]["supported"])
        self.assertIn("Unsupported command", stopped["assistant_response"]["summary"])

    def test_voice_task_stop_extracts_due_date_from_transcript(self) -> None:
        class FakeProcess:
            pid = 99995

            def poll(self) -> None:
                return None

        def fake_transcribe(settings: Settings, audio_path: Path, output_base: Path) -> Path:
            transcript_path = settings.transcripts_dir / "voice-task.txt"
            transcript_path.parent.mkdir(parents=True, exist_ok=True)
            transcript_path.write_text("send app update to Megan by June 8", encoding="utf-8")
            return transcript_path

        with patch("speedwagon_ai.capture.subprocess.Popen", return_value=FakeProcess()), patch("speedwagon_ai.capture.os.kill"):
            started = self.post_json("/api/tasks/record/start", {})
            Path(started["audio_path"]).write_bytes(b"0" * 5000)
            with patch("speedwagon_ai.capture.transcribe_audio", side_effect=fake_transcribe):
                stopped = self.post_json("/api/tasks/record/stop", {})

        self.assertEqual(stopped["task"]["text"], "send app update to Megan")
        self.assertEqual(stopped["task"]["due_date"], date(date.today().year, 6, 8).isoformat())
        self.assertEqual(stopped["transcript"], "send app update to Megan by June 8")

    def test_task_api_create_complete_reopen_and_overdue(self) -> None:
        created = self.post_json(
            "/api/tasks",
            {"text": "Send task API notes", "owner": "Anish", "owed_to": "Alex", "project": "API", "due_date": "2020-01-01"},
        )
        task_id = created["task"]["id"]
        self.assertEqual(created["task"]["owed_to"], "Alex")
        self.assertEqual(created["task"]["project"], "API")
        tasks = self.get_json("/api/tasks?status=&include_done=true")
        self.assertTrue(any(task["id"] == task_id for task in tasks["tasks"]))

        overdue = self.get_json("/api/tasks/overdue")
        self.assertTrue(any(task["id"] == task_id for task in overdue["tasks"]))

        completed = self.post_json(f"/api/tasks/{task_id}/complete", {})
        self.assertEqual(completed["task"]["status"], "done")

        reopened = self.post_json(f"/api/tasks/{task_id}/reopen", {})
        self.assertEqual(reopened["task"]["status"], "open")

        snoozed = self.post_json(f"/api/commitments/{task_id}/snooze", {"until": "2026-06-05"})
        self.assertEqual(snoozed["commitment"]["status"], "snoozed")
        self.assertEqual(snoozed["commitment"]["snoozed_until"], "2026-06-05")

        confirmed = self.post_json(f"/api/commitments/{task_id}/confirm", {})
        self.assertEqual(confirmed["commitment"]["status"], "done")

    def test_assistant_action_api(self) -> None:
        self.post_json("/api/tasks", {"text": "Overdue action", "due_date": "2020-01-01"})
        result = self.post_json("/api/actions", {"action": "list_overdue_tasks", "payload": {}})
        self.assertTrue(any(task["text"] == "Overdue action" for task in result["tasks"]))

    def test_assistant_command_api(self) -> None:
        added = self.post_json("/api/assistant/command", {"command": "add task write API notes due 2026-06-01"})
        self.assertEqual(added["action"], "add_task")
        self.assertEqual(added["category"], "tasks")
        task_id = added["result"]["task"]["id"]

        completed = self.post_json("/api/assistant/command", {"command": f"complete task {task_id}"})
        self.assertEqual(completed["result"]["task"]["status"], "done")

        capabilities = self.get_json("/api/assistant/capabilities")
        self.assertTrue(capabilities["capabilities"])

        command_capabilities = self.post_json("/api/assistant/command", {"command": "what can you do"})
        self.assertEqual(command_capabilities["action"], "list_capabilities")
        self.assertTrue(command_capabilities["result"]["capabilities"])

    def test_context_graph_and_suggestion_apis(self) -> None:
        blocker = self.post_json("/api/tasks", {"text": "Finish DairyMGT tabs", "project": "DairyMGT"})
        email = self.post_json("/api/tasks", {"text": "Email Megan about DairyMGT updates", "project": "DairyMGT"})
        self.post_json(f"/api/tasks/{blocker['task']['id']}/complete", {})

        graph = self.get_json("/api/context-graph?query=DairyMGT")
        suggestions = self.get_json("/api/suggestions")
        suggestion = next(item for item in suggestions["suggestions"] if item["proposed_action"] == "draft_email_from_context")

        self.assertTrue(any(context["name"] == "DairyMGT" for context in graph["contexts"]))
        self.assertTrue(any(task["id"] == email["task"]["id"] for task in graph["tasks"]))
        self.assertEqual(suggestion["context"]["name"], "DairyMGT")

        snoozed = self.post_json(f"/api/suggestions/{suggestion['id']}/snooze", {"until": "2026-06-08"})
        self.assertEqual(snoozed["suggestion"]["status"], "snoozed")
        self.assertEqual(snoozed["suggestion"]["snoozed_until"], "2026-06-08")

        dismissed = self.post_json(f"/api/suggestions/{suggestion['id']}/dismiss", {})
        self.assertEqual(dismissed["suggestion"]["status"], "dismissed")

        confirm_me = self.repo.create_suggestion(
            title="Search related tasks",
            reason="Related work is visible.",
            proposed_action="search_tasks",
            payload={"query": "DairyMGT"},
        )
        confirmed = self.post_json(f"/api/suggestions/{confirm_me['id']}/confirm", {})
        self.assertEqual(confirmed["suggestion"]["status"], "accepted")
        self.assertTrue(confirmed["action_result"]["tasks"])

    def test_notification_apis(self) -> None:
        task = self.post_json("/api/tasks", {"text": "Send notification follow-up", "due_date": "2026-06-01"})["task"]

        status = self.get_json("/api/notifications/status")
        self.assertEqual(status["delivery"], "native_app")
        self.assertGreaterEqual(status["candidate_count"], 1)

        candidates = self.get_json("/api/notifications/candidates")
        suggestion = next(item for item in candidates["candidates"] if task["id"] in item["task_ids"])
        self.assertEqual(suggestion["notification_status"], "candidate")
        self.assertTrue(suggestion["source_fingerprint"])

        delivered = self.post_json(f"/api/notifications/{suggestion['id']}/mark-delivered", {})
        self.assertEqual(delivered["suggestion"]["notification_status"], "delivered")
        self.assertEqual(delivered["notification"]["status"], "delivered")

        snoozed = self.post_json(f"/api/notifications/{suggestion['id']}/snooze", {"until": "2026-06-09"})
        self.assertEqual(snoozed["suggestion"]["notification_status"], "snoozed")
        self.assertEqual(snoozed["suggestion"]["next_notify_at"], "2026-06-09")

        dismissed = self.post_json(f"/api/notifications/{suggestion['id']}/dismiss", {})
        self.assertEqual(dismissed["suggestion"]["status"], "dismissed")

    def test_general_assistant_meeting_commands(self) -> None:
        raw = self.repo.create_meeting("Raw Assistant Meeting", audio_path="audio/raw.wav")
        unprocessed = self.post_json("/api/assistant/command", {"command": "show unprocessed meetings"})
        self.assertEqual(unprocessed["action"], "list_unprocessed_meetings")
        self.assertTrue(any(meeting["id"] == raw.id for meeting in unprocessed["result"]["meetings"]))

    def test_pending_action_confirm_and_cancel_api(self) -> None:
        pending = self.repo.create_pending_action(
            command="please add a task",
            action="add_task",
            category="tasks",
            payload={"text": "Confirm API task", "due_date": "2026-06-01"},
            confidence=0.8,
            source="llm",
            explanation="Interpreted as task creation.",
            safety_notes=["Requires confirmation."],
        )

        listed = self.get_json("/api/assistant/actions")
        self.assertTrue(any(action["id"] == pending["id"] for action in listed["actions"]))

        confirmed = self.post_json(f"/api/assistant/actions/{pending['id']}/confirm", {})
        self.assertEqual(confirmed["action"], "add_task")
        self.assertEqual(confirmed["result"]["task"]["text"], "Confirm API task")
        self.assertEqual(confirmed["result"]["pending_action"]["status"], "confirmed")

        cancel_me = self.repo.create_pending_action(
            command="cancel me",
            action="add_task",
            category="tasks",
            payload={"text": "Canceled API task"},
            confidence=0.8,
        )
        canceled = self.post_json(f"/api/assistant/actions/{cancel_me['id']}/cancel", {})
        self.assertEqual(canceled["result"]["pending_action"]["status"], "canceled")

    def test_screenshot_analysis_api_accepts_base64_png(self) -> None:
        tiny_png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
        mocked = {
            "summary": "A project checklist is visible.",
            "visible_text": ["Send recap"],
            "suggested_tasks": [{"text": "Send recap", "due_date": None, "owner": None, "project": None, "confidence": 0.7}],
            "suggested_context_topics": ["project checklist"],
            "suggested_actions": [],
            "pending_actions": [
                {
                    "id": 99,
                    "command": "screenshot",
                    "action": "add_task",
                    "category": "tasks",
                    "payload": {"text": "Send recap"},
                    "confidence": 0.7,
                    "source": "screenshot",
                    "explanation": "Suggested from screenshot context.",
                    "safety_notes": [],
                    "status": "pending",
                    "created_at": "2026-06-03T00:00:00Z",
                    "updated_at": "2026-06-03T00:00:00Z",
                    "expires_at": None,
                }
            ],
            "confidence": 0.7,
            "provider": "mock",
        }
        with patch("speedwagon_ai.app.analyze_screenshot", return_value=mocked) as analyze:
            response = self.post_json(
                "/api/assistant/screenshot/analyze",
                {"image_base64": tiny_png, "instruction": "find follow-up tasks"},
            )

        analyze.assert_called_once()
        self.assertEqual(response["summary"], "A project checklist is visible.")
        self.assertEqual(response["pending_actions"][0]["action"], "add_task")

    def test_screenshot_analysis_dedupes_same_task_suggestions(self) -> None:
        class FixedDate(date):
            @classmethod
            def today(cls) -> date:
                return cls(2026, 6, 4)

        raw = {
            "summary": "A document asks for a status email.",
            "visible_text": ["Send an email to Manasa about SpeedwagonAI by June 7th"],
            "suggested_tasks": [
                {
                    "text": "Send an email to Manasa about SpeedwagonAI",
                    "due_date": "2023-06-07",
                    "project": "SpeedwagonAI",
                    "confidence": 0.95,
                }
            ],
            "suggested_context_topics": ["SpeedwagonAI"],
            "suggested_actions": [
                {
                    "action": "add_task",
                    "payload": {
                        "text": "Send an email to Manasa about SpeedwagonAI",
                        "due_date": "2023-06-07",
                        "project": "SpeedwagonAI",
                    },
                    "confidence": 0.95,
                    "explanation": "The screenshot contains a task.",
                }
            ],
            "confidence": 0.95,
            "provider": "mock",
        }

        with patch("speedwagon_ai.screenshot_context.date", FixedDate):
            response = build_analysis_response(self.repo, raw, command="screenshot")

        self.assertEqual(len(response["pending_actions"]), 1)
        self.assertEqual(response["pending_actions"][0]["payload"]["due_date"], "2026-06-07")

    def test_commitments_daily_brief_and_future_surface_apis(self) -> None:
        created = self.post_json("/api/tasks", {"text": "Brief API task", "due_date": "2020-01-01"})
        self.repo.upsert_calendar_event(
            {
                "provider_event_id": "event-1",
                "calendar_id": "primary",
                "title": "Calendar API review",
                "start_at": "2026-06-08T10:00:00-07:00",
                "end_at": "2026-06-08T10:30:00-07:00",
            }
        )
        commitments = self.get_json("/api/commitments")
        self.assertIn("commitments", commitments)
        self.assertTrue(any(item["id"] == created["task"]["id"] for item in commitments["items"]))

        brief = self.get_json("/api/daily-brief")
        self.assertTrue(any(task["text"] == "Brief API task" for task in brief["overdue"]))
        self.assertIn("calendar_upcoming", brief)

        google = self.get_json("/api/integrations/google/status")
        self.assertIn("gmail_drafts", google)
        self.assertIn("calendar_status", google)

        calendar_status = self.get_json("/api/calendar/status")
        self.assertEqual(calendar_status["status"], "missing_credentials")

        upcoming = self.get_json("/api/calendar/upcoming")
        self.assertTrue(any(event["title"] == "Calendar API review" for event in upcoming["events"]))

        apple = self.get_json("/api/integrations/apple/reminders")
        self.assertFalse(apple["available"])

        bot = self.get_json("/api/capture/bot/status")
        self.assertFalse(bot["enabled"])

    def test_bot_capture_api_join_sync_and_process_with_fake_provider(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as failure:
            self.post_json(
                "/api/capture/bot/join",
                {"meeting_url": "https://meet.google.com/abc-defg-hij", "title": "No Consent"},
            )
        self.assertEqual(failure.exception.code, 500)

        with patch("speedwagon_ai.meeting_bot.provider_from_settings", return_value=FakeMeetingBotProvider(self.settings)):
            joined = self.post_json(
                "/api/capture/bot/join",
                {
                    "meeting_url": "https://meet.google.com/abc-defg-hij?authuser=0",
                    "title": "Bot API",
                    "consent_confirmed": True,
                },
            )
            session = joined["session"]
            sessions = self.get_json("/api/capture/bot/sessions")
            synced = self.post_json(f"/api/capture/bot/sessions/{session['id']}/sync", {})

            meeting = self.repo.get_meeting(session["meeting_id"])
            with patch(
                "speedwagon_ai.meeting_bot.process_meeting",
                return_value={
                    "meeting": meeting,
                    "transcript_path": Path(synced["transcript_path"]),
                    "note_path": self.settings.notes_dir / "bot-api.md",
                    "commitments_path": self.settings.notes_dir / "commitments.md",
                },
            ):
                processed = self.post_json(f"/api/capture/bot/sessions/{session['id']}/process", {})

        self.assertTrue(any(item["id"] == session["id"] for item in sessions["sessions"]))
        self.assertEqual(session["meeting_url_display"], "https://meet.google.com/abc-defg-hij")
        self.assertTrue(Path(synced["transcript_path"]).exists())
        self.assertEqual(processed["meeting"]["id"], session["meeting_id"])

    def test_calendar_sync_api_uses_service(self) -> None:
        with patch(
            "speedwagon_ai.app.GoogleCalendarService.sync",
            return_value={
                "status": "synced",
                "provider": "google",
                "calendar_ids": ["primary"],
                "time_min": "2026-05-21T00:00:00Z",
                "time_max": "2026-07-04T00:00:00Z",
                "synced_count": 1,
                "events": [],
            },
        ) as sync:
            result = self.post_json("/api/calendar/sync", {})

        sync.assert_called_once()
        self.assertEqual(result["synced_count"], 1)

    def get_json(self, path: str) -> dict:
        with urllib.request.urlopen(f"{self.base_url}{path}", timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def post_json(self, path: str, payload: dict) -> dict:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
