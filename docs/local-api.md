# Local API Reference

SpeedwagonAI's local web app and future native clients use the same HTTP API.

Start the server:

```bash
speedwagon app
```

Default base URL:

```text
http://127.0.0.1:8765
```

## Settings

- `GET /api/settings`

Returns local paths, credential presence, recorder status, and model routing status. API keys are never returned.

Useful model fields:

- `command_model`
- `vision_model`
- `web_model`
- `model_cost_labels`
- `web_search_enabled`

## Meetings

- `GET /api/meetings`
- `GET /api/meetings/{id}`
- `POST /api/meetings/{id}/process`

## Tasks

- `GET /api/tasks`
- `GET /api/tasks?status=&include_done=true`
- `GET /api/tasks/overdue`
- `POST /api/tasks`
- `POST /api/tasks/{id}/complete`
- `POST /api/tasks/{id}/reopen`

Create task body:

```json
{
  "text": "Send follow-up notes",
  "owner": "Anish",
  "owed_to": "Alex",
  "project": "Onboarding",
  "due_date": "2026-06-01"
}
```

## Commitments

- `GET /api/commitments`
- `GET /api/commitments?person=Alex`
- `GET /api/commitments?project=Onboarding`
- `POST /api/commitments/{id}/confirm`
- `POST /api/commitments/{id}/snooze`
- `POST /api/commitments/{id}/cancel`
- `GET /api/daily-brief`

Commitment/task statuses:

- `open`
- `waiting`
- `snoozed`
- `uncertain`
- `done`
- `canceled`

Snooze body:

```json
{
  "until": "2026-06-05"
}
```

## Capture

- `GET /api/capture/status`
- `GET /api/capture/diagnostics`
- `POST /api/capture/local/start`
- `POST /api/capture/local/stop`
- `POST /api/capture/native/prepare`
- `POST /api/capture/native/complete`
- `POST /api/capture/native/fail`
- `GET /api/capture/bot/status`
- `POST /api/capture/bot/join`
- `GET /api/capture/bot/sessions`
- `GET /api/capture/bot/sessions/{id}`
- `POST /api/capture/bot/sessions/{id}/sync`
- `POST /api/capture/bot/sessions/{id}/process`

Start local capture:

```json
{
  "kind": "meeting",
  "title": "Weekly planning",
  "metadata": {}
}
```

Supported local capture kinds:

- `meeting`
- `task_note`

Stop local capture:

```json
{
  "process": true,
  "task_metadata": {
    "owner": "Anish",
    "due_date": "2026-06-05",
    "project": "Launch"
  }
}
```

Meeting capture can stop raw or stop and process. Task-note capture always transcribes the voice note and creates a task.

Native meeting capture is owned by the Swift app in V14. The backend creates the meeting row and reserves file paths, then the Swift app records and mixes the final WAV.

Prepare native capture:

```json
{
  "kind": "meeting",
  "title": "Weekly planning",
  "mode": "system_mic"
}
```

Prepare response:

```json
{
  "session": {
    "active": true,
    "native": true,
    "session_id": "native-meeting-8",
    "kind": "meeting",
    "mode": "system_mic",
    "meeting_id": 8,
    "audio_path": "/path/to/audio/meeting-8.wav",
    "system_audio_path": "/path/to/audio/meeting-8-system.wav",
    "microphone_audio_path": "/path/to/audio/meeting-8-mic.wav",
    "capture_profile": "native_screencapturekit"
  }
}
```

Complete native capture:

```json
{
  "session_id": "native-meeting-8",
  "audio_path": "/path/to/audio/meeting-8.wav",
  "process": true,
  "warnings": []
}
```

Failure handoff:

```json
{
  "session_id": "native-meeting-8",
  "error": "Screen Recording permission is required."
}
```

`GET /api/capture/status` returns the active native session when one is recording. `GET /api/capture/diagnostics` includes `native_capture` for the last native status.

Meeting bot capture is an optional V15 beta. Local capture remains the default and cheapest path. Bot capture uses a managed provider when configured, joins visibly, and requires explicit consent/disclosure confirmation.

Status:

```json
{
  "enabled": true,
  "provider": "recall",
  "status": "configured",
  "cloud_cost_label": "higher",
  "requires_consent": true
}
```

Join bot:

```json
{
  "meeting_url": "https://meet.google.com/abc-defg-hij",
  "title": "Weekly planning",
  "join_at": null,
  "bot_name": "SpeedwagonAI Notetaker",
  "consent_confirmed": true
}
```

