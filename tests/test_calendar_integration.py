from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from speedwagon_ai.config import Settings
from speedwagon_ai.integrations.calendar import GoogleCalendarService, normalize_google_calendar_event, token_has_scope
from speedwagon_ai.storage import Repository


class CalendarIntegrationTests(unittest.TestCase):
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
            google_calendar_ids="primary,work",
        )
        self.repo = Repository(self.settings.db_path)
        self.repo.init()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_status_detects_missing_credentials_token_and_scope(self) -> None:
        service = GoogleCalendarService(self.settings, self.repo)
        self.assertEqual(service.status()["status"], "missing_credentials")

        self.settings.gmail_credentials_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings.gmail_credentials_path.write_text("{}", encoding="utf-8")
        self.assertEqual(service.status()["status"], "needs_oauth")

        self.settings.google_calendar_token_path.write_text(
            json.dumps({"scopes": ["https://www.googleapis.com/auth/gmail.compose"]}),
            encoding="utf-8",
        )
        self.assertEqual(service.status()["status"], "reauth_required")

        self.settings.google_calendar_token_path.write_text(
            json.dumps(
                {
                    "scopes": [
                        "https://www.googleapis.com/auth/calendar.readonly",
                    ]
                }
            ),
            encoding="utf-8",
        )
        self.assertTrue(token_has_scope(self.settings.google_calendar_token_path, "https://www.googleapis.com/auth/calendar.readonly"))
        self.assertEqual(service.status()["status"], "configured")

    def test_normalizes_google_event_fields(self) -> None:
        event = normalize_google_calendar_event(
            {
                "id": "event-1",
                "summary": "DairyMGT review",
                "description": "<p>Review launch graphs</p> https://meet.google.com/abc-defg-hij",
                "start": {"dateTime": "2026-06-08T10:00:00-07:00", "timeZone": "America/Los_Angeles"},
                "end": {"dateTime": "2026-06-08T10:30:00-07:00"},
                "attendees": [{"email": "megan@example.com", "displayName": "Megan"}],
                "htmlLink": "https://calendar.google.com/event",
                "status": "confirmed",
            },
            calendar_id="primary",
        )
        self.assertEqual(event["provider_event_id"], "event-1")
        self.assertEqual(event["title"], "DairyMGT review")
        self.assertEqual(event["description_snippet"], "Review launch graphs https://meet.google.com/abc-defg-hij")
        self.assertEqual(event["meeting_url"], "https://meet.google.com/abc-defg-hij")
        self.assertEqual(event["attendees"][0]["display_name"], "Megan")

    def test_sync_upserts_events_and_daily_brief_includes_calendar(self) -> None:
        service = GoogleCalendarService(self.settings, self.repo)
        fake_service = FakeGoogleCalendarService(
            {
                "items": [
                    {
                        "id": "event-1",
                        "summary": "DairyMGT review",
                        "description": "Review app updates",
                        "start": {"dateTime": "2026-06-08T10:00:00-07:00"},
                        "end": {"dateTime": "2026-06-08T10:30:00-07:00"},
                    }
                ]
            }
        )

        first = service.sync(service=fake_service)
        second = service.sync(service=fake_service)
        events = self.repo.upcoming_calendar_events(limit=10, from_date="2026-06-01")

        self.assertEqual(first["synced_count"], 2)
        self.assertEqual(second["synced_count"], 2)
        self.assertEqual(len(events), 2)
        self.assertEqual({event["calendar_id"] for event in events}, {"primary", "work"})

        brief = self.repo.daily_brief()
        self.assertIn("calendar_upcoming", brief)
        self.assertIn("meeting_prep", brief)


class FakeGoogleCalendarService:
    def __init__(self, response: dict):
        self.response = response
        self.calls: list[dict] = []

    def events(self) -> "FakeGoogleCalendarService":
        return self

    def list(self, **kwargs) -> "FakeGoogleCalendarService":
        self.calls.append(kwargs)
        return self

    def execute(self) -> dict:
        return self.response


if __name__ == "__main__":
    unittest.main()
