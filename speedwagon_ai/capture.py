from __future__ import annotations

import json
import os
import re
import signal
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from speedwagon_ai.config import Settings
from speedwagon_ai.dateparse import parse_date_phrase
from speedwagon_ai.storage import Repository
from speedwagon_ai.timeutil import utc_now_iso
from speedwagon_ai.transcription import transcribe_audio


CAPTURE_KINDS = {"meeting", "task_note", "assistant_voice"}
NATIVE_CAPTURE_KINDS = {"meeting"}
NATIVE_CAPTURE_MODES = {"system_mic", "system_only"}
MIN_RECORDING_BYTES = 4096


class Recorder:
    def __init__(self, settings: Settings, repo: Repository):
        self.settings = settings
        self.repo = repo

    def start(self, title: str) -> int:
        session = CaptureService(self.settings, self.repo).start("meeting", title=title)
        return int(session["meeting_id"])

    def stop(self) -> int:
        result = CaptureService(self.settings, self.repo).stop(kind="meeting")
        return int(result["session"]["meeting_id"])


class CaptureService:
    def __init__(self, settings: Settings, repo: Repository):
        self.settings = settings
        self.repo = repo

    @property
    def meeting_state_path(self) -> Path:
        return self.settings.state_path

    @property
    def task_state_path(self) -> Path:
        return self.settings.state_path.with_name("task-recording.json")

    @property
    def assistant_voice_state_path(self) -> Path:
        return self.settings.state_path.with_name("assistant-voice-recording.json")

    def start(self, kind: str, title: str = "", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        kind = normalize_capture_kind(kind)
        metadata = metadata or {}
        self.settings.ensure_dirs()
        if self.status()["active"]:
            raise RuntimeError("A recording is already in progress. Stop it before starting another capture.")
        if native_capture_active(self.settings):
            raise RuntimeError("A native capture session is already in progress. Stop it before starting another capture.")

        if kind == "meeting":
            clean_title = title.strip()
            if not clean_title:
                raise RuntimeError("Meeting title is required.")
            meeting = self.repo.create_meeting(clean_title)
            audio_path = self.settings.audio_dir / f"meeting-{meeting.id}.wav"
            log_path = self.settings.state_path.parent / f"recording-meeting-{meeting.id}.log"
            started_at = meeting.started_at
            state_path = self.meeting_state_path
            extra = {"meeting_id": meeting.id, "title": clean_title}
        elif kind == "task_note":
            stamp = utc_now_iso().replace(":", "").replace("-", "")
            audio_path = self.settings.audio_dir / f"task-note-{stamp}.wav"
            log_path = self.settings.state_path.parent / f"recording-task-{stamp}.log"
            started_at = utc_now_iso()
            state_path = self.task_state_path
            extra = {"title": title.strip() or "Voice task"}
        else:
            stamp = utc_now_iso().replace(":", "").replace("-", "")
            audio_path = self.settings.audio_dir / f"assistant-voice-{stamp}.wav"
            log_path = self.settings.state_path.parent / f"recording-assistant-voice-{stamp}.log"
            started_at = utc_now_iso()
            state_path = self.assistant_voice_state_path
            extra = {"title": title.strip() or "Assistant voice message"}

        command = recorder_command(
            self.settings.record_cmd,
            audio_path,
            profile=self.settings.capture_profile,
            input_device=self.settings.input_device,
        )
        log = log_path.open("w", encoding="utf-8")
        proc = subprocess.Popen(command, stdout=log, stderr=log)
        log.close()
        time.sleep(0.25)
        if proc.poll() is not None:
            detail = read_tail(log_path)
            raise RuntimeError(f"Recorder exited immediately. Command: {' '.join(command)}\n{detail}")

        session = enrich_session(
            {
                "active": True,
                "kind": kind,
                "pid": proc.pid,
                "audio_path": str(audio_path),
                "log_path": str(log_path),
                "command": command,
                "capture_profile": self.settings.capture_profile,
                "input_device": self.settings.input_device,
                "started_at": started_at,
                "metadata": metadata,
                "last_error": None,
                **extra,
            }
        )
        state_path.write_text(json.dumps(session, indent=2), encoding="utf-8")
        if kind == "meeting":
            self.repo.update_meeting(int(session["meeting_id"]), audio_path=str(audio_path))
        return session

    def stop(
        self,
        kind: str | None = None,
        task_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = self.active_session(kind)
        if not session:
            raise RuntimeError("No recording is in progress.")
        state_path = self.state_path_for_kind(session["kind"])
        try:
            os.kill(int(session["pid"]), signal.SIGINT)
        except ProcessLookupError:
            pass
        time.sleep(0.35)
        state_path.unlink(missing_ok=True)

        audio_path = Path(session.get("audio_path") or "")
        try:
            validate_recording_file(audio_path)
            session = enrich_session({**session, "active": False, "file_size": audio_path.stat().st_size, "last_error": None})
        except RuntimeError as exc:
            session = enrich_session({**session, "active": False, "last_error": str(exc)})
            raise

        if session["kind"] == "meeting":
            meeting_id = int(session["meeting_id"])
            self.repo.update_meeting(
                meeting_id,
                ended_at=utc_now_iso(),
                audio_path=session.get("audio_path"),
            )
            return {"session": session, "meeting_id": meeting_id}

        if session["kind"] == "task_note":
            return self._finish_task_note(session, task_metadata or {})
        return self._finish_assistant_voice(session)

    def status(self) -> dict[str, Any]:
        session = self.active_session()
        if not session:
            return {"active": False}
        return session

    def diagnostics(self) -> dict[str, Any]:
        preview_path = self.settings.audio_dir / "doctor-preview.wav"
        tools = {name: shutil.which(name) for name in ["afrecord", "rec", "ffmpeg"]}
        try:
            command = recorder_command(
                self.settings.record_cmd,
                preview_path,
                profile=self.settings.capture_profile,
                input_device=self.settings.input_device,
            )
            recorder_status = "available"
            command_preview = " ".join(command)
        except Exception as exc:
            recorder_status = str(exc)
            command_preview = ""

        status = self.status()
        log_path = Path(status.get("log_path") or "") if status.get("active") else None
        warnings = capture_warnings(self.settings.capture_profile)
        return {
            "capture_profile": self.settings.capture_profile,
            "input_device": self.settings.input_device or "",
            "record_cmd": self.settings.record_cmd,
            "tools": tools,
            "recorder_status": recorder_status,
            "recorder_command_preview": command_preview,
            "active_session": status,
            "recent_log_tail": read_tail(log_path) if log_path else "",
            "output_file_ok": bool(status.get("active") and status.get("file_size", 0) >= MIN_RECORDING_BYTES),
            "warnings": warnings,
            "smoke_test_hint": "Run `speedwagon capture doctor --smoke-test` to verify macOS can record audio.",
        }

    def active_session(self, kind: str | None = None) -> dict[str, Any] | None:
        requested = normalize_capture_kind(kind) if kind else None
        candidates = []
        for candidate_kind in ["meeting", "task_note", "assistant_voice"]:
            if requested and candidate_kind != requested:
                continue
            path = self.state_path_for_kind(candidate_kind)
            if path.exists():
                session = json.loads(path.read_text(encoding="utf-8"))
                return enrich_session(session)
            candidates.append(path)
        return None

    def state_path_for_kind(self, kind: str) -> Path:
        normalized = normalize_capture_kind(kind)
        if normalized == "meeting":
            return self.meeting_state_path
        if normalized == "task_note":
            return self.task_state_path
        return self.assistant_voice_state_path

    def _finish_task_note(self, session: dict[str, Any], task_metadata: dict[str, Any]) -> dict[str, Any]:
        audio_path = Path(session["audio_path"])
        output_base = self.settings.transcripts_dir / audio_path.with_suffix("").name
        transcript_path = transcribe_audio(self.settings, audio_path, output_base)
        text = clean_task_transcript(transcript_path.read_text(encoding="utf-8"))
        if not text:
            raise RuntimeError("Task recording transcribed as empty. Check microphone input and try again.")
        parsed_task = parse_voice_task_text(text)
        due_date = optional_text(task_metadata.get("due_date") or task_metadata.get("due")) or parsed_task.get("due_date")
        task = self.repo.create_task(
            parsed_task["text"],
            owner=optional_text(task_metadata.get("owner")),
            due_date=due_date,
            owed_to=optional_text(task_metadata.get("owed_to")),
            project=optional_text(task_metadata.get("project")),
            source="voice_task",
            source_type="local_recording",
            confidence=0.8,
        )
        return {
            "session": session,
            "task": task,
            "audio_path": str(audio_path),
            "transcript_path": str(transcript_path),
            "transcript": text,
            "parsed_text": parsed_task["text"],
        }

    def _finish_assistant_voice(self, session: dict[str, Any]) -> dict[str, Any]:
        audio_path = Path(session["audio_path"])
        output_base = self.settings.transcripts_dir / audio_path.with_suffix("").name
        transcript_path = transcribe_audio(self.settings, audio_path, output_base)
        transcript = clean_assistant_transcript(transcript_path.read_text(encoding="utf-8"))
        if not transcript:
            raise RuntimeError("Assistant voice recording transcribed as empty. Check microphone input and try again.")
        return {
            "session": session,
            "audio_path": str(audio_path),
            "transcript_path": str(transcript_path),
            "transcript": transcript,
        }


class NativeCaptureService:
    """Backend-side handoff state for Swift-owned ScreenCaptureKit recording."""

    def __init__(self, settings: Settings, repo: Repository):
        self.settings = settings
        self.repo = repo

    @property
    def state_path(self) -> Path:
        return self.settings.state_path.with_name("native-capture.json")

    def prepare(self, kind: str, title: str, mode: str = "system_mic") -> dict[str, Any]:
        kind = normalize_native_capture_kind(kind)
        mode = normalize_native_capture_mode(mode)
        clean_title = title.strip()
        if not clean_title:
            raise RuntimeError("Meeting title is required.")
        if CaptureService(self.settings, self.repo).status().get("active"):
            raise RuntimeError("A local recorder session is already in progress. Stop it before starting native capture.")
        active = self.active_session()
        if active:
            raise RuntimeError("A native capture session is already in progress. Stop it before starting another one.")

        self.settings.ensure_dirs()
        audio_dir = self.settings.audio_dir.resolve()
        audio_dir.mkdir(parents=True, exist_ok=True)
        meeting = self.repo.create_meeting(clean_title)
        final_path = audio_dir / f"meeting-{meeting.id}.wav"
        system_path = audio_dir / f"meeting-{meeting.id}-system.wav"
        mic_path = audio_dir / f"meeting-{meeting.id}-mic.wav"
        log_path = self.settings.state_path.parent.resolve() / f"native-capture-meeting-{meeting.id}.log"
        session = enrich_session(
            {
                "active": True,
                "native": True,
                "status": "recording",
                "session_id": f"native-meeting-{meeting.id}",
                "kind": kind,
                "mode": mode,
                "meeting_id": meeting.id,
                "title": clean_title,
                "audio_path": str(final_path),
                "system_audio_path": str(system_path),
                "microphone_audio_path": str(mic_path),
                "log_path": str(log_path),
                "command": ["ScreenCaptureKit", "system_audio", "microphone"],
                "capture_profile": "native_screencapturekit",
                "input_device": "system_default",
                "started_at": meeting.started_at,
                "warnings": [],
                "last_error": None,
            }
        )
        self.repo.update_meeting(meeting.id, audio_path=str(final_path))
        self._write(session)
        return session

    def complete(
        self,
        session_id: str,
        audio_path: str,
        process: bool = False,
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        session = self.active_session()
        if not session:
            raise RuntimeError("No native capture session is in progress.")
        if str(session.get("session_id")) != session_id:
            raise RuntimeError("Native capture session id does not match the active session.")

        final_path = Path(audio_path or session.get("audio_path") or "")
        expected_path = Path(str(session.get("audio_path") or ""))
        if final_path.resolve() != expected_path.resolve():
            raise RuntimeError("Native capture completed with an unexpected audio path.")
        validate_recording_file(final_path)
        completed = enrich_session(
            {
                **session,
                "active": False,
                "status": "completed",
                "ended_at": utc_now_iso(),
                "warnings": warnings or [],
                "file_size": final_path.stat().st_size,
                "last_error": None,
                "process_requested": bool(process),
            }
        )
        self.repo.update_meeting(
            int(session["meeting_id"]),
            ended_at=completed["ended_at"],
            audio_path=str(final_path),
        )
        self._write(completed)
        return completed

    def fail(self, session_id: str, error: str) -> dict[str, Any]:
        session = self.active_session() or self.last_session()
        if not session:
            raise RuntimeError("No native capture session was found.")
        if str(session.get("session_id")) != session_id:
            raise RuntimeError("Native capture session id does not match.")
        failed = enrich_session(
            {
                **session,
                "active": False,
                "status": "failed",
                "ended_at": utc_now_iso(),
                "last_error": error,
            }
        )
        if failed.get("meeting_id"):
            self.repo.update_meeting(int(failed["meeting_id"]), ended_at=failed["ended_at"])
        self._write(failed)
        return failed

    def status(self) -> dict[str, Any]:
        session = self.last_session()
        if not session:
            return {"active": False, "native": True, "status": "idle"}
        return session

    def active_session(self) -> dict[str, Any] | None:
        session = self.last_session()
        if session and session.get("active"):
            return session
        return None

    def last_session(self) -> dict[str, Any] | None:
        if not self.state_path.exists():
            return None
        return enrich_session(json.loads(self.state_path.read_text(encoding="utf-8")))

    def _write(self, session: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(session, indent=2), encoding="utf-8")


def recorder_command(
    configured_command: str,
    audio_path: Path,
    profile: str = "mic",
    input_device: str = "",
) -> list[str]:
    if configured_command:
        command = shlex.split(configured_command)
        return [part.format(output=str(audio_path)) for part in command]

    normalized_profile = (profile or "mic").lower()
    afrecord = shutil.which("afrecord")
    if afrecord and normalized_profile == "mic":
        return [afrecord, "-f", "WAVE", str(audio_path)]

    rec = shutil.which("rec")
    if rec:
        if normalized_profile == "blackhole":
            device = input_device or "BlackHole 2ch"
            return [rec, "-t", "coreaudio", device, "-c", "2", "-r", "48000", str(audio_path)]
        if input_device:
            return [rec, "-t", "coreaudio", input_device, "-c", "1", "-r", "16000", str(audio_path)]
        return [rec, "-c", "1", "-r", "16000", str(audio_path)]

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        if normalized_profile == "blackhole":
            device = input_device or "BlackHole 2ch"
            return [ffmpeg, "-f", "avfoundation", "-i", f":{device}", "-ac", "2", "-ar", "48000", str(audio_path)]
        return [ffmpeg, "-f", "avfoundation", "-i", ":0", "-ac", "1", "-ar", "16000", str(audio_path)]

    raise RuntimeError(
        "No audio recorder found. Install one with `brew install sox` and retry, "
        "or set SPEEDWAGON_RECORD_CMD in .env with `{output}` where the WAV path should go."
    )


def validate_recording_file(audio_path: Path) -> None:
    if not audio_path.exists():
        raise RuntimeError(f"Recorder stopped, but no audio file was created: {audio_path}")
    if audio_path.stat().st_size < MIN_RECORDING_BYTES:
        raise RuntimeError(
            f"Recorder created a very small audio file ({audio_path.stat().st_size} bytes). "
            "Check macOS microphone permission and SPEEDWAGON_INPUT_DEVICE."
        )


def normalize_capture_kind(kind: str | None) -> str:
    normalized = (kind or "meeting").strip().lower().replace("-", "_")
    if normalized in {"task", "voice_task"}:
        normalized = "task_note"
    if normalized in {"assistant", "assistant_note", "voice_assistant"}:
        normalized = "assistant_voice"
    if normalized not in CAPTURE_KINDS:
        raise RuntimeError("capture kind must be 'meeting', 'task_note', or 'assistant_voice'")
    return normalized


def normalize_native_capture_kind(kind: str | None) -> str:
    normalized = (kind or "meeting").strip().lower().replace("-", "_")
    if normalized not in NATIVE_CAPTURE_KINDS:
        raise RuntimeError("native capture currently supports kind 'meeting' only")
    return normalized


def normalize_native_capture_mode(mode: str | None) -> str:
    normalized = (mode or "system_mic").strip().lower().replace("-", "_")
    if normalized not in NATIVE_CAPTURE_MODES:
        raise RuntimeError("native capture mode must be 'system_mic' or 'system_only'")
    return normalized


def native_capture_active(settings: Settings) -> bool:
    path = settings.state_path.with_name("native-capture.json")
    if not path.exists():
        return False
    try:
        session = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return bool(session.get("active"))


def enrich_session(session: dict[str, Any]) -> dict[str, Any]:
    audio_path = Path(session.get("audio_path") or "")
    log_path = Path(session.get("log_path") or "")
    enriched = dict(session)
    enriched["active"] = bool(enriched.get("active", True))
    enriched["file_size"] = audio_path.stat().st_size if audio_path.exists() else 0
    enriched["output_file_ok"] = enriched["file_size"] >= MIN_RECORDING_BYTES
    enriched["log_tail"] = read_tail(log_path) if log_path.exists() else ""
    enriched.setdefault("last_error", None)
    return enriched


def read_tail(path: Path | None, max_chars: int = 2000) -> str:
    if not path or not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-max_chars:]


def capture_warnings(profile: str) -> list[str]:
    normalized = (profile or "mic").lower()
    if normalized == "blackhole":
        return [
            "BlackHole mode records routed system audio only after macOS audio routing is configured.",
            "Use Audio MIDI Setup or a multi-output device if you need to hear the meeting while recording it.",
        ]
    return [
        "Mic mode records your selected/default microphone only.",
        "Computer/headphone audio needs BlackHole routing today or future ScreenCaptureKit support.",
    ]


def clean_task_transcript(text: str) -> str:
    cleaned = " ".join(line.strip() for line in text.splitlines() if line.strip())
    ignored = {"[BLANK_AUDIO]", "(BLANK_AUDIO)", "[MUSIC]", "[NO SPEECH]"}
    if cleaned.upper() in ignored:
        return ""
    prefixes = ["remind me to ", "task ", "add task ", "todo ", "to do "]
    lowered = cleaned.lower()
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return cleaned[len(prefix) :].strip()
    return cleaned.strip()


def parse_voice_task_text(text: str) -> dict[str, str | None]:
    cleaned = text.strip()
    match = re.search(
        r"\s+(?:due(?:\s+(?:by|on))?|by|before|on or before)\s+([A-Za-z]+ \d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?|\d{4}-\d{2}-\d{2}|today|tomorrow)[\s.!,?]*$",
        cleaned,
        flags=re.IGNORECASE,
    )
    if not match:
        return {"text": cleaned, "due_date": None}
    due_date = parse_date_phrase(match.group(1))
    if not due_date:
        return {"text": cleaned, "due_date": None}
    task_text = cleaned[: match.start()].strip(" .,;:-")
    return {"text": task_text or cleaned, "due_date": due_date}


def clean_assistant_transcript(text: str) -> str:
    cleaned = " ".join(line.strip() for line in text.splitlines() if line.strip())
    ignored = {"[BLANK_AUDIO]", "(BLANK_AUDIO)", "[MUSIC]", "[NO SPEECH]"}
    if cleaned.upper() in ignored:
        return ""
    return cleaned.strip()


def optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
