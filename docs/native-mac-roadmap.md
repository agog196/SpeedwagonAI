# Native Mac Roadmap

SpeedwagonAI is currently a local Python engine with a browser UI and HTTP API. That is intentional: the API can become the boundary a future SwiftUI app calls instead of rewriting the whole product at once.

## Direction

- Keep the local SQLite database and Python meeting pipeline as the source of truth for now.
- Build a SwiftUI shell later for a more native recording/review/assistant experience.
- Use the current local HTTP API as the first bridge between SwiftUI and the Python engine.
- Move pieces into native macOS code only when they clearly benefit from native permissions or OS integration.

## Native Features To Explore

- Menu bar or compact command UI for quick capture, context lookup, and follow-up drafting.
- macOS notifications for due or overdue commitments.
- Apple Reminders integration for confirmed commitments.
- A SwiftUI task inbox backed by the local `/api/tasks` endpoints.
- ScreenCaptureKit-based meeting/system audio capture as a cleaner long-term alternative to virtual routing.
- Apple Mail / Outlook / Gmail provider adapters.
- Google Drive / Docs editing through explicit user-approved integrations.

## Capture Direction

Current capture modes:

- `mic`: records the default/selected microphone.
- `blackhole`: records routed system audio through a configured virtual audio device.

BlackHole is useful today, but it is not the ideal forever answer. A native Mac app should investigate ScreenCaptureKit because it is Apple's framework for capturing screen and audio streams with macOS permissions.

## Xcode Notes

Xcode may be installed while the active developer directory still points to Command Line Tools. Before native app work, verify:

```bash
xcodebuild -version
xcode-select -p
```

If `xcodebuild` says the active developer directory is Command Line Tools, switch to the full Xcode app:

```bash
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
sudo xcodebuild -license accept
```

Do this only when you are ready to start native Mac development.

## Local API Boundary

The local web UI and future SwiftUI app should share the same assistant/task API. See [Local API Reference](local-api.md).

The `/api/assistant/command` endpoint is the intended first boundary for a future SwiftUI command bar or menu-bar assistant.
