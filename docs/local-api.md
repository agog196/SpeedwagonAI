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
  "due_date": "2026-06-01"
}
```

## Assistant Actions

`POST /api/assistant/command`

```json
{
  "command": "show overdue tasks"
}
```

The command endpoint is the future one-line native Mac command-bar boundary. V5 uses deterministic rules only. Unsupported commands return `supported: false`.

`POST /api/actions`

```json
{
  "action": "list_overdue_tasks",
  "payload": {}
}
```

Supported deterministic actions:

- `list_overdue_tasks`
- `list_today_tasks`
- `list_open_tasks`
- `add_task`
- `complete_task`
- `reopen_task`
- `draft_followup`
- `search_context`

## Email

- `POST /api/meetings/{id}/email/preview`
- `POST /api/meetings/{id}/email/draft`

Draft creation accepts an edited `body`. When provided, SpeedwagonAI uses that body directly instead of regenerating.
