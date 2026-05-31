from __future__ import annotations

import base64
from email.message import EmailMessage

from speedwagon_ai.config import Settings
from speedwagon_ai.storage import Repository


def build_followup_email(
    repo: Repository,
    meeting_id: int,
    to: str = "",
    subject: str | None = None,
    instruction: str = "",
) -> EmailMessage:
    bundle = repo.meeting_bundle(meeting_id)
    meeting = bundle["meeting"]
    message = EmailMessage()
    message["To"] = to
    message["Subject"] = subject or f"Follow-up: {meeting.title}"
    body = render_followup_body(bundle, instruction=instruction)
    message.set_content(body)
    return message


def create_gmail_draft(
    settings: Settings,
    repo: Repository,
    meeting_id: int,
    to: str = "",
    subject: str | None = None,
    instruction: str = "",
) -> str:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "Gmail drafting requires optional Google libraries: "
            "google-api-python-client google-auth-httplib2 google-auth-oauthlib"
        ) from exc

    scopes = ["https://www.googleapis.com/auth/gmail.compose"]
    creds = None
    if settings.gmail_token_path.exists():
        creds = Credentials.from_authorized_user_file(str(settings.gmail_token_path), scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not settings.gmail_credentials_path.exists():
                raise RuntimeError(f"Gmail credentials not found: {settings.gmail_credentials_path}")
            flow = InstalledAppFlow.from_client_secrets_file(str(settings.gmail_credentials_path), scopes)
            creds = flow.run_local_server(port=0)
        settings.gmail_token_path.parent.mkdir(parents=True, exist_ok=True)
        settings.gmail_token_path.write_text(creds.to_json(), encoding="utf-8")

    message = build_followup_email(repo, meeting_id, to=to, subject=subject, instruction=instruction)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    service = build("gmail", "v1", credentials=creds)
    draft = service.users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
    draft_id = str(draft["id"])
    repo.save_email_draft(
        meeting_id=meeting_id,
        provider="gmail",
        provider_draft_id=draft_id,
        recipient=to,
        subject=str(message["Subject"]),
        instruction=instruction or None,
        body=message.get_content(),
    )
    return draft_id


def render_followup_body(bundle: dict, instruction: str = "") -> str:
    meeting = bundle["meeting"]
    lines = [
        "Hi,",
        "",
    ]
    if instruction.strip():
        lines.extend(
            [
                f"Following up on {meeting.title}.",
                "",
                f"Focus for this draft: {instruction.strip()}",
                "",
            ]
        )
    else:
        lines.extend([f"Quick follow-up from {meeting.title}:", ""])
    lines.extend(
        [
            "Summary:",
            meeting.summary or "No summary captured.",
            "",
            "Decisions:",
        ]
    )
    lines.extend([f"- {row['text']}" for row in bundle["decisions"]] or ["- None captured"])
    lines.extend(["", "Action items:"])
    if bundle["action_items"]:
        for row in bundle["action_items"]:
            owner = row.get("owner") or "unassigned"
            deadline = f" due {row['deadline']}" if row.get("deadline") else ""
            lines.append(f"- {row['text']} ({owner}{deadline})")
    else:
        lines.append("- None captured")
    lines.extend(["", "Open questions:"])
    lines.extend([f"- {row['text']}" for row in bundle["open_questions"]] or ["- None captured"])
    lines.extend(["", "Thanks,"])
    return "\n".join(lines)


def preview_followup_email(
    repo: Repository,
    meeting_id: int,
    to: str = "",
    subject: str | None = None,
    instruction: str = "",
) -> dict[str, str]:
    bundle = repo.meeting_bundle(meeting_id)
    meeting = bundle["meeting"]
    return {
        "to": to,
        "subject": subject or f"Follow-up: {meeting.title}",
        "body": render_followup_body(bundle, instruction=instruction),
    }
