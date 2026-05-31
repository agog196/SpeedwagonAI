from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from speedwagon_ai.capture import Recorder, recorder_command
from speedwagon_ai.config import Settings
from speedwagon_ai.context import render_context
from speedwagon_ai.extraction import Extractor
from speedwagon_ai.integrations.gmail import create_gmail_draft, preview_followup_email
from speedwagon_ai.output import MarkdownWriter
from speedwagon_ai.storage import Repository
from speedwagon_ai.transcription import Transcriber


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
                    self._send_json({"items": repo.unresolved_work()})
                elif parsed.path == "/api/settings":
                    self._send_json(settings_payload(settings))
                elif parsed.path == "/api/record/state":
                    self._send_json(recording_state(settings))
                else:
                    self._send_error(HTTPStatus.NOT_FOUND, "Not found")
            except Exception as exc:
                self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            try:
                payload = self._read_json()
                if parsed.path == "/api/record/start":
                    title = str(payload.get("title") or "").strip()
                    if not title:
                        self._send_error(HTTPStatus.BAD_REQUEST, "title is required")
                        return
                    repo.init()
                    meeting_id = Recorder(settings, repo).start(title)
                    self._send_json({"meeting_id": meeting_id})
                elif parsed.path == "/api/record/stop":
                    repo.init()
                    meeting_id = Recorder(settings, repo).stop()
                    self._send_json({"meeting_id": meeting_id})
                elif parsed.path.startswith("/api/meetings/") and parsed.path.endswith("/process"):
                    meeting_id = _meeting_id_from_path(parsed.path)
                    repo.init()
                    meeting = repo.get_meeting(meeting_id)
                    if not meeting.transcript_path:
                        Transcriber(settings, repo).transcribe(meeting_id)
                    Extractor(settings, repo).extract(meeting_id)
                    writer = MarkdownWriter(settings, repo)
                    note_path = writer.write_meeting(meeting_id)
                    commitments_path = writer.write_commitments()
                    self._send_json(
                        {
                            "meeting": meeting_to_dict(repo.get_meeting(meeting_id)),
                            "note_path": str(note_path),
                            "commitments_path": str(commitments_path),
                        }
                    )
                elif parsed.path.startswith("/api/meetings/") and parsed.path.endswith("/email/preview"):
                    meeting_id = _meeting_id_from_path(parsed.path)
                    self._send_json(
                        preview_followup_email(
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
    if not settings.state_path.exists():
        return {"active": False}
    return {"active": True, **json.loads(settings.state_path.read_text(encoding="utf-8"))}


def settings_payload(settings: Settings) -> dict[str, Any]:
    try:
        command = recorder_command(
            settings.record_cmd,
            settings.audio_dir / "preview.wav",
            profile=settings.capture_profile,
            input_device=settings.input_device,
        )
        recorder_status = "available"
        recorder_command_preview = " ".join(command)
    except Exception as exc:
        recorder_status = str(exc)
        recorder_command_preview = ""
    return {
        "db_path": str(settings.db_path),
        "notes_dir": str(settings.notes_dir),
        "audio_dir": str(settings.audio_dir),
        "transcripts_dir": str(settings.transcripts_dir),
        "whisper_cpp_bin": settings.whisper_cpp_bin,
        "whisper_cpp_model": settings.whisper_cpp_model,
        "openai_key_present": bool(settings.openai_api_key),
        "gmail_credentials_present": settings.gmail_credentials_path.exists(),
        "gmail_token_present": settings.gmail_token_path.exists(),
        "capture_profile": settings.capture_profile,
        "input_device": settings.input_device,
        "record_cmd": settings.record_cmd,
        "recorder_status": recorder_status,
        "recorder_command_preview": recorder_command_preview,
    }


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
            <h2>Recent Meetings</h2>
            <div id="recent-meetings" class="list"></div>
          </section>
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
          </div>
          <pre id="record-state"></pre>
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
              <textarea id="email-instruction" placeholder="What should this email accomplish?"></textarea>
              <div class="row">
                <button id="email-preview">Preview</button>
                <button id="email-create">Create Gmail Draft</button>
              </div>
              <pre id="email-body"></pre>
            </div>
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
@media (max-width: 860px) {
  .shell { grid-template-columns: 1fr; }
  .sidebar { border-right: 0; border-bottom: 1px solid var(--line); }
  nav { grid-template-columns: repeat(5, minmax(0, 1fr)); }
  .nav { text-align: center; }
  .two, .meetings-layout { grid-template-columns: 1fr; }
  header { align-items: flex-start; }
}
"""


APP_JS = """
const state = { meetings: [], selectedMeetingId: null };

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
    const [meetings, commitments, settings, recordState] = await Promise.all([
      api("/api/meetings"),
      api("/api/commitments"),
      api("/api/settings"),
      api("/api/record/state"),
    ]);
    state.meetings = meetings.meetings;
    renderMeetings();
    renderCommitments(commitments.items);
    renderSettings(settings);
    $("record-state").textContent = JSON.stringify(recordState, null, 2);
    setStatus("Ready");
  } catch (error) {
    setStatus(error.message);
  }
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

function renderSettings(settings) {
  const target = $("settings-list");
  target.innerHTML = "";
  Object.entries(settings).forEach(([key, value]) => {
    const k = document.createElement("div");
    const v = document.createElement("div");
    k.textContent = key;
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
  const data = await api("/api/record/start", { method: "POST", body: JSON.stringify({ title }) });
  setStatus(`Recording meeting ${data.meeting_id}`);
  refresh();
}

async function stopRecording() {
  const data = await api("/api/record/stop", { method: "POST", body: "{}" });
  setStatus(`Stopped meeting ${data.meeting_id}`);
  refresh();
}

async function processMeeting() {
  if (!state.selectedMeetingId) return setStatus("Select a meeting first");
  setStatus("Processing meeting...");
  await api(`/api/meetings/${state.selectedMeetingId}/process`, { method: "POST", body: "{}" });
  await loadMeeting(state.selectedMeetingId);
  await refresh();
}

async function previewEmail() {
  if (!state.selectedMeetingId) return setStatus("Select a meeting first");
  const payload = emailPayload();
  const data = await api(`/api/meetings/${state.selectedMeetingId}/email/preview`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  $("email-subject").value = data.subject;
  $("email-body").textContent = data.body;
  setStatus("Draft preview ready");
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
$("process-meeting").onclick = () => processMeeting().catch((error) => setStatus(error.message));
$("email-preview").onclick = () => previewEmail().catch((error) => setStatus(error.message));
$("email-create").onclick = () => createEmailDraft().catch((error) => setStatus(error.message));
$("context-search").onclick = () => searchContext().catch((error) => setStatus(error.message));
refresh();
"""
