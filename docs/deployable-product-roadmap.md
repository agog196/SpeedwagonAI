# Deployable Product Roadmap

SpeedwagonAI's product wedge is local-first follow-through: capture work context, remember commitments, and nudge the user before things slip.

## Product Shape

- First users: solo Mac users.
- Billing model: users bring their own LLM API key first.
- Storage model: local SQLite first; no Supabase or external database for the first solo-user deployable.
- Default capture: local Mac audio capture.
- Optional capture: managed meeting bot beta for Zoom/Meet/Teams when speaker/platform metadata matters.
- Core promise: never lose the thread again.

## Implemented Foundation

- Unified task/commitment layer with owner, owed-to, project, source, due date, confidence, and status.
- Commitment statuses: `open`, `waiting`, `snoozed`, `uncertain`, `done`, `canceled`.
- Daily brief for overdue, today, waiting, uncertain, stale, and recommended follow-up work.
- Local APIs for commitments, daily brief, local capture aliases, bot capture status, and integration status.
- Cost-aware model router with cheap/strong/web operation tiers.
- General assistant core with categorized deterministic actions for tasks, commitments, meetings, capture, email, context, brief, and status.

## Assistant Direction

V8 commands are intentionally deterministic and rules-based. That is the safe local action layer, not the final command experience. The deployable assistant should eventually accept flexible user requests in the native app or widget, route common commands through fast local rules, and fall back to LLM interpretation when a request is in SpeedwagonAI's scope but does not match a hard-coded phrase.

The long-term assistant shape:

- Put the assistant palette/widget at the center of the product.
- Accept text first, then voice messages, screenshots, meeting audio, and meeting bot transcripts as context.
- Parse common commands locally for speed, cost, and reliability.
- Use an LLM parser for non-hard-coded requests within SpeedwagonAI's scope.
- Map both local and LLM-parsed requests into the same deterministic action interface.
- Require confirmation before irreversible or externally visible actions.
- Return unsupported/out-of-scope clearly instead of guessing.

## Roadmap

- V8: General assistant core for broader local commands and action routing.
- V9: Make the SwiftUI app the primary UI, add menu bar icon, command palette, and backend lifecycle management.
- V10: Build practical capture UI, investigate ScreenCaptureKit, and keep BlackHole/custom routing as fallback.
- V11: Reset the native assistant UI, add resilient command handling, and add local voice-to-assistant input.
- V12: Add LLM fallback command interpretation, screenshot context, stronger model routing, optional web search mode, and user-visible cost controls.
- V13: Harden Gmail, add Google Calendar context, Apple Reminders, macOS notifications, and Google Docs/Drive export.
- V14: Add optional managed meeting bot beta for Zoom/Meet/Teams.
- V15: Package the first deployable beta with onboarding, Keychain secrets, permissions, import/export, logs, privacy policy, terms, and polished follow-through workflows.

## Capture Strategy

Local capture remains cheapest and most broadly useful because it works for meetings, calls, lectures, videos, and ad hoc audio. Meeting bots should be opt-in because they are more expensive, more visible to other attendees, and require managed infrastructure or provider APIs.

## Trust Defaults

- Draft only; never send emails automatically.
- Confirm before irreversible actions.
- Store user secrets locally.
- Be explicit when Speedwagon is uncertain.
- Fail planned integrations gracefully until configured.

## Cloud And Security Direction

The first deployed solo-user version should remain local-first with SQLite. Supabase or another hosted database may become useful later for accounts, billing, managed bot coordination, team sync, or cross-device features, but it is not needed for the first local Mac assistant.

Before deployable beta, add a security/privacy checklist covering Keychain storage, localhost API binding, permission explanations, user data export/delete, logs, consent for meeting bots, privacy policy, terms of service, and clear user-owned API key handling.
