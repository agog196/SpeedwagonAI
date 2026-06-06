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
speedwagon calendar status
speedwagon calendar sync
speedwagon app
speedwagon export --output data/exports/speedwagon-export.zip
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

Local API calls under `/api/*` require a bearer token in V18. Speedwagon creates one at `data/local_api_token` unless `SPEEDWAGON_API_TOKEN` is set. The bundled browser UI receives a local same-site cookie automatically; native/API clients send `Authorization: Bearer <token>`.

V19 adds local beta privacy tools:

```bash
speedwagon export --output data/exports/speedwagon-export.zip
speedwagon wipe --confirm DELETE-SPEEDWAGON-DATA
```

Export writes a zip with local Speedwagon data plus a manifest. Wipe deletes configured Speedwagon-owned local data directories/files after the exact confirmation phrase.

V23 adds local beta readiness docs:

- [Local beta privacy policy](docs/privacy-policy-local-beta.md)
- [Local beta terms](docs/terms-local-beta.md)
- [Native local app verification checklist](native/SpeedwagonAI/README.md#v25-local-app-verification-checklist)

These beta docs are plain-language tester drafts. They explain local-first storage, explicit external-service use, Gmail draft-only behavior, export/wipe, and permission expectations.

V25 adds native first-run readiness diagnostics for repo root, Python 3.11, backend command, bundle mode, notification status, and Keychain token/key presence. The Settings diagnostics report is designed to be copied for private beta support without exposing secrets. V26 adds opt-in Developer ID signing, notarization, stapling, and private-beta DMG scripts.

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

Voice tasks use lightweight local parsing for simple trailing due dates such as `by June 8`, `due 2026-06-10`, `today`, or `tomorrow`. Full meeting recordings still use the richer meeting extraction path.

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

## Native Notifications

V17 adds local notification candidates from Speedwagon's follow-through suggestions. Notifications are source-linked: completing, canceling, snoozing, or dismissing the related task/suggestion retires stale nudges so the app does not keep nagging you about resolved work.

CLI tools:

```bash
speedwagon notifications status
speedwagon notifications candidates
speedwagon notifications snooze <suggestion-id> --until 2026-06-09
speedwagon notifications dismiss <suggestion-id>
```

Native macOS notification delivery happens from the Swift app while it is running. Open the Notifications tab, allow notifications, and Speedwagon will schedule local notifications for overdue, due-today, stale, waiting/uncertain, unscheduled, and follow-up suggestions. Clicking a notification opens SpeedwagonAI; it never executes an action automatically.

Apple Reminders, Calendar writes, background daemon behavior, and packaged launch-at-login delivery remain later work.

## Follow-Through Graph

V13 adds a local context graph over tasks, meetings, screenshots, and future sources. It links work to project/person/topic contexts, then creates in-app suggestions when follow-through patterns appear.

Examples:

```bash
speedwagon ask "search tasks for DairyMGT"
speedwagon ask "search context graph for DairyMGT"
speedwagon ask "show suggestions"
speedwagon ask "confirm suggestion 3"
speedwagon ask "dismiss suggestion 3"
speedwagon ask "snooze suggestion 3 until 2026-06-08"
```

Suggestions are confirmation-first. V13 can suggest a draft follow-up when related work appears done, but it does not send emails or create external reminders automatically.

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
speedwagon ask "search tasks for onboarding"
speedwagon ask "search context graph for onboarding"
speedwagon ask "show suggestions"
speedwagon ask "show unprocessed meetings"
speedwagon ask "process latest meeting"
speedwagon ask "show bot sessions"
speedwagon ask "sync bot session 3"
speedwagon ask "process bot session 3"
speedwagon ask "sync calendar"
speedwagon ask "show upcoming meetings"
speedwagon ask "prep for my next meeting"
speedwagon ask "what is on my calendar today"
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

The native assistant palette also supports local voice-to-assistant input: record a voice message, transcribe it with your configured local Whisper setup, and run the transcript through the same assistant action layer. The native Screenshot button captures the active display, sends it to the backend for explicit vision analysis, and returns suggested tasks/actions for confirmation.

## Native Mac App

The developer SwiftUI app under `native/SpeedwagonAI` shows an assistant-first dashboard, task inbox, daily brief, commitments, capture controls, screenshot context, follow-through suggestions, pending confirmations, menu bar icon, and Spotlight-like assistant palette backed by the local HTTP API.

Start the Python backend first:

```bash
speedwagon app
```

Then run the Swift app:

```bash
cd native/SpeedwagonAI
swift run SpeedwagonAI
```

For the V25 local beta `.app` shell:

```bash
cd native/SpeedwagonAI
./scripts/build-local-app.sh
SPEEDWAGON_REPO_ROOT="$(cd ../.. && pwd)" open dist/SpeedwagonAI.app
```

The local beta app can start and stop the Python backend it launches. It still expects Python 3.11 and this repo checkout to exist locally. The unsigned build is for local development; V26 signed/notarized DMG packaging is documented in the native README. macOS Keychain prompts ask for the tester's Mac login password so SpeedwagonAI can read or save its own local-beta secrets.

The native palette opens from the menu bar, `Cmd+K` while the app is focused, or global `Option+Space`. It uses a floating `NSPanel` intended to appear over the current Space/full-screen app. In expanded mode, it includes meeting capture controls for `Native system + mic`, `Mic fallback`, Stop, and Stop + Process.

You can also type capture commands in the native palette:

```text
start meeting recording called weekly planning
start native meeting called weekly planning
finish meeting
stop meeting without processing
```

In the native app, these commands use the selected meeting capture mode instead of the backend-only mic recorder.

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

Gmail remains draft-only; SpeedwagonAI does not send mail automatically. Follow-through suggestions create editable local drafts first; creating the Gmail draft is a second explicit action after review.

## Meeting Audio With Headphones

The native Mac app now has a V14 meeting capture mode called `Native system + mic`. It uses ScreenCaptureKit for system audio and an AVFoundation sidecar recorder for microphone audio, writes temp tracks into `audio/`, mixes them into `meeting-<id>.wav`, then hands that final WAV to the existing Whisper/process pipeline.

Start the backend and native app:

```bash
speedwagon app
cd native/SpeedwagonAI
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer swift run SpeedwagonAI
```

In the native Capture panel, choose:

- `Native system + mic` for meeting audio you hear plus your voice.
- `Mic fallback` for the old local mic recorder.

Task voice and assistant voice remain mic-only in V14, even when the meeting capture selector says `Native system + mic`. Use the meeting title field plus `Start Native` when you want headphone/system audio captured. CLI and web capture also continue to use the Python recorder path.

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

BlackHole/custom routing remains a fallback for CLI/web recording. The native ScreenCaptureKit path is the preferred product direction for local meeting capture.

## Meeting Bot Beta

V15 adds an optional managed meeting-bot beta for Zoom/Meet/Teams-style meeting links. Local capture remains the default and cheapest path. Bot capture is provider-backed, joins visibly, can cost more, and requires explicit consent/disclosure confirmation.

For local no-network testing:

```env
SPEEDWAGON_BOT_PROVIDER=fake
```

For Recall.ai-style real provider testing:

```env
SPEEDWAGON_BOT_PROVIDER=recall
RECALL_API_KEY=...
RECALL_REGION=us-east-1
RECALL_BOT_NAME=SpeedwagonAI Notetaker
```

Use the region shown in your Recall dashboard, for example `us-west-2`. Sync uses Recall's current transcript artifact/download flow from the bot recording metadata. If a recording is done but has no transcript artifact yet, Speedwagon requests Recall async transcription for that recording; sync again after Recall finishes. Bot status/session refreshes also run a light auto-sync with a short cooldown, so completed sessions can move to `transcript_requested` or `transcript_ready` without a separate manual sync click. If the transcript is still processing, Speedwagon leaves the session waiting instead of writing a partial metadata blob as a transcript.

CLI flow:

```bash
speedwagon bot status
speedwagon bot join \
  --url "https://meet.google.com/abc-defg-hij" \
  --title "Weekly planning" \
  --confirm-consent
speedwagon bot sessions
speedwagon bot sync <session-id>
speedwagon bot process <session-id>
```

`sync` pulls the provider transcript into `transcripts/bot-<session-id>.txt`. `process` skips Whisper and sends that transcript through the existing extraction, markdown, tasks, context graph, and suggestions pipeline.

## Google Calendar

Google Calendar support syncs a local rolling event cache for daily brief and meeting-prep context. It also supports explicit user-triggered event creation. SpeedwagonAI does not edit/delete events, schedule bots from Calendar, or write reminders.

Add optional Calendar settings:

```env
GOOGLE_CALENDAR_TOKEN_PATH=data/google_calendar_token.json
GOOGLE_CALENDAR_IDS=primary
GOOGLE_CALENDAR_SYNC_DAYS_BACK=14
GOOGLE_CALENDAR_SYNC_DAYS_FORWARD=30
```

Then use:

```bash
pip install -e ".[google]"
speedwagon calendar status
speedwagon calendar sync
speedwagon calendar upcoming
speedwagon calendar create --title "Pilot planning" --start "2026-06-08T10:00:00-07:00" --end "2026-06-08T10:30:00-07:00" --attendee alex@example.com --confirm-write
speedwagon ask "what is on my calendar today"
speedwagon ask "prep for my next meeting"
speedwagon ask "create a calendar event for June 10th at 10am to wish a happy birthday to Raj"
```

Calendar uses the same Google OAuth client credentials as Gmail, but stores its own token at `data/google_calendar_token.json` so Calendar and Gmail do not fight over scopes. If your token was created when Calendar was read-only, creating an event may require deleting `data/google_calendar_token.json` or re-authorizing so Google grants `https://www.googleapis.com/auth/calendar.events`.

Assistant-created Calendar events are confirmation-first. The assistant creates a pending action; the Google Calendar write only happens after you confirm it.

## Cost Controls

SpeedwagonAI routes routine extraction, relationship inference, email drafting, command parsing, screenshot analysis, web search, and deeper synthesis through operation-specific model choices. Relationship inference uses the cheap model tier by default and runs best-effort after meeting extraction. Optional environment overrides:

```env
SPEEDWAGON_MODEL_CHEAP=gpt-4.1-mini
SPEEDWAGON_MODEL_STRONG=gpt-4.1
SPEEDWAGON_MODEL_COMMAND=gpt-4.1-mini
SPEEDWAGON_MODEL_VISION=gpt-4.1
SPEEDWAGON_MODEL_WEB=gpt-4.1
SPEEDWAGON_ENABLE_WEB_SEARCH=false
```

Web search only triggers for explicit requests like `search the web for ...` or `latest ...`. It is disabled unless `SPEEDWAGON_ENABLE_WEB_SEARCH=true`, and V12 still treats web search as a gated summary path rather than an action-taking agent.

Daily intelligence is also explicit: `speedwagon intelligence refresh` or the native “Refresh Intelligence” button updates the cached synthesis and top suggestion narratives. Opening the daily brief reads cached data and does not trigger a model call.

The deployable Mac app direction should store user API keys in macOS Keychain; `.env` remains the local developer setup.
