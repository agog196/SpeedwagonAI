from __future__ import annotations

from pathlib import Path

from speedwagon_ai.capture import CaptureService, clean_task_transcript
from speedwagon_ai.config import Settings
from speedwagon_ai.storage import Repository


class VoiceTaskRecorder:
    def __init__(self, settings: Settings, repo: Repository):
        self.settings = settings
        self.repo = repo

    @property
    def state_path(self) -> Path:
        return self.settings.state_path.with_name("task-recording.json")

    def start(self) -> dict:
        return CaptureService(self.settings, self.repo).start("task_note")

    def stop(self, owner: str | None = None, due_date: str | None = None, project: str | None = None) -> dict:
        return CaptureService(self.settings, self.repo).stop(
            kind="task_note",
            task_metadata={
                "owner": owner,
                "due_date": due_date,
                "project": project,
            },
        )

    def state(self) -> dict:
        return CaptureService(self.settings, self.repo).active_session("task_note") or {"active": False}
