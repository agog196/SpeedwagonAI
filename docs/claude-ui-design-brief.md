# SpeedwagonAI UI Redesign Brief For Claude Design

Use this document as the source-of-truth product/design brief for redesigning the SpeedwagonAI native Mac app frontend. The goal is not to invent a new product. The goal is to make the existing product feel coherent, calm, premium, trustworthy, and easy to use for a private beta.

## One-Line Product Description

SpeedwagonAI is a local-first Mac follow-through assistant that captures meetings, tasks, screenshots, commitments, relationships, and follow-ups so solo users never lose the thread on work they owe, decisions they made, or people they need to follow up with.

## Core Promise

Never lose the thread again.

The app should feel like a computer-resident assistant that quietly understands the user's local work context, remembers commitments, drafts follow-ups, and nudges the user before work slips.

## Target User

The first deployable audience is solo Mac users, early beta testers, and builders/operators who:

- spend a lot of time in meetings;
- collect tasks across meetings, voice notes, screenshots, and email;
- forget follow-ups unless they are surfaced at the right time;
- want local-first control over data;
- are willing to bring their own OpenAI/Google/Recall credentials in beta;
- expect a native Mac experience, not a marketing SaaS dashboard.

This is not a consumer social app, not a corporate analytics suite, and not a generic chatbot. It should feel like a precise personal command center.

## Current Product State

SpeedwagonAI currently has:

- a Python local backend;
- a local SQLite database;
- a SwiftUI native Mac app;
- a menu bar presence;
- a Spotlight-like assistant palette;
- a sidebar-based main window;
- local-first storage with optional external services;
- unsigned and signed/private-beta app packaging scripts.

The native app is the primary product surface. A local web app exists for testing but should not drive this redesign.

## Design Objective

Redesign the native Mac app UI so it feels ready for a private beta:

- clearer information hierarchy;
- less "everything everywhere" dashboard clutter;
- stronger sense of what needs attention now;
- better review flows for suggestions, tasks, meetings, drafts, and person/project context;
- calmer settings/onboarding for permissions, Keychain, backend, and privacy;
- native Mac polish;
- dense enough for repeated work, but not cramped or visually noisy.

The design should preserve existing functionality and API boundaries. It should not introduce new integrations or automatic external writes.

## Important Product Principles

### Local-First Trust

The user should always understand what is local, what leaves the device, and what is user-confirmed. The UI should make the following trust model obvious:

- Most data lives locally in SQLite and local folders.
- OpenAI is used only for LLM-backed features.
- Google is optional and used for Gmail draft creation and read-only Calendar sync.
- Recall.ai meeting bots are optional, provider-backed, visible to meeting participants, and require explicit consent.
- Gmail is draft-only. SpeedwagonAI never sends email automatically.
- Notifications never execute actions automatically.
- Wipe/export are explicit user actions.

### Confirmation-First Actions

The app should avoid scary autonomous behavior. The design should reinforce:

- suggested follow-ups require confirmation;
- Gmail drafts are created only after local draft review;
- notification taps open review, not action execution;
- assistant interpreted mutating actions require confirmation;
- meeting bots require explicit consent.

### Assistant As Control Surface, Not Chat Toy

The assistant should feel like a command/search/control surface over local work. It can answer graph-aware questions and run known commands, but the product is not just a chat window.

### Review Before Action

The central repeated loop is:

1. capture context;
2. extract tasks/decisions/relationships;
3. surface suggestions;
4. review related evidence;
5. confirm or dismiss;
6. optionally draft/edit/send elsewhere.

Design around that loop.

## Current Native App Information Architecture

The current SwiftUI app uses a left sidebar with these sections:

- Assistant
- Capture
- Meetings
- Calendar
- Notifications
- Tasks
- Suggestions
- Commitments
- Settings
- Roadmap

There is also:

- a menu bar extra;
- a global Option+Space command palette;
- a Cmd+K shortcut while the app is focused;
- a contextual person/project/topic review panel that appears in the main content area;
- notification deep-link behavior that routes to suggestions/drafts/tasks for review.

No new sidebar section should be required for the redesign unless the design makes an extremely strong case. Prefer improving the existing structure.

## Recommended High-Level IA For Redesign

The current sidebar has many sections and the Assistant dashboard includes too many panels at once. Consider reorganizing the visual hierarchy around these mental models while preserving the existing routes:

