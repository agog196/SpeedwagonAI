from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from speedwagon_ai.config import Settings
from speedwagon_ai.integrations.calendar import (
    CALENDAR_WRITE_SCOPE,
    GoogleCalendarService,
    normalize_google_calendar_event,
    token_has_scope,
)
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
        self.assertEqual(service.status()["status"], "configured_read_only")
        self.assertFalse(service.status()["write_enabled"])

        self.settings.google_calendar_token_path.write_text(
            json.dumps({"scopes": [CALENDAR_WRITE_SCOPE]}),
            encoding="utf-8",
        )
        self.assertEqual(service.status()["status"], "configured")
        self.assertTrue(service.status()["write_enabled"])

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
        stale = self.repo.upsert_calendar_event(
            {
                "provider": "google",
                "provider_event_id": "stale-event",
                "calendar_id": "primary",
                "title": "Deleted elsewhere",
                "start_at": "2026-06-09T10:00:00-07:00",
                "end_at": "2026-06-09T10:30:00-07:00",
            }
        )
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
        self.assertEqual(first["removed_count"], 1)
        self.assertEqual(second["synced_count"], 2)
        self.assertEqual(second["removed_count"], 0)
        self.assertEqual(len(events), 2)
        self.assertEqual({event["calendar_id"] for event in events}, {"primary", "work"})
        self.assertNotIn(stale["id"], {event["id"] for event in events})

        brief = self.repo.daily_brief()
        self.assertIn("calendar_upcoming", brief)
        self.assertIn("meeting_prep", brief)

    def test_create_event_inserts_google_event_and_caches_result(self) -> None:
        service = GoogleCalendarService(self.settings, self.repo)
        fake_service = FakeGoogleCalendarService(
            {
                "id": "created-1",
                "summary": "Pilot planning",
                "description": "Discuss launch plan",
                "start": {"dateTime": "2026-06-08T10:00:00-07:00", "timeZone": "America/Los_Angeles"},
                "end": {"dateTime": "2026-06-08T10:30:00-07:00", "timeZone": "America/Los_Angeles"},
                "location": "Google Meet",
                "attendees": [{"email": "alex@example.com", "displayName": "Alex"}],
                "htmlLink": "https://calendar.google.com/event?eid=created-1",
                "status": "confirmed",
            }
        )

        result = service.create_event(
            title="Pilot planning",
            start_at="2026-06-08T10:00:00-07:00",
            end_at="2026-06-08T10:30:00-07:00",
            calendar_id="primary",
            timezone_name="America/Los_Angeles",
            description="Discuss launch plan",
            location="Google Meet",
            attendees=["alex@example.com", "alex@example.com"],
            send_updates="none",
            service=fake_service,
        )

        self.assertEqual(result["status"], "created")
        self.assertEqual(result["event"]["provider_event_id"], "created-1")
        self.assertEqual(result["event"]["title"], "Pilot planning")
        self.assertEqual(result["event"]["attendees"][0]["email"], "alex@example.com")
        self.assertEqual(len(result["event"]["attendees"]), 1)
        self.assertEqual(fake_service.inserts[0]["calendarId"], "primary")
        self.assertEqual(fake_service.inserts[0]["sendUpdates"], "none")
        self.assertEqual(fake_service.inserts[0]["body"]["start"]["timeZone"], "America/Los_Angeles")


class FakeGoogleCalendarService:
    def __init__(self, response: dict):
        self.response = response
        self.calls: list[dict] = []
        self.inserts: list[dict] = []

    def events(self) -> "FakeGoogleCalendarService":
        return self

    def list(self, **kwargs) -> "FakeGoogleCalendarService":
        self.calls.append(kwargs)
        return self

    def insert(self, **kwargs) -> "FakeGoogleCalendarService":
        self.inserts.append(kwargs)
        return self

    def execute(self) -> dict:
        return self.response


if __name__ == "__main__":
    unittest.main()
