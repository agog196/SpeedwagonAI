from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import asdict, is_dataclass
from typing import Any, Callable

from speedwagon_ai.assistant_actions import meeting_to_dict, search_calendar_events
from speedwagon_ai.config import Settings
from speedwagon_ai.email_composer import compose_context_email
from speedwagon_ai.model_router import choose_model
from speedwagon_ai.storage import Repository


ASSISTANT_PLANNER_PROMPT = """You are SpeedwagonAI's local tool planner.
Return only valid JSON.

Plan one assistant turn using read tools first. Do not propose writes until the requested entities are clear.
Available read tools: task_by_id, task_search, context_lookup, context_detail, meeting_detail, meeting_search, calendar_search, suggestions, drafts.
Available confirmed write actions: create_local_email_draft, add_task, complete_task, create_calendar_event.
All writes require confirmation.

JSON schema:
{
  "supported": boolean,
  "intent": "answer" | "draft_email" | "write" | "clarify",
  "read_tools": [{"tool": string, "payload": object}],
  "recipient": string or null,
  "topic": string or null,
  "task_id": integer or null,
  "question": string or null,
  "clarification": string or null,
  "confidence": number
}"""

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "about",
    "asking",
    "ask",
    "can",
    "could",
    "draft",
    "email",
    "files",
    "for",
    "from",
    "him",
    "her",
    "his",
    "into",
    "me",
    "note",
    "please",
    "request",
    "send",
    "that",
    "the",
    "them",
    "to",
    "with",
    "write",
    "you",
}

SELF_NAMES = {"me", "myself", "i", "you", "anish", "anish gogineni"}


def execute_tool_assisted_turn(
    settings: Settings,
    repo: Repository,
    command: str,
    *,
    suggested_commands: Callable[[str], list[str]] | None = None,
) -> dict[str, Any] | None:
    plan = local_plan(command)
    planner_source = "tool_assisted_local"
    if not plan:
        plan = llm_plan(settings, repo, command)
        planner_source = "tool_assisted_llm" if plan else planner_source
    if not plan or not plan.get("supported"):
        return None

    if plan.get("intent") == "draft_email":
        return email_draft_turn(settings, repo, command, plan, source=planner_source, suggested_commands=suggested_commands)
    if plan.get("intent") == "answer":
        return answer_turn(settings, repo, command, plan, source=planner_source, suggested_commands=suggested_commands)
    if plan.get("intent") == "clarify":
        return clarification_turn(
            command,
            str(plan.get("clarification") or "What should I use for that?"),
            evidence=[],
            confidence=float(plan.get("confidence") or 0.62),
            source=planner_source,
            suggested_commands=suggested_commands,
        )
    return None


def local_plan(command: str) -> dict[str, Any] | None:
    if not command.strip():
        return None
    if plan := local_email_plan(command):
        return plan
    if plan := local_read_plan(command):
        return plan
    return None


def local_email_plan(command: str) -> dict[str, Any] | None:
    lowered = command.lower()
    if not re.search(r"\b(email|mail|note|message|draft|write|send)\b", lowered):
        return None

    task_id = extract_task_id(command)
    recipient, topic = extract_email_recipient_topic(command)
    if task_id and not topic:
        topic = f"task #{task_id}"
    if not task_id and not recipient:
        return None

    read_tools: list[dict[str, Any]] = []
    if task_id:
        read_tools.append({"tool": "task_by_id", "payload": {"task_id": task_id}})
    if recipient:
        read_tools.append({"tool": "context_lookup", "payload": {"query": recipient, "kind": "person", "limit": 5}})
    if topic and not task_id:
        read_tools.append({"tool": "task_search", "payload": {"query": topic, "status": None, "limit": 12}})

    return {
        "supported": True,
        "intent": "draft_email",
        "recipient": recipient,
        "topic": topic,
        "task_id": task_id,
        "read_tools": read_tools,
        "confidence": 0.82 if recipient or task_id else 0.58,
    }