- **Today / Assistant Home**: "What needs attention now?"
- **Capture**: meetings, voice tasks, screenshots, meeting bot.
- **Work**: tasks, suggestions, commitments, follow-up drafts.
- **Meetings**: meeting list, notes, decisions, transcript.
- **Context**: person/project/topic review, surfaced through chips and assistant results rather than a permanent sidebar section.
- **Calendar + Notifications**: planning and nudges.
- **Settings**: backend, Keychain, privacy, logs, export/wipe.

If keeping the existing sidebar labels, visually group them:

- Primary: Assistant, Capture, Tasks, Suggestions
- Knowledge: Meetings, Calendar, Commitments
- System: Notifications, Settings, Roadmap

## Current Visual Language

The current app uses:

- dark and light mode support;
- muted green/teal accent;
- dark background around RGB `0.10, 0.11, 0.10`;
- sidebar background around RGB `0.13, 0.14, 0.13`;
- panel cards with 8px radius;
- secondary panels with 6px radius;
- capsule chips;
- SF Symbols;
- bordered/prominent buttons;
- a lot of nested panels.

The redesign should feel native to macOS and should avoid a generic web-dashboard look.

## Visual Direction To Aim For

Use a restrained, work-focused Mac utility aesthetic:

- calm but not sterile;
- high signal-to-noise;
- strong spacing and grouping;
- readable at long sessions;
- subtle depth, not heavy card stacks;
- native-feeling sidebar and toolbar;
- task/suggestion states that are visually scannable;
- modern but not flashy.

Avoid:

- marketing hero sections;
- gradient/orb/bokeh backgrounds;
- giant empty cards;
- nested card-heavy layouts;
- oversized headings inside small tool panels;
- single-hue monotony;
- decorative illustrations that do not show product state;
- chat-app-only framing.

## Layout Requirements

The app is a desktop Mac app. Primary target window:

- minimum width around 1120px;
- minimum height around 760px;
- should also behave well around 1280x800 and 1440x900;
- sidebar should remain stable;
- content should scroll vertically;
- compact panels should not become unreadable;
- text must not overlap or be clipped.

Use stable dimensions for:

- sidebar navigation rows;
- toolbar buttons;
- chips/badges;
- task rows;
- suggestion cards;
- capture controls;
- notification cards;
- draft editor.

## Main App Shell

Current shell:

- left sidebar with app title and backend status;
- sidebar navigation;
- "Open Assistant" button;
- optional backend guide when disconnected;
- detail area with large section title and refresh button;
- scrollable section content;
- context detail review panel appears after section content when selected.

Redesign goals:

- Make backend status useful but not alarming when healthy.
- Put global refresh in a predictable toolbar area.
- Make "Open Assistant" feel like a command palette affordance, perhaps with shortcut hint.
- Make disconnected/setup states clear and actionable.
- Avoid burying the most important work below too many panels.

## Assistant/Home Surface

Current Assistant screen includes:

- command input;
- Run button;
- Voice button;
- Screenshot button;
- status badge;
- context chips for counts;
- meeting capture controls;
- command result;
- screenshot analysis;
- pending actions;
- compact suggestions;
- suggested command buttons;
- a grid of capture, bot, calendar, notifications, brain/cost, daily brief, commitments, roadmap;
- suggestions panel;
- task inbox.

This screen currently tries to do too much.

Redesign intent:

- Make it the "Today / Ask" home surface.
- Top area should answer: "What needs my attention?"
- Assistant command input should be prominent but not dominate all workflows.
- Show a compact daily brief/priority stack.
- Show top suggestions and urgent tasks.
- Keep capture entry points available but not visually equal to everything.
- Pending confirmations should be highly visible.
- Assistant results should be easy to scan and include suggested rephrases when unsupported.

Important assistant commands/results to support visually:

- "daily brief"
- "what is overdue"
- "what is due before June 7"
- "what tasks have no due date"
- "what do I owe Alex"
- "what did I say about onboarding"
- "what did we decide about onboarding"
- "everything related to Alex"
- "who should I follow up with"
- "what changed on DairyMGT"
- "show unprocessed meetings"
- "process latest meeting"
- "draft follow-up for meeting 8"
- "search context graph for onboarding"
- "show suggestions"
- "confirm suggestion 3"
- calendar commands
- meeting-bot commands

