# SpeedwagonAI Native Local Beta

This is the V26 local beta native Mac app. It is a SwiftUI shell around the local Python backend with assistant, capture, task, suggestion, context review, notification, privacy, export, and wipe surfaces.

Start the backend from the repo root:

```bash
speedwagon app
```

Then run the native app from this directory:

```bash
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer swift run SpeedwagonAI
```

Build the unsigned local beta `.app` bundle:

```bash
./scripts/build-local-app.sh
SPEEDWAGON_REPO_ROOT="$(cd ../.. && pwd)" open dist/SpeedwagonAI.app
```

This creates an unsigned local testing app. The signed private-beta flow below signs/notarizes and packages a DMG, but it still does not bundle Python, install an updater, or install a background daemon. Python 3.11 and this repo checkout must remain present.

The app talks to:

```text
http://127.0.0.1:8765
```

V18 local API calls require a bearer token. The Python backend creates `data/local_api_token` by default; the Swift client reads `SPEEDWAGON_API_TOKEN`, `SPEEDWAGON_API_TOKEN_PATH`, or a nearby `data/local_api_token` file and sends it as `Authorization: Bearer <token>`.

V26 local beta mode stores the OpenAI API key and local API token in macOS Keychain when configured through Settings. macOS may ask for the `login` Keychain password; that is the tester's Mac login password and lets SpeedwagonAI read or save its own `SpeedwagonAI.LocalBeta` items. Google and Recall configuration remain in the existing `.env`/OAuth-token flows.

## What It Includes

- Menu bar icon with backend status, refresh, main window, assistant palette, and quit
- Global `Option+Space` assistant palette backed by a floating `NSPanel`
- Assistant-first dashboard with backend status, voice input, result panel, tasks, daily brief, commitments, and capture
- Expanded assistant palette with native meeting capture controls and capture commands
- Follow-through suggestions panel with Confirm, Snooze, and Dismiss controls
- Editable local follow-up drafts after confirming email/follow-up suggestions, with explicit Gmail draft creation
- Local beta Settings view for backend lifecycle, core Keychain secrets, logs, export, and wipe
- First-run readiness diagnostics for repo root, Python 3.11, backend command, Keychain token/key presence, bundle mode, and notification status
- Native-managed backend launch using `python3.11 -m speedwagon_ai.cli app --host 127.0.0.1 --port 8765`
- Context chips on graph-linked tasks and suggestions
- Brain + Cost panel for command, vision, and web-search model status
- Capture panel with `Native system + mic` meeting recording, `Mic fallback`, voice-task recording, stop, and stop plus process
- Meeting Bot Beta panel for configured provider status, paste-link join, consent confirmation, manual sync, and processing
- Calendar panel for Google Calendar status, sync, explicit event creation, upcoming events, and meeting-prep context
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

## Local Beta Privacy Docs

- [Local beta privacy policy](../../docs/privacy-policy-local-beta.md)
- [Local beta terms](../../docs/terms-local-beta.md)

The local beta is local-first. External services are optional and explicit: OpenAI for LLM-backed features, Google for OAuth draft/Calendar flows, Recall.ai for consent-confirmed bot sessions, and future web search only when explicitly enabled.

## V25 Local App Verification Checklist

1. Build the unsigned app:
   ```bash
   ./scripts/build-local-app.sh
   ```
2. Quit any manually started backend.
3. Launch the app:
   ```bash
   SPEEDWAGON_REPO_ROOT="$(cd ../.. && pwd)" open dist/SpeedwagonAI.app
   ```
4. Verify the native app starts the Python backend and shows Connected.
5. Save an OpenAI API key in Settings and verify the local API token path remains Keychain-managed.
6. Open Settings, read the Keychain explanation, run Check Readiness, and verify Copy Diagnostics redacts secrets.
7. Export local data and inspect the zip manifest.
8. Test wipe against a temp data root before using it on real local beta data.
9. Open Notifications, request permission in bundled mode, and verify Review opens the related suggestion without running an action.
10. Quit the app and verify only the app-managed backend process is stopped.

## V26 Signed Private Beta Packaging

The signed pipeline is opt-in and uses environment variables. The unsigned `build-local-app.sh` script remains the local developer path.

Required for signing:

```bash
export SPEEDWAGON_SIGN_IDENTITY="Developer ID Application: Your Name (TEAMID1234)"
export SPEEDWAGON_TEAM_ID="TEAMID1234"
```

For notarization, use a notarytool keychain profile:

```bash
xcrun notarytool store-credentials speedwagon-notary --apple-id you@example.com --team-id TEAMID1234 --password app-specific-password
export SPEEDWAGON_NOTARY_PROFILE="speedwagon-notary"
```

Or provide Apple notary credentials directly:

```bash
export SPEEDWAGON_NOTARY_APPLE_ID="you@example.com"
export SPEEDWAGON_NOTARY_PASSWORD="app-specific-password"
```

Build, sign, notarize, staple, and package:

```bash
./scripts/build-signed-app.sh
./scripts/notarize-app.sh
./scripts/build-beta-dmg.sh
```

Outputs:

- signed app: `dist/SpeedwagonAI-signed.app`
- DMG: `dist/SpeedwagonAI-0.26.0-beta.dmg`

The scripts fail fast with setup instructions if signing/notary environment variables are missing. Candidate entitlement areas to audit before future production packaging include microphone, screen capture, outgoing network access to localhost/provider APIs, user-selected file access for export, and notification permission behavior.

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
- `POST /api/calendar/events`
- `GET /api/calendar/upcoming`

Calendar sync caches the configured rolling window into local SQLite, enriches the Daily Brief, and shows prep cards by matching upcoming event details against local meetings, tasks, contexts, and suggestions. Event creation is explicit from the Calendar tab or CLI; the app does not edit/delete events, schedule bots from Calendar, or write reminders.

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

The current local beta does not run a background daemon after quit, does not launch at login, and does not write Apple Reminders.

## Meeting Bot Beta

The Capture screen includes a Meeting Bot Beta panel. It calls:

- `GET /api/capture/bot/status`
- `GET /api/capture/bot/sessions`
- `POST /api/capture/bot/join`
- `POST /api/capture/bot/sessions/{id}/sync`
- `POST /api/capture/bot/sessions/{id}/process`

Use `SPEEDWAGON_BOT_PROVIDER=fake` for local testing, or configure `SPEEDWAGON_BOT_PROVIDER=recall` plus `RECALL_API_KEY` for real provider testing. Bot capture is optional, provider-backed, visible to meeting participants, and requires explicit disclosure/consent confirmation.

## Current Limits

V26 keeps the local unsigned `.app` for developer testing and adds opt-in signed/notarized private-beta DMG packaging. It still does not bundle Python, install an updater, install a Launch Agent, capture selected regions/windows, integrate Apple Reminders, write Calendar events, schedule bots from Calendar, or use provider webhooks yet.

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