def local_read_plan(command: str) -> dict[str, Any] | None:
    lowered = command.lower().strip()
    calendar_match = re.fullmatch(
        r".*(?:when(?:'s| is)?|what time is|find|show).*(?:meeting|calendar event|event).*(?:with|for|about) (.+)\??",
        lowered,
    )
    if calendar_match:
        query = clean_trailing_noise(calendar_match.group(1))
        if query:
            return {
                "supported": True,
                "intent": "answer",
                "question": command,
                "topic": query,
                "read_tools": [{"tool": "calendar_search", "payload": {"query": query, "limit": 8}}],
                "confidence": 0.78,
            }

    task_match = re.fullmatch(r".*(?:what|show|tell me).*(?:task|todo|work).*(?:#|number )(\d+).*", lowered)
    if task_match:
        task_id = int(task_match.group(1))
        return {
            "supported": True,
            "intent": "answer",
            "question": command,
            "task_id": task_id,
            "read_tools": [{"tool": "task_by_id", "payload": {"task_id": task_id}}],
            "confidence": 0.76,
        }
    return None


def llm_plan(settings: Settings, repo: Repository, command: str) -> dict[str, Any] | None:
    if not settings.openai_api_key:
        return None
    try:
        raw = openai_plan(settings, command, planner_snapshot(repo))
    except Exception:
        return None
    if not isinstance(raw, dict) or not raw.get("supported"):
        return None
    intent = str(raw.get("intent") or "")
    if intent not in {"answer", "draft_email", "clarify"}:
        return None
    return {
        "supported": True,
        "intent": intent,
        "read_tools": sanitize_read_tool_calls(raw.get("read_tools")),
        "recipient": optional_str(raw.get("recipient")),
        "topic": optional_str(raw.get("topic")),
        "task_id": coerce_int(raw.get("task_id")),
        "question": optional_str(raw.get("question")) or command,
        "clarification": optional_str(raw.get("clarification")),
        "confidence": clamp_float(raw.get("confidence"), default=0.68),
    }


def openai_plan(settings: Settings, command: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    model = choose_model(settings, "command_parse")
    payload = {
        "model": model.model,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": ASSISTANT_PLANNER_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "command": command,
                        "local_snapshot_summary": snapshot,
                    },
                    indent=2,
                    sort_keys=True,
                    default=str,
                ),
            },
        ],
        "temperature": 0.1,
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI assistant planner failed: HTTP {exc.code}: {body}") from exc
    return json.loads(data["choices"][0]["message"]["content"])