Unsupported assistant commands should show useful suggested commands, not a dead end.

## Command Palette

Current command palette:

- global Option+Space;
- floating NSPanel;
- compact or expanded mode;
- backend status;
- close button;
- AssistantSurfaceView inside it;
- expanded mode can show capture controls, results, pending actions, suggestions, suggested actions.

Design requirements:

- Should feel like Spotlight plus action review.
- Compact mode should be quick command entry and answer preview.
- Expanded mode should handle capture controls and review details.
- Must not look like a full dashboard crammed into a popup.
- Needs clear Esc/close affordance.
- Needs connected/offline state.

## Capture Screen

Current Capture includes:

- active recording status;
- meeting capture mode segmented picker:
  - Native system + mic;
  - Mic fallback;
- native permission rows;
- meeting title input;
- Start Native/Start Mic;
- Voice Task (mic);
- Stop / Stop + Process / Stop + Add Task / Stop + Run depending on capture type;
- warnings;
- Meeting Bot Beta panel.

Capture types:

- native meeting capture via ScreenCaptureKit system audio plus microphone;
- mic fallback meeting capture;
- voice task capture;
- assistant voice capture;
- screenshot analysis from assistant surface;
- optional Recall.ai meeting bot.

Design goals:

- Make active recording state impossible to miss.
- Separate meeting capture, quick voice task, screenshot capture, and meeting bot conceptually.
- Permissions should be clear but not scary.
- "Stop" versus "Stop + Process" should be visually distinct.
- Meeting bot consent should be explicit.
- Meeting bot cost/provider status should be visible.

## Meeting Bot Beta

Current Meeting Bot panel includes:

- provider/configured status;
- explanation about cloud/provider capture;
- provider/status/cost rows;
- meeting title input;
- meeting link input;
- consent checkbox;
- Join Bot;
- Refresh;
- session rows with Sync and Process.

Design requirements:

- Make it clear this is optional and cloud/provider-backed.
- Make consent checkbox prominent enough.
- Do not make "Join Bot" look like a casual low-stakes action.
- Surface transcript readiness clearly.
- Process should only feel available when transcript is ready.

## Meetings Screen

Current Meetings screen:

- left meeting list;
- right meeting detail;
- meeting row shows title, date/id, bot chip, transcript/note chips;
- detail shows title/date/id, Process button, summary, decisions, action items, commitments, open questions, transcript, transcript path/note path.

Design goals:

- Make meetings feel like a source of extracted obligations and decisions.
- Meeting list should be scannable by title, date, status, source, processing completeness.
- Detail should prioritize summary, decisions, tasks/action items, commitments, open questions.
- Transcript can be present but secondary/collapsible.
- Local paths should be hidden in ordinary review unless in debug/settings mode.
- Processing state should be obvious.

## Tasks Screen

Current Tasks screen:

- suggestions panel above task inbox;
- task inbox grouped by:
  - Overdue;
  - Today;
  - Upcoming;
  - Unscheduled;
  - Done.
- task row shows text, owner, due date, source, reminder suggestion, context chips, Complete/Reopen.

Task statuses include:

- open;
- done;
- waiting;
- snoozed;
- uncertain;
- canceled.

Design goals:

- Task inbox should be dense and operational.
- Important statuses should be visually distinct.
- Waiting/uncertain tasks should not feel hidden.
- Context chips should open person/project/topic review.
- Highlighted tasks from notification review should be obvious but not garish.
- Completion/reopen controls should be easy but not accidentally triggered.

## Suggestions Screen

Current Suggestions screen:

- list of follow-through suggestions;
- suggestion card includes id, title, context chip, reason, proposed action, task chips, status, confidence;
- actions:
  - Confirm;
  - Snooze;
  - Dismiss.
- Draft Review editor below list:
  - selected local draft;
  - recipient;
  - subject;
  - body;
  - Save;
  - Create Gmail Draft.

Suggestion types include:

- overdue;
- due today;
- stale;
- unscheduled;
- waiting/uncertain;
- follow-up-ready;
- implicit follow-up from meeting extraction.

Design goals:

- Suggestions are the heart of the follow-through loop.
- Make each suggestion answer:
  - why this surfaced;
  - what evidence/source it is based on;
  - what confirming will do;
  - whether it already created/reused a draft/task;
  - whether it is snoozed/dismissed/retired/accepted.
