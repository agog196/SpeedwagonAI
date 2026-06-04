# SpeedwagonAI Native Mac Core

This is the V17 developer native Mac core. It makes the SwiftUI app an assistant-first Mac surface, adds native meeting capture, managed meeting-bot beta controls, read-only Google Calendar context, local notifications, and still uses the Python backend as the source of truth.

Start the backend from the repo root:

```bash
speedwagon app
```

Then run the native app from this directory:

```bash
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer swift run SpeedwagonAI
```

The app talks to:

```text
http://127.0.0.1:8765
```

## What It Includes

- Menu bar icon with backend status, refresh, main window, assistant palette, and quit
- Global `Option+Space` assistant palette backed by a floating `NSPanel`
- Assistant-first dashboard with backend status, voice input, result panel, tasks, daily brief, commitments, and capture
- Expanded assistant palette with native meeting capture controls and capture commands
- Follow-through suggestions panel with Confirm, Snooze, and Dismiss controls
- Context chips on graph-linked tasks and suggestions
- Brain + Cost panel for command, vision, and web-search model status
- Capture panel with `Native system + mic` meeting recording, `Mic fallback`, voice-task recording, stop, and stop plus process
- Meeting Bot Beta panel for configured provider status, paste-link join, consent confirmation, manual sync, and processing
- Calendar panel for read-only Google Calendar status, sync, upcoming events, and meeting-prep context
- Daily Brief Calendar cards for today's meetings, upcoming meetings, and prep context
- Notifications panel for macOS permission status, local notification candidates, delivered counts, snooze, and dismiss
- Native meeting capture that writes a ScreenCaptureKit system-audio WAV plus an AVFoundation microphone WAV, mixes the final WAV, and hands it back to Python for processing
- Spotlight-like assistant palette from the menu bar, `Cmd+K` while the app is focused, or global `Option+Space`
- Local voice-to-assistant input using the configured Whisper transcription path
- Active-display screenshot capture and explicit screenshot analysis through the backend
- Pending action review with visually distinct Confirm and Cancel controls
- Task inbox grouped by Overdue, Today, Upcoming, Unscheduled, and Done
- Complete and reopen task actions
- Richer assistant result rendering for capabilities, tasks, meetings, drafts, markdown/context, and processed meeting output
- Clear disconnected state with the exact backend command: `speedwagon app`

## Native Capture

Meeting capture defaults to `Native system + mic` in the Capture panel. The Swift app calls:

- `POST /api/capture/native/prepare`
- native ScreenCaptureKit system-audio recording plus AVFoundation microphone recording
- local WAV mixing
- `POST /api/capture/native/complete`

The final file is `audio/meeting-<id>.wav`, so the existing Whisper, extraction, notes, tasks, and graph flows consume it without a separate path.

macOS may ask for Screen Recording and Microphone permission. If microphone capture is unavailable but system audio is captured, the app saves system-only audio with a warning. If system audio fails, the app marks the native capture failed and tells you to use `Mic fallback`.

Task voice and assistant voice are still mic-only in V16, even when the meeting capture selector is set to `Native system + mic`. Use the meeting title field plus `Start Native` when you want system/headphone audio captured.

The native assistant palette also handles capture commands directly:

```text
start meeting recording called weekly planning
start native meeting called weekly planning
finish meeting
stop meeting without processing
```

These use the selected native capture mode in the Swift app instead of the backend-only mic recorder.

## Google Calendar

The Calendar tab calls:

- `GET /api/calendar/status`
- `POST /api/calendar/sync`
- `GET /api/calendar/upcoming`

Calendar is read-only in V16. It syncs the configured rolling window into local SQLite, enriches the Daily Brief, and shows prep cards by matching upcoming event details against local meetings, tasks, contexts, and suggestions.

Configure from the repo root:

```env
GOOGLE_CALENDAR_IDS=primary
GOOGLE_CALENDAR_SYNC_DAYS_BACK=14
GOOGLE_CALENDAR_SYNC_DAYS_FORWARD=30
```

The integration reuses the existing Google OAuth credential and token paths. If the token was created before Calendar support, the app may show `reauth_required`; refresh or delete the token and run `speedwagon calendar sync` to authorize the readonly Calendar scope.

## Notifications

The Notifications tab requests macOS notification permission and schedules local notifications from backend suggestion candidates while the app is running. Candidates come from source-linked follow-through suggestions: overdue, due-today, stale, waiting/uncertain, unscheduled, and follow-up-ready work.

Clicking a notification opens SpeedwagonAI and refreshes local state. Notifications never confirm, dismiss, send, or complete anything automatically.

V17 does not run a background daemon after quit, does not launch at login, and does not write Apple Reminders.

## Meeting Bot Beta

The Capture screen includes a Meeting Bot Beta panel. It calls:

- `GET /api/capture/bot/status`
- `GET /api/capture/bot/sessions`
- `POST /api/capture/bot/join`
- `POST /api/capture/bot/sessions/{id}/sync`
- `POST /api/capture/bot/sessions/{id}/process`

Use `SPEEDWAGON_BOT_PROVIDER=fake` for local testing, or configure `SPEEDWAGON_BOT_PROVIDER=recall` plus `RECALL_API_KEY` for real provider testing. Bot capture is optional, provider-backed, visible to meeting participants, and requires explicit disclosure/consent confirmation.

## Current Limits

V17 does not package, sign, notarize, or distribute the app. It does not launch the Python backend automatically, capture selected regions/windows, integrate Apple Reminders, write Calendar events, schedule bots from Calendar, or use provider webhooks yet.

Screenshots are captured only when you press the Screenshot button. The palette hides briefly and captures the active display based on the current mouse screen. macOS may require Screen Recording permission for the terminal/Xcode-launched app. Screenshot suggestions become pending actions and never create tasks automatically.

The global hotkey is developer-only and may conflict with another app if that app already owns `Option+Space`.

The local web app remains available and still has the richer meeting/email workflows. CLI and web recording continue to use the Python recorder path.

## Tests

```bash
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer swift test
```

The tests cover API JSON decoding, task grouping logic, and native WAV mixer behavior in the `SpeedwagonAICore` library.

## Xcode Setup

If Xcode is installed but command-line tools are still active, switch to full Xcode before opening or building the app in Xcode:

```bash
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
sudo xcodebuild -license accept
xcodebuild -version
```
