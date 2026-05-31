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

    def test_task_api_create_complete_reopen_and_overdue(self) -> None:
        created = self.post_json(
            "/api/tasks",
            {"text": "Send task API notes", "owner": "Anish", "due_date": "2020-01-01"},
        )
        task_id = created["task"]["id"]
        tasks = self.get_json("/api/tasks?status=&include_done=true")
        self.assertTrue(any(task["id"] == task_id for task in tasks["tasks"]))

        overdue = self.get_json("/api/tasks/overdue")
        self.assertTrue(any(task["id"] == task_id for task in overdue["tasks"]))

        completed = self.post_json(f"/api/tasks/{task_id}/complete", {})
        self.assertEqual(completed["task"]["status"], "done")

        reopened = self.post_json(f"/api/tasks/{task_id}/reopen", {})
        self.assertEqual(reopened["task"]["status"], "open")

    def test_assistant_action_api(self) -> None:
        self.post_json("/api/tasks", {"text": "Overdue action", "due_date": "2020-01-01"})
        result = self.post_json("/api/actions", {"action": "list_overdue_tasks", "payload": {}})
        self.assertTrue(any(task["text"] == "Overdue action" for task in result["tasks"]))

    def test_assistant_command_api(self) -> None:
        added = self.post_json("/api/assistant/command", {"command": "add task write API notes due 2026-06-01"})
        self.assertEqual(added["action"], "add_task")
        task_id = added["result"]["task"]["id"]

        completed = self.post_json("/api/assistant/command", {"command": f"complete task {task_id}"})
        self.assertEqual(completed["result"]["task"]["status"], "done")

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
