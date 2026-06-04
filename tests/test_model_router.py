from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from speedwagon_ai.config import Settings
from speedwagon_ai.model_router import choose_model, web_search_enabled


class ModelRouterTests(unittest.TestCase):
    def make_settings(self) -> Settings:
        root = Path(tempfile.gettempdir())
        return Settings(
            db_path=root / "speedwagon.db",
            notes_dir=root / "notes",
            audio_dir=root / "audio",
            transcripts_dir=root / "transcripts",
            state_path=root / "recording.json",
            app_host="127.0.0.1",
            app_port=8765,
            record_cmd="",
            capture_profile="mic",
            input_device="",
            whisper_cpp_bin="",
            whisper_cpp_model="",
            llm_provider="openai",
            openai_api_key="",
            openai_model="default-mini",
            anthropic_api_key="",
            gmail_credentials_path=root / "google_credentials.json",
            gmail_token_path=root / "google_token.json",
        )

    def test_routes_routine_and_strong_operations(self) -> None:
        settings = self.make_settings()
        with patch.dict(
            os.environ,
            {
                "SPEEDWAGON_MODEL_CHEAP": "cheap-model",
                "SPEEDWAGON_MODEL_STRONG": "strong-model",
                "SPEEDWAGON_MODEL_WEB": "web-model",
                "SPEEDWAGON_MODEL_COMMAND": "command-model",
                "SPEEDWAGON_MODEL_VISION": "vision-model",
                "SPEEDWAGON_ENABLE_WEB_SEARCH": "true",
            },
        ):
            self.assertEqual(choose_model(settings, "email_draft").model, "cheap-model")
            self.assertEqual(choose_model(settings, "deep_synthesis").model, "strong-model")
            self.assertEqual(choose_model(settings, "web_search").model, "web-model")
            self.assertEqual(choose_model(settings, "command_parse").model, "command-model")
            self.assertEqual(choose_model(settings, "vision_context").model, "vision-model")
            self.assertTrue(web_search_enabled())


if __name__ == "__main__":
    unittest.main()
