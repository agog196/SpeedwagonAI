from __future__ import annotations

import subprocess
from pathlib import Path

from speedwagon_ai.config import Settings
from speedwagon_ai.storage import Repository


class Transcriber:
    def __init__(self, settings: Settings, repo: Repository):
        self.settings = settings
        self.repo = repo

    def transcribe(self, meeting_id: int) -> Path:
        meeting = self.repo.get_meeting(meeting_id)
        if not meeting.audio_path:
            raise RuntimeError(f"Meeting {meeting_id} has no audio path.")
        if not self.settings.whisper_cpp_bin:
            raise RuntimeError("WHISPER_CPP_BIN is not configured.")
        if not self.settings.whisper_cpp_model:
            raise RuntimeError("WHISPER_CPP_MODEL is not configured.")
        audio_path = Path(meeting.audio_path)
        if not audio_path.exists():
            raise RuntimeError(f"Audio file does not exist: {audio_path}")
        self.settings.transcripts_dir.mkdir(parents=True, exist_ok=True)
        output_base = self.settings.transcripts_dir / f"meeting-{meeting_id}"
        command = [
            self.settings.whisper_cpp_bin,
            "-m",
            self.settings.whisper_cpp_model,
            "-f",
            str(audio_path),
            "-otxt",
            "-of",
            str(output_base),
        ]
        result = subprocess.run(command, check=False, text=True, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(f"whisper.cpp failed: {result.stderr.strip() or result.stdout.strip()}")
        transcript_path = output_base.with_suffix(".txt")
        if not transcript_path.exists():
            transcript_path.write_text(result.stdout.strip(), encoding="utf-8")
        self.repo.update_meeting(meeting_id, transcript_path=str(transcript_path))
        return transcript_path