- Confirmation should feel safe and reversible/review-first.
- Draft Review should feel like an email composer, but local-first.
- "Create Gmail Draft" must be clearly external/provider action and not automatic sending.
- Snoozed/dismissed/retired states should be reviewable without looking active.

## Follow-Up Draft Review

Current local draft fields:

- recipient;
- subject;
- body;
- status;
- linked suggestion/task/context/meeting;
- provider/provider draft ID after Gmail draft creation.

Design goals:

- Make local draft versus Gmail draft status clear.
- Let users edit comfortably.
- Show source context: meeting/task/person/project that caused the draft.
- The button hierarchy should be:
  - Save local draft;
  - Create Gmail Draft as explicit next external action.
- Never imply email is sent automatically.

## Notifications Screen

Current Notifications screen:

- notification permission status chip;
- status note;
- candidate/delivered/snoozed counts;
- Allow Notifications;
- Refresh;
- notification candidate cards;
- actions:
  - Review;
  - Mark Delivered;
  - Snooze;
  - Dismiss.

Notification behavior:

- scheduled by Mac app while running;
- tapping opens review;
- never confirms, sends, dismisses, or completes automatically;
- Review routes to suggestion, draft, or related task highlights.

Design goals:

- Make notification permission state understandable.
- Make notification candidates feel like reminders to review, not commands to execute.
- Review should be primary.
- Mark Delivered/Snooze/Dismiss should be available but secondary.
- If notification permission has macOS errors, show friendly plain language and next steps.

Known issue:

- Unsigned/unbundled notification permission can hit `UNErrorDomain error 1`; signed/bundled app testing is expected to improve this. UI should be resilient and not look broken.

## Calendar Screen

Current Calendar screen:

- Google Calendar status;
- read-only sync note;
- calendars/window/note rows;
- Sync Calendar;
- Refresh;
- upcoming event list.

Calendar is read-only:

- no event creation;
- no Calendar writes;
- local rolling window cache;
- enriches daily brief and meeting prep.

Design goals:

- Make read-only status explicit.
- Show sync state and credential issues clearly.
- Meeting prep context should be a major value point.
- Avoid showing full meeting URLs unless needed; summarize paths/URLs where possible.

## Commitments Screen

Current Commitments screen:

- list of open commitments using task rows;
- daily brief also appears in commitments section.

Commitments are extracted from meetings and local context.

Design goals:

- Show commitments as "promises/owed work," slightly distinct from generic tasks.
- Make owed-to/owner/project/date/source scannable.
- Tie commitments to meetings and person/project context.

## Person/Project/Topic Context Review

Current context review panel can be opened from:

- context chips on tasks;
- context chips on suggestions;
- assistant graph answers;
- person/project/topic chips;
- suggestions and related objects.

Current detail includes:

- selected context name/kind;
- counts for tasks/meetings/suggestions;
- related contexts;
- relationships;
- decisions;
- tasks;
- meetings;
- suggestions;
- follow-up drafts.

Relationships have:

- source context;
- target context;
- relationship type;
- evidence;
- confidence;
- source meeting.

Design goals:

- This is a key differentiator. Treat it as a rich review drawer/panel, not a tacked-on card.
- It should answer: "What does Speedwagon know about this person/project/topic?"
- Show one-hop relationships clearly.
- Use sections for:
  - related people/projects/topics;
  - recent decisions;
  - open tasks/commitments;
  - relevant meetings;
  - suggestions/follow-ups;
  - drafts.
- Provide existing local actions only:
  - open task;
  - open meeting;
  - review suggestion;
  - edit local draft.
- Reads should feel deterministic/local, not like a fresh AI call.

## Settings / Local Beta Readiness

Current Settings includes:

- first-run readiness;
- repo root;
- Python 3.11 status;
- local API token presence;
- OpenAI key presence;
- app bundle versus swift run;
- Keychain explanation;
- Check Readiness;
- Copy Diagnostics;
- backend state;
- backend command/log path;
- start backend;
- stop managed backend;
- OpenAI API key secure field;
- Save Secrets;
- permission/data leaving device disclosures;
- privacy data tools;
- export local data;
- wipe local data with exact confirmation phrase;
- logs.

Design goals:

