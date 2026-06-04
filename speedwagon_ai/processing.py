from __future__ import annotations

from pathlib import Path
from typing import Any

from speedwagon_ai.config import Settings
from speedwagon_ai.extraction import Extractor
from speedwagon_ai.output import MarkdownWriter
from speedwagon_ai.storage import Repository
from speedwagon_ai.transcription import Transcriber


def process_meeting(settings: Settings, repo: Repository, meeting_id: int, fixture_path: Path | None = None) -> dict[str, Any]:
    meeting = repo.get_meeting(meeting_id)
    transcript_path = Path(meeting.transcript_path) if meeting.transcript_path else Transcriber(settings, repo).transcribe(meeting_id)
    extraction = Extractor(settings, repo).extract(meeting_id, fixture_path=fixture_path)
    writer = MarkdownWriter(settings, repo)
    note_path = writer.write_meeting(meeting_id)
    commitments_path = writer.write_commitments()
    return {
        "meeting": repo.get_meeting(meeting_id),
        "transcript_path": transcript_path,
        "extraction": extraction,
        "note_path": note_path,
        "commitments_path": commitments_path,
    }
