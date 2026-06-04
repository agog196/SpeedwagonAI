from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from speedwagon_ai.config import Settings
from speedwagon_ai.processing import process_meeting
from speedwagon_ai.storage import Repository, as_meeting_dict
from speedwagon_ai.timeutil import utc_now_iso


@dataclass(frozen=True)
class BotJoinResult:
    provider_bot_id: str
    status: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class BotSyncResult:
    status: str
    transcript_text: str
    raw: dict[str, Any]


class MeetingBotProvider(Protocol):
    name: str

    def status(self) -> dict[str, Any]:
        ...

    def join(self, *, meeting_url: str, title: str, join_at: str | None, bot_name: str | None) -> BotJoinResult:
        ...

    def sync(self, provider_bot_id: str, *, request_transcript: bool = True) -> BotSyncResult:
        ...


class DisabledMeetingBotProvider:
    name = "disabled"

    def __init__(self, reason: str):
        self.reason = reason

    def status(self) -> dict[str, Any]:
        return {
            "enabled": False,
            "provider": "none",
            "status": "not_configured",
            "note": self.reason,
            "requires_consent": True,
        }

    def join(self, *, meeting_url: str, title: str, join_at: str | None, bot_name: str | None) -> BotJoinResult:
        raise RuntimeError(self.reason)

    def sync(self, provider_bot_id: str, *, request_transcript: bool = True) -> BotSyncResult:
        raise RuntimeError(self.reason)


class FakeMeetingBotProvider:
    name = "fake"

    def __init__(self, settings: Settings):
        self.settings = settings

    def status(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "provider": "fake",
            "status": "configured",
            "note": "Fake meeting bot provider is enabled for local development and tests.",
            "requires_consent": True,
        }

    def join(self, *, meeting_url: str, title: str, join_at: str | None, bot_name: str | None) -> BotJoinResult:
        digest = hashlib.sha256(f"{meeting_url}|{title}|{join_at or ''}".encode("utf-8")).hexdigest()[:12]
        return BotJoinResult(
            provider_bot_id=f"fake-{digest}",
            status="joined",
            raw={
                "id": f"fake-{digest}",
                "meeting_url": redact_meeting_url(meeting_url),
                "bot_name": bot_name or self.settings.recall_bot_name,
                "join_at": join_at,
                "status": "joined",
                "provider": "fake",
            },
        )

    def sync(self, provider_bot_id: str, *, request_transcript: bool = True) -> BotSyncResult:
        fixture_path = os.getenv("SPEEDWAGON_FAKE_BOT_TRANSCRIPT_PATH", "")
        if fixture_path and Path(fixture_path).exists():
            transcript_text = Path(fixture_path).read_text(encoding="utf-8").strip()
        else:
            transcript_text = (
                "Speaker 1: We should send the project update after the meeting.\n"
                "Speaker 2: I will review the next steps by Friday."
            )
        return BotSyncResult(
            status="transcript_ready",
            transcript_text=transcript_text,
            raw={"id": provider_bot_id, "status": "done", "transcript": transcript_text, "provider": "fake"},
        )


