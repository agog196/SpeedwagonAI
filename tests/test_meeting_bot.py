from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from speedwagon_ai.config import Settings
from speedwagon_ai.meeting_bot import FakeMeetingBotProvider, MeetingBotService, RecallMeetingBotProvider, normalize_transcript, redact_meeting_url
from speedwagon_ai.storage import Repository


class MeetingBotTests(unittest.TestCase):
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
            bot_provider="fake",
        )
        self.repo = Repository(self.settings.db_path)
        self.repo.init()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_redacts_meeting_url_query(self) -> None:
        self.assertEqual(
            redact_meeting_url("https://zoom.us/j/123?pwd=secret"),
            "https://zoom.us/j/123",
        )

    def test_normalizes_recall_transcript_segments(self) -> None:
        text = normalize_transcript(
            [
                {"speaker": "Alex", "words": [{"text": "Ship"}, {"text": "it"}]},
                {"speaker": "Megan", "text": "Looks good."},
            ]
        )
        self.assertEqual(text, "Alex: Ship it\nMegan: Looks good.")

    def test_recall_sync_uses_current_transcript_download_url(self) -> None:
        settings = self._recall_settings()
        provider = RecallMeetingBotProvider(settings)
        with patch.object(provider, "_request") as request, patch.object(provider, "_request_url") as request_url:
            request.return_value = {
                "id": "bot-1",
                "status": "done",
                "recordings": [
                    {
                        "id": "recording-1",
                        "media_shortcuts": {
                            "transcript": {
                                "id": "transcript-1",
                                "data": {"download_url": "https://us-west-2.recall.ai/api/v1/download/transcript/example"},
                            }
                        },
                    }
                ],
            }
            request_url.return_value = [
                {"speaker": "Alex", "words": [{"text": "Send"}, {"text": "notes"}]},
                {"speaker": "Megan", "text": "Thanks."},
            ]

            synced = provider.sync("bot-1")

        request.assert_called_once_with("GET", "/bot/bot-1/")
        request_url.assert_called_once_with("https://us-west-2.recall.ai/api/v1/download/transcript/example")
        self.assertEqual(synced.status, "transcript_ready")
        self.assertEqual(synced.transcript_text, "Alex: Send notes\nMegan: Thanks.")

    def test_recall_sync_lists_transcripts_by_recording_when_shortcut_is_missing(self) -> None:
        settings = self._recall_settings()
        provider = RecallMeetingBotProvider(settings)
        with patch.object(provider, "_request") as request, patch.object(provider, "_request_url") as request_url:
            request.side_effect = [
                {"id": "bot-1", "status": "done", "recordings": [{"id": "recording-1"}]},
                {"results": [{"id": "transcript-1", "data": {"download_url": "/download/transcript/example"}}]},
            ]
            request_url.return_value = [{"speaker": "Alex", "text": "Fallback works."}]

            synced = provider.sync("bot-1")

        self.assertEqual(
            [call.args for call in request.call_args_list],
            [
                ("GET", "/bot/bot-1/"),
                ("GET", "/transcript/?recording_id=recording-1"),
            ],
        )
        request_url.assert_called_once_with("/download/transcript/example")
        self.assertEqual(synced.status, "transcript_ready")
        self.assertEqual(synced.transcript_text, "Alex: Fallback works.")

    def test_recall_sync_requests_async_transcript_when_recording_has_no_transcript_artifact(self) -> None:
        settings = self._recall_settings()
        provider = RecallMeetingBotProvider(settings)
        with patch.object(provider, "_request") as request:
            request.side_effect = [
                {
                    "id": "bot-1",
                    "recordings": [
                        {
                            "id": "recording-1",
                            "status": {"code": "done"},
                            "media_shortcuts": {"transcript": None},
                        }
                    ],
                    "status_changes": [{"code": "done"}],
                },
                {"results": []},
                {
                    "id": "transcript-1",
                    "recording": {"id": "recording-1"},
                    "status": {"code": "processing", "sub_code": None},
                    "data": {"download_url": None},
                },
            ]

            synced = provider.sync("bot-1")

        self.assertEqual(
            [call.args for call in request.call_args_list],
            [
                ("GET", "/bot/bot-1/"),
                ("GET", "/transcript/?recording_id=recording-1"),
                ("POST", "/recording/recording-1/create_transcript/"),
            ],
        )
        self.assertEqual(
            request.call_args_list[-1].kwargs["body"],
            {"provider": {"recallai_async": {"language_code": "auto"}}},
        )
        self.assertEqual(synced.status, "transcript_requested")
        self.assertEqual(synced.transcript_text, "")

    def test_recall_sync_does_not_request_async_transcript_twice(self) -> None:
        settings = self._recall_settings()
        provider = RecallMeetingBotProvider(settings)
        meeting = self.repo.create_meeting("Recall pending", source_type="meeting_bot")
        session = self.repo.create_bot_session(
            provider="recall",
            provider_bot_id="bot-1",
            meeting_id=meeting.id,
            meeting_url_display="https://meet.google.com/abc-defg-hij",
            meeting_url_hash="hash",
            title="Recall pending",
            status="transcript_requested",
            consent_confirmed=True,
        )
        service = MeetingBotService(settings, self.repo, provider=provider)
        with patch.object(provider, "_request") as request:
            request.side_effect = [
                {
                    "id": "bot-1",
                    "recordings": [
                        {
                            "id": "recording-1",
                            "status": {"code": "done"},
                            "media_shortcuts": {"transcript": None},
                        }
                    ],
                    "status_changes": [{"code": "done"}],
                },
                {"results": []},
            ]

            synced = service.sync(session["id"])

        self.assertEqual(
            [call.args for call in request.call_args_list],
            [
                ("GET", "/bot/bot-1/"),
                ("GET", "/transcript/?recording_id=recording-1"),
            ],
        )
        self.assertEqual(synced["session"]["status"], "transcript_requested")
        self.assertIsNone(synced["transcript_path"])

    def test_recall_sync_waits_when_no_transcript_text_is_available(self) -> None:
        settings = self._recall_settings()
        provider = RecallMeetingBotProvider(settings)
        with patch.object(provider, "_request") as request:
            request.return_value = {"id": "bot-1", "status": "joining_call", "recordings": []}
            synced = provider.sync("bot-1")

        self.assertEqual(synced.status, "waiting_for_transcript")
        self.assertEqual(synced.transcript_text, "")

    def test_join_requires_consent(self) -> None:
        service = MeetingBotService(self.settings, self.repo, provider=FakeMeetingBotProvider(self.settings))
        with self.assertRaisesRegex(ValueError, "consent"):
            service.join(meeting_url="https://meet.google.com/abc-defg-hij", title="No Consent")

    def test_fake_join_sync_and_process_without_whisper(self) -> None:
        service = MeetingBotService(self.settings, self.repo, provider=FakeMeetingBotProvider(self.settings))
        joined = service.join(
            meeting_url="https://meet.google.com/abc-defg-hij",
            title="Bot Planning",
            consent_confirmed=True,
        )
        session = joined["session"]
        meeting = self.repo.get_meeting(session["meeting_id"])
        self.assertEqual(meeting.source_type, "meeting_bot")
        self.assertEqual(session["meeting_url_display"], "https://meet.google.com/abc-defg-hij")

        synced = service.sync(session["id"])
        self.assertTrue(Path(synced["transcript_path"]).exists())
        self.assertEqual(self.repo.get_meeting(session["meeting_id"]).transcript_path, synced["transcript_path"])

        with patch(
            "speedwagon_ai.meeting_bot.process_meeting",
            return_value={
                "meeting": self.repo.get_meeting(session["meeting_id"]),
                "transcript_path": Path(synced["transcript_path"]),
                "note_path": self.settings.notes_dir / "bot.md",
                "commitments_path": self.settings.notes_dir / "commitments.md",
            },
        ) as process:
            processed = service.process(session["id"])

        process.assert_called_once_with(self.settings, self.repo, session["meeting_id"])
        self.assertEqual(processed["meeting"]["id"], session["meeting_id"])
        self.assertEqual(self.repo.get_bot_session(session["id"])["status"], "processed")

    def test_status_auto_syncs_pending_sessions(self) -> None:
        service = MeetingBotService(self.settings, self.repo, provider=FakeMeetingBotProvider(self.settings))
        joined = service.join(
            meeting_url="https://meet.google.com/abc-defg-hij",
            title="Auto Sync",
            consent_confirmed=True,
        )
        session_id = joined["session"]["id"]

        status = service.status()
        session = self.repo.get_bot_session(session_id)

        self.assertEqual(status["auto_sync"]["synced"], 1)
        self.assertTrue(session["transcript_ready"])
        self.assertTrue(Path(session["transcript_path"]).exists())

    def test_auto_sync_respects_cooldown(self) -> None:
        service = MeetingBotService(self.settings, self.repo, provider=FakeMeetingBotProvider(self.settings))
        joined = service.join(
            meeting_url="https://meet.google.com/abc-defg-hij",
            title="Cool Down",
            consent_confirmed=True,
        )
        session_id = joined["session"]["id"]
        self.repo.update_bot_session(session_id, status="waiting_for_transcript", last_sync_at="2026-06-04T10:00:00+00:00")

        with patch("speedwagon_ai.meeting_bot.datetime") as fake_datetime:
            fake_datetime.fromisoformat.side_effect = datetime.fromisoformat
            fake_datetime.now.return_value = datetime.fromisoformat("2026-06-04T10:00:30+00:00")
            result = service.auto_sync_pending_sessions(min_interval_seconds=120)

        self.assertEqual(result["synced"], 0)
        self.assertEqual(result["skipped"], 1)
        self.assertIsNone(self.repo.get_bot_session(session_id)["transcript_path"])

    def _recall_settings(self) -> Settings:
        return Settings(
            **{
                **self.settings.__dict__,
                "bot_provider": "recall",
                "recall_api_key": "test-key",
                "recall_region": "us-west-2",
            }
        )


if __name__ == "__main__":
    unittest.main()
