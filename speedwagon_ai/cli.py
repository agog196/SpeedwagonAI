from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from speedwagon_ai.assistant_actions import run_action
from speedwagon_ai.assistant_commands import execute_command
from speedwagon_ai.capture import CaptureService, Recorder, recorder_command
from speedwagon_ai.app import run_app
from speedwagon_ai.config import Settings
from speedwagon_ai.context import render_context
from speedwagon_ai.extraction import Extractor
from speedwagon_ai.integrations.gmail import create_gmail_draft, preview_followup_email
from speedwagon_ai.output import MarkdownWriter
from speedwagon_ai.processing import process_meeting
from speedwagon_ai.storage import Repository
from speedwagon_ai.transcription import Transcriber
from speedwagon_ai.voice_tasks import VoiceTaskRecorder


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = Settings.load()
    repo = Repository(settings.db_path)
    try:
        return args.func(args, settings, repo)
    except Exception as exc:
        print(f"error: {exc}")
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="speedwagon")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize local folders and SQLite database.")
    init_parser.set_defaults(func=cmd_init)

    app_parser = subparsers.add_parser("app", help="Start the local SpeedwagonAI web app.")
    app_parser.add_argument("--host")
    app_parser.add_argument("--port", type=int)
    app_parser.set_defaults(func=cmd_app)

    ask_parser = subparsers.add_parser("ask", help="Run a one-line SpeedwagonAI assistant command.")
    ask_parser.add_argument("command")
    ask_parser.set_defaults(func=cmd_ask)

    assistant_parser = subparsers.add_parser("assistant", help="Assistant capabilities and diagnostics.")
    assistant_sub = assistant_parser.add_subparsers(dest="assistant_command", required=True)
    capabilities_parser = assistant_sub.add_parser("capabilities", help="List assistant capabilities.")
    capabilities_parser.set_defaults(func=cmd_assistant_capabilities)

    record_parser = subparsers.add_parser("record", help="Start or stop local audio recording.")
    record_sub = record_parser.add_subparsers(dest="record_command", required=True)
    record_start = record_sub.add_parser("start", help="Start recording with macOS afrecord.")
    record_start.add_argument("--title", required=True)
    record_start.set_defaults(func=cmd_record_start)
    record_stop = record_sub.add_parser("stop", help="Stop the active recording.")
    record_stop.add_argument("--process", action="store_true", help="Transcribe, extract, and write notes after stopping.")
    record_stop.set_defaults(func=cmd_record_stop)
    record_doctor = record_sub.add_parser("doctor", help="Show recorder configuration and optionally smoke-test audio input.")
    record_doctor.add_argument("--smoke-test", action="store_true", help="Record one second to a temporary WAV file.")
    record_doctor.set_defaults(func=cmd_record_doctor)

    capture_parser = subparsers.add_parser("capture", help="Inspect and control local capture.")
    capture_sub = capture_parser.add_subparsers(dest="capture_command", required=True)
    capture_status = capture_sub.add_parser("status", help="Show active capture session state.")
    capture_status.set_defaults(func=cmd_capture_status)
    capture_doctor = capture_sub.add_parser("doctor", help="Show capture diagnostics and optionally smoke-test audio input.")
    capture_doctor.add_argument("--smoke-test", action="store_true", help="Record one second to a temporary WAV file.")
    capture_doctor.set_defaults(func=cmd_capture_doctor)

    transcribe_parser = subparsers.add_parser("transcribe", help="Transcribe a meeting with whisper.cpp.")
    transcribe_parser.add_argument("meeting_id", type=int)
    transcribe_parser.set_defaults(func=cmd_transcribe)

    extract_parser = subparsers.add_parser("extract", help="Extract structured meeting context.")
    extract_parser.add_argument("meeting_id", type=int)
    extract_parser.add_argument("--fixture", type=Path, help="Read extraction JSON from a local fixture.")
    extract_parser.set_defaults(func=cmd_extract)

    process_parser = subparsers.add_parser("process", help="Transcribe, extract, and write markdown.")
    process_parser.add_argument("meeting_id", type=int)
    process_parser.add_argument("--fixture", type=Path, help="Read extraction JSON from a local fixture.")
    process_parser.set_defaults(func=cmd_process)

    context_parser = subparsers.add_parser("context", help="Show cross-meeting context for a topic.")
    context_parser.add_argument("--topic", required=True)
    context_parser.set_defaults(func=cmd_context)

    brief_parser = subparsers.add_parser("brief", help="Show the daily follow-through brief.")
    brief_parser.set_defaults(func=cmd_brief)

    commitments_parser = subparsers.add_parser("commitments", help="List and manage commitments.")
    commitments_sub = commitments_parser.add_subparsers(dest="commitments_command")
    commitments_parser.set_defaults(func=cmd_commitments)
    confirm_parser = commitments_sub.add_parser("confirm", help="Confirm a commitment/task is complete.")
    confirm_parser.add_argument("task_id", type=int)
    confirm_parser.set_defaults(func=cmd_commitments_confirm)
    snooze_parser = commitments_sub.add_parser("snooze", help="Snooze a commitment/task.")
    snooze_parser.add_argument("task_id", type=int)
    snooze_parser.add_argument("--until")
    snooze_parser.set_defaults(func=cmd_commitments_snooze)
    cancel_parser = commitments_sub.add_parser("cancel", help="Cancel a commitment/task.")
    cancel_parser.add_argument("task_id", type=int)
    cancel_parser.set_defaults(func=cmd_commitments_cancel)
    waiting_parser = commitments_sub.add_parser("waiting", help="Mark a commitment/task as waiting on someone else.")
    waiting_parser.add_argument("task_id", type=int)
    waiting_parser.set_defaults(func=cmd_commitments_waiting)
    uncertain_parser = commitments_sub.add_parser("uncertain", help="Mark a commitment/task as uncertain.")
    uncertain_parser.add_argument("task_id", type=int)
    uncertain_parser.set_defaults(func=cmd_commitments_uncertain)

    tasks_parser = subparsers.add_parser("tasks", help="List and manage local tasks.")
    tasks_sub = tasks_parser.add_subparsers(dest="tasks_command")
    tasks_parser.set_defaults(func=cmd_tasks_list)
    overdue_parser = tasks_sub.add_parser("overdue", help="List overdue tasks.")
    overdue_parser.set_defaults(func=cmd_tasks_overdue)
    waiting_tasks_parser = tasks_sub.add_parser("waiting", help="List tasks waiting on someone else.")
    waiting_tasks_parser.set_defaults(func=cmd_tasks_waiting)
    complete_parser = tasks_sub.add_parser("complete", help="Mark a task complete.")
    complete_parser.add_argument("task_id", type=int)
    complete_parser.set_defaults(func=cmd_tasks_complete)
    reopen_parser = tasks_sub.add_parser("reopen", help="Reopen a completed task.")
    reopen_parser.add_argument("task_id", type=int)
    reopen_parser.set_defaults(func=cmd_tasks_reopen)
    snooze_task_parser = tasks_sub.add_parser("snooze", help="Snooze a task.")
    snooze_task_parser.add_argument("task_id", type=int)
    snooze_task_parser.add_argument("--until")
    snooze_task_parser.set_defaults(func=cmd_tasks_snooze)
    cancel_task_parser = tasks_sub.add_parser("cancel", help="Cancel a task.")
    cancel_task_parser.add_argument("task_id", type=int)
    cancel_task_parser.set_defaults(func=cmd_tasks_cancel)
    add_parser = tasks_sub.add_parser("add", help="Add a manual task.")
    add_parser.add_argument("text")
    add_parser.add_argument("--owner")
    add_parser.add_argument("--owed-to")
    add_parser.add_argument("--project")
    add_parser.add_argument("--due")
    add_parser.set_defaults(func=cmd_tasks_add)
    task_record_parser = tasks_sub.add_parser("record", help="Record a voice note and turn it into a task.")
    task_record_sub = task_record_parser.add_subparsers(dest="task_record_command", required=True)
    task_record_start = task_record_sub.add_parser("start", help="Start recording a voice task.")
    task_record_start.set_defaults(func=cmd_tasks_record_start)
    task_record_stop = task_record_sub.add_parser("stop", help="Stop voice task recording, transcribe it, and add a task.")
    task_record_stop.add_argument("--owner")
    task_record_stop.add_argument("--project")
    task_record_stop.add_argument("--due")
    task_record_stop.set_defaults(func=cmd_tasks_record_stop)

    gmail_parser = subparsers.add_parser("gmail", help="Gmail integrations.")
    gmail_sub = gmail_parser.add_subparsers(dest="gmail_command", required=True)
    preview_parser = gmail_sub.add_parser("preview", help="Preview a follow-up email without creating a Gmail draft.")
    preview_parser.add_argument("meeting_id", type=int)
    preview_parser.add_argument("--to", default="")
    preview_parser.add_argument("--subject")
    preview_parser.add_argument("--instruction", default="")
    preview_parser.set_defaults(func=cmd_gmail_preview)
    draft_parser = gmail_sub.add_parser("draft", help="Create a Gmail draft for a meeting.")
    draft_parser.add_argument("meeting_id", type=int)
    draft_parser.add_argument("--to", default="")
    draft_parser.add_argument("--subject")
    draft_parser.add_argument("--instruction", default="")
    draft_parser.set_defaults(func=cmd_gmail_draft)

    return parser