class RecallMeetingBotProvider:
    name = "recall"

    def __init__(self, settings: Settings):
        self.settings = settings
        region = settings.recall_region.strip() or "us-east-1"
        self.base_url = f"https://{region}.recall.ai/api/v1"

    def status(self) -> dict[str, Any]:
        configured = bool(self.settings.recall_api_key.strip())
        return {
            "enabled": configured,
            "provider": "recall",
            "status": "configured" if configured else "missing_api_key",
            "region": self.settings.recall_region,
            "bot_name": self.settings.recall_bot_name,
            "note": (
                "Recall.ai meeting bot beta is configured. Bots join visibly and use provider/cloud infrastructure."
                if configured
                else "Set RECALL_API_KEY to enable the Recall.ai meeting bot beta."
            ),
            "requires_consent": True,
        }

    def join(self, *, meeting_url: str, title: str, join_at: str | None, bot_name: str | None) -> BotJoinResult:
        body: dict[str, Any] = {
            "meeting_url": meeting_url,
            "bot_name": bot_name or self.settings.recall_bot_name,
        }
        if join_at:
            body["join_at"] = join_at
        raw = self._request("POST", "/bot/", body=body)
        provider_bot_id = str(raw.get("id") or raw.get("bot_id") or "").strip()
        if not provider_bot_id:
            raise RuntimeError("Recall.ai did not return a bot id.")
        return BotJoinResult(provider_bot_id=provider_bot_id, status=bot_status_from_raw(raw) or "created", raw=raw)

    def sync(self, provider_bot_id: str, *, request_transcript: bool = True) -> BotSyncResult:
        bot_raw = self._request("GET", f"/bot/{provider_bot_id}/")
        transcript_raw = self._fetch_transcript_for_bot(bot_raw, request_transcript=request_transcript)
        transcript_text = normalize_transcript(transcript_raw)
        status = "transcript_ready" if transcript_text else transcript_status_from_raw(transcript_raw) or bot_status_from_raw(bot_raw) or "waiting_for_transcript"
        return BotSyncResult(
            status=status,
            transcript_text=transcript_text,
            raw={"bot": bot_raw, "transcript": transcript_raw},
        )

    def _fetch_transcript_for_bot(self, bot_raw: dict[str, Any], *, request_transcript: bool = True) -> Any:
        for shortcut in transcript_shortcuts_from_bot(bot_raw):
            transcript_raw = self._fetch_transcript_artifact(shortcut)
            if normalize_transcript(transcript_raw):
                return transcript_raw

        for recording_id in recording_ids_from_bot(bot_raw):
            artifacts = transcript_artifacts_from_list_response(
                self._request("GET", f"/transcript/?recording_id={urllib.parse.quote(recording_id)}")
            )
            for artifact in artifacts:
                transcript_raw = self._fetch_transcript_artifact(artifact)
                if normalize_transcript(transcript_raw):
                    return transcript_raw
            if artifacts:
                return {"status": "waiting_for_transcript", "recording_id": recording_id, "transcripts": artifacts}

            if not request_transcript:
                return {"status": "waiting_for_transcript", "recording_id": recording_id}

            created = self._create_async_transcript(recording_id)
            if normalize_transcript(created):
                return created
            return {"status": "transcript_requested", "recording_id": recording_id, "transcript": created}

        return {"status": "waiting_for_transcript", "bot": bot_raw}

    def _fetch_transcript_artifact(self, artifact: dict[str, Any]) -> Any:
        download_url = transcript_download_url(artifact)
        if download_url:
            return self._request_url(download_url)

        transcript_id = str(artifact.get("id") or "").strip()
        if transcript_id:
            retrieved = self._request("GET", f"/transcript/{urllib.parse.quote(transcript_id)}/")
            download_url = transcript_download_url(retrieved)
            if download_url:
                return self._request_url(download_url)
            return retrieved

        return artifact

    def _create_async_transcript(self, recording_id: str) -> Any:
        return self._request(
            "POST",
            f"/recording/{urllib.parse.quote(recording_id)}/create_transcript/",
            body={"provider": {"recallai_async": {"language_code": "auto"}}},
        )

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        if not self.settings.recall_api_key.strip():
            raise RuntimeError("RECALL_API_KEY is not configured.")
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={
                "Authorization": self.settings.recall_api_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                raw_text = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Recall.ai request failed: HTTP {exc.code}: {detail}") from exc
        if not raw_text.strip():
            return {}
        return json.loads(raw_text)

    def _request_url(self, url: str) -> Any:
        if not self.settings.recall_api_key.strip():
            raise RuntimeError("RECALL_API_KEY is not configured.")
        resolved = urllib.parse.urljoin(f"{self.base_url}/", url)
        request = urllib.request.Request(
            resolved,
            headers={
                "Authorization": self.settings.recall_api_key,
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                raw_text = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Recall.ai transcript download failed: HTTP {exc.code}: {detail}") from exc
        if not raw_text.strip():
            return {}
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            return raw_text


class MeetingBotService:
    def __init__(self, settings: Settings, repo: Repository, provider: MeetingBotProvider | None = None):
        self.settings = settings
        self.repo = repo
        self.provider = provider or provider_from_settings(settings)

    def status(self) -> dict[str, Any]:
        auto_sync = self.auto_sync_pending_sessions()
        base = self.provider.status()
        sessions = self.repo.list_bot_sessions(limit=5) if self.repo.db_path.exists() else []
        return {
            **base,
            "sessions": sessions,
            "session_count": len(sessions),
            "default_bot_name": self.settings.recall_bot_name,
            "cloud_cost_label": "higher",
            "auto_sync": auto_sync,
        }

    def sessions(self, *, limit: int = 20, status: str | None = None, auto_sync: bool = True) -> list[dict[str, Any]]:
        if auto_sync:
            self.auto_sync_pending_sessions(limit=min(limit, 5))
        return self.repo.list_bot_sessions(limit=limit, status=status)

    def auto_sync_pending_sessions(self, *, limit: int = 5, min_interval_seconds: int = 120) -> dict[str, Any]:
        provider_status = self.provider.status()
        if not provider_status.get("enabled"):
            return {"enabled": False, "checked": 0, "synced": 0, "skipped": 0}
        if not self.repo.db_path.exists():
            return {"enabled": False, "checked": 0, "synced": 0, "skipped": 0}

        checked = 0
        synced = 0
        skipped = 0
        errors: list[dict[str, Any]] = []
        for session in self.repo.list_bot_sessions(limit=limit):
            checked += 1
            if not should_auto_sync_bot_session(session, self.provider.name, min_interval_seconds=min_interval_seconds):
                skipped += 1
                continue
            try:
                self.sync(int(session["id"]), automatic=True)
                synced += 1
            except Exception as exc:
                errors.append({"session_id": session.get("id"), "error": str(exc)})
                self.repo.update_bot_session(int(session["id"]), error=str(exc), last_sync_at=utc_now_iso())
        return {"enabled": True, "checked": checked, "synced": synced, "skipped": skipped, "errors": errors}

    def join(
        self,
        *,
        meeting_url: str,
        title: str,
        join_at: str | None = None,
        bot_name: str | None = None,
        consent_confirmed: bool = False,
    ) -> dict[str, Any]:
        meeting_url = meeting_url.strip()
        title = title.strip() or "Bot meeting"
        if not meeting_url:
            raise ValueError("meeting_url is required")
        if not consent_confirmed:
            raise ValueError("Meeting bot join requires explicit consent confirmation.")
        status = self.provider.status()
        if not status.get("enabled"):
            raise RuntimeError(str(status.get("note") or "Meeting bot provider is not configured."))
        joined = self.provider.join(meeting_url=meeting_url, title=title, join_at=join_at, bot_name=bot_name)
        meeting = self.repo.create_meeting(title, source_type="meeting_bot")
        session = self.repo.create_bot_session(
            provider=self.provider.name,
            provider_bot_id=joined.provider_bot_id,
            meeting_id=meeting.id,
            meeting_url_display=redact_meeting_url(meeting_url),
            meeting_url_hash=hash_meeting_url(meeting_url),
            title=title,
            status=joined.status,
            join_at=join_at,
            consent_confirmed=True,
        )
        raw_path = self._write_raw(session["id"], {"join": joined.raw})
        session = self.repo.update_bot_session(session["id"], raw_metadata_path=str(raw_path))
        return {"session": session, "meeting": as_meeting_dict(meeting), "provider_response": joined.raw}

    def sync(self, session_id: int, *, automatic: bool = False) -> dict[str, Any]:
        session = self.repo.get_bot_session(session_id)
        provider_bot_id = str(session.get("provider_bot_id") or "")
        if not provider_bot_id:
            raise ValueError("Bot session has no provider bot id.")
        request_transcript = should_request_transcript_for_session(session)
        synced = self.provider.sync(provider_bot_id, request_transcript=request_transcript)
        raw_path = self._write_raw(session_id, {"sync": synced.raw})
        fields: dict[str, Any] = {
            "status": synced.status,
            "raw_metadata_path": str(raw_path),
            "last_sync_at": utc_now_iso(),
            "error": None,
        }
        if not request_transcript and synced.status == "waiting_for_transcript":
            fields["status"] = str(session.get("status") or synced.status)
        transcript_path: Path | None = None
        if synced.transcript_text.strip():
            transcript_path = self._write_transcript(session_id, synced.transcript_text)
            fields["transcript_path"] = str(transcript_path)
            self.repo.update_meeting(
                int(session["meeting_id"]),
                transcript_path=str(transcript_path),
                ended_at=utc_now_iso(),
                source_type="meeting_bot",
            )
        updated = self.repo.update_bot_session(session_id, **fields)
        return {"session": updated, "transcript_path": str(transcript_path) if transcript_path else None}

    def process(self, session_id: int) -> dict[str, Any]:
        session = self.repo.get_bot_session(session_id)
        if not (session.get("transcript_path") or session.get("meeting_transcript_path")):
            self.sync(session_id)
            session = self.repo.get_bot_session(session_id)
        if not (session.get("transcript_path") or session.get("meeting_transcript_path")):
            raise ValueError("Bot transcript is not ready yet. Sync this bot session after the meeting ends.")
        result = process_meeting(self.settings, self.repo, int(session["meeting_id"]))
        updated = self.repo.update_bot_session(session_id, status="processed", last_sync_at=utc_now_iso())
        return {
            "session": updated,
            "meeting": as_meeting_dict(result["meeting"]),
            "transcript_path": str(result["transcript_path"]),
            "note_path": str(result["note_path"]),
            "commitments_path": str(result["commitments_path"]),
        }

    def _write_raw(self, session_id: int, payload: dict[str, Any]) -> Path:
        path = self.settings.db_path.parent / "bot_sessions" / f"bot-session-{session_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def _write_transcript(self, session_id: int, transcript_text: str) -> Path:
        self.settings.transcripts_dir.mkdir(parents=True, exist_ok=True)
        path = self.settings.transcripts_dir / f"bot-{session_id}.txt"
        path.write_text(transcript_text.strip() + "\n", encoding="utf-8")
        return path


def provider_from_settings(settings: Settings) -> MeetingBotProvider:
    provider = settings.bot_provider.strip().lower()
    if provider == "recall":
        return RecallMeetingBotProvider(settings)
    if provider == "fake":
        return FakeMeetingBotProvider(settings)
    return DisabledMeetingBotProvider("Meeting bot capture is optional. Set SPEEDWAGON_BOT_PROVIDER=recall and RECALL_API_KEY to enable it.")


def should_auto_sync_bot_session(session: dict[str, Any], provider_name: str, *, min_interval_seconds: int = 120) -> bool:
    if str(session.get("provider") or "").lower() != provider_name:
        return False
    if session.get("transcript_ready") or session.get("transcript_path") or session.get("meeting_transcript_path"):
        return False
    if str(session.get("status") or "").lower() == "processed":
        return False
    if not session.get("provider_bot_id"):
        return False
    last_sync_at = parse_iso_datetime(str(session.get("last_sync_at") or ""))
    if last_sync_at and datetime.now(last_sync_at.tzinfo) - last_sync_at < timedelta(seconds=min_interval_seconds):
        return False
    return True


def should_request_transcript_for_session(session: dict[str, Any]) -> bool:
    status = str(session.get("status") or "").lower()
    return status not in {"transcript_requested", "transcript_processing", "transcript_queued", "transcript_in_progress"}


def parse_iso_datetime(value: str) -> datetime | None:
    if not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def redact_meeting_url(meeting_url: str) -> str:
    parsed = urllib.parse.urlparse(meeting_url.strip())
    if not parsed.netloc:
        return meeting_url[:80]
    path = parsed.path.rstrip("/")
    return urllib.parse.urlunparse((parsed.scheme or "https", parsed.netloc, path, "", "", ""))


def hash_meeting_url(meeting_url: str) -> str:
    return hashlib.sha256(meeting_url.strip().encode("utf-8")).hexdigest()


def bot_status_from_raw(raw: dict[str, Any]) -> str | None:
    for key in ["status", "status_code", "state"]:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    status_changes = raw.get("status_changes")
    if isinstance(status_changes, list) and status_changes:
        latest = status_changes[-1]
        if isinstance(latest, dict):
            value = latest.get("code") or latest.get("status") or latest.get("message")
            if value:
                return str(value).strip().lower()
    return None


def transcript_status_from_raw(raw: Any) -> str | None:
    if not isinstance(raw, dict):
        return None
    status = raw.get("status")
    if isinstance(status, str) and status.strip():
        return status.strip().lower()
    if isinstance(status, dict):
        code = status.get("code")
        if isinstance(code, str) and code.strip():
            return f"transcript_{code.strip().lower()}"
    transcript = raw.get("transcript")
    if isinstance(transcript, dict):
        return transcript_status_from_raw(transcript)
    return None


def transcript_shortcuts_from_bot(bot_raw: dict[str, Any]) -> list[dict[str, Any]]:
    shortcuts: list[dict[str, Any]] = []
    for recording in recordings_from_bot(bot_raw):
        media_shortcuts = recording.get("media_shortcuts")
        if not isinstance(media_shortcuts, dict):
            continue
        transcript = media_shortcuts.get("transcript")
        if isinstance(transcript, dict):
            shortcuts.append(transcript)
    return shortcuts


def recording_ids_from_bot(bot_raw: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for recording in recordings_from_bot(bot_raw):
        recording_id = str(recording.get("id") or recording.get("recording") or "").strip()
        if recording_id:
            ids.append(recording_id)
    return ids


def recordings_from_bot(bot_raw: dict[str, Any]) -> list[dict[str, Any]]:
    recordings = bot_raw.get("recordings")
    if isinstance(recordings, list):
        return [recording for recording in recordings if isinstance(recording, dict)]
    recording = bot_raw.get("recording")
    if isinstance(recording, dict):
        return [recording]
    return []


def transcript_artifacts_from_list_response(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        results = raw.get("results") or raw.get("data")
        if isinstance(results, list):
            return [item for item in results if isinstance(item, dict)]
    return []


def transcript_download_url(raw: dict[str, Any]) -> str | None:
    data = raw.get("data")
    if isinstance(data, dict):
        download_url = data.get("download_url")
        if isinstance(download_url, str) and download_url.strip():
            return download_url.strip()
    download_url = raw.get("download_url")
    if isinstance(download_url, str) and download_url.strip():
        return download_url.strip()
    return None


def normalize_transcript(raw: Any) -> str:
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, dict):
        if isinstance(raw.get("transcript"), str):
            return raw["transcript"].strip()
        if isinstance(raw.get("data"), list):
            raw = raw["data"]
        elif isinstance(raw.get("transcript"), list):
            raw = raw["transcript"]
        else:
            return ""
    if not isinstance(raw, list):
        return ""
    lines: list[str] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        speaker = str(entry.get("speaker") or entry.get("speaker_name") or "Speaker").strip()
        text = transcript_entry_text(entry)
        if text:
            lines.append(f"{speaker}: {text}")
    return "\n".join(lines).strip()


def transcript_entry_text(entry: dict[str, Any]) -> str:
    if isinstance(entry.get("text"), str):
        return entry["text"].strip()
    words = entry.get("words")
    if isinstance(words, list):
        return " ".join(str(word.get("text") or "").strip() for word in words if isinstance(word, dict)).strip()
    return ""
