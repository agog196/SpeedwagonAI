from __future__ import annotations

import base64
from email.message import EmailMessage

from speedwagon_ai.config import Settings
from speedwagon_ai.email_composer import EmailComposer, EmailDraftContent
from speedwagon_ai.storage import Repository


def build_email_message(
    draft: EmailDraftContent,
    to: str = "",
) -> EmailMessage:
    message = EmailMessage()
    message["To"] = to
    message["Subject"] = draft.subject
    message.set_content(draft.body)
    return message


def create_gmail_draft(
    settings: Settings,
    repo: Repository,
    meeting_id: int,
    to: str = "",
    subject: str | None = None,
    instruction: str = "",
    body: str | None = None,
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

    if body is None:
        draft_content = EmailComposer(settings, repo).compose(
            meeting_id,
            to=to,
            subject=subject,
            instruction=instruction,
        )
    else:
        fallback_subject = subject or f"Follow-up: {repo.get_meeting(meeting_id).title}"
        draft_content = EmailDraftContent(
            subject=fallback_subject,
            body=body,
            tone="edited",
            included_items=[],
            provider="edited",
        )
    message = build_email_message(draft_content, to=to)
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
        tone=draft_content.tone,
        included_items=draft_content.included_items,
    )
    return draft_id


def preview_followup_email(
    settings: Settings,
    repo: Repository,
    meeting_id: int,
    to: str = "",
    subject: str | None = None,
    instruction: str = "",
) -> dict:
    draft = EmailComposer(settings, repo).compose(meeting_id, to=to, subject=subject, instruction=instruction)
    return {
        "to": to,
        **draft.to_dict(),
    }
