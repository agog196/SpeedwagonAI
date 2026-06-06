from __future__ import annotations

import json
import re
import shutil
import traceback
import zipfile
from pathlib import Path
from typing import Any

from speedwagon_ai.config import Settings, local_api_token
from speedwagon_ai.storage import Repository
from speedwagon_ai.timeutil import utc_now_iso


WIPE_CONFIRMATION = "DELETE-SPEEDWAGON-DATA"


def logs_dir(settings: Settings) -> Path:
    return settings.db_path.parent / "logs"


def app_log_path(settings: Settings) -> Path:
    return logs_dir(settings) / "speedwagon.log"


def backend_log_path(settings: Settings) -> Path:
    return logs_dir(settings) / "backend.log"


def redact_secret(value: str, settings: Settings) -> str:
    redacted = value
    try:
        api_token = local_api_token(settings)
    except Exception:
        api_token = getattr(settings, "api_token", "")
    for secret in [
        settings.openai_api_key,
        settings.anthropic_api_key,
        settings.recall_api_key,
        api_token,
    ]:
        secret = (secret or "").strip()
        if secret and len(secret) >= 6:
            redacted = redacted.replace(secret, "[REDACTED]")
    redacted = re.sub(r"(?i)(authorization:\s*bearer\s+)[^\s,;]+", r"\1[REDACTED]", redacted)
    redacted = re.sub(r"(?i)(speedwagon_api_token=)[^;\s]+", r"\1[REDACTED]", redacted)
    redacted = re.sub(r"(?i)(api[_-]?key[\"'\s:=]+)[A-Za-z0-9_\-\.]{6,}", r"\1[REDACTED]", redacted)
    redacted = re.sub(r"(?i)(token[\"'\s:=]+)[A-Za-z0-9_\-\.]{6,}", r"\1[REDACTED]", redacted)
    redacted = re.sub(r"(https?://[^\s?]+)\?[^\s\"']+", r"\1?[REDACTED]", redacted)
    return redacted


def write_log(settings: Settings, message: str, *, level: str = "INFO") -> Path:
    path = app_log_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = f"{utc_now_iso()} [{level}] {redact_secret(message, settings)}\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
    return path


def log_exception(settings: Settings, exc: BaseException, *, path: str = "") -> None:
    detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    prefix = f"Unhandled API error at {path}: " if path else "Unhandled error: "
    write_log(settings, prefix + detail, level="ERROR")


def logs_status(settings: Settings, *, tail_lines: int = 80) -> dict[str, Any]:
    path = app_log_path(settings)
    backend = backend_log_path(settings)
    return {
        "log_dir": str(logs_dir(settings)),
        "app_log_path": str(path),
        "backend_log_path": str(backend),
        "app_log_exists": path.exists(),
        "backend_log_exists": backend.exists(),
        "log_tail": tail(path, tail_lines),
        "backend_log_tail": tail(backend, tail_lines),
    }


def tail(path: Path, lines: int) -> str:
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(content[-lines:])


def privacy_status(settings: Settings, repo: Repository) -> dict[str, Any]:
    paths = data_paths(settings)
    existing = [path for path in paths if path.exists()]
    return {
        "db_path": str(settings.db_path),
        "notes_dir": str(settings.notes_dir),
        "audio_dir": str(settings.audio_dir),
        "transcripts_dir": str(settings.transcripts_dir),
        "logs_dir": str(logs_dir(settings)),
        "export_supported": True,
        "wipe_supported": True,
        "wipe_confirmation": WIPE_CONFIRMATION,
        "path_visibility_note": (
            "Detailed local paths are limited to Settings, logs, privacy, export, and debugging responses. "
            "Export manifests remain detailed because export is explicitly user-requested."
        ),
        "local_data_dirs": {
            "database_dir": str(settings.db_path.parent),
            "notes_dir": str(settings.notes_dir),
            "audio_dir": str(settings.audio_dir),
            "transcripts_dir": str(settings.transcripts_dir),
            "logs_dir": str(logs_dir(settings)),
        },
        "external_services": external_services(settings),
        "data_disclosures": data_disclosures(settings),
        "existing_paths": [str(path) for path in existing],
        "counts": {
            "meetings": safe_count(repo, "meetings"),
            "tasks": safe_count(repo, "tasks"),
            "suggestions": safe_count(repo, "suggestions"),
            "followup_drafts": safe_count(repo, "followup_drafts"),
        },
    }


def external_services(settings: Settings) -> dict[str, Any]:
    return {
        "openai": {
            "configured": bool(settings.openai_api_key),
            "purpose": "LLM extraction, assistant interpretation, email drafts, screenshots, and explicit daily intelligence refresh.",
        },
        "google_gmail": {
            "configured": settings.gmail_credentials_path.exists() or settings.gmail_token_path.exists(),
            "purpose": "OAuth draft creation only; SpeedwagonAI does not send email automatically.",
        },
        "google_calendar": {
            "configured": settings.gmail_credentials_path.exists() or settings.google_calendar_token_path.exists(),
            "purpose": "Calendar sync for local context plus explicit user-confirmed event creation.",
        },
        "recall": {
            "configured": bool(settings.bot_provider and settings.recall_api_key),
            "purpose": "Optional consent-required meeting bot capture and transcript retrieval.",
        },
        "web_search": {
            "configured": False,
            "purpose": "Future explicit opt-in search only; no background web search.",
        },
    }


