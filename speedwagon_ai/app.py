from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from speedwagon_ai.assistant_actions import CAPABILITIES, run_action
from speedwagon_ai.assistant_commands import cancel_pending_action, confirm_pending_action, execute_command
from speedwagon_ai.capture import CaptureService, NativeCaptureService
from speedwagon_ai.config import Settings, local_api_token
from speedwagon_ai.context import render_context
from speedwagon_ai.email_composer import EmailDraftContent, ensure_email_signature
from speedwagon_ai.extraction import Extractor
from speedwagon_ai.integrations.calendar import GoogleCalendarService
from speedwagon_ai.integrations.gmail import create_gmail_draft, create_gmail_draft_from_content, preview_followup_email
from speedwagon_ai.intelligence import intelligence_status, refresh_daily_intelligence
from speedwagon_ai.meeting_bot import MeetingBotService
from speedwagon_ai.model_router import choose_model, cost_label, web_search_enabled
from speedwagon_ai.output import MarkdownWriter
from speedwagon_ai.processing import process_meeting
from speedwagon_ai.screenshot_context import analyze_screenshot
from speedwagon_ai.storage import Repository
from speedwagon_ai.system_tools import export_data, log_exception, logs_status, privacy_status, wipe_data
from speedwagon_ai.transcription import Transcriber
from speedwagon_ai.voice_tasks import VoiceTaskRecorder


TASK_MUTATING_ACTIONS = {
    "add_task",
    "complete_task",
    "reopen_task",
    "snooze_task",
    "cancel_task",
    "mark_task_waiting",
    "mark_task_uncertain",
    "confirm_suggestion",
    "dismiss_suggestion",
    "snooze_suggestion",
}

MAX_JSON_BODY_BYTES = 1_000_000
MAX_SCREENSHOT_BODY_BYTES = 8_000_000


def run_app(settings: Settings, repo: Repository, host: str, port: int) -> None:
    handler = make_handler(settings, repo)
    server = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}"
    settings.ensure_dirs()
    print(f"SpeedwagonAI app running at {url}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping SpeedwagonAI app.")
    finally:
        server.server_close()