def email_draft_turn(
    settings: Settings,
    repo: Repository,
    command: str,
    plan: dict[str, Any],
    *,
    source: str,
    suggested_commands: Callable[[str], list[str]] | None,
) -> dict[str, Any]:
    evidence_packet = run_read_tools(repo, plan.get("read_tools") or [])
    task_id = coerce_int(plan.get("task_id"))
    task = evidence_packet.first_task(task_id) if task_id else None
    task_missing = task_id is not None and task is None
    if task_missing:
        return clarification_turn(
            command,
            f"I couldn't find task #{task_id}.",
            evidence=evidence_packet.evidence,
            confidence=0.88,
            source=source,
            suggested_commands=suggested_commands,
        )

    recipient_label = optional_str(plan.get("recipient"))
    recipient_context = evidence_packet.best_context(recipient_label)
    if not recipient_label and task:
        recipient_label, recipient_context = infer_task_recipient(repo, task)

    if not recipient_label:
        task_label = f"task #{task_id}" if task_id else "that email"
        return clarification_turn(
            command,
            f"Who should I send the draft about {task_label} to?",
            evidence=evidence_packet.evidence,
            confidence=0.86,
            source=source,
            suggested_commands=suggested_commands,
        )

    to_address = resolve_recipient_email(recipient_label, recipient_context)
    if not to_address:
        return clarification_turn(
            command,
            f"I found {recipient_label}, but I do not have an email address for them yet. What email should I use?",
            evidence=evidence_packet.evidence,
            confidence=0.84,
            source=source,
            suggested_commands=suggested_commands,
        )

    topic = optional_str(plan.get("topic")) or (f"task #{task_id}" if task_id else "")
    filtered = filtered_context_for_email(repo, evidence_packet, recipient_context, task=task, topic=topic)
    context = recipient_context or filtered.get("context")
    subject = email_subject(topic=topic, task=task, recipient=recipient_label)
    draft = compose_context_email(
        settings,
        recipient=to_address,
        subject=subject,
        instruction=email_instruction(command, topic=topic, recipient=recipient_label, task=task),
        context=context,
        tasks=filtered["tasks"],
        meetings=filtered["meetings"],
        decisions=filtered["decisions"],
        related_contexts=filtered["related_contexts"],
    ).to_dict()
    draft["to"] = to_address

    linked_task = task or first(filtered["tasks"])
    linked_meeting = first(filtered["meetings"])
    pending_payload = {
        "to": to_address,
        "recipient": to_address,
        "subject": str(draft.get("subject") or subject),
        "body": str(draft.get("body") or ""),
        "task_id": linked_task.get("id") if linked_task else None,
        "context_id": context.get("id") if context else None,
        "meeting_id": linked_meeting.get("id") if linked_meeting else None,
        "source": "assistant_pipeline",
        "linked_task_ids": [item.get("id") for item in filtered["tasks"] if item.get("id")],
        "linked_meeting_ids": [item.get("id") for item in filtered["meetings"] if item.get("id")],
        "request": command,
    }
    pending = repo.create_pending_action(
        command=command,
        action="create_local_email_draft",
        category="email",
        payload=pending_payload,
        confidence=clamp_float(plan.get("confidence"), default=0.84),
        source=source,
        explanation="Retrieved local context and prepared a frozen email draft preview. Confirmation will create the local draft exactly as shown.",
        safety_notes=["This will create a local editable draft only. It will not send email."],
    )

    evidence = compact_evidence_for_email(evidence_packet.evidence, filtered, task)
    message = f"Draft preview ready for {recipient_label}. Confirm pending action {pending['id']} to create the local draft."
    return {
        "supported": True,
        "action": "create_local_email_draft",
        "category": "email",
        "payload": pending_payload,
        "summary": message,
        "command": command,
        "result": json_safe(
            {
                "assistant_message": message,
                "evidence": evidence,
                "draft_preview": draft,
                "pending_action": pending,
                "clarification_required": False,
            }
        ),
        "requires_confirmation": True,
        "confidence": clamp_float(plan.get("confidence"), default=0.84),
        "explanation": "I retrieved the relevant local task/person context before proposing this email draft.",
        "safety_notes": ["Writes require confirmation. This pending action creates a local editable draft only."],
        "source": source,
        "pending_action_id": pending["id"],
        "suggested_commands": maybe_suggestions(suggested_commands, command),
    }


def answer_turn(
    settings: Settings,
    repo: Repository,
    command: str,
    plan: dict[str, Any],
    *,
    source: str,
    suggested_commands: Callable[[str], list[str]] | None,
) -> dict[str, Any]:
    evidence_packet = run_read_tools(repo, plan.get("read_tools") or [])
    message = local_answer(command, evidence_packet)
    return {
        "supported": True,
        "action": "answer_question",
        "category": "assistant",
        "payload": {"query": command},
        "summary": message,
        "command": command,
        "result": json_safe(
            {
                "assistant_message": message,
                "evidence": evidence_packet.evidence,
                "clarification_required": False,
            }
        ),
        "requires_confirmation": False,
        "confidence": clamp_float(plan.get("confidence"), default=0.7),
        "explanation": "Answered from local SpeedwagonAI read tools. No action was run.",
        "safety_notes": ["Read-only local assistant answer. No writes or external sends were performed."],
        "source": source,
        "suggested_commands": maybe_suggestions(suggested_commands, command),
    }


