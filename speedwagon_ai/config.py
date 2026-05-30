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
    record_cmd: str
    whisper_cpp_bin: str
    whisper_cpp_model: str
    llm_provider: str
    openai_api_key: str
    openai_model: str
    anthropic_api_key: str
    gmail_credentials_path: Path
    gmail_token_path: Path

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv()
        return cls(
            db_path=Path(os.getenv("SPEEDWAGON_DB_PATH", "data/speedwagon.db")),
            notes_dir=Path(os.getenv("SPEEDWAGON_NOTES_DIR", "notes")),
            audio_dir=Path(os.getenv("SPEEDWAGON_AUDIO_DIR", "audio")),
            transcripts_dir=Path(os.getenv("SPEEDWAGON_TRANSCRIPTS_DIR", "transcripts")),
            state_path=Path(os.getenv("SPEEDWAGON_STATE_PATH", "data/recording.json")),
            record_cmd=os.getenv("SPEEDWAGON_RECORD_CMD", ""),
            whisper_cpp_bin=os.getenv("WHISPER_CPP_BIN", ""),
            whisper_cpp_model=os.getenv("WHISPER_CPP_MODEL", ""),
            llm_provider=os.getenv("LLM_PROVIDER", "openai"),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            gmail_credentials_path=Path(os.getenv("GMAIL_CREDENTIALS_PATH", "data/google_credentials.json")),
            gmail_token_path=Path(os.getenv("GMAIL_TOKEN_PATH", "data/google_token.json")),
        )

    def ensure_dirs(self) -> None:
        for path in [self.db_path.parent, self.notes_dir, self.audio_dir, self.transcripts_dir, self.state_path.parent]:
            path.mkdir(parents=True, exist_ok=True)
