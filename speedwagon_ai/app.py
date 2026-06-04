from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from speedwagon_ai.assistant_actions import CAPABILITIES, run_action
from speedwagon_ai.assistant_commands import cancel_pending_action, confirm_pending_action, execute_command
from speedwagon_ai.capture import CaptureService
from speedwagon_ai.config import Settings
from speedwagon_ai.context import render_context
from speedwagon_ai.extraction import Extractor
from speedwagon_ai.integrations.gmail import create_gmail_draft, preview_followup_email
from speedwagon_ai.model_router import choose_model, cost_label, web_search_enabled
from speedwagon_ai.output import MarkdownWriter
from speedwagon_ai.processing import process_meeting
from speedwagon_ai.screenshot_context import analyze_screenshot
from speedwagon_ai.storage import Repository
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
}


def run_app(settings: Settings, repo: Repository, host: str, port: int) -> None:
    handler = make_handler(settings, repo)
    server = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}"
    print(f"SpeedwagonAI app running at {url}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping SpeedwagonAI app.")
    finally:
        server.server_close()


def make_handler(settings: Settings, repo: Repository) -> type[BaseHTTPRequestHandler]:
    class SpeedwagonHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/":
                    self._send_html(APP_HTML)
                elif parsed.path == "/app.css":
                    self._send_text(APP_CSS, "text/css")
                elif parsed.path == "/app.js":
                    self._send_text(APP_JS, "application/javascript")
                elif parsed.path == "/api/meetings":
                    limit = int(parse_qs(parsed.query).get("limit", ["20"])[0])
                    self._send_json({"meetings": [meeting_to_dict(m) for m in repo.list_meetings(limit=limit)]})
                elif parsed.path.startswith("/api/meetings/"):
                    meeting_id = _meeting_id_from_path(parsed.path)
                    self._send_json(meeting_detail(repo, meeting_id))
                elif parsed.path == "/api/context":
                    topic = parse_qs(parsed.query).get("topic", [""])[0]
                    self._send_json({"topic": topic, "markdown": render_context(repo, topic)})
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
                elif parsed.path == "/api/assistant/capabilities":
                    self._send_json({"capabilities": CAPABILITIES})
                elif parsed.path == "/api/assistant/actions":
                    status = parse_qs(parsed.query).get("status", ["pending"])[0] or None
                    self._send_json({"actions": repo.list_pending_actions(status=status)})
                elif parsed.path == "/api/assistant/voice/status":
                    self._send_json(CaptureService(settings, repo).active_session("assistant_voice") or {"active": False})
                elif parsed.path == "/api/tasks":
                    status = parse_qs(parsed.query).get("status", ["open"])[0] or None
                    include_done = parse_qs(parsed.query).get("include_done", ["false"])[0].lower() == "true"
                    self._send_json({"tasks": repo.list_tasks(status=status, include_done=include_done)})
                elif parsed.path == "/api/tasks/overdue":
                    self._send_json({"tasks": repo.overdue_tasks()})
                elif parsed.path == "/api/settings":
                    self._send_json(settings_payload(settings))
                elif parsed.path == "/api/record/state":
                    self._send_json(recording_state(settings))
                elif parsed.path == "/api/tasks/record/state":
                    self._send_json(VoiceTaskRecorder(settings, repo).state())
                elif parsed.path == "/api/capture/status":
                    self._send_json(CaptureService(settings, repo).status())
                elif parsed.path == "/api/capture/diagnostics":
                    self._send_json(CaptureService(settings, repo).diagnostics())
                elif parsed.path == "/api/capture/bot/status":
                    self._send_json(bot_capture_status())
                elif parsed.path == "/api/integrations/google/status":
                    self._send_json(google_status(settings))
                elif parsed.path == "/api/integrations/apple/reminders":
                    self._send_json(apple_reminders_status())
                else:
                    self._send_error(HTTPStatus.NOT_FOUND, "Not found")
            except Exception as exc:
                self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            try:
                payload = self._read_json()
                if parsed.path in {"/api/record/start", "/api/capture/local/start"}:
                    title = str(payload.get("title") or "").strip()
                    kind = str(payload.get("kind") or "meeting")
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
                elif parsed.path == "/api/capture/bot/join":
                    self._send_error(
                        HTTPStatus.NOT_IMPLEMENTED,
                        "Meeting bot capture is planned as an opt-in managed-provider beta and is not configured yet.",
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
                elif parsed.path == "/api/tasks":
                    task = repo.create_task(
                        str(payload.get("text") or ""),
                        owner=_optional(payload.get("owner")),
                        due_date=_optional(payload.get("due_date")),
                        owed_to=_optional(payload.get("owed_to")),
                        project=_optional(payload.get("project")),
                    )
                    MarkdownWriter(settings, repo).write_commitments()
                    self._send_json({"task": task})
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
                elif parsed.path == "/api/integrations/apple/reminders":
                    self._send_error(
                        HTTPStatus.NOT_IMPLEMENTED,
                        "Apple Reminders writes are planned for the native Mac app and require explicit user approval.",
                    )
                elif parsed.path == "/api/actions":
                    action = str(payload.get("action") or "")
                    self._send_json(run_action(settings, repo, action, payload.get("payload") or {}))
                elif parsed.path == "/api/assistant/command":
                    command = str(payload.get("command") or "")
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
                    self._send_json(
                        preview_followup_email(
                            settings,
                            repo,
                            meeting_id,
                            to=str(payload.get("to") or ""),
                            subject=_optional(payload.get("subject")),
                            instruction=str(payload.get("instruction") or ""),
                        )
                    )
                elif parsed.path.startswith("/api/meetings/") and parsed.path.endswith("/email/draft"):
                    meeting_id = _meeting_id_from_path(parsed.path)
                    draft_id = create_gmail_draft(
                        settings,
                        repo,
                        meeting_id,
                        to=str(payload.get("to") or ""),
                        subject=_optional(payload.get("subject")),
                        instruction=str(payload.get("instruction") or ""),
                        body=_optional(payload.get("body")),
                    )
                    self._send_json({"draft_id": draft_id, "drafts": repo.email_drafts_for_meeting(meeting_id)})
                else:
                    self._send_error(HTTPStatus.NOT_FOUND, "Not found")
            except Exception as exc:
                self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or "0")
            if length == 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            return json.loads(raw)

        def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            data = json.dumps(payload, default=json_default).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_html(self, text: str) -> None:
            self._send_text(text, "text/html; charset=utf-8")

        def _send_text(self, text: str, content_type: str) -> None:
            data = text.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_error(self, status: HTTPStatus, message: str) -> None:
            self._send_json({"error": message}, status=status)

    return SpeedwagonHandler


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


