from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from speedwagon_ai.config import Settings
from speedwagon_ai.storage import Repository
from speedwagon_ai.timeutil import utc_now_iso


CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
CALENDAR_SCOPES = [CALENDAR_SCOPE]
GMAIL_COMPOSE_SCOPE = "https://www.googleapis.com/auth/gmail.compose"
GMAIL_SCOPES = [GMAIL_COMPOSE_SCOPE]
GOOGLE_SCOPES = [GMAIL_COMPOSE_SCOPE, CALENDAR_SCOPE]


@dataclass(frozen=True)
class CalendarStatus:
    enabled: bool
    status: str
    note: str
    credentials_present: bool
    token_present: bool
    calendar_scope_present: bool
    calendar_ids: list[str]
    sync_days_back: int
    sync_days_forward: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "provider": "google",
            "status": self.status,
            "note": self.note,
            "credentials_present": self.credentials_present,
            "token_present": self.token_present,
            "calendar_scope_present": self.calendar_scope_present,
            "calendar_ids": self.calendar_ids,
            "sync_days_back": self.sync_days_back,
            "sync_days_forward": self.sync_days_forward,
        }


class GoogleCalendarService:
    def __init__(self, settings: Settings, repo: Repository):
        self.settings = settings
        self.repo = repo

    def status(self) -> dict[str, Any]:
        credentials_present = self.settings.gmail_credentials_path.exists()
        token_present = self.settings.google_calendar_token_path.exists()
        scope_present = token_has_scope(self.settings.google_calendar_token_path, CALENDAR_SCOPE)
        if not credentials_present:
            status = "missing_credentials"
            note = f"Google credentials not found: {self.settings.gmail_credentials_path}"
        elif not token_present:
            status = "needs_oauth"
            note = "Google Calendar OAuth token not found. Run calendar sync to authorize read-only access."
        elif not scope_present:
            status = "reauth_required"
            note = "Google Calendar token exists but does not include Calendar read-only scope. Re-authorize Google Calendar access."
        else:
            status = "configured"
            note = "Google Calendar read-only sync is configured."
        return CalendarStatus(
            enabled=credentials_present and token_present and scope_present,
            status=status,
            note=note,
            credentials_present=credentials_present,
            token_present=token_present,
            calendar_scope_present=scope_present,
            calendar_ids=calendar_ids(self.settings),
            sync_days_back=self.settings.google_calendar_sync_days_back,
            sync_days_forward=self.settings.google_calendar_sync_days_forward,
        ).to_dict()

    def sync(self, service: Any | None = None) -> dict[str, Any]:
        google = service or self._google_service()
        now = datetime.now(timezone.utc)
        time_min = (now - timedelta(days=self.settings.google_calendar_sync_days_back)).isoformat().replace("+00:00", "Z")
        time_max = (now + timedelta(days=self.settings.google_calendar_sync_days_forward)).isoformat().replace("+00:00", "Z")
        synced: list[dict[str, Any]] = []
        raw_paths: list[str] = []
        for calendar_id in calendar_ids(self.settings):
            response = (
                google.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            for raw in response.get("items", []):
                normalized = normalize_google_calendar_event(raw, calendar_id=calendar_id)
                raw_path = self._write_raw_event(calendar_id, normalized["provider_event_id"], raw)
                normalized["raw_json_path"] = str(raw_path)
                synced.append(self.repo.upsert_calendar_event(normalized))
                raw_paths.append(str(raw_path))
        return {
            "status": "synced",
            "provider": "google",
            "calendar_ids": calendar_ids(self.settings),
            "time_min": time_min,
            "time_max": time_max,
            "synced_count": len(synced),
            "events": synced,
            "raw_paths": raw_paths,
        }

    def upcoming(self, limit: int = 10) -> dict[str, Any]:
        return {"events": self.repo.upcoming_calendar_events(limit=limit)}

    def events(self, start_date: str | None = None, end_date: str | None = None, limit: int = 50) -> dict[str, Any]:
        return {"events": self.repo.list_calendar_events(start_date=start_date, end_date=end_date, limit=limit)}

    def _google_service(self) -> Any:
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError(
                "Google Calendar sync requires optional Google libraries: "
                "google-api-python-client google-auth-httplib2 google-auth-oauthlib"
            ) from exc

        creds = None
        if self.settings.google_calendar_token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.settings.google_calendar_token_path), CALENDAR_SCOPES)
            if hasattr(creds, "has_scopes") and not creds.has_scopes([CALENDAR_SCOPE]):
                creds = None
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not self.settings.gmail_credentials_path.exists():
                    raise RuntimeError(f"Google credentials not found: {self.settings.gmail_credentials_path}")
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.settings.gmail_credentials_path),
                    CALENDAR_SCOPES,
                )
                creds = flow.run_local_server(port=0)
            self.settings.google_calendar_token_path.parent.mkdir(parents=True, exist_ok=True)
            self.settings.google_calendar_token_path.write_text(creds.to_json(), encoding="utf-8")
        return build("calendar", "v3", credentials=creds)

    def _write_raw_event(self, calendar_id: str, event_id: str, raw: dict[str, Any]) -> Path:
        root = self.settings.db_path.parent / "calendar"
        root.mkdir(parents=True, exist_ok=True)
        safe_calendar = safe_filename(calendar_id)
        safe_event = safe_filename(event_id)
        path = root / f"{safe_calendar}-{safe_event}.json"
        path.write_text(json.dumps(raw, indent=2, sort_keys=True), encoding="utf-8")
        return path


