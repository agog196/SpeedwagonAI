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

Returns local paths, credential presence, recorder status, and V12 model routing status. API keys are never returned.

Useful V12 fields:

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
- `GET /api/capture/bot/status`
- `POST /api/capture/bot/join`

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

Bot join currently fails gracefully until a managed provider is configured.

## Integrations

- `GET /api/integrations/google/status`
- `GET /api/integrations/apple/reminders`
- `POST /api/integrations/apple/reminders`

Apple Reminders writes are planned for the native Mac app and require explicit user approval.

## Assistant Actions

`GET /api/assistant/capabilities`

Returns the deterministic local actions the assistant can currently perform.

`POST /api/assistant/command`

```json
{
  "command": "show overdue tasks"
}
```

The command endpoint is the one-line native Mac command-bar boundary. Rules are tried first. If no rule matches and `OPENAI_API_KEY` is configured, V12 uses an LLM fallback parser that can only choose from the existing deterministic action registry.

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
- `list_waiting_tasks`
- `list_commitments_for_person`
- `daily_brief`
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
- `search_context`
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