Sync pulls provider status/transcript into local files. For Recall, Speedwagon retrieves the bot, finds the recording transcript artifact/download URL, and only writes `transcripts/bot-<session-id>.txt` once transcript text is available. If a recording is done but no transcript artifact exists yet, Speedwagon calls Recall's async transcript creation endpoint for that recording and returns a transcript-requested/waiting state; sync again after Recall finishes. Bot status/session endpoints run a light auto-sync with a short cooldown, so UI refreshes can request or import transcripts for pending sessions without a separate manual sync click. Process runs the imported transcript through the existing extraction, markdown, task, context graph, and suggestion pipeline without Whisper.

## Context Graph And Suggestions

- `GET /api/context-graph?query=...`
- `GET /api/suggestions`
- `POST /api/suggestions/{id}/confirm`
- `POST /api/suggestions/{id}/dismiss`
- `POST /api/suggestions/{id}/snooze`

The graph layer is local SQLite-backed and deterministic in V13. Tasks, meetings, screenshots, and future integration sources can link to contexts such as projects, people, and topics.

Context graph response:

```json
{
  "query": "DairyMGT",
  "contexts": [{ "id": 4, "name": "DairyMGT", "kind": "project" }],
  "tasks": [{ "id": 9, "text": "Email Megan about DairyMGT updates" }],
  "meetings": [],
  "suggestions": []
}
```

Suggestion response:

```json
{
  "suggestions": [
    {
      "id": 6,
      "title": "Draft follow-up for DairyMGT",
      "reason": "All other open work linked to DairyMGT appears resolved.",
      "status": "open",
      "confidence": 0.82,
      "context": { "id": 4, "name": "DairyMGT", "kind": "project" },
      "proposed_action": "draft_email_from_context",
      "payload": { "context_id": 4, "task_id": 9 },
      "task_ids": [8, 9],
      "meeting_ids": []
    }
  ]
}
```

Suggestions remain the action-review surface. V17 adds local notification candidates for native delivery.

## Native Notifications

V17 turns open follow-through suggestions into local notification candidates. The Python backend owns candidate/audit state; the native Mac app owns macOS permission and delivery.

- `GET /api/notifications/status`
- `GET /api/notifications/candidates`
- `POST /api/notifications/{id}/mark-delivered`
- `POST /api/notifications/{id}/dismiss`
- `POST /api/notifications/{id}/snooze`

Notification candidates are suggestion objects with lifecycle fields:

```json
{
  "id": 12,
  "title": "Review overdue task #4",
  "source_fingerprint": "search_tasks|context:|tasks:4|meetings:|payload:{...}",
  "next_notify_at": "2026-06-04",
  "last_notified_at": null,
  "notification_reason": "This work is overdue and needs a decision.",
  "notification_status": "candidate"
}
```

Snooze body:

```json
{
  "until": "2026-06-09"
}
```

Notifications are local-only in V17 and require the native app to be running. Delivery never executes the proposed action; it only opens SpeedwagonAI for review. Apple Reminders, Calendar writes, background daemon delivery, and packaged launch-at-login behavior remain later work.

## Integrations

- `GET /api/integrations/google/status`
- `GET /api/integrations/apple/reminders`
- `POST /api/integrations/apple/reminders`

Apple Reminders writes are planned for the native Mac app and require explicit user approval.

## Google Calendar

Calendar sync is read-only in V16. It reuses the existing Google installed-app OAuth client credentials, keeps a dedicated Calendar token by default, and caches a limited local window for daily brief and meeting-prep context.

Install the optional Google client libraries before using real OAuth sync:

```bash
pip install -e ".[google]"
```

- `GET /api/calendar/status`
- `POST /api/calendar/sync`
- `GET /api/calendar/events?from=YYYY-MM-DD&to=YYYY-MM-DD`
- `GET /api/calendar/upcoming?limit=10`

Status response:

```json
{
  "enabled": true,
  "status": "configured",
  "credentials_present": true,
  "token_present": true,
  "calendar_scope_present": true,
  "calendar_ids": ["primary"],
  "sync_days_back": 14,
  "sync_days_forward": 30,
  "note": "Google Calendar read-only sync is configured."
}
```

Sync response:

```json
{
  "synced_count": 4,
  "events": [],
  "calendar_ids": ["primary"],
  "time_min": "2026-05-21T00:00:00Z",
  "time_max": "2026-07-04T00:00:00Z"
}
```

Upcoming response:

```json
{
  "events": [
    {
      "id": 3,
      "title": "Weekly planning",
      "start_at": "2026-06-05T10:00:00-07:00",
      "end_at": "2026-06-05T10:30:00-07:00",
      "meeting_url": "https://meet.google.com/abc-defg-hij",
      "attendees": [{ "email": "alex@example.com", "displayName": "Alex" }]
    }
  ]
}
```

