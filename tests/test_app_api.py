from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from speedwagon_ai.app import make_handler
from speedwagon_ai.config import Settings
from speedwagon_ai.models import ExtractionResult, ExtractedItem
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

    def test_commitments_daily_brief_and_future_surface_apis(self) -> None:
        created = self.post_json("/api/tasks", {"text": "Brief API task", "due_date": "2020-01-01"})
        commitments = self.get_json("/api/commitments")
        self.assertIn("commitments", commitments)
        self.assertTrue(any(item["id"] == created["task"]["id"] for item in commitments["items"]))

        brief = self.get_json("/api/daily-brief")
        self.assertTrue(any(task["text"] == "Brief API task" for task in brief["overdue"]))

        google = self.get_json("/api/integrations/google/status")
        self.assertIn("gmail_drafts", google)

        apple = self.get_json("/api/integrations/apple/reminders")
        self.assertFalse(apple["available"])

        bot = self.get_json("/api/capture/bot/status")
        self.assertFalse(bot["enabled"])

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
