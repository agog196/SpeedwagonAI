from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from speedwagon_ai.config import Settings
from speedwagon_ai.storage import Repository


class MarkdownWriter:
    def __init__(self, settings: Settings, repo: Repository):
        self.settings = settings
        self.repo = repo

    def write_meeting(self, meeting_id: int) -> Path:
        self.settings.notes_dir.mkdir(parents=True, exist_ok=True)
        bundle = self.repo.meeting_bundle(meeting_id)
        meeting = bundle["meeting"]
        filename = f"{meeting.started_at[:10]}-{slugify(meeting.title)}-m{meeting.id}.md"
        path = self.settings.notes_dir / filename
        text = render_meeting_markdown(bundle)
        path.write_text(text, encoding="utf-8")
        self.repo.update_meeting(meeting_id, note_path=str(path))
        return path

    def write_commitments(self) -> Path:
        self.settings.notes_dir.mkdir(parents=True, exist_ok=True)
        path = self.settings.notes_dir / "commitments.md"
        path.write_text(render_commitments_markdown(self.repo.unresolved_work()), encoding="utf-8")
        return path


def render_meeting_markdown(bundle: dict[str, Any]) -> str:
    meeting = bundle["meeting"]
    entities = [row["name"] for row in bundle["entities"]]
    topics = [row["topic"] for row in bundle["key_topics"]]
    frontmatter = [
        "---",
        f'title: "{escape_yaml(meeting.title)}"',
        f"meeting_id: {meeting.id}",
        f"date: {meeting.started_at[:10]}",
        "tags:",
        "  - speedwagon",
        "  - meeting",
        "entities:",
        *[f'  - "{escape_yaml(entity)}"' for entity in entities],
        "topics:",
        *[f'  - "{escape_yaml(topic)}"' for topic in topics],
        f'audio_path: "{escape_yaml(meeting.audio_path or "")}"',
        f'transcript_path: "{escape_yaml(meeting.transcript_path or "")}"',
        "---",
        "",
    ]
    lines = frontmatter + [
        f"# {meeting.title}",
        "",
        f"Started: {meeting.started_at}",
        f"Ended: {meeting.ended_at or 'Unknown'}",
        "",
        "## Summary",
        "",
        meeting.summary or "_No summary extracted yet._",
        "",
        "## Key Topics",
        "",
        *bullet_list(topics),
        "",
        "## Decisions",
        "",
        *bullet_list([row["text"] for row in bundle["decisions"]]),
        "",
        "## Action Items",
        "",
        *work_list(bundle["action_items"]),
        "",
        "## Commitments",
        "",
        *work_list(bundle["commitments"]),
        "",
        "## Open Questions",
        "",
        *bullet_list([row["text"] for row in bundle["open_questions"]]),
        "",
        "## Links",
        "",
        "- [[commitments]]",
        f"- Transcript: `{meeting.transcript_path or 'Not available'}`",
        f"- Audio: `{meeting.audio_path or 'Not available'}`",
        "",
    ]
    return "\n".join(lines)


def render_commitments_markdown(rows: list[dict[str, Any]]) -> str:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row.get("owner") or "Unassigned"].append(row)
    lines = [
        "---",
        'title: "Open Commitments"',
        "tags:",
        "  - speedwagon",
        "  - commitments",
        "---",
        "",
        "# Open Commitments",
        "",
    ]
    if not rows:
        lines.extend(["_No unresolved commitments or action items._", ""])
        return "\n".join(lines)
    for owner in sorted(grouped):
        lines.extend([f"## {owner}", ""])
        for row in grouped[owner]:
            due = f" due {row['deadline']}" if row.get("deadline") else ""
            lines.append(
                f"- [{row['kind']}] {row['text']}{due} "
                f"([[{row['meeting_title']}]]; meeting {row['meeting_id']})"
            )
        lines.append("")
    return "\n".join(lines)


def bullet_list(values: list[str]) -> list[str]:
    return [f"- {value}" for value in values] or ["_None captured._"]


def work_list(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["_None captured._"]
    rendered = []
    for row in rows:
        owner = f" owner: {row['owner']}" if row.get("owner") else " owner: unassigned"
        deadline = f" deadline: {row['deadline']}" if row.get("deadline") else ""
        rendered.append(f"- [ ] {row['text']} ({row['status']};{owner}{deadline})")
    return rendered


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug or "meeting"


def escape_yaml(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
