# SpeedwagonAI Native Mac Core

This is the V12 developer native Mac core. It makes the SwiftUI app an assistant-first Mac surface, but it still uses the Python backend as the source of truth.

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
- Assistant-first dashboard with backend status, voice input, result panel, tasks, daily brief, commitments, and capture
- Brain + Cost panel for command, vision, and web-search model status
- Capture panel for meeting recording, voice-task recording, stop, and stop plus process
- Spotlight-like assistant palette from the menu bar or `Cmd+K` while the app is focused
- Local voice-to-assistant input using the configured Whisper transcription path
- Full-screen screenshot capture and explicit screenshot analysis through the backend
- Pending action review with visually distinct Confirm and Cancel controls
- Task inbox grouped by Overdue, Today, Upcoming, Unscheduled, and Done
- Complete and reopen task actions
- Richer assistant result rendering for capabilities, tasks, meetings, drafts, markdown/context, and processed meeting output
- Clear disconnected state with the exact backend command: `speedwagon app`

## Current Limits

V12 does not package, sign, notarize, or distribute the app. It does not launch the Python backend automatically, register a global system-wide hotkey, capture selected regions/windows, use ScreenCaptureKit as the active recorder, show notifications, or integrate Apple Reminders yet.

Screenshots are captured only when you press the Screenshot button. macOS may require Screen Recording permission for the terminal/Xcode-launched app. Screenshot suggestions become pending actions and never create tasks automatically.

The local web app remains available and still has the richer meeting/email workflows.

## Tests

```bash
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer swift test
```

The tests cover API JSON decoding and task grouping logic in the `SpeedwagonAICore` library.

## Xcode Setup

If Xcode is installed but command-line tools are still active, switch to full Xcode before opening or building the app in Xcode:

```bash
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
sudo xcodebuild -license accept
xcodebuild -version
```
