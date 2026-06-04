# ScreenCaptureKit Spike

SpeedwagonAI V14 adds the first developer ScreenCaptureKit recorder for native meeting audio. The existing Python recorder stack remains the CLI/web path and the native mic fallback.

## Why This Matters

Mic capture is cheap and simple, but it only records the microphone. BlackHole can route system audio today, but it requires user setup and can be confusing. ScreenCaptureKit is Apple's native framework for screen and audio capture with macOS permission prompts.

## Feasibility Questions

- Can the native app capture system audio without recording video frames?
- Which macOS versions support the audio-only flow we need?
- What permission prompts appear for microphone, screen recording, and system audio?
- Can capture output be streamed or written directly to WAV/PCM files that whisper.cpp can consume?
- How should Python receive capture output: file path, local socket, or native-owned recording with backend import?

## V14 Architecture

- SwiftUI app owns ScreenCaptureKit permissions and native capture sessions.
- Python backend remains the processing/storage layer.
- Native app writes system and microphone temp WAV files into SpeedwagonAI's configured audio directory.
- Native app mixes available tracks into `meeting-<id>.wav`.
- Native app calls the local native handoff API to create/update meetings and process captured files.
- BlackHole/custom recorder remains a fallback for users who prefer routed audio.

## V14 Boundary

V14 ships ScreenCaptureKit as the default native meeting recorder in the developer Swift app. It does not yet package the app, start the backend automatically, capture selected windows/regions, or replace CLI/web recording.
