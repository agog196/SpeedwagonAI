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
speedwagon capture status
speedwagon capture doctor --smoke-test
speedwagon process <meeting-id>
speedwagon context --topic "weekly planning"
speedwagon commitments
speedwagon tasks
speedwagon brief
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

## Tasks

SpeedwagonAI mirrors extracted action items and commitments into a unified local task inbox.

```bash
speedwagon tasks
speedwagon tasks overdue
speedwagon tasks waiting
speedwagon tasks add "Send revised follow-up" --due 2026-06-01
speedwagon tasks record start
speedwagon tasks record stop --due 2026-06-01
speedwagon tasks complete <task-id>
speedwagon tasks reopen <task-id>
speedwagon tasks snooze <task-id> --until 2026-06-05
speedwagon tasks cancel <task-id>
```

The local app also has a Tasks screen for completing, reopening, and reviewing overdue work.

Voice tasks are available from the CLI and the local app Tasks screen. They record a short audio note, transcribe it with whisper.cpp, and create a task from the transcript.

## Commitment Intelligence

The task layer now acts as the local commitment graph. Commitments can be `open`, `waiting`, `snoozed`, `uncertain`, `done`, or `canceled`, with optional owner, owed-to person, project, source, due date, confidence, and source meeting.

```bash
speedwagon brief
speedwagon commitments
speedwagon commitments confirm <task-id>
speedwagon commitments snooze <task-id> --until 2026-06-05
speedwagon commitments waiting <task-id>
speedwagon commitments uncertain <task-id>
speedwagon commitments cancel <task-id>
```

The daily brief groups overdue, due-today, waiting, uncertain, stale, and recommended follow-up work.

## Assistant Commands

Run deterministic one-line commands:

```bash
speedwagon ask "what is overdue"
speedwagon ask "what should I do today"
speedwagon ask "daily brief"
speedwagon ask "what can you do"
speedwagon ask "what do I owe Alex"
speedwagon ask "what am I waiting on"
speedwagon ask "what did I say about onboarding"
speedwagon ask "show unprocessed meetings"
speedwagon ask "process latest meeting"
speedwagon ask "start meeting recording called weekly planning"
speedwagon ask "finish meeting"
speedwagon ask "draft follow-up for meeting 8"
speedwagon ask "add task send notes due 2026-06-01"
speedwagon ask "complete task 12"
speedwagon ask "snooze task 12 until 2026-06-05"
speedwagon ask "search context for onboarding"
speedwagon assistant capabilities
```

The local app dashboard includes the same command box. SpeedwagonAI uses fast deterministic rules first, then falls back to OpenAI command interpretation for unsupported in-scope requests when `OPENAI_API_KEY` is configured. The LLM fallback can only choose from SpeedwagonAI's existing deterministic actions.

Mutating LLM-interpreted actions require confirmation. For example, a flexible request that maps to `add_task` becomes a pending action instead of creating the task immediately.

The native assistant palette also supports local voice-to-assistant input: record a voice message, transcribe it with your configured local Whisper setup, and run the transcript through the same assistant action layer. The native Screenshot button captures the main display, sends it to the backend for explicit vision analysis, and returns suggested tasks/actions for confirmation.

## Native Mac App

The developer SwiftUI app under `native/SpeedwagonAI` shows an assistant-first dashboard, task inbox, daily brief, commitments, capture controls, screenshot context, pending confirmations, menu bar icon, and Spotlight-like assistant palette backed by the local HTTP API.

Start the Python backend first:

```bash
speedwagon app
```

Then run the Swift app:

```bash
cd native/SpeedwagonAI
swift run SpeedwagonAI
```

If Xcode is installed but builds are blocked, accept the Xcode license and switch the active developer directory as described in [native/SpeedwagonAI/README.md](native/SpeedwagonAI/README.md).

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

Check the active recorder setup:

```bash
speedwagon capture status
speedwagon capture doctor
speedwagon capture doctor --smoke-test
```

`speedwagon record doctor` still works as a compatibility alias.

If the smoke test says there is no default audio device, grant microphone permission to your terminal app or VS Code, then set `SPEEDWAGON_INPUT_DEVICE` to the exact device name shown in macOS System Settings → Sound → Input.

To capture routed meeting/system audio today, install and configure a virtual audio device such as BlackHole, then set:

```env
SPEEDWAGON_CAPTURE_PROFILE=blackhole
SPEEDWAGON_INPUT_DEVICE=BlackHole 2ch
```

For most local testing, keep:

```env
SPEEDWAGON_CAPTURE_PROFILE=mic
```

Long term, the native Mac app direction should explore Apple's ScreenCaptureKit for a cleaner built-in capture path. See [Native Mac Roadmap](docs/native-mac-roadmap.md) and [ScreenCaptureKit Spike](docs/screencapturekit-spike.md).

## Cost Controls

SpeedwagonAI routes routine extraction, email drafting, command parsing, screenshot analysis, web search, and deeper synthesis through operation-specific model choices. Optional environment overrides:

```env
SPEEDWAGON_MODEL_CHEAP=gpt-4.1-mini
SPEEDWAGON_MODEL_STRONG=gpt-4.1
SPEEDWAGON_MODEL_COMMAND=gpt-4.1-mini
SPEEDWAGON_MODEL_VISION=gpt-4.1
SPEEDWAGON_MODEL_WEB=gpt-4.1
SPEEDWAGON_ENABLE_WEB_SEARCH=false
```

Web search only triggers for explicit requests like `search the web for ...` or `latest ...`. It is disabled unless `SPEEDWAGON_ENABLE_WEB_SEARCH=true`, and V12 still treats web search as a gated summary path rather than an action-taking agent.

The deployable Mac app direction should store user API keys in macOS Keychain; `.env` remains the local developer setup.
