from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any

from speedwagon_ai.config import Settings
from speedwagon_ai.model_router import choose_model
from speedwagon_ai.storage import Repository


EMAIL_SYSTEM_PROMPT = """You write concise, useful follow-up emails from meeting notes.
Return only valid JSON with these keys:
subject: string
body: string
tone: string
included_items: array of strings
The user's draft instruction is private guidance. Do not quote it or include it verbatim in the email unless the user explicitly asks you to quote it.
Use natural prose, not a raw dump of extracted action items and open questions.
Do not invent facts beyond the provided meeting context."""


@dataclass(frozen=True)
class EmailDraftContent:
    subject: str
    body: str
    tone: str = "neutral"
    included_items: list[str] = field(default_factory=list)
    provider: str = "fallback"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EmailComposer:
    def __init__(self, settings: Settings, repo: Repository):
        self.settings = settings
        self.repo = repo

    def compose(
        self,
        meeting_id: int,
        to: str = "",
        subject: str | None = None,
        instruction: str = "",
    ) -> EmailDraftContent:
        bundle = self.repo.meeting_bundle(meeting_id)
        if self.settings.openai_api_key:
            try:
                return self._compose_openai(bundle, to=to, subject=subject, instruction=instruction)
            except Exception:
                # Drafting should remain usable even if the API is temporarily unavailable.
                return fallback_compose(bundle, subject=subject, instruction=instruction)
        return fallback_compose(bundle, subject=subject, instruction=instruction)

    def _compose_openai(
        self,
        bundle: dict[str, Any],
        to: str,
        subject: str | None,
        instruction: str,
    ) -> EmailDraftContent:
        model = choose_model(self.settings, "email_draft")
        payload = {
            "model": model.model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": EMAIL_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "recipient": to,
                            "requested_subject": subject,
                            "draft_instruction": instruction,
                            "meeting": _bundle_for_prompt(bundle),
                        },
                        indent=2,
                    ),
                },
            ],
        }
        request = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI email composition failed: HTTP {exc.code}: {body}") from exc
        raw = json.loads(data["choices"][0]["message"]["content"])
        return parse_email_content(raw, fallback_subject=subject or f"Follow-up: {bundle['meeting'].title}", provider="openai")


def parse_email_content(raw: dict[str, Any], fallback_subject: str, provider: str = "openai") -> EmailDraftContent:
    subject = str(raw.get("subject") or fallback_subject).strip() or fallback_subject
    body = str(raw.get("body") or "").strip()
    if not body:
        body = "Hi,\n\nThanks for the conversation. I will follow up with next steps soon.\n\nBest,"
    tone = str(raw.get("tone") or "neutral").strip() or "neutral"
    included_items = [str(item).strip() for item in _as_list(raw.get("included_items")) if str(item).strip()]
    return EmailDraftContent(subject=subject, body=body, tone=tone, included_items=included_items, provider=provider)


def fallback_compose(bundle: dict[str, Any], subject: str | None = None, instruction: str = "") -> EmailDraftContent:
    meeting = bundle["meeting"]
    desired_subject = subject or f"Follow-up: {meeting.title}"
    tone = infer_tone(instruction)
    body_lines = [
        "Hi,",
        "",
        f"Thanks for the conversation about {meeting.title}.",
    ]
    if meeting.summary:
        body_lines.extend(["", meeting.summary])

    decisions = [row["text"] for row in bundle["decisions"]]
    action_items = [format_work_item(row) for row in bundle["action_items"]]
    open_questions = [row["text"] for row in bundle["open_questions"]]

    if decisions:
        body_lines.extend(["", "The main decision I have noted is:"])
        body_lines.extend([f"- {item}" for item in decisions[:3]])
    if action_items:
        body_lines.extend(["", "Next steps:"])
        body_lines.extend([f"- {item}" for item in action_items[:5]])
    if open_questions:
        body_lines.extend(["", "Open question to confirm:"])
        body_lines.extend([f"- {item}" for item in open_questions[:2]])

    body_lines.extend(["", closing_for_tone(tone)])
    included = []
    if decisions:
        included.append("decisions")
    if action_items:
        included.append("action_items")
    if open_questions:
        included.append("open_questions")
    return EmailDraftContent(
        subject=desired_subject,
        body="\n".join(body_lines),
        tone=tone,
        included_items=included,
        provider="fallback",
    )


def infer_tone(instruction: str) -> str:
    text = instruction.lower()
    if "warm" in text or "friendly" in text:
        return "warm"
    if "formal" in text or "professional" in text:
        return "professional"
    if "short" in text or "concise" in text or "brief" in text:
        return "concise"
    return "neutral"


def closing_for_tone(tone: str) -> str:
    if tone == "warm":
        return "Thanks again,"
    if tone == "concise":
        return "Thanks,"
    return "Best,"


def format_work_item(row: dict[str, Any]) -> str:
    owner = row.get("owner") or "unassigned"
    deadline = f" by {row['deadline']}" if row.get("deadline") else ""
    return f"{row['text']} ({owner}{deadline})"


def _bundle_for_prompt(bundle: dict[str, Any]) -> dict[str, Any]:
    meeting = bundle["meeting"]
    return {
        "title": meeting.title,
        "started_at": meeting.started_at,
        "summary": meeting.summary,
        "decisions": [row["text"] for row in bundle["decisions"]],
        "action_items": [
            {"text": row["text"], "owner": row.get("owner"), "deadline": row.get("deadline")}
            for row in bundle["action_items"]
        ],
        "commitments": [
            {"text": row["text"], "owner": row.get("owner"), "deadline": row.get("deadline")}
            for row in bundle["commitments"]
        ],
        "open_questions": [row["text"] for row in bundle["open_questions"]],
        "key_topics": [row["topic"] for row in bundle["key_topics"]],
        "entities": [row["name"] for row in bundle["entities"]],
    }


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