def clarification_turn(
    command: str,
    message: str,
    *,
    evidence: list[dict[str, Any]],
    confidence: float,
    source: str,
    suggested_commands: Callable[[str], list[str]] | None,
) -> dict[str, Any]:
    return {
        "supported": True,
        "action": "answer_question",
        "category": "assistant",
        "payload": {"query": command},
        "summary": message,
        "command": command,
        "result": json_safe(
            {
                "assistant_message": message,
                "evidence": evidence,
                "clarification_required": True,
            }
        ),
        "requires_confirmation": False,
        "confidence": confidence,
        "explanation": "I retrieved what I could, but a required target is missing.",
        "safety_notes": ["No draft or write was created."],
        "source": source,
        "suggested_commands": maybe_suggestions(suggested_commands, command),
    }


class EvidencePacket:
    def __init__(self) -> None:
        self.data: dict[str, list[dict[str, Any]]] = {
            "tasks": [],
            "contexts": [],
            "meetings": [],
            "calendar_events": [],
            "suggestions": [],
            "drafts": [],
            "decisions": [],
            "related_contexts": [],
        }
        self.evidence: list[dict[str, Any]] = []
        self._seen_evidence: set[tuple[str, int | str]] = set()

    def add(self, kind: str, item: dict[str, Any], *, title: str | None = None, subtitle: str | None = None) -> None:
        collection = self.data.setdefault(kind_plural(kind), [])
        item_id = item.get("id")
        if item_id is not None and any(existing.get("id") == item_id for existing in collection):
            return
        collection.append(item)
        evidence_key: tuple[str, int | str] = (kind, int(item_id) if str(item_id).isdigit() else str(title or item_id or len(self.evidence)))
        if evidence_key in self._seen_evidence:
            return
        self._seen_evidence.add(evidence_key)
        self.evidence.append(
            {
                "kind": kind,
                "id": coerce_int(item_id),
                "title": title or evidence_title(kind, item),
                "subtitle": subtitle or evidence_subtitle(kind, item),
            }
        )

    def first_task(self, task_id: int | None = None) -> dict[str, Any] | None:
        for task in self.data.get("tasks", []):
            if task_id is None or int(task.get("id") or -1) == task_id:
                return task
        return None

    def best_context(self, label: str | None = None) -> dict[str, Any] | None:
        contexts = self.data.get("contexts", [])
        if not contexts:
            return None
        if label:
            normalized = normalize_name(label)
            for context in contexts:
                if normalize_name(str(context.get("name") or "")) == normalized:
                    return context
            for context in contexts:
                if str(context.get("kind") or "") == "person":
                    return context
        return contexts[0]


READ_TOOL_NAMES = {
    "task_by_id",
    "task_search",
    "context_lookup",
    "context_detail",
    "meeting_detail",
    "meeting_search",
    "calendar_search",
    "suggestions",
    "drafts",
}


def run_read_tools(repo: Repository, calls: list[dict[str, Any]]) -> EvidencePacket:
    packet = EvidencePacket()
    for call in sanitize_read_tool_calls(calls)[:8]:
        tool = call["tool"]
        payload = call["payload"]
        try:
            if tool == "task_by_id":
                task = repo.get_task(int(payload["task_id"]))
                packet.add("task", task)
            elif tool == "task_search":
                for task in multi_search_tasks(repo, str(payload.get("query") or ""), limit=int(payload.get("limit") or 12)):
                    packet.add("task", task)
            elif tool == "context_lookup":
                query = str(payload.get("query") or "")
                for context in repo.find_contexts(query, limit=int(payload.get("limit") or 8)):
                    packet.add("context", context)
                    detail = repo.context_detail(int(context["id"]), limit=16)
                    add_context_detail(packet, detail)
            elif tool == "context_detail":
                detail = repo.context_detail(int(payload["context_id"]), limit=int(payload.get("limit") or 20))
                add_context_detail(packet, detail)
            elif tool == "meeting_detail":
                meeting = repo.get_meeting(int(payload["meeting_id"]))
                packet.add("meeting", meeting_to_dict(meeting))
            elif tool == "meeting_search":
                topic = str(payload.get("query") or "")
                for meeting in repo.context_for_topic(topic, limit=int(payload.get("limit") or 8)).get("meetings", []):
                    packet.add("meeting", meeting_to_dict(meeting) if not isinstance(meeting, dict) else meeting)
            elif tool == "calendar_search":
                for event in search_calendar_events(repo, str(payload.get("query") or ""), limit=int(payload.get("limit") or 8)):
                    packet.add("calendar_event", event)
            elif tool == "suggestions":
                for suggestion in repo.list_suggestions(status=str(payload.get("status") or "open"), limit=int(payload.get("limit") or 8)):
                    packet.add("suggestion", suggestion)
            elif tool == "drafts":
                for draft in repo.list_followup_drafts(status=payload.get("status"), limit=int(payload.get("limit") or 8)):
                    packet.add("draft", draft)
        except Exception:
            continue
    return packet


