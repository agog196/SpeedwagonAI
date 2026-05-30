from __future__ import annotations

from speedwagon_ai.storage import Repository


def render_context(repo: Repository, topic: str) -> str:
    data = repo.context_for_topic(topic)
    lines = [f"# Context for {topic}", ""]
    lines.extend(["## Relevant Meetings", ""])
    if data["meetings"]:
        for meeting in data["meetings"]:
            summary = f" - {meeting.summary}" if meeting.summary else ""
            lines.append(f"- [{meeting.id}] {meeting.title} ({meeting.started_at[:10]}){summary}")
    else:
        lines.append("_No relevant meetings found._")
    lines.extend(["", "## Past Decisions", ""])
    if data["decisions"]:
        for decision in data["decisions"]:
            lines.append(f"- {decision['text']} ({decision['meeting_title']}, {decision['started_at'][:10]})")
    else:
        lines.append("_No matching decisions found._")
    lines.extend(["", "## Unresolved Work", ""])
    unresolved = data["unresolved"][:12]
    if unresolved:
        for row in unresolved:
            owner = row.get("owner") or "unassigned"
            due = f", due {row['deadline']}" if row.get("deadline") else ""
            lines.append(f"- {row['text']} ({owner}{due}; {row['meeting_title']})")
    else:
        lines.append("_No unresolved work._")
    return "\n".join(lines)