- Settings should reduce anxiety.
- Use plain language for Keychain prompts: "this is your Mac login password."
- Separate:
  - Setup/readiness;
  - Secrets;
  - Permissions;
  - Privacy/export/wipe;
  - Logs/debug.
- Avoid huge walls of text.
- Keep dangerous wipe action visually isolated.
- Logs should be readable but clearly advanced/debug.

## Privacy Status And Data Disclosures

Settings can show:

- counts of local data:
  - meetings;
  - tasks;
  - suggestions;
  - etc.
- local data directories;
- external services configured;
- data disclosures;
- export/wipe availability;
- path visibility note.

Design goals:

- Give users confidence that data is local-first.
- Show external services as configured/not configured.
- Do not expose secrets.
- Detailed local paths belong in Settings/log/debug/export manifest, not ordinary workflow screens.

## Roadmap Screen

Current Roadmap/PlannedCapabilities is basic and says:

- Meeting Bot;
- Window/Region Screenshots;
- Calendar + Reminders;
- Privacy + Security.

Given current V26 state, this screen may be stale or less important. For redesign:

- Make it unobtrusive.
- Could be renamed "About Beta" or "Roadmap" depending product decision.
- Do not let it compete with daily work.

## Important Data Objects To Design Around

### Task

Fields:

- id;
- text;
- owner;
- owedTo;
- project;
- dueDate;
- status;
- source/sourceType;
- sourceMeetingId/meetingId;
- meetingTitle;
- reminderSuggestion;
- isOverdue;
- snoozedUntil;
- completedAt;
- createdAt/updatedAt;
- contexts.

### Suggestion

Fields:

- id;
- title;
- reason;
- status;
- confidence;
- context/contextName/contextKind;
- proposedAction;
- payload;
- taskIds;
- meetingIds;
- sourceFingerprint;
- retiredAt;
- nextNotifyAt;
- lastNotifiedAt;
- notificationReason;
- notificationStatus;
- snoozedUntil;
- createdAt/updatedAt.

### Meeting

Fields:

- id;
- title;
- startedAt/endedAt;
- audioPath;
- transcriptPath;
- notePath;
- summary;
- sourceType.

Meeting detail includes:

- action items;
- commitments;
- decisions;
- open questions;
- key topics;
- entities;
- email drafts;
- transcript.

### Context

Fields:

- id;
- name;
- normalizedName;
- kind;
- confidence;
- reason;
- createdAt/updatedAt.

Kinds can represent people, projects, topics, and similar work context.

### Context Relationship

Fields:

- id;
- sourceContext;
- targetContext;
- relationshipType;
- evidence;
- confidence;
- sourceMeetingId;
- sourceMeetingTitle;
- createdAt/updatedAt.

### Follow-Up Draft

Fields:

- id;
- suggestionId;
- taskId;
- contextId;
- meetingId;
- provider;
- providerDraftId;
- recipient;
- subject;
- body;
- status;
- source;
- contextName;
- taskText;
- meetingTitle;
- createdAt/updatedAt.

### Daily Brief

Contains:

- date;
- optional cached synthesis;
- overdue;
- today;
- upcoming;
- waiting;
- snoozed;
- uncertain;
- stale;
- unscheduled;
- recommendedFollowups;
- calendarToday;
- calendarUpcoming;
- meetingPrep;
- notificationCandidates;
- counts.

### Daily Synthesis

Contains:

- summary;
- risks;
- droppedThreads;
- followups;
- recentChanges;
- provider/model;
- generatedAt.

## Key User Workflows

### First Run / Local Beta Setup

1. User launches app.
2. App checks backend availability.
3. If backend unavailable, native app can start Python backend.
4. User checks readiness in Settings.
5. User may save OpenAI API key in Keychain.
6. User reads permission and external-service disclosures.
7. User optionally connects Google/Recall through existing setup flows.

Design should make this feel guided, not broken.

### Daily Review

1. User opens app.
2. Sees connected/offline state.
3. Reviews daily brief and top risks.
4. Reviews top suggestions.
5. Completes/reopens tasks or asks assistant questions.
6. Refreshes intelligence explicitly if desired.

Design should prioritize "what matters now."

### Meeting Capture And Processing

1. User enters meeting title.
2. Chooses native system+mic or mic fallback.
3. Starts capture.
4. Active capture state appears.
5. User stops or stops + processes.
6. Meeting appears in Meetings.
7. Extraction creates tasks, decisions, commitments, relationships, and suggestions.

