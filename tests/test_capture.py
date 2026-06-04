from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from speedwagon_ai.capture import CaptureService, recorder_command
from speedwagon_ai.config import Settings
from speedwagon_ai.storage import Repository


class RecorderCommandTests(unittest.TestCase):
    def test_configured_command_injects_output(self) -> None:
        command = recorder_command("rec -c 1 {output}", Path("audio/test.wav"))
        self.assertEqual(command, ["rec", "-c", "1", "audio/test.wav"])

    def test_auto_detects_rec(self) -> None:
        with patch("speedwagon_ai.capture.shutil.which", side_effect=lambda name: "/opt/homebrew/bin/rec" if name == "rec" else None):
            command = recorder_command("", Path("audio/test.wav"))
        self.assertEqual(command, ["/opt/homebrew/bin/rec", "-c", "1", "-r", "16000", "audio/test.wav"])

    def test_mic_profile_can_use_named_coreaudio_device(self) -> None:
        with patch("speedwagon_ai.capture.shutil.which", side_effect=lambda name: "/opt/homebrew/bin/rec" if name == "rec" else None):
            command = recorder_command("", Path("audio/test.wav"), profile="mic", input_device="MacBook Air Microphone")
        self.assertEqual(
            command,
            ["/opt/homebrew/bin/rec", "-t", "coreaudio", "MacBook Air Microphone", "-c", "1", "-r", "16000", "audio/test.wav"],
        )

    def test_blackhole_profile_uses_coreaudio_device(self) -> None:
        with patch("speedwagon_ai.capture.shutil.which", side_effect=lambda name: "/opt/homebrew/bin/rec" if name == "rec" else None):
            command = recorder_command("", Path("audio/test.wav"), profile="blackhole", input_device="BlackHole 2ch")
        self.assertEqual(
            command,
            ["/opt/homebrew/bin/rec", "-t", "coreaudio", "BlackHole 2ch", "-c", "2", "-r", "48000", "audio/test.wav"],
        )

    def test_raises_clear_error_when_no_recorder_exists(self) -> None:
        with patch("speedwagon_ai.capture.shutil.which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "brew install sox"):
                recorder_command("", Path("audio/test.wav"))

    def test_ffmpeg_fallback_for_mic_profile(self) -> None:
        with patch("speedwagon_ai.capture.shutil.which", side_effect=lambda name: "/opt/homebrew/bin/ffmpeg" if name == "ffmpeg" else None):
            command = recorder_command("", Path("audio/test.wav"))
        self.assertEqual(
            command,
            ["/opt/homebrew/bin/ffmpeg", "-f", "avfoundation", "-i", ":0", "-ac", "1", "-ar", "16000", "audio/test.wav"],
        )

    def test_diagnostics_reports_profile_warnings_without_audio_hardware(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root)
            repo = Repository(settings.db_path)
            repo.init()
            with patch("speedwagon_ai.capture.shutil.which", side_effect=lambda name: "/opt/homebrew/bin/rec" if name == "rec" else None):
                diagnostics = CaptureService(settings, repo).diagnostics()
        self.assertEqual(diagnostics["capture_profile"], "mic")
        self.assertEqual(diagnostics["recorder_status"], "available")
        self.assertTrue(any("Mic mode" in warning for warning in diagnostics["warnings"]))

    def test_enriches_existing_meeting_session_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root)
            repo = Repository(settings.db_path)
            repo.init()
            settings.ensure_dirs()
            audio = settings.audio_dir / "meeting-1.wav"
            audio.write_bytes(b"0" * 5000)
            log = settings.state_path.parent / "recording-meeting-1.log"
            log.write_text("recording ok", encoding="utf-8")
            settings.state_path.write_text(
                """
                {
                  "kind": "meeting",
                  "meeting_id": 1,
                  "pid": 123,
                  "title": "Planning",
                  "audio_path": "%s",
                  "log_path": "%s",
                  "command": ["rec"],
                  "capture_profile": "mic",
                  "input_device": "",
                  "started_at": "2026-06-03T10:00:00"
                }
                """
                % (audio, log),
                encoding="utf-8",
            )
            status = CaptureService(settings, repo).status()
        self.assertTrue(status["active"])
        self.assertEqual(status["kind"], "meeting")
        self.assertEqual(status["file_size"], 5000)
        self.assertTrue(status["output_file_ok"])


def make_settings(root: Path) -> Settings:
    return Settings(
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


if __name__ == "__main__":
    unittest.main()
