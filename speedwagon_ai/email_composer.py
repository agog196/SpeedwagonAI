from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any

from speedwagon_ai.config import Settings
from speedwagon_ai.model_router import choose_model
from speedwagon_ai.storage import Repository


DEFAULT_EMAIL_SIGNATURE = "Anish Gogineni"


EMAIL_SYSTEM_PROMPT = """You write concise, useful follow-up emails from meeting notes.
Return only valid JSON with these keys:
subject: string
body: string
tone: string
included_items: array of strings
The user's draft instruction is private guidance. Do not quote it or include it verbatim in the email unless the user explicitly asks you to quote it.
Use natural prose, not a raw dump of extracted action items and open questions.
Do not invent facts beyond the provided meeting context.
End the body with this exact sender signature on its own line: Anish Gogineni."""

CONTEXT_EMAIL_SYSTEM_PROMPT = """You write concise, useful email drafts from a local assistant context snapshot.
Return only valid JSON with these keys:
subject: string
body: string
tone: string
included_items: array of strings
The user's draft instruction is private guidance. Do not quote it or include it verbatim unless the user explicitly asks you to quote it.
Use the provided local tasks, meetings, decisions, and profile metadata. Do not invent facts beyond the local context and the user's requested message.
This creates a local editable draft only; do not say the email was sent.
End the body with this exact sender signature on its own line: Anish Gogineni."""


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
    body = ensure_email_signature(body)
    tone = str(raw.get("tone") or "neutral").strip() or "neutral"
    included_items = [str(item).strip() for item in _as_list(raw.get("included_items")) if str(item).strip()]
    return EmailDraftContent(subject=subject, body=body, tone=tone, included_items=included_items, provider=provider)


def compose_context_email(
    settings: Settings,
    *,
    recipient: str,
    subject: str | None,
    instruction: str,
    context: dict[str, Any] | None = None,
    tasks: list[dict[str, Any]] | None = None,
    meetings: list[dict[str, Any]] | None = None,
    decisions: list[dict[str, Any]] | None = None,
    related_contexts: list[dict[str, Any]] | None = None,
) -> EmailDraftContent:
    snapshot = {
        "context": context or {},
        "recipient": recipient,
        "tasks": _tasks_for_context_prompt(tasks or []),
        "meetings": _meetings_for_context_prompt(meetings or []),
        "decisions": _decisions_for_context_prompt(decisions or []),
        "related_contexts": _contexts_for_context_prompt(related_contexts or []),
    }
    fallback_subject = subject or context_email_subject(context, instruction)
    if settings.openai_api_key:
        try:
            return _compose_context_email_openai(
                settings,
                snapshot=snapshot,
                subject=fallback_subject,
                instruction=instruction,
            )
        except Exception:
            return fallback_context_email(
                snapshot,
                subject=fallback_subject,
                instruction=instruction,
            )
    return fallback_context_email(snapshot, subject=fallback_subject, instruction=instruction)


def _compose_context_email_openai(
    settings: Settings,
    *,
    snapshot: dict[str, Any],
    subject: str,
    instruction: str,
) -> EmailDraftContent:
    model = choose_model(settings, "email_draft")
    payload = {
        "model": model.model,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": CONTEXT_EMAIL_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "requested_subject": subject,
                        "draft_instruction": instruction,
                        "local_context": snapshot,
                    },
                    indent=2,
                    default=str,
                ),
            },
        ],
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI context email composition failed: HTTP {exc.code}: {body}") from exc
    raw = json.loads(data["choices"][0]["message"]["content"])
    return parse_email_content(raw, fallback_subject=subject, provider="openai")


def fallback_context_email(snapshot: dict[str, Any], *, subject: str, instruction: str) -> EmailDraftContent:
    context = snapshot.get("context") or {}
    context_name = context.get("name") or "that thread"
    tasks = snapshot.get("tasks") or []
    decisions = snapshot.get("decisions") or []
    tone = infer_tone(instruction)
    body_lines = [
        "Hi,",
        "",
        f"Following up on {context_name}.",
    ]
    if instruction:
        body_lines.extend(["", instruction.strip()])
    if decisions:
        body_lines.extend(["", "Relevant notes:"])
        body_lines.extend([f"- {item.get('text')}" for item in decisions[:3] if item.get("text")])
    open_tasks = [task for task in tasks if task.get("status") not in {"done", "canceled"}]
    if open_tasks:
        body_lines.extend(["", "Open items I have noted:"])
        for task in open_tasks[:5]:
            due = f" due {task['due_date']}" if task.get("due_date") else ""
            body_lines.append(f"- {task.get('text')}{due}")
    body_lines.extend(["", closing_for_tone(tone)])
    included = [f"task:{task.get('id')}" for task in open_tasks[:5] if task.get("id")]
    included.extend([f"decision:{item.get('id')}" for item in decisions[:3] if item.get("id")])
    return EmailDraftContent(
        subject=subject,
        body=ensure_email_signature("\n".join(body_lines)),
        tone=tone,
        included_items=included,
        provider="fallback",
    )


def context_email_subject(context: dict[str, Any] | None, instruction: str) -> str:
    name = (context or {}).get("name")
    if name:
        return f"Follow-up on {name}"
    cleaned = " ".join(str(instruction or "").split())
    return cleaned[:72] or "Follow-up"


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
        body=ensure_email_signature("\n".join(body_lines)),
        tone=tone,
        included_items=included,
        provider="fallback",
    )


def ensure_email_signature(body: str, signature: str = DEFAULT_EMAIL_SIGNATURE) -> str:
    cleaned = str(body or "").strip()
    if not cleaned:
        cleaned = "Hi,\n\nThanks,"
    for pattern in (
        r"\[Your Name\]",
        r"\{Your Name\}",
        r"\{\{Your Name\}\}",
        r"<Your Name>",
        r"\[Name\]",
    ):
        cleaned = re.sub(pattern, signature, cleaned, flags=re.IGNORECASE)
    if signature.lower() in cleaned[-300:].lower():
        return cleaned
    lines = cleaned.rstrip().splitlines()
    if lines and lines[-1].strip().lower() in {
        "best,",
        "best regards,",
        "regards,",
        "thanks,",
        "thanks again,",
        "thank you,",
    }:
        return f"{cleaned.rstrip()}\n{signature}"
    return f"{cleaned.rstrip()}\n\n{signature}"


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


def _tasks_for_context_prompt(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": task.get("id"),
            "text": task.get("text"),
            "status": task.get("status"),
            "due_date": task.get("due_date"),
            "owner": task.get("owner"),
            "owed_to": task.get("owed_to"),
            "project": task.get("project"),
            "meeting_title": task.get("meeting_title"),
        }
        for task in tasks[:12]
    ]


def _meetings_for_context_prompt(meetings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": meeting.get("id"),
            "title": meeting.get("title"),
            "started_at": meeting.get("started_at"),
            "summary": meeting.get("summary"),
        }
        for meeting in meetings[:8]
    ]


def _decisions_for_context_prompt(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": decision.get("id"),
            "text": decision.get("text"),
            "meeting_title": decision.get("meeting_title"),
            "started_at": decision.get("started_at"),
        }
        for decision in decisions[:8]
    ]


def _contexts_for_context_prompt(contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": context.get("id"),
            "name": context.get("name"),
            "kind": context.get("kind"),
            "profile_role": context.get("profile_role"),
            "profile_company": context.get("profile_company"),
        }
        for context in contexts[:8]
    ]


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