def make_handler(settings: Settings, repo: Repository) -> type[BaseHTTPRequestHandler]:
    api_token = local_api_token(settings)

    class SpeedwagonHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            try:
                if parsed.path.startswith("/api/") and not self._authorized():
                    return
                if parsed.path == "/":
                    self._send_html(APP_HTML, set_token_cookie=True)
                elif parsed.path == "/app.css":
                    self._send_text(APP_CSS, "text/css")
                elif parsed.path == "/app.js":
                    self._send_text(APP_JS, "application/javascript")
                elif parsed.path == "/api/meetings":
                    limit = _limit_param(parse_qs(parsed.query).get("limit", ["20"])[0])
                    self._send_json({"meetings": [meeting_to_dict(m) for m in repo.list_meetings(limit=limit)]})
                elif parsed.path.startswith("/api/meetings/"):
                    meeting_id = _meeting_id_from_path(parsed.path)
                    self._send_json(meeting_detail(repo, meeting_id))
                elif parsed.path == "/api/context":
                    topic = parse_qs(parsed.query).get("topic", [""])[0]
                    self._send_json({"topic": topic, "markdown": render_context(repo, topic)})
                elif parsed.path == "/api/context-graph":
                    query = parse_qs(parsed.query).get("query", [""])[0]
                    self._send_json(repo.context_graph(query))
                elif parsed.path.startswith("/api/contexts/") and parsed.path.endswith("/detail"):
                    context_id = _context_id_from_path(parsed.path)
                    self._send_json(repo.context_detail(context_id))
                elif parsed.path == "/api/commitments":
                    query = parse_qs(parsed.query)
                    status = query.get("status", [""])[0] or None
                    person = query.get("person", [""])[0] or None
                    project = query.get("project", [""])[0] or None
                    include_final = query.get("include_final", ["false"])[0].lower() == "true"
                    items = repo.list_commitments(
                        status=status,
                        include_final=include_final,
                        person=person,
                        project=project,
                    )
                    self._send_json({"items": items, "commitments": items})
                elif parsed.path == "/api/daily-brief":
                    self._send_json(repo.daily_brief())
                elif parsed.path == "/api/intelligence/daily":
                    query = parse_qs(parsed.query)
                    self._send_json(intelligence_status(repo, query.get("date", [""])[0] or None))
                elif parsed.path == "/api/calendar/status":
                    self._send_json(GoogleCalendarService(settings, repo).status())
                elif parsed.path == "/api/calendar/events":
                    query = parse_qs(parsed.query)
                    start = query.get("from", [""])[0] or None
                    end = query.get("to", [""])[0] or None
                    if start:
                        _iso_date(start[:10], "from")
                    if end:
                        _iso_date(end[:10], "to")
                    limit = _limit_param(query.get("limit", ["50"])[0], maximum=100)
                    self._send_json(GoogleCalendarService(settings, repo).events(start_date=start, end_date=end, limit=limit))
                elif parsed.path == "/api/calendar/upcoming":
                    limit = _limit_param(parse_qs(parsed.query).get("limit", ["10"])[0], maximum=50)
                    self._send_json(GoogleCalendarService(settings, repo).upcoming(limit=limit))
                elif parsed.path == "/api/suggestions":
                    query = parse_qs(parsed.query, keep_blank_values=True)
                    status = query.get("status", ["open"])[0] or None
                    limit = _limit_param(query.get("limit", ["20"])[0])
                    self._send_json({"suggestions": repo.list_suggestions(status=status, limit=limit)})
                elif parsed.path.startswith("/api/suggestions/"):
                    suggestion_id = _suggestion_id_from_path(parsed.path)
                    self._send_json(suggestion_detail(repo, suggestion_id))
                elif parsed.path == "/api/email/drafts":
                    query = parse_qs(parsed.query, keep_blank_values=True)
                    status = query.get("status", ["local"])[0] or None
                    limit = _limit_param(query.get("limit", ["20"])[0])
                    self._send_json({"drafts": repo.list_followup_drafts(status=status, limit=limit)})
                elif parsed.path.startswith("/api/email/drafts/"):
                    draft_id = _draft_id_from_path(parsed.path)
                    self._send_json({"draft": repo.get_followup_draft(draft_id)})
                elif parsed.path == "/api/notifications/status":
                    self._send_json(repo.notification_status())
                elif parsed.path == "/api/notifications/candidates":
                    limit = _limit_param(parse_qs(parsed.query).get("limit", ["20"])[0])
                    self._send_json({"candidates": repo.notification_candidates(limit=limit)})
                elif parsed.path == "/api/assistant/capabilities":
                    self._send_json({"capabilities": CAPABILITIES})
                elif parsed.path == "/api/assistant/actions":
                    status = parse_qs(parsed.query).get("status", ["pending"])[0] or None
                    self._send_json({"actions": repo.list_pending_actions(status=status)})
                elif parsed.path == "/api/assistant/voice/status":
                    self._send_json(CaptureService(settings, repo).active_session("assistant_voice") or {"active": False})
                elif parsed.path == "/api/tasks":
                    task_query = parse_qs(parsed.query, keep_blank_values=True)
                    status = task_query.get("status", ["open"])[0] or None
                    include_done = task_query.get("include_done", ["false"])[0].lower() == "true"
                    self._send_json({"tasks": repo.list_tasks(status=status, include_done=include_done)})
                elif parsed.path == "/api/tasks/overdue":
                    self._send_json({"tasks": repo.overdue_tasks()})
                elif parsed.path == "/api/settings":
                    self._send_json(settings_payload(settings))
                elif parsed.path == "/api/system/logs":
                    self._send_json(logs_status(settings))
                elif parsed.path == "/api/system/privacy-status":
                    self._send_json(privacy_status(settings, repo))
                elif parsed.path == "/api/record/state":
                    self._send_json(recording_state(settings))
                elif parsed.path == "/api/tasks/record/state":
                    self._send_json(VoiceTaskRecorder(settings, repo).state())
                elif parsed.path == "/api/capture/status":
                    local_status = CaptureService(settings, repo).status()
                    native_status = NativeCaptureService(settings, repo).status()
                    if native_status.get("active"):
                        self._send_json(native_status)
                    else:
                        self._send_json({**local_status, "native_session": native_status})
                elif parsed.path == "/api/capture/diagnostics":
                    diagnostics = CaptureService(settings, repo).diagnostics()
                    diagnostics["native_capture"] = NativeCaptureService(settings, repo).status()
                    diagnostics["native_capture_note"] = (
                        "Native meeting capture uses ScreenCaptureKit for system audio and microphone where macOS supports it."
                    )
                    self._send_json(diagnostics)
                elif parsed.path == "/api/capture/bot/status":
                    self._send_json(MeetingBotService(settings, repo).status())
                elif parsed.path == "/api/capture/bot/sessions":
                    limit = _limit_param(parse_qs(parsed.query).get("limit", ["20"])[0])
                    status = parse_qs(parsed.query).get("status", [""])[0] or None
                    self._send_json({"sessions": MeetingBotService(settings, repo).sessions(limit=limit, status=status)})
                elif parsed.path.startswith("/api/capture/bot/sessions/"):
                    session_id = _bot_session_id_from_path(parsed.path)
                    self._send_json({"session": repo.get_bot_session(session_id)})
                elif parsed.path == "/api/integrations/google/status":
                    self._send_json(google_status(settings))
                elif parsed.path == "/api/integrations/apple/reminders":
                    self._send_json(apple_reminders_status())
                else:
                    self._send_error(HTTPStatus.NOT_FOUND, "Not found")
            except RequestTooLarge as exc:
                self._send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, str(exc))
            except ValueError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            except KeyError as exc:
                self._send_error(HTTPStatus.NOT_FOUND, str(exc))
            except Exception as exc:
                log_exception(settings, exc, path=parsed.path)
                self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "Internal SpeedwagonAI error. See local logs for details.")

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            try:
                if parsed.path.startswith("/api/") and not self._authorized():
                    return
                payload = self._read_json(max_bytes=MAX_SCREENSHOT_BODY_BYTES if parsed.path == "/api/assistant/screenshot/analyze" else MAX_JSON_BODY_BYTES)
                if parsed.path in {"/api/record/start", "/api/capture/local/start"}:
                    title = str(payload.get("title") or "").strip()
                    kind = str(payload.get("kind") or "meeting")
                    _optional_choice(kind, "kind", {"meeting", "assistant_voice", "task_note"})
                    if parsed.path == "/api/record/start" and not title:
                        self._send_error(HTTPStatus.BAD_REQUEST, "title is required")
                        return
                    repo.init()
                    session = CaptureService(settings, repo).start(
                        kind,
                        title=title,
                        metadata=payload.get("metadata") or {},
                    )
                    if parsed.path == "/api/record/start":
                        self._send_json({"meeting_id": session.get("meeting_id"), "session": session})
                    else:
                        self._send_json({"session": session})
                elif parsed.path in {"/api/record/stop", "/api/capture/local/stop"}:
                    repo.init()
                    process_after_stop = bool(payload.get("process"))
                    stop_kind = "meeting" if parsed.path == "/api/record/stop" else None
                    result = CaptureService(settings, repo).stop(kind=stop_kind, task_metadata=payload.get("task_metadata") or {})
                    session = result["session"]
                    if session["kind"] == "meeting" and process_after_stop:
                        processed = process_meeting(settings, repo, int(session["meeting_id"]))
                        result.update(
                            {
                                "meeting_id": int(session["meeting_id"]),
                                "meeting": meeting_to_dict(processed["meeting"]),
                                "transcript_path": str(processed["transcript_path"]),
                                "note_path": str(processed["note_path"]),
                                "commitments_path": str(processed["commitments_path"]),
                            }
                        )
                    if parsed.path == "/api/record/stop":
                        self._send_json({"meeting_id": result.get("meeting_id") or session.get("meeting_id"), "session": session})
                    else:
                        self._send_json(result)
                elif parsed.path == "/api/record/stop-process":
                    repo.init()
                    result = CaptureService(settings, repo).stop(kind="meeting")
                    meeting_id = int(result["session"]["meeting_id"])
                    result = process_meeting(settings, repo, meeting_id)
                    self._send_json(
                        {
                            "meeting_id": meeting_id,
                            "meeting": meeting_to_dict(result["meeting"]),
                            "transcript_path": str(result["transcript_path"]),
                            "note_path": str(result["note_path"]),
                            "commitments_path": str(result["commitments_path"]),
                        }
                    )
                elif parsed.path == "/api/capture/native/prepare":
                    repo.init()
                    kind = _optional_choice(str(payload.get("kind") or "meeting"), "kind", {"meeting", "task_note", "assistant_voice"})
                    title = str(payload.get("title") or "")
                    if kind == "meeting":
                        _required_string(title, "title")
                    session = NativeCaptureService(settings, repo).prepare(
                        kind=kind,
                        title=title,
                        mode=str(payload.get("mode") or "system_mic"),
                    )
                    self._send_json({"session": session})
                elif parsed.path == "/api/capture/native/complete":
                    repo.init()
                    process_after_stop = bool(payload.get("process"))
                    session = NativeCaptureService(settings, repo).complete(
                        session_id=str(payload.get("session_id") or ""),
                        audio_path=str(payload.get("audio_path") or ""),
                        process=process_after_stop,
                        warnings=[str(item) for item in payload.get("warnings") or []],
                    )
                    result: dict[str, Any] = {"session": session, "meeting_id": int(session["meeting_id"])}
                    if process_after_stop:
                        processed = process_meeting(settings, repo, int(session["meeting_id"]))
                        result.update(
                            {
                                "meeting": meeting_to_dict(processed["meeting"]),
                                "transcript_path": str(processed["transcript_path"]),
                                "note_path": str(processed["note_path"]),
                                "commitments_path": str(processed["commitments_path"]),
                            }
                        )
                    self._send_json(result)
                elif parsed.path == "/api/capture/native/fail":
                    repo.init()
                    session = NativeCaptureService(settings, repo).fail(
                        session_id=str(payload.get("session_id") or ""),
                        error=str(payload.get("error") or "Native capture failed."),
                    )
                    self._send_json({"session": session})
                elif parsed.path == "/api/capture/bot/join":
                    repo.init()
                    meeting_url = _required_string(payload.get("meeting_url"), "meeting_url")
                    title = _required_string(payload.get("title"), "title")
                    self._send_json(
                        MeetingBotService(settings, repo).join(
                            meeting_url=meeting_url,
                            title=title,
                            join_at=_optional(payload.get("join_at")),
                            bot_name=_optional(payload.get("bot_name")),
                            consent_confirmed=bool(payload.get("consent_confirmed")),
                        )
                    )
                elif parsed.path == "/api/capture/bot/sessions/clear":
                    repo.init()
                    cleared_count = repo.clear_bot_sessions()
                    self._send_json(
                        {
                            "cleared_count": cleared_count,
                            "sessions": MeetingBotService(settings, repo).sessions(limit=20),
                        }
                    )
                elif parsed.path.startswith("/api/capture/bot/sessions/") and parsed.path.endswith("/sync"):
                    repo.init()
                    self._send_json(MeetingBotService(settings, repo).sync(_bot_session_id_from_path(parsed.path)))
                elif parsed.path.startswith("/api/capture/bot/sessions/") and parsed.path.endswith("/process"):
                    repo.init()
                    self._send_json(
                        MeetingBotService(settings, repo).process(_bot_session_id_from_path(parsed.path))
                    )
                elif parsed.path == "/api/calendar/sync":
                    repo.init()
                    self._send_json(GoogleCalendarService(settings, repo).sync())
                elif parsed.path == "/api/calendar/events":
                    repo.init()
                    title = _required_string(payload.get("title"), "title")
                    start_at = _required_string(payload.get("start_at"), "start_at")
                    end_at = _required_string(payload.get("end_at"), "end_at")
                    _iso_datetime(start_at, "start_at")
                    _iso_datetime(end_at, "end_at")
                    if _datetime_value(end_at) <= _datetime_value(start_at):
                        raise ValueError("end_at must be after start_at")
                    attendees = _attendees_payload(payload.get("attendees"))
                    send_updates = str(payload.get("send_updates") or "none")
                    self._send_json(
                        GoogleCalendarService(settings, repo).create_event(
                            title=title,
                            start_at=start_at,
                            end_at=end_at,
                            calendar_id=str(payload.get("calendar_id") or "primary"),
                            timezone_name=_optional(payload.get("timezone")),
                            description=_optional(payload.get("description")),
                            location=_optional(payload.get("location")),
                            attendees=attendees,
                            send_updates=send_updates,
                        )
                    )
                elif parsed.path == "/api/system/export":
                    output = _optional(payload.get("output_path") or payload.get("path"))
                    if output and "\x00" in output:
                        raise ValueError("output_path is invalid")
                    self._send_json(export_data(settings, repo, Path(output) if output else None))
                elif parsed.path == "/api/system/wipe":
                    _required_string(payload.get("confirm"), "confirm")
                    self._send_json(wipe_data(settings, repo, str(payload.get("confirm") or "")))
                elif parsed.path == "/api/intelligence/daily/refresh":
                    repo.init()
                    refresh_date = _optional(payload.get("date"))
                    if refresh_date:
                        _iso_date(refresh_date, "date")
                    self._send_json(
                        refresh_daily_intelligence(
                            settings,
                            repo,
                            refresh_date,
                            top_suggestion_limit=_limit_param(payload.get("top_suggestion_limit") or 8, default=8, maximum=8),
                        )
                    )
                elif parsed.path == "/api/assistant/voice/start":
                    repo.init()
                    session = CaptureService(settings, repo).start("assistant_voice")
                    self._send_json({"session": session})
                elif parsed.path == "/api/assistant/voice/stop":
                    repo.init()
                    result = CaptureService(settings, repo).stop(kind="assistant_voice")
                    response = execute_command(settings, repo, result["transcript"])
                    if response.get("action") in TASK_MUTATING_ACTIONS:
                        MarkdownWriter(settings, repo).write_commitments()
                    result["assistant_response"] = response
                    self._send_json(result)
                elif parsed.path == "/api/assistant/voice/transcribe":
                    repo.init()
                    result = CaptureService(settings, repo).stop(kind="assistant_voice")
                    self._send_json(result)
                elif parsed.path == "/api/tasks":
                    text = _required_string(payload.get("text"), "text")
                    due_date = _optional(payload.get("due_date"))
                    if due_date:
                        _iso_date(due_date, "due_date")
                    task = repo.create_task(
                        text,
                        owner=_optional(payload.get("owner")),
                        due_date=due_date,
                        owed_to=_optional(payload.get("owed_to")),
                        project=_optional(payload.get("project")),
                    )
                    MarkdownWriter(settings, repo).write_commitments()
                    self._send_json({"task": task})
                elif parsed.path == "/api/tasks/done/clear":
                    cleared = repo.clear_done_tasks()
                    MarkdownWriter(settings, repo).write_commitments()
                    self._send_json({"cleared": cleared})
                elif parsed.path == "/api/tasks/record/start":
                    state = CaptureService(settings, repo).start("task_note")
                    self._send_json(state)
                elif parsed.path == "/api/tasks/record/stop":
                    result = CaptureService(settings, repo).stop(
                        kind="task_note",
                        task_metadata={
                            "owner": _optional(payload.get("owner")),
                            "due_date": _optional(payload.get("due_date")),
                            "project": _optional(payload.get("project")),
                        },
                    )
                    MarkdownWriter(settings, repo).write_commitments()
                    self._send_json(result)
                elif parsed.path.startswith("/api/tasks/") and parsed.path.endswith("/complete"):
                    task_id = _task_id_from_path(parsed.path)
                    task = run_action(settings, repo, "complete_task", {"task_id": task_id})["task"]
                    MarkdownWriter(settings, repo).write_commitments()
                    self._send_json({"task": task})
                elif parsed.path.startswith("/api/tasks/") and parsed.path.endswith("/reopen"):
                    task_id = _task_id_from_path(parsed.path)
                    task = repo.reopen_task(task_id)
                    MarkdownWriter(settings, repo).write_commitments()
                    self._send_json({"task": task})
                elif parsed.path.startswith("/api/commitments/") and parsed.path.endswith("/confirm"):
                    task_id = _task_id_from_path(parsed.path)
                    task = repo.complete_task(task_id)
                    MarkdownWriter(settings, repo).write_commitments()
                    self._send_json({"task": task, "commitment": task})
                elif parsed.path.startswith("/api/commitments/") and parsed.path.endswith("/snooze"):
                    task_id = _task_id_from_path(parsed.path)
                    task = repo.snooze_task(task_id, _optional(payload.get("until")))
                    MarkdownWriter(settings, repo).write_commitments()
                    self._send_json({"task": task, "commitment": task})
                elif parsed.path.startswith("/api/commitments/") and parsed.path.endswith("/cancel"):
                    task_id = _task_id_from_path(parsed.path)
                    task = repo.cancel_task(task_id)
                    MarkdownWriter(settings, repo).write_commitments()
                    self._send_json({"task": task, "commitment": task})
                elif parsed.path == "/api/suggestions/reviewed/clear":
                    self._send_json({"cleared": repo.clear_reviewed_suggestions()})
                elif parsed.path.startswith("/api/suggestions/") and parsed.path.endswith("/confirm"):
                    suggestion_id = _suggestion_id_from_path(parsed.path)
                    response = run_action(settings, repo, "confirm_suggestion", {"suggestion_id": suggestion_id})
                    if response.get("action_result", {}).get("task"):
                        MarkdownWriter(settings, repo).write_commitments()
                    self._send_json(response)
                elif parsed.path.startswith("/api/suggestions/") and parsed.path.endswith("/dismiss"):
                    suggestion_id = _suggestion_id_from_path(parsed.path)
                    self._send_json(run_action(settings, repo, "dismiss_suggestion", {"suggestion_id": suggestion_id}))
                elif parsed.path.startswith("/api/suggestions/") and parsed.path.endswith("/snooze"):
                    suggestion_id = _suggestion_id_from_path(parsed.path)
                    until = _optional(payload.get("until"))
                    if until:
                        _iso_date(until, "until")
                    self._send_json(
                        run_action(
                            settings,
                            repo,
                            "snooze_suggestion",
                            {"suggestion_id": suggestion_id, "until": until},
                        )
                    )
                elif parsed.path.startswith("/api/notifications/") and parsed.path.endswith("/mark-delivered"):
                    suggestion_id = _notification_id_from_path(parsed.path)
                    self._send_json(repo.mark_notification_delivered(suggestion_id))
                elif parsed.path.startswith("/api/notifications/") and parsed.path.endswith("/dismiss"):
                    suggestion_id = _notification_id_from_path(parsed.path)
                    self._send_json(repo.dismiss_notification(suggestion_id))
                elif parsed.path.startswith("/api/notifications/") and parsed.path.endswith("/snooze"):
                    suggestion_id = _notification_id_from_path(parsed.path)
                    until = _optional(payload.get("until"))
                    if until:
                        _iso_date(until, "until")
                    self._send_json(repo.snooze_notification(suggestion_id, until))
                elif parsed.path.startswith("/api/email/drafts/") and parsed.path.endswith("/update"):
                    draft_id = _draft_id_from_path(parsed.path)
                    subject = _optional(payload.get("subject"))
                    body = str(payload.get("body")) if payload.get("body") is not None else None
                    if subject is not None:
                        _required_string(subject, "subject")
                    if body is not None:
                        _required_string(body, "body")
                        body = ensure_email_signature(body)
                    self._send_json(
                        {
                            "draft": repo.update_followup_draft(
                                draft_id,
                                recipient=_optional(payload.get("to") or payload.get("recipient")),
                                subject=subject,
                                body=body,
                            )
                        }
                    )
                elif parsed.path.startswith("/api/email/drafts/") and parsed.path.endswith("/gmail-draft"):
                    draft_id = _draft_id_from_path(parsed.path)
                    draft = repo.get_followup_draft(draft_id)
                    if draft.get("status") == "gmail_draft" and draft.get("provider_draft_id"):
                        self._send_json({"draft_id": draft.get("provider_draft_id"), "draft": draft, "reused": True})
                        return
                    recipient = _optional(payload.get("to") or payload.get("recipient") or draft.get("recipient"))
                    if not recipient:
                        self._send_error(HTTPStatus.BAD_REQUEST, "recipient is required")
                        return
                    subject = str(payload.get("subject") or draft.get("subject") or "Follow-up")
                    body = str(payload.get("body") if payload.get("body") is not None else draft.get("body") or "")
                    body = ensure_email_signature(body)
                    updated = repo.update_followup_draft(draft_id, recipient=recipient, subject=subject, body=body)
                    content = EmailDraftContent(
                        subject=str(updated.get("subject") or subject),
                        body=str(updated.get("body") or body),
                        tone="edited",
                        included_items=[str(value) for value in [updated.get("task_id"), updated.get("suggestion_id")] if value],
                        provider="edited",
                    )
                    provider_draft_id = create_gmail_draft_from_content(settings, content, to=recipient)
                    saved = repo.update_followup_draft(
                        draft_id,
                        status="gmail_draft",
                        provider="gmail",
                        provider_draft_id=provider_draft_id,
                    )
                    if saved.get("meeting_id"):
                        repo.save_email_draft(
                            meeting_id=int(saved["meeting_id"]),
                            provider="gmail",
                            provider_draft_id=provider_draft_id,
                            recipient=recipient,
                            subject=str(saved.get("subject") or subject),
                            instruction=None,
                            body=str(saved.get("body") or body),
                            tone="edited",
                            included_items=content.included_items,
                        )
                    self._send_json({"draft_id": provider_draft_id, "draft": saved})
                elif parsed.path == "/api/integrations/apple/reminders":
                    self._send_error(
                        HTTPStatus.NOT_IMPLEMENTED,
                        "Apple Reminders writes are planned for the native Mac app and require explicit user approval.",
                    )
                elif parsed.path == "/api/actions":
                    action = str(payload.get("action") or "")
                    self._send_json(run_action(settings, repo, action, payload.get("payload") or {}))
                elif parsed.path == "/api/contexts":
                    repo.init()
                    name = _required_string(payload.get("name"), "name")
                    kind = str(payload.get("kind") or "person").strip().lower() or "person"
                    if kind not in {"person", "project", "topic"}:
                        raise ValueError("kind must be person, project, or topic")
                    context = repo.ensure_context(name, kind=kind)
                    profile_fields = {
                        "email": _optional(payload.get("email")),
                        "phone": _optional(payload.get("phone")),
                        "role": _optional(payload.get("role")),
                        "company": _optional(payload.get("company")),
                        "notes": _optional(payload.get("notes")),
                    }
                    if any(value is not None for value in profile_fields.values()):
                        repo.update_context_profile(int(context["id"]), **profile_fields)
                    self._send_json(repo.context_detail(int(context["id"])))
                elif parsed.path.startswith("/api/contexts/") and parsed.path.endswith("/profile"):
                    context_id = _context_id_from_path(parsed.path)
                    repo.update_context_profile(
                        context_id,
                        email=_optional(payload.get("email")),
                        phone=_optional(payload.get("phone")),
                        role=_optional(payload.get("role")),
                        company=_optional(payload.get("company")),
                        notes=_optional(payload.get("notes")),
                    )
                    self._send_json(repo.context_detail(context_id))
                elif parsed.path == "/api/assistant/command":
                    command = _required_string(payload.get("command"), "command")
                    response = execute_command(settings, repo, command)
                    if response.get("action") in TASK_MUTATING_ACTIONS:
                        MarkdownWriter(settings, repo).write_commitments()
                    self._send_json(response)
                elif parsed.path.startswith("/api/assistant/actions/") and parsed.path.endswith("/confirm"):
                    action_id = _assistant_action_id_from_path(parsed.path)
                    response = confirm_pending_action(settings, repo, action_id)
                    if response.get("action") in TASK_MUTATING_ACTIONS:
                        MarkdownWriter(settings, repo).write_commitments()
                    self._send_json(response)
                elif parsed.path.startswith("/api/assistant/actions/") and parsed.path.endswith("/cancel"):
                    action_id = _assistant_action_id_from_path(parsed.path)
                    self._send_json(cancel_pending_action(repo, action_id))
                elif parsed.path == "/api/assistant/screenshot/analyze":
                    _required_string(payload.get("image_base64"), "image_base64")
                    self._send_json(
                        analyze_screenshot(
                            settings,
                            repo,
                            image_base64=str(payload.get("image_base64") or ""),
                            instruction=str(payload.get("instruction") or ""),
                        )
                    )
                elif parsed.path.startswith("/api/meetings/") and parsed.path.endswith("/process"):
                    meeting_id = _meeting_id_from_path(parsed.path)
                    repo.init()
                    result = process_meeting(settings, repo, meeting_id)
                    self._send_json(
                        {
                            "meeting": meeting_to_dict(result["meeting"]),
                            "transcript_path": str(result["transcript_path"]),
                            "note_path": str(result["note_path"]),
                            "commitments_path": str(result["commitments_path"]),
                        }
                    )
                elif parsed.path.startswith("/api/meetings/") and parsed.path.endswith("/email/preview"):
                    meeting_id = _meeting_id_from_path(parsed.path)
                    recipient = _required_string(payload.get("to"), "to")
                    self._send_json(
                        preview_followup_email(
                            settings,
                            repo,
                            meeting_id,
                            to=recipient,
                            subject=_optional(payload.get("subject")),
                            instruction=str(payload.get("instruction") or ""),
                        )
                    )
                elif parsed.path.startswith("/api/meetings/") and parsed.path.endswith("/email/draft"):
                    meeting_id = _meeting_id_from_path(parsed.path)
                    recipient = _required_string(payload.get("to"), "to")
                    draft_id = create_gmail_draft(
                        settings,
                        repo,
                        meeting_id,
                        to=recipient,
                        subject=_optional(payload.get("subject")),
                        instruction=str(payload.get("instruction") or ""),
                        body=ensure_email_signature(_optional(payload.get("body"))) if _optional(payload.get("body")) else None,
                    )
                    self._send_json({"draft_id": draft_id, "drafts": repo.email_drafts_for_meeting(meeting_id)})
                else:
                    self._send_error(HTTPStatus.NOT_FOUND, "Not found")
            except RequestTooLarge as exc:
                self._send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, str(exc))
            except ValueError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            except KeyError as exc:
                self._send_error(HTTPStatus.NOT_FOUND, str(exc))
            except Exception as exc:
                log_exception(settings, exc, path=parsed.path)
                self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "Internal SpeedwagonAI error. See local logs for details.")

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _read_json(self, *, max_bytes: int = MAX_JSON_BODY_BYTES) -> dict[str, Any]:
            try:
                length = int(self.headers.get("Content-Length") or "0")
            except ValueError as exc:
                raise ValueError("Content-Length is invalid") from exc
            if length == 0:
                return {}
            if length > max_bytes:
                self.rfile.read(length)
                raise RequestTooLarge(f"JSON body is too large. Limit is {max_bytes} bytes.")
            raw = self.rfile.read(length).decode("utf-8")
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError("Malformed JSON body") from exc
            if not isinstance(payload, dict):
                raise ValueError("JSON body must be an object")
            return payload

        def _authorized(self) -> bool:
            if not self._loopback_request_allowed():
                self._send_error(HTTPStatus.FORBIDDEN, "Remote local API access is disabled.")
                return False
            auth = self.headers.get("Authorization", "")
            if auth == f"Bearer {api_token}":
                return True
            cookie_header = self.headers.get("Cookie", "")
            cookies = parse_cookie_header(cookie_header)
            if cookies.get("speedwagon_api_token") == api_token:
                return True
            self._send_error(HTTPStatus.UNAUTHORIZED, "SpeedwagonAI API token is required.")
            return False

        def _loopback_request_allowed(self) -> bool:
            if settings.allow_remote_api:
                return True
            host = (self.headers.get("Host") or "").split(":", 1)[0].strip().lower()
            if host not in {"127.0.0.1", "localhost", "::1"}:
                return False
            for header in ["Origin", "Referer"]:
                value = self.headers.get(header)
                if not value:
                    continue
                parsed = urlparse(value)
                if (parsed.hostname or "").lower() not in {"127.0.0.1", "localhost", "::1"}:
                    return False
            return True

        def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            data = json.dumps(payload, default=json_default).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_html(self, text: str, *, set_token_cookie: bool = False) -> None:
            self._send_text(text, "text/html; charset=utf-8", set_token_cookie=set_token_cookie)

        def _send_text(self, text: str, content_type: str, *, set_token_cookie: bool = False) -> None:
            data = text.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            if set_token_cookie:
                self.send_header(
                    "Set-Cookie",
                    f"speedwagon_api_token={api_token}; Path=/; SameSite=Strict; HttpOnly",
                )
            self.end_headers()
            self.wfile.write(data)

        def _send_error(self, status: HTTPStatus, message: str) -> None:
            self._send_json({"error": message}, status=status)

    return SpeedwagonHandler