def _optional(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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


def recording_state(settings: Settings) -> dict[str, Any]:
    return CaptureService(settings, Repository(settings.db_path)).active_session("meeting") or {"active": False}


def settings_payload(settings: Settings) -> dict[str, Any]:
    diagnostics = CaptureService(settings, Repository(settings.db_path)).diagnostics()
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
        "gmail_credentials_present": settings.gmail_credentials_path.exists(),
        "gmail_token_present": settings.gmail_token_path.exists(),
        "capture_profile": settings.capture_profile,
        "input_device": settings.input_device,
        "record_cmd": settings.record_cmd,
        "recorder_status": diagnostics["recorder_status"],
        "recorder_command_preview": diagnostics["recorder_command_preview"],
        "capture_note": capture_note(settings.capture_profile),
    }


def google_status(settings: Settings) -> dict[str, Any]:
    return {
        "gmail_credentials_present": settings.gmail_credentials_path.exists(),
        "gmail_token_present": settings.gmail_token_path.exists(),
        "gmail_drafts": "available" if settings.gmail_token_path.exists() else "needs_oauth",
        "calendar": "planned",
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
    const [meetings, commitments, tasks, settings, captureStatus, taskRecordState, dailyBrief, captureDiagnostics] = await Promise.all([
      api("/api/meetings"),
      api("/api/commitments"),
      api("/api/tasks?status=&include_done=true"),
      api("/api/settings"),
      api("/api/capture/status"),
      api("/api/tasks/record/state"),
      api("/api/daily-brief"),
      api("/api/capture/diagnostics"),
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
  ];
  target.innerHTML = "";
  cards.forEach(([label, items]) => {
    const node = document.createElement("div");
    node.className = "brief-card";
    const preview = items.slice(0, 3).map((task) => `<div class="meta">[${task.id}] ${escapeHtml(task.text)}</div>`).join("");
    node.innerHTML = `<strong>${label}: ${items.length}</strong>${preview || '<div class="meta">Nothing here.</div>'}`;
    target.appendChild(node);
  });
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
  if (["add_task", "complete_task", "reopen_task"].includes(data.action)) {
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
  } else if (result.task) {
    const task = result.task;
    const due = task.due_date ? ` due ${task.due_date}` : "";
    lines.push("", `[${task.id}] ${task.text}${due} (${task.status})`);
  } else if (result.draft) {
    lines.push("", `Subject: ${result.draft.subject}`, "", result.draft.body || "");
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
