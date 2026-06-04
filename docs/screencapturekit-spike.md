# ScreenCaptureKit Spike

SpeedwagonAI V10 keeps the existing Python recorder stack as the production path. ScreenCaptureKit is the likely long-term native path for system audio and optional screen capture in the Mac app.

## Why This Matters

Mic capture is cheap and simple, but it only records the microphone. BlackHole can route system audio today, but it requires user setup and can be confusing. ScreenCaptureKit is Apple's native framework for screen and audio capture with macOS permission prompts.

## Feasibility Questions

- Can the native app capture system audio without recording video frames?
- Which macOS versions support the audio-only flow we need?
- What permission prompts appear for microphone, screen recording, and system audio?
- Can capture output be streamed or written directly to WAV/PCM files that whisper.cpp can consume?
- How should Python receive capture output: file path, local socket, or native-owned recording with backend import?

## Expected Architecture

- SwiftUI app owns ScreenCaptureKit permissions and native capture sessions.
- Python backend remains the processing/storage layer.
- Native app writes local audio files into SpeedwagonAI's configured audio directory.
- Native app calls the existing local API to create/update meetings and process captured files.
- BlackHole/custom recorder remains a fallback for users who prefer routed audio.

## V10 Boundary

V10 does not ship ScreenCaptureKit as the active recorder. It only clarifies the path and keeps the capture API shaped so a native recorder can replace the Python subprocess later.