class RequestTooLarge(ValueError):
    pass


def _limit_param(value: Any, *, default: int = 20, maximum: int = 100) -> int:
    if value in {None, ""}:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an integer") from exc
    if parsed < 1 or parsed > maximum:
        raise ValueError(f"limit must be between 1 and {maximum}")
    return parsed


def _required_string(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text


def _optional_choice(value: str, field: str, allowed: set[str]) -> str:
    text = str(value or "").strip()
    if text not in allowed:
        raise ValueError(f"{field} must be one of: {', '.join(sorted(allowed))}")
    return text


def _iso_date(value: str, field: str) -> str:
    text = str(value or "").strip()
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc
    return text


def _iso_datetime(value: str, field: str) -> str:
    _datetime_value(value, field)
    return str(value).strip()


def _datetime_value(value: str, field: str = "datetime") -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 datetime") from exc


def _attendees_payload(value: Any) -> list[str | dict[str, Any]]:
    if value is None or value == "":
        return []
    if not isinstance(value, list):
        raise ValueError("attendees must be a list")
    attendees: list[str | dict[str, Any]] = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
            if text and "@" not in text:
                raise ValueError("attendee emails must contain @")
            if text:
                attendees.append(text)
        elif isinstance(item, dict):
            email = str(item.get("email") or "").strip()
            if not email:
                continue
            if "@" not in email:
                raise ValueError("attendee emails must contain @")
            attendees.append(item)
        else:
            raise ValueError("attendees must contain emails or attendee objects")
    return attendees


def _meeting_id_from_path(path: str) -> int:
    parts = [part for part in path.split("/") if part]
    try:
        return int(parts[2])
    except (IndexError, ValueError) as exc:
        raise ValueError("Invalid meeting id") from exc


def _task_id_from_path(path: str) -> int:
    parts = [part for part in path.split("/") if part]
    try:
        return int(parts[2])
    except (IndexError, ValueError) as exc:
        raise ValueError("Invalid task id") from exc


def _assistant_action_id_from_path(path: str) -> int:
    parts = [part for part in path.split("/") if part]
    try:
        return int(parts[3])
    except (IndexError, ValueError) as exc:
        raise ValueError("Invalid assistant action id") from exc


def _suggestion_id_from_path(path: str) -> int:
    parts = [part for part in path.split("/") if part]
    try:
        return int(parts[2])
    except (IndexError, ValueError) as exc:
        raise ValueError("Invalid suggestion id") from exc


def _context_id_from_path(path: str) -> int:
    parts = [part for part in path.split("/") if part]
    try:
        return int(parts[2])
    except (IndexError, ValueError) as exc:
        raise ValueError("Invalid context id") from exc


def _notification_id_from_path(path: str) -> int:
    parts = [part for part in path.split("/") if part]
    try:
        return int(parts[2])
    except (IndexError, ValueError) as exc:
        raise ValueError("Invalid notification id") from exc


def _draft_id_from_path(path: str) -> int:
    parts = [part for part in path.split("/") if part]
    try:
        return int(parts[3])
    except (IndexError, ValueError) as exc:
        raise ValueError("Invalid draft id") from exc


def _bot_session_id_from_path(path: str) -> int:
    parts = [part for part in path.split("/") if part]
    try:
        return int(parts[4])
    except (IndexError, ValueError) as exc:
        raise ValueError("Invalid bot session id") from exc


def _optional(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_cookie_header(header: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for part in header.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        cookies[key.strip()] = value.strip()
    return cookies


def meeting_to_dict(meeting: Any) -> dict[str, Any]:
    return asdict(meeting)


def meeting_detail(repo: Repository, meeting_id: int) -> dict[str, Any]:
    bundle = repo.meeting_bundle(meeting_id)
    meeting = bundle["meeting"]
    transcript = ""
    if meeting.transcript_path and Path(meeting.transcript_path).exists():
        transcript = Path(meeting.transcript_path).read_text(encoding="utf-8")
    return {
        "meeting": meeting_to_dict(meeting),
        "action_items": bundle["action_items"],
        "commitments": bundle["commitments"],
        "decisions": bundle["decisions"],
        "open_questions": bundle["open_questions"],
        "key_topics": bundle["key_topics"],
        "entities": bundle["entities"],
        "email_drafts": repo.email_drafts_for_meeting(meeting_id),
        "transcript": transcript,
    }


def suggestion_detail(repo: Repository, suggestion_id: int) -> dict[str, Any]:
    suggestion = repo.get_suggestion(suggestion_id)
    related_tasks = []
    for task_id in suggestion.get("task_ids") or []:
        try:
            related_tasks.append(repo.get_task(int(task_id)))
        except (KeyError, ValueError):
            continue
    return {
        "suggestion": suggestion,
        "related_tasks": related_tasks,
        "followup_draft": repo.followup_draft_for_suggestion(suggestion_id),
        "review_status": suggestion_review_status(suggestion),
    }


def suggestion_review_status(suggestion: dict[str, Any]) -> str:
    if suggestion.get("status") in {"dismissed", "snoozed", "accepted", "retired", "archived"}:
        return str(suggestion.get("status"))
    if suggestion.get("retired_at"):
        return "retired"
    return "reviewable"


def recording_state(settings: Settings) -> dict[str, Any]:
    return CaptureService(settings, Repository(settings.db_path)).active_session("meeting") or {"active": False}


def settings_payload(settings: Settings) -> dict[str, Any]:
    diagnostics = CaptureService(settings, Repository(settings.db_path)).diagnostics()
    calendar_status = GoogleCalendarService(settings, Repository(settings.db_path)).status()
    cheap = choose_model(settings, "email_draft")
    strong = choose_model(settings, "deep_synthesis")
    command = choose_model(settings, "command_parse")
    vision = choose_model(settings, "vision_context")
    web = choose_model(settings, "web_search")
    return {
        "db_path": str(settings.db_path),
        "notes_dir": str(settings.notes_dir),
        "audio_dir": str(settings.audio_dir),
        "transcripts_dir": str(settings.transcripts_dir),
        "whisper_cpp_bin": settings.whisper_cpp_bin,
        "whisper_cpp_model": settings.whisper_cpp_model,
        "openai_key_present": bool(settings.openai_api_key),
        "cheap_model": cheap.model,
        "strong_model": strong.model,
        "command_model": command.model,
        "vision_model": vision.model,
        "web_model": web.model,
        "model_cost_labels": {
            "email_draft": cost_label(cheap),
            "deep_synthesis": cost_label(strong),
            "command_parse": cost_label(command),
            "vision_context": cost_label(vision),
            "web_search": cost_label(web),
        },
        "web_search_enabled": web_search_enabled(),
        "api_token_path": str(settings.api_token_path),
        "log_dir": logs_status(settings)["log_dir"],
        "app_log_path": logs_status(settings)["app_log_path"],
        "backend_log_path": logs_status(settings)["backend_log_path"],
        "gmail_credentials_present": settings.gmail_credentials_path.exists(),
        "gmail_token_present": settings.gmail_token_path.exists(),
        "calendar_status": calendar_status.get("status"),
        "calendar_enabled": calendar_status.get("enabled"),
        "calendar_note": calendar_status.get("note"),
        "calendar_ids": calendar_status.get("calendar_ids"),
        "calendar_sync_days_back": calendar_status.get("sync_days_back"),
        "calendar_sync_days_forward": calendar_status.get("sync_days_forward"),
        "capture_profile": settings.capture_profile,
        "input_device": settings.input_device,
        "record_cmd": settings.record_cmd,
        "recorder_status": diagnostics["recorder_status"],
        "recorder_command_preview": diagnostics["recorder_command_preview"],
        "capture_note": capture_note(settings.capture_profile),
        "native_capture_available": True,
        "native_capture_default": "system_mic",
        "native_capture_note": (
            "Native Mac meeting capture records system audio with ScreenCaptureKit and microphone audio where allowed."
        ),
        "bot_provider": settings.bot_provider or "not_configured",
        "bot_configured": MeetingBotService(settings, Repository(settings.db_path)).status().get("enabled", False),
        "bot_note": "Meeting bot beta is optional, provider-backed, and should only join with explicit consent.",
    }


def google_status(settings: Settings) -> dict[str, Any]:
    calendar = GoogleCalendarService(settings, Repository(settings.db_path)).status()
    return {
        "gmail_credentials_present": settings.gmail_credentials_path.exists(),
        "gmail_token_present": settings.gmail_token_path.exists(),
        "gmail_drafts": "available" if settings.gmail_token_path.exists() else "needs_oauth",
        "calendar": calendar["status"],
        "calendar_status": calendar,
        "drive_docs": "planned",
    }


def apple_reminders_status() -> dict[str, Any]:
    return {
        "available": False,
        "status": "planned_native_mac_app_feature",
        "requires_user_approval": True,
    }


def bot_capture_status() -> dict[str, Any]:
    return {
        "enabled": False,
        "provider": "managed_provider_planned",
        "status": "not_configured",
        "note": "Meeting bot capture is planned as an opt-in beta; local capture remains the default path.",
    }


def capture_note(profile: str) -> str:
    if (profile or "mic").lower() == "blackhole":
        return "BlackHole mode records routed system audio only after macOS audio routing is configured."
    return (
        "Mic mode records your selected/default microphone only. It will not capture headphone/system audio. "
        "If SoX says no default audio device is configured, grant microphone permission to Terminal/VS Code "
        "and set SPEEDWAGON_INPUT_DEVICE to your macOS Sound Input device name."
    )


def json_default(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    return str(value)


APP_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SpeedwagonAI</title>
  <link rel="stylesheet" href="/app.css">
</head>
<body>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand">SpeedwagonAI</div>
      <nav>
        <button class="nav active" data-view="dashboard">Dashboard</button>
        <button class="nav" data-view="record">Recorder</button>
        <button class="nav" data-view="meetings">Meetings</button>
        <button class="nav" data-view="calendar">Calendar</button>
        <button class="nav" data-view="notifications">Notifications</button>
        <button class="nav" data-view="tasks">Tasks</button>
        <button class="nav" data-view="commitments">Commitments</button>
        <button class="nav" data-view="settings">Settings</button>
      </nav>
    </aside>
    <main>
      <header>
        <div>
          <h1 id="view-title">Dashboard</h1>
          <p id="status">Ready</p>
        </div>
        <button id="refresh">Refresh</button>
      </header>

      <section id="dashboard" class="view active">
        <div class="grid two">
          <section class="panel">
            <h2>Assistant</h2>
            <div class="row">
              <input id="assistant-command" placeholder="Ask: what is overdue, complete task 12, search context for onboarding">
              <button id="assistant-run">Run</button>
            </div>
            <pre id="assistant-output"></pre>
          </section>
          <section class="panel">
            <h2>Recent Meetings</h2>
            <div id="recent-meetings" class="list"></div>
          </section>
        </div>
        <div class="grid single">
          <section class="panel">
            <h2>Daily Brief</h2>
            <div id="daily-brief" class="brief-grid"></div>
          </section>
        </div>
        <div class="grid single">
          <section class="panel">
            <h2>Context Search</h2>
            <div class="row">
              <input id="context-topic" placeholder="Topic">
              <button id="context-search">Search</button>
            </div>
            <pre id="context-output"></pre>
          </section>
        </div>
      </section>

      <section id="record" class="view">
        <section class="panel">
          <h2>Recorder</h2>
          <div class="row">
            <input id="record-title" placeholder="Meeting title">
            <button id="record-start">Start</button>
            <button id="record-stop">Stop</button>
            <button id="record-stop-process">Stop + Process</button>
          </div>
          <pre id="record-state"></pre>
          <h3>Diagnostics</h3>
          <pre id="capture-diagnostics"></pre>
        </section>
        <section class="panel">
          <h2>Meeting Bot Beta</h2>
          <p class="meta">Optional provider-backed capture for Zoom, Meet, Teams, and similar meeting links. Bots join visibly and may incur provider cost. Refresh/sessions can request provider transcription for completed recordings.</p>
          <div class="stack">
            <input id="bot-title" placeholder="Meeting title">
            <input id="bot-url" placeholder="Meeting link">
            <label class="check-row">
              <input id="bot-consent" type="checkbox">
              <span>I confirm bot capture is allowed and disclosed for this meeting.</span>
            </label>
            <div class="row">
              <button id="bot-join">Join Bot</button>
              <button id="bot-refresh">Refresh Bot Sessions</button>
            </div>
          </div>
          <pre id="bot-status"></pre>
          <div id="bot-sessions" class="list"></div>
        </section>
      </section>

      <section id="meetings" class="view">
        <div class="grid meetings-layout">
          <section class="panel">
            <h2>Meetings</h2>
            <div id="meeting-list" class="list"></div>
          </section>
          <section class="panel detail">
            <div class="detail-head">
              <h2 id="meeting-title">Select a meeting</h2>
              <button id="process-meeting">Process</button>
            </div>
            <div id="meeting-detail"></div>
            <h3>Email Draft</h3>
            <div class="stack">
              <input id="email-to" placeholder="Recipient">
              <input id="email-subject" placeholder="Subject">
              <textarea id="email-instruction" placeholder="Draft instructions, e.g. make it warm, concise, and focus on next steps"></textarea>
              <div class="row">
                <button id="email-preview">Generate Preview</button>
                <button id="email-create">Create Gmail Draft</button>
              </div>
              <textarea id="email-body" class="email-preview" placeholder="Generated draft body will appear here. You can edit it before creating the Gmail draft."></textarea>
              <pre id="email-meta"></pre>
            </div>
          </section>
        </div>
      </section>

      <section id="tasks" class="view">
        <div class="grid two">
          <section class="panel">
            <h2>Task Inbox</h2>
            <div class="stack task-add">
              <input id="task-text" placeholder="Add a task">
              <div class="row">
                <input id="task-owner" placeholder="Owner">
                <input id="task-due" placeholder="Due YYYY-MM-DD">
                <button id="task-add">Add</button>
              </div>
            </div>
            <h3>Voice Task</h3>
            <div class="row">
              <button id="task-record-start">Start Voice Task</button>
              <button id="task-record-stop">Stop + Add Task</button>
            </div>
            <pre id="task-record-state"></pre>
          </section>
          <section class="panel">
            <h2>Reminder Suggestions</h2>
            <div id="task-suggestions" class="list"></div>
          </section>
        </div>
        <div id="task-groups" class="task-groups"></div>
      </section>

      <section id="calendar" class="view">
        <div class="grid two">
          <section class="panel">
            <h2>Google Calendar</h2>
            <p class="meta">Syncs a limited local window for daily brief/prep context. Event creation is explicit.</p>
            <div class="row">
              <button id="calendar-sync">Sync Calendar</button>
              <button id="calendar-refresh">Refresh Calendar</button>
            </div>
            <pre id="calendar-status"></pre>
          </section>
          <section class="panel">
            <h2>Upcoming</h2>
            <div id="calendar-upcoming" class="list"></div>
          </section>
        </div>
      </section>

      <section id="notifications" class="view">
        <div class="grid two">
          <section class="panel">
            <h2>Notifications</h2>
            <p class="meta">Local candidates only. Native macOS delivery happens from the Mac app while it is running.</p>
            <div class="row">
              <button id="notifications-refresh">Refresh Notifications</button>
            </div>
            <pre id="notifications-status"></pre>
          </section>
          <section class="panel">
            <h2>Candidates</h2>
            <div id="notifications-candidates" class="list"></div>
          </section>
        </div>
      </section>

      <section id="commitments" class="view">
        <section class="panel">
          <h2>Open Work</h2>
          <div id="commitment-list" class="list"></div>
        </section>
      </section>

      <section id="settings" class="view">
        <section class="panel">
          <h2>Settings</h2>
          <div id="settings-list" class="kv"></div>
        </section>
      </section>
    </main>
  </div>
  <script src="/app.js"></script>
</body>
</html>
"""


APP_CSS = """
:root {
  --bg: #f5f5f2;
  --panel: #ffffff;
  --line: #d8d8d2;
  --text: #1d211f;
  --muted: #68706b;
  --accent: #186a5d;
  --accent-2: #9b3c45;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 14px;
}
.shell { display: grid; grid-template-columns: 220px 1fr; min-height: 100vh; }
.sidebar {
  border-right: 1px solid var(--line);
  background: #ebeee9;
  padding: 18px 14px;
}
.brand { font-weight: 750; font-size: 18px; margin: 4px 6px 22px; }
nav { display: grid; gap: 6px; }
button, input, textarea {
  font: inherit;
}
button {
  border: 1px solid var(--line);
  background: #ffffff;
  color: var(--text);
  border-radius: 6px;
  min-height: 34px;
  padding: 7px 11px;
  cursor: pointer;
}
button:hover { border-color: var(--accent); }
.nav {
  text-align: left;
  background: transparent;
  border-color: transparent;
}
.nav.active {
  background: #ffffff;
  border-color: var(--line);
  color: var(--accent);
}
main { padding: 22px; min-width: 0; }
header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 18px;
}
h1, h2, h3, p { margin: 0; }
h1 { font-size: 24px; font-weight: 760; }
h2 { font-size: 16px; margin-bottom: 14px; }
h3 { font-size: 14px; margin: 20px 0 10px; }
#status { color: var(--muted); margin-top: 4px; }
.view { display: none; }
.view.active { display: block; }
.grid { display: grid; gap: 16px; }
.two { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
.single { grid-template-columns: minmax(0, 1fr); margin-top: 16px; }
.brief-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.brief-card {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 10px;
  background: #fbfbf9;
}
.brief-card strong { display: block; margin-bottom: 5px; }
.meetings-layout { grid-template-columns: 320px minmax(0, 1fr); align-items: start; }
.panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 16px;
}
.row { display: flex; gap: 8px; align-items: center; }
.check-row { display: flex; gap: 8px; align-items: center; color: var(--muted); font-size: 13px; }
.check-row input { width: auto; }
.stack { display: grid; gap: 8px; }
input, textarea {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 6px;
  min-height: 36px;
  padding: 8px 10px;
  background: #fff;
  color: var(--text);
}
textarea { min-height: 92px; resize: vertical; }
.email-preview { min-height: 260px; line-height: 1.45; }
.list { display: grid; gap: 8px; }
.item {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 10px;
  background: #fbfbf9;
}
.item button { margin-top: 8px; }
.meta { color: var(--muted); font-size: 12px; margin-top: 3px; }
.detail-head { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
pre {
  white-space: pre-wrap;
  background: #f6f6f3;
  border: 1px solid var(--line);
  border-radius: 6px;
  min-height: 42px;
  padding: 10px;
  overflow: auto;
}
.kv { display: grid; grid-template-columns: 220px minmax(0, 1fr); gap: 8px 14px; }
.kv div:nth-child(odd) { color: var(--muted); }
.task-add { margin-bottom: 4px; }
.task-groups {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-top: 16px;
}
.task-group h2 { margin-bottom: 10px; }
.task-actions { display: flex; gap: 8px; margin-top: 8px; }
.badge {
  display: inline-block;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 2px 7px;
  font-size: 12px;
  color: var(--muted);
}
@media (max-width: 860px) {
  .shell { grid-template-columns: 1fr; }
  .sidebar { border-right: 0; border-bottom: 1px solid var(--line); }
  nav { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .nav { text-align: center; }
  .two, .meetings-layout, .task-groups, .brief-grid { grid-template-columns: 1fr; }
  header { align-items: flex-start; }
}
"""


APP_JS = """
const state = { meetings: [], tasks: [], selectedMeetingId: null };

const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Request failed");
  return data;
}

function setStatus(text) {
  $("status").textContent = text;
}

function showView(name) {
  document.querySelectorAll(".view").forEach((node) => node.classList.toggle("active", node.id === name));
  document.querySelectorAll(".nav").forEach((node) => node.classList.toggle("active", node.dataset.view === name));
  $("view-title").textContent = name[0].toUpperCase() + name.slice(1);
}

async function refresh() {
  try {
    const [meetings, commitments, tasks, settings, captureStatus, taskRecordState, dailyBrief, captureDiagnostics, botStatus, botSessions, calendarStatus, calendarUpcoming, notificationStatus, notificationCandidates] = await Promise.all([
      api("/api/meetings"),
      api("/api/commitments"),
      api("/api/tasks?status=&include_done=true"),
      api("/api/settings"),
      api("/api/capture/status"),
      api("/api/tasks/record/state"),
      api("/api/daily-brief"),
      api("/api/capture/diagnostics"),
      api("/api/capture/bot/status"),
      api("/api/capture/bot/sessions"),
      api("/api/calendar/status"),
      api("/api/calendar/upcoming"),
      api("/api/notifications/status"),
      api("/api/notifications/candidates"),
    ]);
    state.meetings = meetings.meetings;
    state.tasks = tasks.tasks;
    renderMeetings();
    renderCommitments(commitments.items);
    renderTasks(tasks.tasks);
    renderDailyBrief(dailyBrief);
    renderSettings(settings);
    $("record-state").textContent = JSON.stringify(captureStatus, null, 2);
    $("task-record-state").textContent = JSON.stringify(taskRecordState, null, 2);
    $("capture-diagnostics").textContent = JSON.stringify(captureDiagnostics, null, 2);
    renderBotStatus(botStatus, botSessions.sessions || []);
    renderCalendar(calendarStatus, calendarUpcoming.events || [], dailyBrief);
    renderNotifications(notificationStatus, notificationCandidates.candidates || []);
    setStatus("Ready");
  } catch (error) {
    setStatus(error.message);
  }
}

function renderDailyBrief(brief) {
  const target = $("daily-brief");
  const cards = [
    ["Overdue", brief.overdue || []],
    ["Due today", brief.today || []],
    ["Waiting", brief.waiting || []],
    ["Uncertain", brief.uncertain || []],
    ["Stale", brief.stale || []],
    ["Recommended follow-ups", brief.recommended_followups || []],
    ["Calendar today", brief.calendar_today || []],
    ["Upcoming meetings", brief.calendar_upcoming || []],
    ["Meeting prep", brief.meeting_prep || []],
  ];
  target.innerHTML = "";
  cards.forEach(([label, items]) => {
    const node = document.createElement("div");
    node.className = "brief-card";
    const preview = items.slice(0, 3).map((item) => `<div class="meta">${escapeHtml(briefItemLabel(item))}</div>`).join("");
    node.innerHTML = `<strong>${label}: ${items.length}</strong>${preview || '<div class="meta">Nothing here.</div>'}`;
    target.appendChild(node);
  });
}

function briefItemLabel(item) {
  if (item.event) return `${item.event.start_at || ""} ${item.event.title || "Untitled event"}`;
  if (item.title && item.start_at) return `${item.start_at} ${item.title}`;
  if (item.text) return `[${item.id}] ${item.text}`;
  return JSON.stringify(item);
}

function renderMeetings() {
  const render = (target, compact) => {
    target.innerHTML = "";
    if (!state.meetings.length) {
      target.innerHTML = '<div class="meta">No meetings yet.</div>';
      return;
    }
    state.meetings.forEach((meeting) => {
      const item = document.createElement("div");
      item.className = "item";
      item.innerHTML = `
        <strong>${escapeHtml(meeting.title)}</strong>
        <div class="meta">${meeting.started_at.slice(0, 10)} · meeting ${meeting.id}</div>
        ${compact ? "" : `<button data-id="${meeting.id}">Open</button>`}
      `;
      if (!compact) item.querySelector("button").onclick = () => loadMeeting(meeting.id);
      target.appendChild(item);
    });
  };
  render($("recent-meetings"), true);
  render($("meeting-list"), false);
}

function renderCommitments(items) {
  const target = $("commitment-list");
  target.innerHTML = "";
  if (!items.length) {
    target.innerHTML = '<div class="meta">No unresolved work.</div>';
    return;
  }
  items.forEach((item) => {
    const node = document.createElement("div");
    node.className = "item";
    node.innerHTML = `
      <strong>${escapeHtml(item.text)}</strong>
      <div class="meta">${escapeHtml(item.kind)} · ${escapeHtml(item.owner || "unassigned")} ${item.deadline ? "· due " + escapeHtml(item.deadline) : ""}</div>
      <div class="meta">${escapeHtml(item.meeting_title)}</div>
    `;
    target.appendChild(node);
  });
}

function renderTasks(tasks) {
  const groups = groupTasks(tasks);
  const target = $("task-groups");
  target.innerHTML = "";
  ["Overdue", "Today", "Upcoming", "Unscheduled", "Done"].forEach((name) => {
    const panel = document.createElement("section");
    panel.className = "panel task-group";
    panel.innerHTML = `<h2>${name}</h2><div class="list"></div>`;
    const listNode = panel.querySelector(".list");
    const items = groups[name] || [];
    if (!items.length) {
      listNode.innerHTML = '<div class="meta">Nothing here.</div>';
    } else {
      items.forEach((task) => listNode.appendChild(taskNode(task)));
    }
    target.appendChild(panel);
  });
  renderTaskSuggestions(tasks);
}

function groupTasks(tasks) {
  const today = new Date().toISOString().slice(0, 10);
  const groups = { Overdue: [], Today: [], Upcoming: [], Unscheduled: [], Done: [] };
  tasks.forEach((task) => {
    if (task.status === "done") groups.Done.push(task);
    else if (!task.due_date) groups.Unscheduled.push(task);
    else if (task.due_date < today) groups.Overdue.push(task);
    else if (task.due_date === today) groups.Today.push(task);
    else groups.Upcoming.push(task);
  });
  return groups;
}

function taskNode(task) {
  const node = document.createElement("div");
  node.className = "item";
  const meetingMeta = task.meeting_title ? ` · ${escapeHtml(task.meeting_title)}` : "";
  const due = task.due_date ? ` · due ${escapeHtml(task.due_date)}` : "";
  const suggestion = task.reminder_suggestion ? `<div class="meta">${escapeHtml(task.reminder_suggestion)}</div>` : "";
  node.innerHTML = `
    <strong>${escapeHtml(task.text)}</strong>
    <div class="meta">${escapeHtml(task.owner || "unassigned")}${task.owed_to ? " → " + escapeHtml(task.owed_to) : ""}${task.project ? " #" + escapeHtml(task.project) : ""}${due}${meetingMeta}</div>
    ${suggestion}
    <span class="badge">${escapeHtml(task.source)}</span>
    <span class="badge">${escapeHtml(task.status)}</span>
    <div class="task-actions">
      ${task.status === "done"
        ? `<button data-action="reopen">Reopen</button>`
        : `<button data-action="complete">Complete</button>`}
      ${task.status !== "done" && task.status !== "canceled" ? `<button data-action="snooze">Snooze</button>` : ""}
      ${task.status !== "done" && task.status !== "canceled" ? `<button data-action="cancel">Cancel</button>` : ""}
      ${task.meeting_id ? `<button data-action="meeting">Open Meeting</button>` : ""}
    </div>
  `;
  const complete = node.querySelector('[data-action="complete"]');
  const reopen = node.querySelector('[data-action="reopen"]');
  const snooze = node.querySelector('[data-action="snooze"]');
  const cancel = node.querySelector('[data-action="cancel"]');
  const meetingButton = node.querySelector('[data-action="meeting"]');
  if (complete) complete.onclick = () => completeTask(task.id);
  if (reopen) reopen.onclick = () => reopenTask(task.id);
  if (snooze) snooze.onclick = () => snoozeCommitment(task.id);
  if (cancel) cancel.onclick = () => cancelCommitment(task.id);
  if (meetingButton) meetingButton.onclick = () => loadMeeting(task.meeting_id);
  return node;
}

function renderTaskSuggestions(tasks) {
  const target = $("task-suggestions");
  const suggested = tasks.filter((task) => task.status !== "done" && task.reminder_suggestion);
  target.innerHTML = "";
  if (!suggested.length) {
    target.innerHTML = '<div class="meta">No reminder suggestions right now.</div>';
    return;
  }
  suggested.slice(0, 6).forEach((task) => target.appendChild(taskNode(task)));
}

function renderSettings(settings) {
  const target = $("settings-list");
  target.innerHTML = "";
  const labels = {
    openai_key_present: "OpenAI key configured",
    gmail_credentials_present: "Gmail credentials file",
    gmail_token_present: "Gmail OAuth token",
    capture_profile: "Capture profile",
    input_device: "Input device",
    capture_note: "Capture note",
    recorder_status: "Recorder status",
    recorder_command_preview: "Recorder command",
  };
  Object.entries(settings).forEach(([key, value]) => {
    const k = document.createElement("div");
    const v = document.createElement("div");
    k.textContent = labels[key] || key;
    v.textContent = String(value);
    target.append(k, v);
  });
}

function renderBotStatus(status, sessions) {
  $("bot-status").textContent = JSON.stringify({
    provider: status.provider,
    status: status.status,
    enabled: status.enabled,
    note: status.note,
    cloud_cost_label: status.cloud_cost_label,
  }, null, 2);
  const target = $("bot-sessions");
  target.innerHTML = "";
  if (!sessions.length) {
    target.innerHTML = '<div class="meta">No bot sessions yet.</div>';
    return;
  }
  sessions.forEach((session) => {
    const item = document.createElement("div");
    item.className = "item";
    const transcriptLabel = session.transcript_ready
      ? "transcript ready"
      : session.status === "transcript_requested"
        ? "transcript requested; sync again after Recall finishes"
        : session.status && session.status.startsWith("transcript_processing")
          ? "transcript processing; sync again in a few minutes"
          : "waiting for transcript";
    item.innerHTML = `
      <strong>${escapeHtml(session.title || session.meeting_title)}</strong>
      <div class="meta">session ${session.id} · meeting ${session.meeting_id} · ${escapeHtml(session.status)} · ${escapeHtml(transcriptLabel)}</div>
      <div class="meta">${escapeHtml(session.meeting_url_display || "")}</div>
      <div class="task-actions">
        <button data-action="sync">Sync</button>
        <button data-action="process">Process</button>
        ${session.meeting_id ? `<button data-action="meeting">Open Meeting</button>` : ""}
      </div>
    `;
    item.querySelector('[data-action="sync"]').onclick = () => syncBotSession(session.id);
    const processButton = item.querySelector('[data-action="process"]');
    processButton.disabled = !session.transcript_ready && !session.meeting_transcript_path;
    processButton.onclick = () => processBotSession(session.id);
    const meeting = item.querySelector('[data-action="meeting"]');
    if (meeting) meeting.onclick = () => loadMeeting(session.meeting_id);
    target.appendChild(item);
  });
}

function renderCalendar(status, events, brief) {
  $("calendar-status").textContent = JSON.stringify(status, null, 2);
  const target = $("calendar-upcoming");
  target.innerHTML = "";
  if (!events.length) {
    target.innerHTML = '<div class="meta">No synced upcoming events.</div>';
  } else {
    events.forEach((event) => target.appendChild(calendarEventNode(event)));
  }
}

function calendarEventNode(event) {
  const item = document.createElement("div");
  item.className = "item";
  item.innerHTML = `
    <strong>${escapeHtml(event.title || "Untitled event")}</strong>
    <div class="meta">${escapeHtml(event.start_at || "")} → ${escapeHtml(event.end_at || "")}</div>
    ${event.meeting_url ? `<div class="meta">${escapeHtml(event.meeting_url)}</div>` : ""}
    ${event.location ? `<div class="meta">${escapeHtml(event.location)}</div>` : ""}
  `;
  return item;
}

function renderNotifications(status, candidates) {
  $("notifications-status").textContent = JSON.stringify(status, null, 2);
  const target = $("notifications-candidates");
  target.innerHTML = "";
  if (!candidates.length) {
    target.innerHTML = '<div class="meta">No notification candidates right now.</div>';
    return;
  }
  candidates.forEach((candidate) => {
    const item = document.createElement("div");
    item.className = "item";
    item.innerHTML = `
      <strong>#${candidate.id} ${escapeHtml(candidate.title)}</strong>
      <div class="meta">${escapeHtml(candidate.notification_reason || candidate.reason || "")}</div>
      <div class="meta">${escapeHtml(candidate.notification_status || "candidate")}</div>
      <div class="task-actions">
        <button data-action="delivered">Mark Delivered</button>
        <button data-action="snooze">Snooze</button>
        <button data-action="dismiss">Dismiss</button>
      </div>
    `;
    item.querySelector('[data-action="delivered"]').onclick = () => markNotificationDelivered(candidate.id);
    item.querySelector('[data-action="snooze"]').onclick = () => snoozeNotification(candidate.id);
    item.querySelector('[data-action="dismiss"]').onclick = () => dismissNotification(candidate.id);
    target.appendChild(item);
  });
}

async function loadMeeting(id) {
  try {
    const data = await api(`/api/meetings/${id}`);
    state.selectedMeetingId = id;
    $("meeting-title").textContent = data.meeting.title;
    $("meeting-detail").innerHTML = `
      <p>${escapeHtml(data.meeting.summary || "No summary yet.")}</p>
      <h3>Decisions</h3>
      ${list(data.decisions.map((row) => row.text))}
      <h3>Action Items</h3>
      ${list(data.action_items.map((row) => row.text))}
      <h3>Open Questions</h3>
      ${list(data.open_questions.map((row) => row.text))}
      <h3>Transcript</h3>
      <pre>${escapeHtml(data.transcript || "No transcript available.")}</pre>
    `;
    showView("meetings");
    setStatus(`Loaded meeting ${id}`);
  } catch (error) {
    setStatus(error.message);
  }
}

function list(items) {
  if (!items.length) return '<div class="meta">None captured.</div>';
  return `<ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

async function startRecording() {
  const title = $("record-title").value.trim();
  if (!title) return setStatus("Meeting title is required");
  const data = await api("/api/capture/local/start", { method: "POST", body: JSON.stringify({ kind: "meeting", title }) });
  setStatus(`Recording meeting ${data.session.meeting_id}`);
  refresh();
}

async function stopRecording() {
  const data = await api("/api/capture/local/stop", { method: "POST", body: JSON.stringify({ process: false }) });
  setStatus(`Stopped meeting ${data.meeting_id}`);
  refresh();
}

async function stopAndProcessRecording() {
  setStatus("Stopping and processing meeting...");
  const data = await api("/api/capture/local/stop", { method: "POST", body: JSON.stringify({ process: true }) });
  state.selectedMeetingId = data.meeting_id;
  setStatus(`Processed meeting ${data.meeting_id}`);
  await refresh();
  await loadMeeting(data.meeting_id);
}

async function joinBotSession() {
  const title = $("bot-title").value.trim();
  const meetingUrl = $("bot-url").value.trim();
  if (!title) return setStatus("Bot meeting title is required");
  if (!meetingUrl) return setStatus("Meeting link is required");
  if (!$("bot-consent").checked) return setStatus("Confirm consent/disclosure before sending a meeting bot.");
  const data = await api("/api/capture/bot/join", {
    method: "POST",
    body: JSON.stringify({
      title,
      meeting_url: meetingUrl,
      consent_confirmed: true,
    }),
  });
  setStatus(`Joined bot session ${data.session.id}`);
  $("bot-url").value = "";
  $("bot-consent").checked = false;
  refresh();
}

async function syncBotSession(id) {
  const data = await api(`/api/capture/bot/sessions/${id}/sync`, { method: "POST", body: "{}" });
  setStatus(data.transcript_path ? `Bot transcript ready for session ${id}` : `Synced bot session ${id}`);
  refresh();
}

async function processBotSession(id) {
  const data = await api(`/api/capture/bot/sessions/${id}/process`, { method: "POST", body: "{}" });
  setStatus(`Processed bot meeting ${data.meeting.id}`);
  await refresh();
  await loadMeeting(data.meeting.id);
}

async function processMeeting() {
  if (!state.selectedMeetingId) return setStatus("Select a meeting first");
  setStatus("Processing meeting...");
  await api(`/api/meetings/${state.selectedMeetingId}/process`, { method: "POST", body: "{}" });
  await loadMeeting(state.selectedMeetingId);
  await refresh();
}

async function runAssistantCommand() {
  const command = $("assistant-command").value.trim();
  if (!command) return setStatus("Assistant command is required");
  const data = await api("/api/assistant/command", {
    method: "POST",
    body: JSON.stringify({ command }),
  });
  $("assistant-output").textContent = renderAssistantResult(data);
  setStatus(data.summary);
  if (["add_task", "complete_task", "reopen_task", "confirm_suggestion", "dismiss_suggestion", "snooze_suggestion"].includes(data.action)) {
    refresh();
  }
}

function renderAssistantResult(data) {
  const prefix = data.category ? `[${data.category}] ` : "";
  const lines = [`${prefix}${data.summary}`];
  if (!data.supported) return lines.join("\\n");
  const result = data.result || {};
  if (result.capabilities) {
    lines.push("");
    result.capabilities.forEach((capability) => {
      lines.push(`[${capability.category}] ${capability.command} - ${capability.description}`);
    });
  } else if (result.contexts) {
    if (result.contexts.length) {
      lines.push("", "Contexts");
      result.contexts.forEach((context) => lines.push(`[${context.id}] ${context.name} (${context.kind})`));
    }
    if (result.tasks && result.tasks.length) {
      lines.push("", "Tasks");
      result.tasks.forEach((task) => {
        const due = task.due_date ? ` due ${task.due_date}` : "";
        lines.push(`[${task.id}] ${task.text}${due}`);
      });
    }
    if (result.suggestions && result.suggestions.length) {
      lines.push("", "Suggestions");
      result.suggestions.slice(0, 8).forEach((suggestion) => {
        lines.push(`[${suggestion.id}] ${suggestion.title} (${suggestion.status})`);
      });
    }
  } else if (result.tasks) {
    if (!result.tasks.length) return lines.join("\\n");
    lines.push("");
    result.tasks.forEach((task) => {
      const due = task.due_date ? ` due ${task.due_date}` : "";
      lines.push(`[${task.id}] ${task.text}${due}`);
    });
  } else if (result.meetings) {
    if (!result.meetings.length) return lines.join("\\n");
    lines.push("");
    result.meetings.forEach((meeting) => {
      const flags = [];
      if (!meeting.transcript_path) flags.push("no transcript");
      if (!meeting.note_path) flags.push("no note");
      lines.push(`[${meeting.id}] ${meeting.title}${flags.length ? " (" + flags.join(", ") + ")" : ""}`);
    });
  } else if (result.sessions) {
    if (!result.sessions.length) return lines.join("\\n");
    lines.push("");
    result.sessions.forEach((session) => {
      lines.push(`[${session.id}] ${session.title || session.meeting_title} · ${session.status} · meeting ${session.meeting_id}`);
    });
  } else if (result.task) {
    const task = result.task;
    const due = task.due_date ? ` due ${task.due_date}` : "";
    lines.push("", `[${task.id}] ${task.text}${due} (${task.status})`);
  } else if (result.draft) {
    lines.push("", `Subject: ${result.draft.subject}`, "", result.draft.body || "");
  } else if (result.suggestions) {
    if (!result.suggestions.length) return lines.join("\\n");
    lines.push("");
    result.suggestions.forEach((suggestion) => {
      const context = suggestion.context && suggestion.context.name ? ` · ${suggestion.context.name}` : "";
      lines.push(`[${suggestion.id}] ${suggestion.title}${context} (${suggestion.status})`);
    });
  } else if (result.suggestion) {
    lines.push("", `[${result.suggestion.id}] ${result.suggestion.title} (${result.suggestion.status})`);
  } else if (result.meeting) {
    lines.push("", `[${result.meeting.id}] ${result.meeting.title}`);
    if (result.note_path) lines.push(`Note: ${result.note_path}`);
    if (result.transcript_path) lines.push(`Transcript: ${result.transcript_path}`);
  } else if (result.markdown) {
    lines.push("", result.markdown);
  }
  return lines.join("\\n");
}

async function addTask() {
  const text = $("task-text").value.trim();
  if (!text) return setStatus("Task text is required");
  await api("/api/tasks", {
    method: "POST",
    body: JSON.stringify({
      text,
      owner: $("task-owner").value,
      due_date: $("task-due").value,
    }),
  });
  $("task-text").value = "";
  $("task-owner").value = "";
  $("task-due").value = "";
  setStatus("Task added");
  refresh();
}

async function startTaskRecording() {
  const data = await api("/api/capture/local/start", { method: "POST", body: JSON.stringify({ kind: "task_note" }) });
  $("task-record-state").textContent = JSON.stringify(data, null, 2);
  setStatus("Recording voice task");
}

async function stopTaskRecording() {
  const data = await api("/api/capture/local/stop", {
    method: "POST",
    body: JSON.stringify({
      task_metadata: {
        owner: $("task-owner").value,
        due_date: $("task-due").value,
      },
    }),
  });
  $("task-record-state").textContent = JSON.stringify(data, null, 2);
  setStatus(`Added voice task ${data.task.id}`);
  refresh();
}

async function completeTask(id) {
  await api(`/api/tasks/${id}/complete`, { method: "POST", body: "{}" });
  setStatus(`Completed task ${id}`);
  refresh();
}

async function reopenTask(id) {
  await api(`/api/tasks/${id}/reopen`, { method: "POST", body: "{}" });
  setStatus(`Reopened task ${id}`);
  refresh();
}

async function snoozeCommitment(id) {
  await api(`/api/commitments/${id}/snooze`, { method: "POST", body: "{}" });
  setStatus(`Snoozed task ${id}`);
  refresh();
}

async function cancelCommitment(id) {
  await api(`/api/commitments/${id}/cancel`, { method: "POST", body: "{}" });
  setStatus(`Canceled task ${id}`);
  refresh();
}

async function previewEmail() {
  if (!state.selectedMeetingId) return setStatus("Select a meeting first");
  const payload = emailPayload();
  const data = await api(`/api/meetings/${state.selectedMeetingId}/email/preview`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  $("email-subject").value = data.subject;
  $("email-body").value = data.body;
  $("email-meta").textContent = `Tone: ${data.tone}\\nProvider: ${data.provider}\\nIncluded: ${(data.included_items || []).join(", ") || "not specified"}`;
  setStatus(`Draft preview ready (${data.provider})`);
}

async function createEmailDraft() {
  if (!state.selectedMeetingId) return setStatus("Select a meeting first");
  const data = await api(`/api/meetings/${state.selectedMeetingId}/email/draft`, {
    method: "POST",
    body: JSON.stringify(emailPayload()),
  });
  setStatus(`Created Gmail draft ${data.draft_id}`);
}

function emailPayload() {
  return {
    to: $("email-to").value,
    subject: $("email-subject").value,
    instruction: $("email-instruction").value,
    body: $("email-body").value,
  };
}

async function searchContext() {
  const topic = $("context-topic").value.trim();
  if (!topic) return setStatus("Topic is required");
  const data = await api(`/api/context?topic=${encodeURIComponent(topic)}`);
  $("context-output").textContent = data.markdown;
}

async function syncCalendar() {
  setStatus("Syncing Google Calendar...");
  const data = await api("/api/calendar/sync", { method: "POST", body: "{}" });
  setStatus(`Synced ${data.synced_count} calendar events`);
  refresh();
}

async function markNotificationDelivered(id) {
  await api(`/api/notifications/${id}/mark-delivered`, { method: "POST", body: "{}" });
  setStatus(`Marked notification ${id} delivered`);
  refresh();
}

async function snoozeNotification(id) {
  const until = prompt("Snooze until YYYY-MM-DD", "");
  await api(`/api/notifications/${id}/snooze`, {
    method: "POST",
    body: JSON.stringify({ until }),
  });
  setStatus(`Snoozed notification ${id}`);
  refresh();
}

async function dismissNotification(id) {
  await api(`/api/notifications/${id}/dismiss`, { method: "POST", body: "{}" });
  setStatus(`Dismissed notification ${id}`);
  refresh();
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  })[char]);
}

document.querySelectorAll(".nav").forEach((button) => button.onclick = () => showView(button.dataset.view));
$("refresh").onclick = refresh;
$("record-start").onclick = () => startRecording().catch((error) => setStatus(error.message));
$("record-stop").onclick = () => stopRecording().catch((error) => setStatus(error.message));
$("record-stop-process").onclick = () => stopAndProcessRecording().catch((error) => setStatus(error.message));
$("bot-join").onclick = () => joinBotSession().catch((error) => setStatus(error.message));
$("bot-refresh").onclick = () => refresh().catch((error) => setStatus(error.message));
$("calendar-sync").onclick = () => syncCalendar().catch((error) => setStatus(error.message));
$("calendar-refresh").onclick = () => refresh().catch((error) => setStatus(error.message));
$("notifications-refresh").onclick = () => refresh().catch((error) => setStatus(error.message));
$("assistant-run").onclick = () => runAssistantCommand().catch((error) => setStatus(error.message));
$("assistant-command").addEventListener("keydown", (event) => {
  if (event.key === "Enter") runAssistantCommand().catch((error) => setStatus(error.message));
});
$("task-add").onclick = () => addTask().catch((error) => setStatus(error.message));
$("task-record-start").onclick = () => startTaskRecording().catch((error) => setStatus(error.message));
$("task-record-stop").onclick = () => stopTaskRecording().catch((error) => setStatus(error.message));
$("process-meeting").onclick = () => processMeeting().catch((error) => setStatus(error.message));
$("email-preview").onclick = () => previewEmail().catch((error) => setStatus(error.message));
$("email-create").onclick = () => createEmailDraft().catch((error) => setStatus(error.message));
$("context-search").onclick = () => searchContext().catch((error) => setStatus(error.message));
refresh();
"""