Design should make state transitions clear.

### Meeting Bot Capture

1. User configures Recall/fake provider outside or through env.
2. User enters meeting title/link.
3. User confirms capture is allowed/disclosed.
4. Bot joins visibly.
5. User syncs session.
6. User processes transcript when ready.

Design should emphasize consent and provider/cost status.

### Suggestion Confirmation To Draft

1. User sees follow-up suggestion.
2. User reviews reason/source/context.
3. User confirms.
4. App creates or reuses local follow-up draft.
5. Draft Review selects the draft.
6. User edits recipient/subject/body.
7. User optionally creates Gmail draft.
8. No email is sent automatically.

Design should make this loop beautiful and trustworthy.

### Notification Review

1. User sees notification candidate or receives a local notification.
2. User taps notification or clicks Review.
3. App opens Suggestions.
4. Related suggestion is highlighted.
5. If local draft exists, Draft Review selects it.
6. If related task exists, task is highlighted.
7. No action is executed automatically.

Design should make "review, then act" clear.

### Person/Project Review

1. User clicks context chip or assistant graph answer.
2. Context review panel opens.
3. User sees related contexts, decisions, tasks, meetings, suggestions, drafts.
4. User opens related meeting/task/suggestion/draft.

Design should make this feel like opening a memory file for a person/project/topic.

### Export/Wipe

1. User opens Settings.
2. User reviews local data counts and disclosures.
3. User exports local data to zip.
4. User may wipe local data only with exact confirmation phrase.

Design should treat wipe as serious and isolated.

## States That Need Good Design

Design must cover these states:

- connected backend;
- disconnected backend;
- backend starting;
- manually started backend;
- app-managed backend;
- loading/refreshing;
- partial API failure;
- empty tasks;
- empty suggestions;
- empty meetings;
- active recording;
- capture permission unavailable;
- notification permission not determined;
- notification permission denied/error;
- OpenAI key missing;
- Google not configured;
- Recall not configured;
- local draft created;
- Gmail draft created;
- suggestion accepted;
- suggestion snoozed;
- suggestion dismissed;
- suggestion retired;
- task highlighted from notification/context;
- context detail selected;
- no context detail selected;
- pending confirmation exists;
- dangerous wipe confirmation not typed;
- export complete;
- log/debug details available.

## UX Copy Tone

Tone should be:

- calm;
- direct;
- plain-language;
- slightly warm;
- not cute;
- not magical;
- not overpromising autonomy.

Example good copy:

- "Review before creating a Gmail draft."
- "This suggestion is based on unresolved follow-up work from Friday's meeting."
- "SpeedwagonAI stores this key in your Mac Keychain."
- "Notifications open review only. They never complete tasks or send email."

Avoid copy like:

- "AI supercharges your productivity."
- "Let SpeedwagonAI handle everything."
- "Autopilot your work."
- vague hype.

## Interaction Requirements

Use familiar Mac controls:

- sidebar navigation;
- toolbar buttons;
- segmented controls for capture mode;
- checkboxes/toggles for consent and binary settings;
- text fields for meeting title/link/repo path;
- secure field for API key;
- list/detail layout for meetings;
- editable composer for drafts;
- badges/chips for status/counts;
- confirmation buttons for risky actions;
- destructive styling for wipe only.

Use SF Symbols in buttons and navigation where possible.

Avoid custom metaphors that are hard to implement in SwiftUI.

## Button Hierarchy

Primary actions:

- Run assistant command;
- Start capture;
- Stop + Process;
- Confirm suggestion;
- Review notification/suggestion;
- Save local draft;
- Create Gmail Draft;
- Check Readiness.

Secondary actions:

- Refresh;
- Snooze;
- Dismiss;
- Mark Delivered;
- Open related item;
- Sync Calendar;
- Sync bot session;
- Process bot session when ready.

Destructive:

- Wipe Local Data.

Do not make "Dismiss" or "Wipe" visually compete with primary work actions.

## Suggested Redesign Deliverables

Please produce:

1. A full native Mac app information architecture proposal.
2. A redesigned main window layout.
3. A redesigned Assistant/Home screen.
4. A redesigned Suggestions + Draft Review flow.
5. A redesigned Task Inbox.
6. A redesigned Meeting detail view.
7. A redesigned Context Review panel/drawer.
8. A redesigned Settings/onboarding/readiness screen.
9. A command palette design.
10. A notification review design.
11. A visual style guide:
    - colors;
    - typography;
    - spacing;
    - panels;
    - chips/badges;
    - buttons;
    - empty/error/loading states.
