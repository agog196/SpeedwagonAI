# SpeedwagonAI Local Beta Privacy Policy

Last updated: 2026-06-05

SpeedwagonAI is a local-first Mac beta. The app is designed for solo local use, with your SQLite database, notes, transcripts, audio, logs, drafts, and exports stored on your machine by default.

## What Stays Local

Speedwagon-owned local data includes:

- the SQLite database under `data/`;
- generated notes under `notes/`;
- audio captures under `audio/`;
- transcripts under `transcripts/`;
- local logs under `data/logs/`;
- local follow-up drafts and settings state.

SpeedwagonAI does not run a hosted Speedwagon cloud service for this local beta.

## When Data Leaves Your Device

Data leaves your device only when you configure and use an external service:

- OpenAI: used for meeting extraction, relationship inference, assistant fallback, screenshot analysis, email draft generation, and explicit daily intelligence refresh.
- Google APIs: used for Gmail OAuth draft creation, Calendar sync, and explicit Calendar event creation when configured.
- Recall.ai: used only when you explicitly send a meeting bot to a meeting and confirm consent.
- Future web search: disabled unless explicitly enabled and requested.

SpeedwagonAI does not automatically send Gmail messages. Gmail support creates drafts only.

## Secrets

The local beta stores core app secrets, such as the OpenAI API key and local API token, in macOS Keychain when entered through the native app. Some Google and Recall setup still uses existing OAuth/token or environment flows.

SpeedwagonAI should not display API keys in the UI, API responses, or logs. Local logs redact known tokens and meeting URL query strings where possible.

## Export And Wipe

You can export local Speedwagon data with:

```bash
speedwagon export --output data/exports/speedwagon-export.zip
```

You can wipe Speedwagon-owned local data with:

```bash
speedwagon wipe --confirm DELETE-SPEEDWAGON-DATA
```

Export and wipe are explicit user actions. Wipe targets configured Speedwagon-owned data paths, not arbitrary files in your repo.

## Beta Notes

This is an early local beta privacy policy, not a production legal document. Before broader distribution, the policy should be reviewed and tightened for the final packaging, signing, and support model.