def cmd_init(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    settings.ensure_dirs()
    repo.init()
    if not Path(".env").exists():
        source = Path(".env.example")
        if not source.exists():
            source = Path(__file__).resolve().parent.parent / ".env.example"
        shutil.copyfile(source, ".env")
        print("Created .env from .env.example")
    print(f"Initialized database at {settings.db_path}")
    print(f"Notes directory: {settings.notes_dir}")
    return 0


def cmd_app(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    run_app(settings, repo, host=args.host or settings.app_host, port=args.port or settings.app_port)
    return 0


def cmd_ask(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    response = execute_command(settings, repo, args.command)
    print(response["summary"])
    result = response.get("result") or {}
    if "capabilities" in result:
        print_capabilities(result["capabilities"])
    elif "tasks" in result:
        print_tasks(result["tasks"])
    elif "meetings" in result:
        print_meetings(result["meetings"])
    elif "task" in result:
        print_tasks([result["task"]])
        MarkdownWriter(settings, repo).write_commitments()
    elif "draft" in result:
        print_draft(result["draft"])
    elif "meeting" in result and result["meeting"]:
        print_meetings([result["meeting"]])
        if result.get("note_path"):
            print(f"Note: {result['note_path']}")
        if result.get("transcript_path"):
            print(f"Transcript: {result['transcript_path']}")
    elif "markdown" in result:
        print()
        print(result["markdown"])
    return 0 if response["supported"] else 1


def cmd_assistant_capabilities(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    response = execute_command(settings, repo, "what can you do")
    print(response["summary"])
    print_capabilities((response.get("result") or {}).get("capabilities", []))
    return 0


def cmd_record_start(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    meeting_id = Recorder(settings, repo).start(args.title)
    print(f"Recording meeting {meeting_id}: {args.title}")
    return 0


def cmd_record_stop(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    meeting_id = Recorder(settings, repo).stop()
    print(f"Stopped recording meeting {meeting_id}")
    if args.process:
        result = process_meeting(settings, repo, meeting_id)
        print(f"Wrote transcript: {result['transcript_path']}")
        print(f"Wrote note: {result['note_path']}")
        print(f"Wrote commitments: {result['commitments_path']}")
    return 0


def cmd_record_doctor(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    return cmd_capture_doctor(args, settings, repo)


def cmd_capture_status(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    settings.ensure_dirs()
    status = CaptureService(settings, repo).status()
    if not status.get("active"):
        print("No active capture session.")
        return 0
    print_capture_session(status)
    return 0


def cmd_capture_doctor(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    settings.ensure_dirs()
    diagnostics = CaptureService(settings, repo).diagnostics()
    print(f"Capture profile: {diagnostics['capture_profile']}")
    print(f"Input device: {diagnostics['input_device'] or '(default)'}")
    print(f"Recorder status: {diagnostics['recorder_status']}")
    print(f"Recorder command: {diagnostics['recorder_command_preview']}")
    for warning in diagnostics["warnings"]:
        print(f"Note: {warning}")
    if not args.smoke_test:
        print(diagnostics["smoke_test_hint"])
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "speedwagon-smoke.wav"
        smoke_command = recorder_command(
            settings.record_cmd,
            path,
            profile=settings.capture_profile,
            input_device=settings.input_device,
        ) + ["trim", "0", "1"]
        result = subprocess.run(smoke_command, check=False, text=True, capture_output=True)
        if result.returncode != 0:
            print(result.stderr.strip() or result.stdout.strip())
            print("Smoke test failed. On macOS, check microphone permission for Terminal/VS Code and set SPEEDWAGON_INPUT_DEVICE to your Sound Input device name.")
            return 1
        print(f"Smoke test wrote {path.stat().st_size} bytes.")
    return 0


def cmd_transcribe(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    path = Transcriber(settings, repo).transcribe(args.meeting_id)
    print(f"Wrote transcript: {path}")
    return 0


def cmd_extract(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    result = Extractor(settings, repo).extract(args.meeting_id, fixture_path=args.fixture)
    MarkdownWriter(settings, repo).write_commitments()
    print(f"Extracted {len(result.action_items)} action items and {len(result.commitments)} commitments")
    return 0


def cmd_process(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    result = process_meeting(settings, repo, args.meeting_id, fixture_path=args.fixture)
    print(f"Wrote transcript: {result['transcript_path']}")
    print(f"Wrote note: {result['note_path']}")
    print(f"Wrote commitments: {result['commitments_path']}")
    return 0


def cmd_context(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    print(render_context(repo, args.topic))
    return 0


def cmd_commitments(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    path = MarkdownWriter(settings, repo).write_commitments()
    print(path.read_text(encoding="utf-8"))
    print(f"\nWrote {path}")
    return 0


def cmd_brief(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    print_daily_brief(repo.daily_brief())
    return 0


def cmd_commitments_confirm(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    return _commitment_status_change(settings, repo, repo.complete_task(args.task_id), "Confirmed")


def cmd_commitments_snooze(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    return _commitment_status_change(settings, repo, repo.snooze_task(args.task_id, args.until), "Snoozed")


def cmd_commitments_cancel(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    return _commitment_status_change(settings, repo, repo.cancel_task(args.task_id), "Canceled")


def cmd_commitments_waiting(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    return _commitment_status_change(settings, repo, repo.update_task_status(args.task_id, "waiting"), "Marked waiting")


def cmd_commitments_uncertain(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    return _commitment_status_change(settings, repo, repo.update_task_status(args.task_id, "uncertain"), "Marked uncertain")


def _commitment_status_change(settings: Settings, repo: Repository, task: dict, label: str) -> int:
    MarkdownWriter(settings, repo).write_commitments()
    print(f"{label} task {task['id']}: {task['text']}")
    return 0


def cmd_tasks_list(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    print_tasks(repo.list_tasks(status="open"))
    return 0


def cmd_tasks_overdue(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    print_tasks(run_action(settings, repo, "list_overdue_tasks")["tasks"])
    return 0


def cmd_tasks_waiting(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    print_tasks(run_action(settings, repo, "list_waiting_tasks")["tasks"])
    return 0


def cmd_tasks_complete(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    task = repo.complete_task(args.task_id)
    MarkdownWriter(settings, repo).write_commitments()
    print(f"Completed task {task['id']}: {task['text']}")
    return 0


def cmd_tasks_reopen(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    task = repo.reopen_task(args.task_id)
    MarkdownWriter(settings, repo).write_commitments()
    print(f"Reopened task {task['id']}: {task['text']}")
    return 0


def cmd_tasks_snooze(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    task = repo.snooze_task(args.task_id, args.until)
    MarkdownWriter(settings, repo).write_commitments()
    print(f"Snoozed task {task['id']}: {task['text']}")
    return 0


def cmd_tasks_cancel(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    task = repo.cancel_task(args.task_id)
    MarkdownWriter(settings, repo).write_commitments()
    print(f"Canceled task {task['id']}: {task['text']}")
    return 0


def cmd_tasks_add(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    task = repo.create_task(args.text, owner=args.owner, owed_to=args.owed_to, project=args.project, due_date=args.due)
    MarkdownWriter(settings, repo).write_commitments()
    print(f"Added task {task['id']}: {task['text']}")
    return 0


def cmd_tasks_record_start(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    state = VoiceTaskRecorder(settings, repo).start()
    print(f"Recording voice task: {state['audio_path']}")
    return 0


def cmd_tasks_record_stop(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    result = VoiceTaskRecorder(settings, repo).stop(owner=args.owner, due_date=args.due, project=args.project)
    MarkdownWriter(settings, repo).write_commitments()
    task = result["task"]
    print(f"Added voice task {task['id']}: {task['text']}")
    print(f"Transcript: {result['transcript_path']}")
    return 0


def print_tasks(tasks: list[dict]) -> None:
    if not tasks:
        print("No tasks.")
        return
    for task in tasks:
        due = f" due {task['due_date']}" if task.get("due_date") else ""
        owner = task.get("owner") or "unassigned"
        owed_to = f" -> {task['owed_to']}" if task.get("owed_to") else ""
        project = f" #{task['project']}" if task.get("project") else ""
        source = task.get("meeting_title") or task.get("source")
        marker = "!" if task.get("is_overdue") else "-"
        print(f"{marker} [{task['id']}] {task['text']} [{task['status']}] ({owner}{owed_to}{project}{due}; {source})")


def print_daily_brief(brief: dict) -> None:
    print(f"Daily brief for {brief['date']}")
    for key, label in [
        ("overdue", "Overdue"),
        ("today", "Due today"),
        ("waiting", "Waiting"),
        ("uncertain", "Uncertain"),
        ("stale", "Stale"),
        ("recommended_followups", "Recommended follow-ups"),
    ]:
        print(f"\n{label}")
        print_tasks(brief.get(key, []))


def print_capabilities(capabilities: list[dict]) -> None:
    if not capabilities:
        print("No capabilities registered.")
        return
    for capability in capabilities:
        print(f"- [{capability['category']}] {capability['command']} - {capability['description']}")


def print_meetings(meetings: list[dict]) -> None:
    if not meetings:
        print("No meetings.")
        return
    for meeting in meetings:
        markers = []
        if not meeting.get("transcript_path"):
            markers.append("no transcript")
        if not meeting.get("note_path"):
            markers.append("no note")
        suffix = f" ({', '.join(markers)})" if markers else ""
        print(f"- [{meeting['id']}] {meeting['title']} {meeting.get('started_at', '')[:10]}{suffix}")


def print_draft(draft: dict) -> None:
    print(f"Subject: {draft.get('subject', '')}")
    print(f"Tone: {draft.get('tone', '')}")
    print()
    print(draft.get("body", ""))


def print_capture_session(session: dict) -> None:
    print(f"Capture kind: {session.get('kind')}")
    if session.get("title"):
        print(f"Title: {session['title']}")
    if session.get("meeting_id"):
        print(f"Meeting: {session['meeting_id']}")
    print(f"Started: {session.get('started_at')}")
    print(f"Audio: {session.get('audio_path')}")
    print(f"File size: {session.get('file_size', 0)} bytes")
    print(f"Profile: {session.get('capture_profile')}")
    print(f"Input device: {session.get('input_device') or '(default)'}")
    if session.get("last_error"):
        print(f"Last error: {session['last_error']}")


def cmd_gmail_draft(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    draft_id = create_gmail_draft(
        settings,
        repo,
        args.meeting_id,
        to=args.to,
        subject=args.subject,
        instruction=args.instruction,
    )
    print(f"Created Gmail draft: {draft_id}")
    return 0


def cmd_gmail_preview(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    preview = preview_followup_email(
        settings,
        repo,
        args.meeting_id,
        to=args.to,
        subject=args.subject,
        instruction=args.instruction,
    )
    print(f"To: {preview['to']}")
    print(f"Subject: {preview['subject']}")
    print(f"Tone: {preview['tone']}")
    if preview["included_items"]:
        print(f"Included: {', '.join(preview['included_items'])}")
    print()
    print(preview["body"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