12. SwiftUI implementation guidance:
    - component names;
    - layout strategy;
    - reusable primitives;
    - where to use lists, grids, drawers, split views, sheets, and toolbars.

## Suggested Visual System

This is guidance, not a hard requirement:

- keep a muted green/teal accent, but introduce a more balanced neutral palette;
- use semantic colors for risk/overdue/waiting/snoozed/done;
- prefer subtle bordered surfaces over heavy cards;
- use 8px or less corner radius unless native controls dictate otherwise;
- keep typography compact and native:
  - large section title only at top-level;
  - panel titles smaller;
  - row text readable;
  - metadata clearly secondary;
- preserve dark mode first, but ensure light mode is clean.

## Current Pain Points To Solve

- Assistant screen is overloaded with too many panels.
- Suggestions and tasks can feel visually repetitive.
- Draft Review is functional but could be more obviously tied to selected suggestion.
- Context Review is powerful but currently appears as another panel below content; it may deserve a right-side drawer or inspector.
- Settings contains necessary disclosures but feels like a long stack.
- Notification permission errors need friendlier handling.
- Local paths appear in some ordinary surfaces where they are more debug than workflow.
- The current UI is useful but still has a developer-tool feel.

## Things Not To Add In This Redesign

Do not design new product scope that implies:

- Apple Reminders integration;
- Calendar writes;
- automatic email sending;
- autonomous task completion;
- background daemon/Launch Agent;
- auto-update;
- bundled Python runtime;
- cloud account system;
- team/collaboration features;
- new external integrations;
- public SaaS onboarding;
- a marketing landing page.

## What The App Should Feel Like After Redesign

It should feel like a polished private-beta Mac utility that sits between:

- Things/OmniFocus for operational task trust;
- Spotlight/Raycast for command speed;
- Apple Notes/Calendar for native familiarity;
- a lightweight CRM memory file for people/projects;
- a careful assistant that asks before acting.

The user should open it and immediately understand:

- what needs attention;
- why SpeedwagonAI thinks so;
- what evidence/source backs it;
- what will happen if they confirm;
- what data stays local;
- what actions touch external services.

## Implementation Context

Frontend is SwiftUI under:

```text
native/SpeedwagonAI/Sources/SpeedwagonAI/
native/SpeedwagonAI/Sources/SpeedwagonAICore/
```

Primary UI file today:

```text
native/SpeedwagonAI/Sources/SpeedwagonAI/ContentView.swift
```

Current app state object:

```text
native/SpeedwagonAI/Sources/SpeedwagonAI/AppState.swift
```

Current shared theme:

```text
native/SpeedwagonAI/Sources/SpeedwagonAI/SpeedwagonTheme.swift
```

Current API models:

```text
native/SpeedwagonAI/Sources/SpeedwagonAICore/Models.swift
```

Backend is local HTTP at:

```text
http://127.0.0.1:8765
```

Local API uses bearer token auth. Native app obtains/manages local token and OpenAI key through Keychain/local beta flows.

## Existing Native Sections And SF Symbols

Current section enum:

```text
Assistant      sparkle.magnifyingglass
Capture        waveform
Meetings       rectangle.stack
Calendar       calendar
Notifications  bell
Tasks          checklist
Suggestions    lightbulb
Commitments    person.2
Settings       gearshape
Roadmap        map
```

These can be adjusted visually, but the redesign should not require backend changes.

## Recommended First Screen

The first screen should be the actual work surface, not a landing page. Prefer:

- compact assistant command bar at top;
- "Attention" or "Today" stack showing overdue, waiting, follow-ups, pending confirmations;
- top suggestions with review/confirm;
- upcoming/capture entry points;
- recent context/meeting prep.

The first screen should hint at the rest of the app but not show every panel at full size.

## Final Instruction For Claude Design

Design a native Mac beta UI for the existing SpeedwagonAI product. Preserve the local-first, confirmation-first behavior. Make the app feel trustworthy, operational, and polished. Improve hierarchy before adding ornament. Treat suggestions, context review, and draft review as the core product loop. Do not add new external integrations or autonomous actions.
