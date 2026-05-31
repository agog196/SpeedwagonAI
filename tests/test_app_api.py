from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

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
        self.assertIn("Focus on the decision.", preview["body"])

    def test_context_and_settings_api(self) -> None:
        context = self.get_json("/api/context?topic=API")
        self.assertIn("API Meeting", context["markdown"])

        settings = self.get_json("/api/settings")
        self.assertFalse(settings["openai_key_present"])
        self.assertIn("recorder_status", settings)

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
