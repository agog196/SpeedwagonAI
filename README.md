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
speedwagon app
```

## V1 Notes

- Audio capture auto-detects `afrecord`, SoX `rec`, or `ffmpeg`.
- Transcription shells out to `whisper.cpp`.
- Extraction uses one OpenAI API call per meeting by default.
- Data is stored locally in SQLite under `data/`.
- Markdown notes are written under `notes/`.
- Gmail integration creates drafts only and requires optional Google client libraries.

## Local App

Start the local browser UI:

```bash
speedwagon app
```

The app runs at `http://127.0.0.1:8765` by default and uses the same local SQLite database as the CLI.

## Gmail Draft Instructions

Preview a draft with an instruction:

```bash
speedwagon gmail preview <meeting-id> \
  --to person@example.com \
  --instruction "Write a warm follow-up thanking them and listing next steps."
```

Create the Gmail draft:

```bash
speedwagon gmail draft <meeting-id> \
  --to person@example.com \
  --instruction "Write a warm follow-up thanking them and listing next steps."
```

Gmail remains draft-only; SpeedwagonAI does not send mail automatically.

## Meeting Audio With Headphones

The default capture mode records your microphone. It does not capture meeting audio playing only through headphones.

To capture routed meeting/system audio today, install and configure a virtual audio device such as BlackHole, then set:

```env
SPEEDWAGON_CAPTURE_PROFILE=blackhole
SPEEDWAGON_INPUT_DEVICE=BlackHole 2ch
```

For most local testing, keep:

```env
SPEEDWAGON_CAPTURE_PROFILE=mic
```

Long term, the native Mac app direction should explore Apple's ScreenCaptureKit for a cleaner built-in capture path. See [Native Mac Roadmap](docs/native-mac-roadmap.md).