def add_context_detail(packet: EvidencePacket, detail: dict[str, Any]) -> None:
    context = detail.get("context")
    if isinstance(context, dict):
        packet.add("context", context)
    for key, kind in [
        ("tasks", "task"),
        ("meetings", "meeting"),
        ("decisions", "decision"),
        ("related_contexts", "context"),
        ("suggestions", "suggestion"),
        ("followup_drafts", "draft"),
    ]:
        for item in detail.get(key) or []:
            if isinstance(item, dict):
                packet.add(kind, item)


def sanitize_read_tool_calls(raw: Any) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return calls
    for item in raw:
        if not isinstance(item, dict):
            continue
        tool = str(item.get("tool") or "").strip()
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        if tool in READ_TOOL_NAMES:
            calls.append({"tool": tool, "payload": json_safe(payload)})
    return calls


def filtered_context_for_email(
    repo: Repository,
    packet: EvidencePacket,
    recipient_context: dict[str, Any] | None,
    *,
    task: dict[str, Any] | None,
    topic: str,
) -> dict[str, list[dict[str, Any]] | dict[str, Any] | None]:
    terms = topic_terms(topic)
    tasks = list(packet.data.get("tasks", []))
    meetings = list(packet.data.get("meetings", []))
    decisions = list(packet.data.get("decisions", []))
    related_contexts = [context for context in packet.data.get("contexts", []) if context != recipient_context]

    if recipient_context:
        try:
            detail = repo.context_detail(int(recipient_context["id"]), limit=24)
            tasks.extend(detail.get("tasks") or [])
            meetings.extend(detail.get("meetings") or [])
            decisions.extend(detail.get("decisions") or [])
            related_contexts.extend(detail.get("related_contexts") or [])
        except Exception:
            pass
    if topic:
        tasks.extend(multi_search_tasks(repo, topic, limit=12))
        context_topic = repo.context_for_topic(topic, limit=8)
        meetings.extend(
            meeting_to_dict(meeting) if not isinstance(meeting, dict) else meeting
            for meeting in context_topic.get("meetings", [])
        )
        decisions.extend(context_topic.get("decisions", []))

    if task:
        tasks.insert(0, task)
    tasks = dedupe_by_id(tasks)
    meetings = dedupe_by_id(meetings)
    decisions = dedupe_by_id(decisions)
    related_contexts = dedupe_by_id(related_contexts)

    if terms:
        explicit_task_id = int(task.get("id")) if task and task.get("id") else None
        tasks = [
            item
            for item in tasks
            if (explicit_task_id and int(item.get("id") or -1) == explicit_task_id) or matches_terms(task_blob(item), terms)
        ]
        meetings = [item for item in meetings if matches_terms(meeting_blob(item), terms)]
        decisions = [item for item in decisions if matches_terms(decision_blob(item), terms)]

    return {
        "context": recipient_context,
        "tasks": tasks[:8],
        "meetings": meetings[:5],
        "decisions": decisions[:5],
        "related_contexts": related_contexts[:6],
    }