`GET /api/daily-brief` also includes:

- `calendar_today`
- `calendar_upcoming`
- `meeting_prep`

Meeting prep matches synced event title, description snippet, attendees, and meeting URL against local contexts, meetings, tasks, and suggestions. It does not create tasks, write Calendar events, or schedule bots.

If the configured Calendar token lacks `https://www.googleapis.com/auth/calendar.readonly`, status returns `reauth_required`. Delete or refresh `GOOGLE_CALENDAR_TOKEN_PATH`, then run Calendar sync to authorize the new read-only scope.

## Assistant Actions

`GET /api/assistant/capabilities`

Returns the deterministic local actions the assistant can currently perform.

`POST /api/assistant/command`

```json
{
  "command": "show overdue tasks"
}
```

The command endpoint is the one-line native Mac command-bar boundary. Rules are tried first. If no rule matches and `OPENAI_API_KEY` is configured, SpeedwagonAI uses an LLM fallback parser that can only choose from the existing deterministic action registry.

Command responses include:

```json
{
  "supported": true,
  "action": "daily_brief",
  "category": "brief",
  "requires_confirmation": false,
  "confidence": null,
  "pending_action_id": null,
  "summary": "Daily brief: 1 overdue, 0 due today, 0 waiting, 0 uncertain.",
  "result": {}
}
```

Mutating actions interpreted by the LLM fallback return `requires_confirmation: true` and a `pending_action_id`. They do not run until confirmed.

`GET /api/assistant/actions`

Returns pending assistant actions by default:

```json
{
  "actions": [
    {
      "id": 14,
      "action": "add_task",
      "category": "tasks",
      "payload": { "text": "Send recap" },
      "confidence": 0.82,
      "status": "pending"
    }
  ]
}
```

`POST /api/assistant/actions/{id}/confirm`

Runs a pending action and marks it confirmed.

`POST /api/assistant/actions/{id}/cancel`

Marks a pending action canceled without running it.

`POST /api/assistant/screenshot/analyze`

```json
{
  "image_base64": "iVBORw0KGgo...",
  "instruction": "Find follow-up tasks"
}
```

Analyzes a user-approved full-screen screenshot with a vision-capable model. Suggested tasks/actions are returned as pending actions; nothing is created automatically.

```json
{
  "summary": "A checklist is visible.",
  "visible_text": ["Send recap"],
  "suggested_tasks": [{ "text": "Send recap", "confidence": 0.7 }],
  "suggested_context_topics": ["checklist"],
  "pending_actions": [{ "id": 21, "action": "add_task", "status": "pending" }],
  "confidence": 0.7
}
```

`POST /api/actions`

```json
{
  "action": "list_overdue_tasks",
  "payload": {}
}
```

Supported deterministic actions:

- `list_capabilities`
- `system_status`
- `list_overdue_tasks`
- `list_today_tasks`
- `list_open_tasks`
- `list_unscheduled_tasks`
- `list_waiting_tasks`
- `search_tasks`
- `list_commitments_for_person`
- `daily_brief`
- `list_suggestions`
- `confirm_suggestion`
- `dismiss_suggestion`
- `snooze_suggestion`
- `list_unprocessed_meetings`
- `process_meeting`
- `process_latest_meeting`
- `start_meeting_recording`
- `finish_meeting_recording`
- `stop_meeting_recording`
- `add_task`
- `complete_task`
- `reopen_task`
- `snooze_task`
- `cancel_task`
- `mark_task_waiting`
- `mark_task_uncertain`
- `draft_meeting_followup`
- `draft_followup`
- `draft_email_from_context`
- `calendar_status`
- `sync_calendar`
- `list_calendar_events`
- `list_upcoming_calendar_events`
- `prep_next_meeting`
- `search_context`
- `search_context_graph`
- `web_search`

## Assistant Voice

- `GET /api/assistant/voice/status`
- `POST /api/assistant/voice/start`
- `POST /api/assistant/voice/stop`

Voice input records a local audio note, transcribes it with the configured local Whisper path, and sends the transcript through the same deterministic assistant command endpoint. The stop response includes:

```json
{
  "transcript": "what is overdue",
  "assistant_response": {
    "supported": true,
    "summary": "No overdue tasks."
  },
  "audio_path": "audio/assistant-voice-...",
  "transcript_path": "transcripts/assistant-voice-..."
}
```

## Email

- `POST /api/meetings/{id}/email/preview`
- `POST /api/meetings/{id}/email/draft`

Draft creation accepts an edited `body`. When provided, SpeedwagonAI uses that body directly instead of regenerating.