def calendar_ids(settings: Settings) -> list[str]:
    values = [value.strip() for value in settings.google_calendar_ids.split(",")]
    return [value for value in values if value] or ["primary"]


def token_has_scope(token_path: Path, scope: str) -> bool:
    if not token_path.exists():
        return False
    try:
        data = json.loads(token_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    scopes = data.get("scopes") or data.get("scope")
    if isinstance(scopes, str):
        return scope in scopes.split()
    if isinstance(scopes, list):
        return scope in scopes
    return False


def normalize_google_calendar_event(raw: dict[str, Any], *, calendar_id: str) -> dict[str, Any]:
    start = raw.get("start") or {}
    end = raw.get("end") or {}
    start_at = google_event_time(start)
    end_at = google_event_time(end) or start_at
    timezone_name = start.get("timeZone") or end.get("timeZone")
    attendees = [
        {
            "email": attendee.get("email"),
            "display_name": attendee.get("displayName"),
            "response_status": attendee.get("responseStatus"),
        }
        for attendee in raw.get("attendees") or []
        if isinstance(attendee, dict)
    ]
    return {
        "provider": "google",
        "provider_event_id": str(raw.get("id") or raw.get("iCalUID") or ""),
        "calendar_id": calendar_id,
        "title": str(raw.get("summary") or "Untitled event"),
        "description_snippet": description_snippet(raw.get("description") or ""),
        "start_at": start_at,
        "end_at": end_at,
        "timezone": timezone_name,
        "location": raw.get("location"),
        "meeting_url": meeting_url_from_event(raw),
        "attendees": attendees,
        "status": raw.get("status"),
        "html_link": raw.get("htmlLink"),
        "last_synced_at": utc_now_iso(),
    }


def google_event_time(value: dict[str, Any]) -> str:
    if value.get("dateTime"):
        return str(value["dateTime"])
    if value.get("date"):
        return str(value["date"])
    return ""


def description_snippet(value: str, limit: int = 240) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def meeting_url_from_event(raw: dict[str, Any]) -> str | None:
    for key in ["hangoutLink", "location", "description"]:
        value = raw.get(key)
        if isinstance(value, str):
            match = re.search(r"https://[^\s<>\"]+", value)
            if match:
                return match.group(0).rstrip(".,)")
    conference = raw.get("conferenceData") or {}
    for entry in conference.get("entryPoints") or []:
        if isinstance(entry, dict) and entry.get("uri"):
            return str(entry["uri"])
    return None


def safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value or "event").strip("-")
    return cleaned[:120] or "event"
