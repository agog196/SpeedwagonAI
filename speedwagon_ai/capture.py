from __future__ import annotations

import json
import os
import signal
import shlex
import shutil
import subprocess
from pathlib import Path

from speedwagon_ai.config import Settings
from speedwagon_ai.storage import Repository
from speedwagon_ai.timeutil import utc_now_iso


class Recorder:
    def __init__(self, settings: Settings, repo: Repository):
        self.settings = settings
        self.repo = repo

    def start(self, title: str) -> int:
        self.settings.ensure_dirs()
        if self.settings.state_path.exists():
            raise RuntimeError("A recording is already in progress. Run `speedwagon record stop` first.")
        meeting = self.repo.create_meeting(title)
        audio_path = self.settings.audio_dir / f"meeting-{meeting.id}.wav"
        command = recorder_command(self.settings.record_cmd, audio_path)
        proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        state = {
            "meeting_id": meeting.id,
            "pid": proc.pid,
            "audio_path": str(audio_path),
            "started_at": meeting.started_at,
        }
        self.settings.state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        self.repo.update_meeting(meeting.id, audio_path=str(audio_path))
        return meeting.id

    def stop(self) -> int:
        if not self.settings.state_path.exists():
            raise RuntimeError("No recording is in progress.")
        state = json.loads(self.settings.state_path.read_text(encoding="utf-8"))
        pid = int(state["pid"])
        try:
            os.kill(pid, signal.SIGINT)
        except ProcessLookupError:
            pass
        meeting_id = int(state["meeting_id"])
        self.repo.update_meeting(
            meeting_id,
            ended_at=utc_now_iso(),
            audio_path=state.get("audio_path"),
        )
        self.settings.state_path.unlink()
        return meeting_id


def recorder_command(configured_command: str, audio_path: Path) -> list[str]:
    if configured_command:
        command = shlex.split(configured_command)
        return [part.format(output=str(audio_path)) for part in command]

    afrecord = shutil.which("afrecord")
    if afrecord:
        return [afrecord, "-f", "WAVE", str(audio_path)]

    rec = shutil.which("rec")
    if rec:
        return [rec, "-c", "1", "-r", "16000", str(audio_path)]

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return [ffmpeg, "-f", "avfoundation", "-i", ":0", "-ac", "1", "-ar", "16000", str(audio_path)]

    raise RuntimeError(
        "No audio recorder found. Install one with `brew install sox` and retry, "
        "or set SPEEDWAGON_RECORD_CMD in .env with `{output}` where the WAV path should go."
    )
