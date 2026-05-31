from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from speedwagon_ai.assistant_actions import run_action
from speedwagon_ai.assistant_commands import execute_command
from speedwagon_ai.capture import Recorder
from speedwagon_ai.app import run_app
from speedwagon_ai.config import Settings
from speedwagon_ai.context import render_context
from speedwagon_ai.extraction import Extractor
from speedwagon_ai.integrations.gmail import create_gmail_draft, preview_followup_email
from speedwagon_ai.output import MarkdownWriter
from speedwagon_ai.storage import Repository
from speedwagon_ai.transcription import Transcriber


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

    record_parser = subparsers.add_parser("record", help="Start or stop local audio recording.")
    record_sub = record_parser.add_subparsers(dest="record_command", required=True)
    record_start = record_sub.add_parser("start", help="Start recording with macOS afrecord.")
    record_start.add_argument("--title", required=True)
    record_start.set_defaults(func=cmd_record_start)
    record_stop = record_sub.add_parser("stop", help="Stop the active recording.")
    record_stop.set_defaults(func=cmd_record_stop)

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

    commitments_parser = subparsers.add_parser("commitments", help="Regenerate and print open commitments.")
    commitments_parser.set_defaults(func=cmd_commitments)

    tasks_parser = subparsers.add_parser("tasks", help="List and manage local tasks.")
    tasks_sub = tasks_parser.add_subparsers(dest="tasks_command")
    tasks_parser.set_defaults(func=cmd_tasks_list)
    overdue_parser = tasks_sub.add_parser("overdue", help="List overdue tasks.")
    overdue_parser.set_defaults(func=cmd_tasks_overdue)
    complete_parser = tasks_sub.add_parser("complete", help="Mark a task complete.")
    complete_parser.add_argument("task_id", type=int)
    complete_parser.set_defaults(func=cmd_tasks_complete)
    reopen_parser = tasks_sub.add_parser("reopen", help="Reopen a completed task.")
    reopen_parser.add_argument("task_id", type=int)
    reopen_parser.set_defaults(func=cmd_tasks_reopen)
    add_parser = tasks_sub.add_parser("add", help="Add a manual task.")
    add_parser.add_argument("text")
    add_parser.add_argument("--owner")
    add_parser.add_argument("--due")
    add_parser.set_defaults(func=cmd_tasks_add)

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
    if "tasks" in result:
        print_tasks(result["tasks"])
    elif "task" in result:
        print_tasks([result["task"]])
        MarkdownWriter(settings, repo).write_commitments()
    elif "markdown" in result:
        print()
        print(result["markdown"])
    return 0 if response["supported"] else 1


def cmd_record_start(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    meeting_id = Recorder(settings, repo).start(args.title)
    print(f"Recording meeting {meeting_id}: {args.title}")
    return 0


def cmd_record_stop(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    meeting_id = Recorder(settings, repo).stop()
    print(f"Stopped recording meeting {meeting_id}")
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
    meeting = repo.get_meeting(args.meeting_id)
    if not meeting.transcript_path:
        Transcriber(settings, repo).transcribe(args.meeting_id)
    Extractor(settings, repo).extract(args.meeting_id, fixture_path=args.fixture)
    writer = MarkdownWriter(settings, repo)
    note_path = writer.write_meeting(args.meeting_id)
    commitments_path = writer.write_commitments()
    print(f"Wrote note: {note_path}")
    print(f"Wrote commitments: {commitments_path}")
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


def cmd_tasks_list(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    print_tasks(repo.list_tasks(status="open"))
    return 0


def cmd_tasks_overdue(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    print_tasks(run_action(settings, repo, "list_overdue_tasks")["tasks"])
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


def cmd_tasks_add(args: argparse.Namespace, settings: Settings, repo: Repository) -> int:
    repo.init()
    task = repo.create_task(args.text, owner=args.owner, due_date=args.due)
    MarkdownWriter(settings, repo).write_commitments()
    print(f"Added task {task['id']}: {task['text']}")
    return 0


def print_tasks(tasks: list[dict]) -> None:
    if not tasks:
        print("No tasks.")
        return
    for task in tasks:
        due = f" due {task['due_date']}" if task.get("due_date") else ""
        owner = task.get("owner") or "unassigned"
        source = task.get("meeting_title") or task.get("source")
        marker = "!" if task.get("is_overdue") else "-"
        print(f"{marker} [{task['id']}] {task['text']} ({owner}{due}; {source})")


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