def multi_search_tasks(repo: Repository, query: str, *, limit: int = 12) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    cleaned = query.strip()
    if cleaned:
        tasks.extend(repo.search_tasks(query=cleaned, status=None, limit=limit))
    for term in topic_terms(query)[:4]:
        tasks.extend(repo.search_tasks(query=term, status=None, limit=limit))
    return dedupe_by_id(tasks)[:limit]


def infer_task_recipient(repo: Repository, task: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    candidates = [task.get("owed_to"), task.get("owner")]
    for candidate in candidates:
        label = optional_str(candidate)
        if not label or normalize_name(label) in SELF_NAMES:
            continue
        context = best_context_for_label(repo, label)
        if context and resolve_recipient_email(label, context):
            return label, context
    return None, None


def best_context_for_label(repo: Repository, label: str) -> dict[str, Any] | None:
    contexts = repo.find_contexts(label, limit=8)
    if not contexts:
        return None
    normalized = normalize_name(label)
    for context in contexts:
        if normalize_name(str(context.get("name") or "")) == normalized:
            return context
    for context in contexts:
        if str(context.get("kind") or "") == "person":
            return context
    return contexts[0]


def resolve_recipient_email(label: str, context: dict[str, Any] | None) -> str:
    explicit = label.strip()
    if "@" in explicit:
        return explicit
    if context:
        email = str(context.get("profile_email") or "").strip()
        if email:
            return email
    return ""


def compact_evidence_for_email(
    evidence: list[dict[str, Any]],
    filtered: dict[str, Any],
    task: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    seen: set[tuple[str, int | str]] = set()

    def add(kind: str, item: dict[str, Any]) -> None:
        item_id = coerce_int(item.get("id"))
        key = (kind, item_id if item_id is not None else evidence_title(kind, item))
        if key in seen:
            return
        seen.add(key)
        compact.append(
            {
                "kind": kind,
                "id": item_id,
                "title": evidence_title(kind, item),
                "subtitle": evidence_subtitle(kind, item),
            }
        )

    if task:
        add("task", task)
    context = filtered.get("context")
    if isinstance(context, dict):
        add("context", context)
    for kind, key in [("task", "tasks"), ("meeting", "meetings"), ("decision", "decisions")]:
        for item in filtered.get(key) or []:
            if isinstance(item, dict):
                add(kind, item)
    return compact[:8]


def local_answer(command: str, packet: EvidencePacket) -> str:
    events = packet.data.get("calendar_events", [])
    if events:
        event = events[0]
        title = event.get("title") or "That event"
        start = event.get("start_at") or "an unsynced time"
        location = f" at {event['location']}" if event.get("location") else ""
        return f"{title} is scheduled for {start}{location}."

    task = packet.first_task()
    if task:
        due = f", due {task['due_date']}" if task.get("due_date") else ""
        return f"Task #{task.get('id')}: {task.get('text')} is {task.get('status') or 'open'}{due}."

    if packet.evidence:
        return f"I found {len(packet.evidence)} relevant local item(s), but not a single direct answer."
    return "I could not find matching local evidence for that."


def planner_snapshot(repo: Repository) -> dict[str, Any]:
    try:
        brief = repo.daily_brief()
    except Exception:
        brief = {}
    return {
        "counts": brief.get("counts") or {},
        "open_tasks": summarize_items(repo.list_tasks(status="open")[:8], "task"),
        "people": summarize_items([context for context in repo.find_contexts(limit=20) if context.get("kind") == "person"][:8], "context"),
        "upcoming_calendar": summarize_items(repo.upcoming_calendar_events(limit=6), "calendar_event"),
        "suggestions": summarize_items(repo.list_suggestions(status="open", limit=6), "suggestion"),
    }


def summarize_items(items: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [
        {
            "kind": kind,
            "id": item.get("id"),
            "title": evidence_title(kind, item),
            "subtitle": evidence_subtitle(kind, item),
        }
        for item in items
    ]


def extract_task_id(command: str) -> int | None:
    match = re.search(r"\btask\s*#?\s*(\d+)\b|#(\d+)\b", command, flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1) or match.group(2))


def extract_email_recipient_topic(command: str) -> tuple[str | None, str | None]:
    cleaned = re.sub(r"\s+", " ", command.strip()).strip(" ?")
    patterns = [
        r"(?:send|write|draft|create|make)(?:\s+an?)?\s+(?:email|mail|note|message)\s+to\s+(.+?)\s+(?:about|regarding|re:|asking\s+for|ask(?:ing)?\s+for|requesting)\s+(.+)$",
        r"(?:email|mail|message|note)\s+(.+?)\s+(?:about|regarding|re:|asking\s+for|ask(?:ing)?\s+for|requesting)\s+(.+)$",
        r"(?:send|write|draft|create|make)\s+(.+?)\s+(?:an?\s+)?(?:email|mail|note|message)\s+(?:about|regarding|re:|asking\s+for|ask(?:ing)?\s+for|requesting)\s+(.+)$",
        r"(?:send|write|draft|create|make)\s+(.+?)\s+(?:about|regarding|re:|asking\s+for|ask(?:ing)?\s+for|requesting)\s+(.+)$",
    ]
    prefix = r"^(?:okay\s+)?(?:can|could|would)\s+you\s+|^(?:okay\s+)?please\s+|^okay\s+"
    reduced = re.sub(prefix, "", cleaned, flags=re.IGNORECASE).strip()
    for text in [cleaned, reduced]:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                recipient = clean_recipient(match.group(1))
                topic = clean_topic(match.group(2))
                if recipient and topic:
                    return recipient, topic
    return None, None


def clean_recipient(value: str) -> str:
    value = re.sub(r"\b(an?|the)\s+(email|mail|note|message)\b", "", value, flags=re.IGNORECASE)
    value = value.strip(" ,")
    if normalize_name(value) in {"", "a", "an", "the", "email", "mail", "note", "message"}:
        return ""
    return value


def clean_topic(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" ?,.")
    value = re.sub(r"^(?:to\s+)?", "", value, flags=re.IGNORECASE).strip()
    return value


def clean_trailing_noise(value: str) -> str:
    value = re.sub(r"\b(?:please|thanks|thank you)\b.*$", "", value, flags=re.IGNORECASE)
    return value.strip(" ?.,")


def topic_terms(topic: str) -> list[str]:
    terms: list[str] = []
    for token in re.findall(r"[a-zA-Z]+[0-9]+|[0-9]+[a-zA-Z]+|[a-zA-Z0-9]+", topic.lower()):
        if len(token) < 2 or token in STOPWORDS:
            continue
        if token not in terms:
            terms.append(token)
    return terms


def matches_terms(blob: str, terms: list[str]) -> bool:
    haystack = blob.lower()
    return any(term in haystack for term in terms)


def task_blob(task: dict[str, Any]) -> str:
    parts = [
        task.get("text"),
        task.get("owner"),
        task.get("owed_to"),
        task.get("project"),
        task.get("meeting_title"),
    ]
    parts.extend(context.get("name") for context in task.get("contexts") or [] if isinstance(context, dict))
    return " ".join(str(part or "") for part in parts)


def meeting_blob(meeting: dict[str, Any]) -> str:
    return " ".join(str(meeting.get(key) or "") for key in ["title", "summary", "started_at"])


def decision_blob(decision: dict[str, Any]) -> str:
    return " ".join(str(decision.get(key) or "") for key in ["text", "meeting_title"])


def email_subject(*, topic: str, task: dict[str, Any] | None, recipient: str) -> str:
    if task:
        return f"Follow-up on task #{task.get('id')}"
    cleaned = re.sub(r"\s+", " ", topic).strip(" .")
    if not cleaned:
        return f"Follow-up for {recipient}"
    if re.search(r"\b(v\d+|files?|docs?|documents?|assets?)\b", cleaned, flags=re.IGNORECASE):
        return f"Request for {smart_title(cleaned)}"
    return smart_title(cleaned)[:80]


def smart_title(value: str) -> str:
    words = []
    for word in value.split():
        if re.fullmatch(r"v\d+", word, flags=re.IGNORECASE):
            words.append(word.lower())
        elif word.isupper():
            words.append(word)
        else:
            words.append(word[:1].upper() + word[1:])
    return " ".join(words)


def email_instruction(command: str, *, topic: str, recipient: str, task: dict[str, Any] | None) -> str:
    if task:
        return f"Draft a concise email to {recipient} about task #{task.get('id')}: {task.get('text')}."
    cleaned = re.sub(r"^(?:okay\s+)?(?:can|could|would)\s+you\s+", "", command.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:please|okay)\s+", "", cleaned, flags=re.IGNORECASE).strip(" ?")
    if topic and cleaned.lower() == command.strip().lower().strip(" ?"):
        return f"Ask {recipient} about {topic}."
    return cleaned or f"Ask {recipient} about {topic}."


def evidence_title(kind: str, item: dict[str, Any]) -> str:
    if kind == "task":
        return str(item.get("text") or f"Task #{item.get('id')}")
    if kind == "context":
        return str(item.get("name") or f"Context #{item.get('id')}")
    if kind == "meeting":
        return str(item.get("title") or f"Meeting #{item.get('id')}")
    if kind == "calendar_event":
        return str(item.get("title") or f"Calendar event #{item.get('id')}")
    if kind == "suggestion":
        return str(item.get("title") or f"Suggestion #{item.get('id')}")
    if kind == "draft":
        return str(item.get("subject") or f"Draft #{item.get('id')}")
    if kind == "decision":
        return str(item.get("text") or f"Decision #{item.get('id')}")
    return str(item.get("title") or item.get("name") or item.get("id") or kind)


def evidence_subtitle(kind: str, item: dict[str, Any]) -> str | None:
    if kind == "task":
        bits = [str(item.get("status") or "open")]
        if item.get("due_date"):
            bits.append(f"due {item['due_date']}")
        if item.get("owner"):
            bits.append(f"owner {item['owner']}")
        if item.get("owed_to"):
            bits.append(f"owed to {item['owed_to']}")
        return " · ".join(bits)
    if kind == "context":
        bits = [str(item.get("kind") or "context")]
        if item.get("profile_email"):
            bits.append(str(item["profile_email"]))
        return " · ".join(bits)
    if kind == "meeting":
        return optional_str(item.get("started_at"))
    if kind == "calendar_event":
        return optional_str(item.get("start_at"))
    if kind == "suggestion":
        return optional_str(item.get("status")) or optional_str(item.get("reason"))
    if kind == "draft":
        return optional_str(item.get("recipient")) or optional_str(item.get("status"))
    return None


def kind_plural(kind: str) -> str:
    return {
        "task": "tasks",
        "context": "contexts",
        "meeting": "meetings",
        "calendar_event": "calendar_events",
        "suggestion": "suggestions",
        "draft": "drafts",
        "decision": "decisions",
    }.get(kind, f"{kind}s")


def dedupe_by_id(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    seen_blobs: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = coerce_int(item.get("id"))
        if item_id is not None:
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)
        else:
            blob = json.dumps(json_safe(item), sort_keys=True)
            if blob in seen_blobs:
                continue
            seen_blobs.add(blob)
        result.append(item)
    return result


def first(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    return items[0] if items else None


def optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        text = str(value).strip()
        if not text:
            return None
        return int(text)
    except (TypeError, ValueError):
        return None


def clamp_float(value: Any, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, parsed))


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def maybe_suggestions(callback: Callable[[str], list[str]] | None, command: str) -> list[str]:
    if not callback:
        return []
    try:
        return callback(command)
    except Exception:
        return []


def json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    return value
