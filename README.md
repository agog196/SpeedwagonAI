# SpeedwagonAI

Local-first meeting context engine for Mac.

## Quick Start

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
speedwagon init
```

Configure `.env` with your local `whisper.cpp` binary/model paths and OpenAI API key.

```bash
speedwagon record start --title "Weekly planning"
speedwagon record stop
speedwagon process <meeting-id>
speedwagon context --topic "weekly planning"
speedwagon commitments
```

## V1 Notes

- Audio capture uses macOS `afrecord`.
- Transcription shells out to `whisper.cpp`.
- Extraction uses one OpenAI API call per meeting by default.
- Data is stored locally in SQLite under `data/`.
- Markdown notes are written under `notes/`.
- Gmail integration creates drafts only and requires optional Google client libraries.
