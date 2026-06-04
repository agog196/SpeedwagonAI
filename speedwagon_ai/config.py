from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    db_path: Path
    notes_dir: Path
    audio_dir: Path
    transcripts_dir: Path
    state_path: Path
    app_host: str
    app_port: int
    record_cmd: str
    capture_profile: str
    input_device: str
    whisper_cpp_bin: str
    whisper_cpp_model: str
    llm_provider: str
    openai_api_key: str
    openai_model: str
    anthropic_api_key: str
    gmail_credentials_path: Path
    gmail_token_path: Path
    google_calendar_token_path: Path
    bot_provider: str = ""
    recall_api_key: str = ""
    recall_region: str = "us-east-1"
    recall_bot_name: str = "SpeedwagonAI Notetaker"
    google_calendar_ids: str = "primary"
    google_calendar_sync_days_back: int = 14
    google_calendar_sync_days_forward: int = 30

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv()
        return cls(
            db_path=Path(os.getenv("SPEEDWAGON_DB_PATH", "data/speedwagon.db")),
            notes_dir=Path(os.getenv("SPEEDWAGON_NOTES_DIR", "notes")),
            audio_dir=Path(os.getenv("SPEEDWAGON_AUDIO_DIR", "audio")),
            transcripts_dir=Path(os.getenv("SPEEDWAGON_TRANSCRIPTS_DIR", "transcripts")),
            state_path=Path(os.getenv("SPEEDWAGON_STATE_PATH", "data/recording.json")),
            app_host=os.getenv("SPEEDWAGON_APP_HOST", "127.0.0.1"),
            app_port=int(os.getenv("SPEEDWAGON_APP_PORT", "8765")),
            record_cmd=os.getenv("SPEEDWAGON_RECORD_CMD", ""),
            capture_profile=os.getenv("SPEEDWAGON_CAPTURE_PROFILE", "mic"),
            input_device=os.getenv("SPEEDWAGON_INPUT_DEVICE", ""),
            whisper_cpp_bin=os.getenv("WHISPER_CPP_BIN", ""),
            whisper_cpp_model=os.getenv("WHISPER_CPP_MODEL", ""),
            llm_provider=os.getenv("LLM_PROVIDER", "openai"),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            gmail_credentials_path=Path(os.getenv("GMAIL_CREDENTIALS_PATH", "data/google_credentials.json")),
            gmail_token_path=Path(os.getenv("GMAIL_TOKEN_PATH", "data/google_token.json")),
            google_calendar_token_path=Path(
                os.getenv("GOOGLE_CALENDAR_TOKEN_PATH", "data/google_calendar_token.json")
            ),
            bot_provider=os.getenv("SPEEDWAGON_BOT_PROVIDER", "").strip().lower(),
            recall_api_key=os.getenv("RECALL_API_KEY", ""),
            recall_region=os.getenv("RECALL_REGION", "us-east-1"),
            recall_bot_name=os.getenv("RECALL_BOT_NAME", "SpeedwagonAI Notetaker"),
            google_calendar_ids=os.getenv("GOOGLE_CALENDAR_IDS", "primary"),
            google_calendar_sync_days_back=int(os.getenv("GOOGLE_CALENDAR_SYNC_DAYS_BACK", "14")),
            google_calendar_sync_days_forward=int(os.getenv("GOOGLE_CALENDAR_SYNC_DAYS_FORWARD", "30")),
        )

    def ensure_dirs(self) -> None:
        for path in [self.db_path.parent, self.notes_dir, self.audio_dir, self.transcripts_dir, self.state_path.parent]:
            path.mkdir(parents=True, exist_ok=True)