def data_disclosures(settings: Settings) -> list[dict[str, Any]]:
    services = external_services(settings)
    return [
        {
            "service": "OpenAI",
            "enabled": bool(services["openai"]["configured"]),
            "data": "Selected prompts, transcripts, screenshots, task/context summaries, and draft instructions only when those features are used.",
            "trigger": "Meeting processing, screenshot analysis, assistant fallback, draft generation, or explicit intelligence refresh.",
        },
        {
            "service": "Google APIs",
            "enabled": bool(services["google_gmail"]["configured"] or services["google_calendar"]["configured"]),
            "data": "OAuth tokens, Gmail draft content when creating a draft, synced Calendar event metadata, and event details when creating a Calendar event.",
            "trigger": "User-initiated OAuth, Calendar sync, explicit Calendar event creation, or explicit Gmail draft creation.",
        },
        {
            "service": "Recall.ai",
            "enabled": bool(services["recall"]["configured"]),
            "data": "Meeting link, bot metadata, and provider transcript data for consent-confirmed bot sessions.",
            "trigger": "User sends a bot to a meeting and confirms consent.",
        },
        {
            "service": "Web search",
            "enabled": False,
            "data": "Search query text only when future explicit web search is enabled and requested.",
            "trigger": "Future explicit opt-in web search command.",
        },
    ]


def safe_count(repo: Repository, table: str) -> int:
    try:
        with repo.connect() as conn:
            row = conn.execute(f"SELECT count(*) AS count FROM {table}").fetchone()
        return int(row["count"] or 0) if row else 0
    except Exception:
        return 0


def export_data(settings: Settings, repo: Repository, output_path: Path | None = None) -> dict[str, Any]:
    settings.ensure_dirs()
    output = output_path or (settings.db_path.parent / "exports" / f"speedwagon-export-{utc_now_iso().replace(':', '-')}.zip")
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "created_at": utc_now_iso(),
        "db_path": str(settings.db_path),
        "notes_dir": str(settings.notes_dir),
        "audio_dir": str(settings.audio_dir),
        "transcripts_dir": str(settings.transcripts_dir),
        "logs_dir": str(logs_dir(settings)),
        "counts": privacy_status(settings, repo)["counts"],
        "files": [],
    }
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in data_paths(settings):
            add_path_to_archive(path, archive, output, manifest["files"])
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
    write_log(settings, f"Exported local data to {output}")
    return {
        "status": "exported",
        "path": str(output),
        "manifest": manifest,
        "file_count": len(manifest["files"]),
    }


def add_path_to_archive(path: Path, archive: zipfile.ZipFile, output_path: Path, files: list[dict[str, Any]]) -> None:
    if not path.exists():
        return
    if path.is_file():
        add_file(path, archive, output_path, files)
        return
    for child in sorted(path.rglob("*")):
        if child.is_file():
            add_file(child, archive, output_path, files)


def add_file(path: Path, archive: zipfile.ZipFile, output_path: Path, files: list[dict[str, Any]]) -> None:
    if path.resolve() == output_path.resolve():
        return
    arcname = archive_name(path)
    archive.write(path, arcname)
    files.append({"path": str(path), "archive_name": arcname, "size": path.stat().st_size})


def archive_name(path: Path) -> str:
    parts = path.parts
    for marker in ["data", "notes", "audio", "transcripts"]:
        if marker in parts:
            index = parts.index(marker)
            return str(Path(*parts[index:]))
    return path.name


def wipe_data(settings: Settings, repo: Repository, confirmation: str) -> dict[str, Any]:
    if confirmation != WIPE_CONFIRMATION:
        raise ValueError(f"Confirmation must be exactly {WIPE_CONFIRMATION}")
    write_log(settings, "Local Speedwagon data wipe requested.")
    removed: list[str] = []
    for path in data_paths(settings):
        if path.exists():
            remove_path_contents(path)
            removed.append(str(path))
    settings.ensure_dirs()
    return {"status": "wiped", "removed": removed}


def remove_path_contents(path: Path) -> None:
    if path.is_file():
        path.unlink()
        return
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def data_paths(settings: Settings) -> list[Path]:
    values = [
        settings.db_path.parent,
        settings.notes_dir,
        settings.audio_dir,
        settings.transcripts_dir,
        logs_dir(settings),
    ]
    output: list[Path] = []
    seen: set[Path] = set()
    for path in values:
        key = path.resolve() if path.exists() else path.absolute()
        if key in seen:
            continue
        seen.add(key)
        output.append(path)
    return output
