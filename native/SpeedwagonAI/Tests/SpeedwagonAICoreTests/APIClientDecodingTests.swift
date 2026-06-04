import XCTest
@testable import SpeedwagonAICore

final class APIClientDecodingTests: XCTestCase {
    func testDecodesTaskListResponse() throws {
        let json = """
        {
          "tasks": [
            {
              "id": 12,
              "text": "Send notes",
              "owner": "Anish",
              "owed_to": "Alex",
              "project": "Onboarding",
              "due_date": "2026-06-01",
              "status": "open",
              "source": "manual",
              "source_type": "manual",
              "source_meeting_id": 3,
              "meeting_title": "Planning",
              "reminder_suggestion": "This is due today. Confirm status or follow up.",
              "is_overdue": false,
              "contexts": [
                {
                  "id": 2,
                  "name": "Onboarding",
                  "normalized_name": "onboarding",
                  "kind": "project",
                  "confidence": 1.0,
                  "reason": "explicit task project"
                }
              ],
              "created_at": "2026-05-31T10:00:00Z",
              "updated_at": "2026-05-31T10:00:00Z"
            }
          ]
        }
        """.data(using: .utf8)!

        let response = try SpeedwagonJSON.decoder.decode(TaskListResponse.self, from: json)

        XCTAssertEqual(response.tasks.count, 1)
        XCTAssertEqual(response.tasks[0].id, 12)
        XCTAssertEqual(response.tasks[0].owedTo, "Alex")
        XCTAssertEqual(response.tasks[0].project, "Onboarding")
        XCTAssertEqual(response.tasks[0].dueDate, "2026-06-01")
        XCTAssertEqual(response.tasks[0].sourceType, "manual")
        XCTAssertEqual(response.tasks[0].sourceMeetingId, 3)
        XCTAssertEqual(response.tasks[0].meetingTitle, "Planning")
        XCTAssertEqual(response.tasks[0].contexts?.first?.name, "Onboarding")
    }

    func testDecodesContextGraphAndSuggestions() throws {
        let graphJSON = """
        {
          "query": "DairyMGT",
          "contexts": [
            {
              "id": 4,
              "name": "DairyMGT",
              "normalized_name": "dairymgt",
              "kind": "project",
              "confidence": 1.0,
              "reason": "explicit task project"
            }
          ],
          "tasks": [
            {
              "id": 9,
              "text": "Email Megan about DairyMGT",
              "project": "DairyMGT",
              "due_date": null,
              "status": "open",
              "source": "manual",
              "contexts": [
                {
                  "id": 4,
                  "name": "DairyMGT",
                  "kind": "project"
                }
              ]
            }
          ],
          "meetings": [],
          "suggestions": [
            {
              "id": 6,
              "title": "Draft follow-up for DairyMGT",
              "reason": "All other open work linked to DairyMGT appears resolved.",
              "status": "open",
              "confidence": 0.82,
              "context_id": 4,
              "context_name": "DairyMGT",
              "context_kind": "project",
              "context": {
                "id": 4,
                "name": "DairyMGT",
                "kind": "project"
              },
              "proposed_action": "draft_email_from_context",
              "payload": { "context_id": 4, "task_id": 9 },
              "task_ids": [8, 9],
              "meeting_ids": [],
              "source_fingerprint": "draft_email_from_context|context:4|tasks:8,9",
              "retired_at": null,
              "next_notify_at": "2026-06-04",
              "last_notified_at": null,
              "notification_reason": "Related work looks ready for follow-up.",
              "notification_status": "candidate",
              "snoozed_until": null,
              "created_at": "2026-06-04T10:00:00Z",
              "updated_at": "2026-06-04T10:00:00Z"
            }
          ]
        }
        """.data(using: .utf8)!

        let graph = try SpeedwagonJSON.decoder.decode(ContextGraphResponse.self, from: graphJSON)

        XCTAssertEqual(graph.contexts.first?.name, "DairyMGT")
        XCTAssertEqual(graph.tasks.first?.contexts?.first?.name, "DairyMGT")
        XCTAssertEqual(graph.suggestions.first?.displayContext, "DairyMGT")

        let listJSON = """
        {
          "suggestions": [
            {
              "id": 6,
              "title": "Draft follow-up for DairyMGT",
              "reason": "All other open work linked to DairyMGT appears resolved.",
              "status": "open",
              "confidence": 0.82,
              "context_id": 4,
              "context_name": "DairyMGT",
              "context_kind": "project",
              "context": {
                "id": 4,
                "name": "DairyMGT",
                "kind": "project"
              },
              "proposed_action": "draft_email_from_context",
              "payload": { "context_id": 4, "task_id": 9 },
              "task_ids": [8, 9],
              "meeting_ids": [],
              "source_fingerprint": "draft_email_from_context|context:4|tasks:8,9",
              "retired_at": null,
              "next_notify_at": "2026-06-04",
              "last_notified_at": null,
              "notification_reason": "Related work looks ready for follow-up.",
              "notification_status": "candidate",
              "snoozed_until": null,
              "created_at": "2026-06-04T10:00:00Z",
              "updated_at": "2026-06-04T10:00:00Z"
            }
          ]
        }
        """.data(using: .utf8)!

        let list = try SpeedwagonJSON.decoder.decode(SuggestionListResponse.self, from: listJSON)

        XCTAssertEqual(list.suggestions.first?.proposedAction, "draft_email_from_context")
        XCTAssertEqual(list.suggestions.first?.taskIds, [8, 9])
        XCTAssertEqual(list.suggestions.first?.notificationStatus, "candidate")
        XCTAssertEqual(list.suggestions.first?.notificationReason, "Related work looks ready for follow-up.")
    }

    func testDecodesNotificationPayloads() throws {
        let statusJSON = """
        {
          "enabled": true,
          "delivery": "native_app",
          "runtime": "while_app_running",
          "permission_owner": "native",
          "candidate_count": 2,
          "delivered_count": 1,
          "dismissed_count": 0,
          "snoozed_count": 1,
          "note": "Native notifications are scheduled by the Mac app while it is running."
        }
        """.data(using: .utf8)!
        let candidatesJSON = """
        {
          "candidates": [
            {
              "id": 12,
              "title": "Review overdue task #4",
              "reason": "This task is overdue.",
              "status": "open",
              "confidence": 0.85,
              "context_id": null,
              "context_name": null,
              "context_kind": null,
              "context": null,
              "proposed_action": "search_tasks",
              "payload": { "task_id": 4 },
              "task_ids": [4],
              "meeting_ids": [],
              "source_fingerprint": "search_tasks|tasks:4",
              "next_notify_at": "2026-06-04",
              "last_notified_at": "2026-06-04T10:00:00Z",
              "notification_reason": "This work is overdue and needs a decision.",
              "notification_status": "delivered"
            }
          ]
        }
        """.data(using: .utf8)!
        let deliveredJSON = """
        {
          "suggestion": {
            "id": 12,
            "title": "Review overdue task #4",
            "reason": "This task is overdue.",
            "status": "open",
            "confidence": 0.85,
            "context_id": null,
            "context_name": null,
            "context_kind": null,
            "context": null,
            "proposed_action": "search_tasks",
            "payload": { "task_id": 4 },
            "task_ids": [4],
            "meeting_ids": [],
            "notification_status": "delivered"
          },
          "notification": {
            "id": 7,
            "suggestion_id": 12,
            "source_fingerprint": "search_tasks|tasks:4",
            "scheduled_at": "2026-06-04",
            "delivered_at": "2026-06-04T10:00:00Z",
            "status": "delivered",
            "reason": "This work is overdue and needs a decision.",
            "action_taken": "delivered",
            "created_at": "2026-06-04T10:00:00Z",
            "updated_at": "2026-06-04T10:00:00Z"
          }
        }
        """.data(using: .utf8)!

        let status = try SpeedwagonJSON.decoder.decode(NotificationStatusResponse.self, from: statusJSON)
        let candidates = try SpeedwagonJSON.decoder.decode(NotificationCandidateListResponse.self, from: candidatesJSON)
        let delivered = try SpeedwagonJSON.decoder.decode(NotificationEnvelope.self, from: deliveredJSON)

        XCTAssertEqual(status.candidateCount, 2)
        XCTAssertEqual(status.permissionOwner, "native")
        XCTAssertEqual(candidates.candidates.first?.notificationStatus, "delivered")
        XCTAssertEqual(delivered.notification?.suggestionId, 12)
    }

    func testDecodesAssistantCommandResponse() throws {
        let json = """
        {
          "supported": true,
          "action": "list_overdue_tasks",
          "category": "tasks",
          "requires_confirmation": false,
          "payload": {},
          "confidence": 0.99,
          "pending_action_id": null,
          "explanation": "Rules parser matched.",
          "safety_notes": [],
          "source": "rules",
          "summary": "Found 1 task.",
          "command": "what is overdue",
          "result": {
            "tasks": [
              {
                "id": 4,
                "text": "Follow up",
                "owner": null,
                "due_date": "2026-05-30",
                "status": "open",
                "source": "manual",
                "reminder_suggestion": "This was due 1 day ago. Confirm complete or follow up.",
                "is_overdue": true
              }
            ]
          }
        }
        """.data(using: .utf8)!

        let response = try SpeedwagonJSON.decoder.decode(AssistantCommandResponse.self, from: json)

        XCTAssertTrue(response.supported)
        XCTAssertEqual(response.action, "list_overdue_tasks")
        XCTAssertEqual(response.category, "tasks")
        XCTAssertEqual(response.requiresConfirmation, false)
        XCTAssertEqual(response.confidence, 0.99)
        XCTAssertEqual(response.explanation, "Rules parser matched.")
        XCTAssertEqual(response.source, "rules")
        XCTAssertEqual(response.result?.tasks?.first?.id, 4)
        XCTAssertEqual(response.summary, "Found 1 task.")
    }

    func testDecodesPendingAssistantActionResponse() throws {
        let json = """
        {
          "supported": true,
          "action": "add_task",
          "category": "tasks",
          "requires_confirmation": true,
          "payload": { "text": "Send recap" },
          "confidence": 0.82,
          "pending_action_id": 14,
          "explanation": "Mapped to task creation.",
          "safety_notes": ["Mutating interpreted actions require confirmation."],
          "source": "llm",
          "summary": "Ready to run add_task. Confirm pending action 14 to continue.",
          "command": "remind me to send recap",
          "result": {
            "pending_action": {
              "id": 14,
              "command": "remind me to send recap",
              "action": "add_task",
              "category": "tasks",
              "payload": { "text": "Send recap" },
              "confidence": 0.82,
              "source": "llm",
              "explanation": "Mapped to task creation.",
              "safety_notes": ["Mutating interpreted actions require confirmation."],
              "status": "pending",
              "created_at": "2026-06-03T10:00:00Z",
              "updated_at": "2026-06-03T10:00:00Z",
              "expires_at": null
            }
          }
        }
        """.data(using: .utf8)!

        let response = try SpeedwagonJSON.decoder.decode(AssistantCommandResponse.self, from: json)

        XCTAssertTrue(response.requiresConfirmation == true)
        XCTAssertEqual(response.pendingActionId, 14)
        XCTAssertEqual(response.result?.pendingAction?.id, 14)
        XCTAssertEqual(response.result?.pendingAction?.status, "pending")
    }

    func testDecodesAssistantCapabilitiesResponse() throws {
        let json = """
        {
          "capabilities": [
            {
              "category": "brief",
              "command": "daily brief",
              "description": "Show what needs attention today."
            },
            {
              "category": "meetings",
              "command": "show unprocessed meetings",
              "description": "List meetings that still need processing."
            }
          ]
        }
        """.data(using: .utf8)!

        let response = try SpeedwagonJSON.decoder.decode(AssistantCapabilitiesResponse.self, from: json)

        XCTAssertEqual(response.capabilities.count, 2)
        XCTAssertEqual(response.capabilities[0].id, "brief:daily brief")
        XCTAssertEqual(response.capabilities[1].category, "meetings")
    }

    func testDecodesAssistantResultWithMeetingsDraftAndDailyBriefFields() throws {
        let json = """
        {
          "supported": true,
          "action": "daily_brief",
          "category": "brief",
          "requires_confirmation": false,
          "payload": {},
          "summary": "Here is today's brief.",
          "result": {
            "date": "2026-06-03",
            "counts": { "overdue": 1, "today": 1 },
            "overdue": [
              {
                "id": 7,
                "text": "Send recap",
                "owner": "Anish",
                "due_date": "2026-06-01",
                "status": "open",
                "source": "meeting",
                "is_overdue": true
              }
            ],
            "today": [],
            "upcoming": [],
            "waiting": [],
            "snoozed": [],
            "uncertain": [],
            "stale": [],
            "unscheduled": [],
            "recommended_followups": [],
            "meetings": [
              {
                "id": 8,
                "title": "Weekly Planning",
                "started_at": "2026-06-03T09:00:00",
                "ended_at": null,
                "audio_path": "audio/meeting-8.wav",
                "transcript_path": null,
                "note_path": null,
                "summary": null
              }
            ],
            "draft": {
              "subject": "Follow-up from Weekly Planning",
              "body": "Thanks for the time today.",
              "tone": "warm",
              "provider": "openai",
              "included_items": ["action_items"],
              "to": "alex@example.com"
            }
          }
        }
        """.data(using: .utf8)!

        let response = try SpeedwagonJSON.decoder.decode(AssistantCommandResponse.self, from: json)

        XCTAssertEqual(response.result?.overdue?.first?.id, 7)
        XCTAssertEqual(response.result?.meetings?.first?.title, "Weekly Planning")
        XCTAssertEqual(response.result?.draft?.subject, "Follow-up from Weekly Planning")
        XCTAssertEqual(response.result?.counts?["overdue"], 1)
    }

    func testDecodesMeetingListDetailAndProcessResponses() throws {
        let listJSON = """
        {
          "meetings": [
            {
              "id": 13,
              "title": "testMeet",
              "started_at": "2026-06-04T09:00:00",
              "ended_at": "2026-06-04T09:30:00",
              "audio_path": null,
              "transcript_path": "transcripts/bot-1.txt",
              "note_path": "notes/testmeet.md",
              "summary": "Discussed next steps.",
              "source_type": "meeting_bot"
            }
          ]
        }
        """.data(using: .utf8)!

        let list = try SpeedwagonJSON.decoder.decode(MeetingListResponse.self, from: listJSON)

        XCTAssertEqual(list.meetings.first?.id, 13)
        XCTAssertEqual(list.meetings.first?.sourceType, "meeting_bot")

        let detailJSON = """
        {
          "meeting": {
            "id": 13,
            "title": "testMeet",
            "started_at": "2026-06-04T09:00:00",
            "ended_at": "2026-06-04T09:30:00",
            "audio_path": null,
            "transcript_path": "transcripts/bot-1.txt",
            "note_path": "notes/testmeet.md",
            "summary": "Discussed next steps.",
            "source_type": "meeting_bot"
          },
          "action_items": [
            {"id": 1, "meeting_id": 13, "text": "Send update", "owner": null, "deadline": "2026-06-08", "status": "open"}
          ],
          "commitments": [],
          "decisions": [
            {"id": 2, "meeting_id": 13, "text": "Use native app"}
          ],
          "open_questions": [],
          "key_topics": [
            {"id": 3, "meeting_id": 13, "topic": "project update"}
          ],
          "entities": [
            {"id": 4, "meeting_id": 13, "name": "Megan"}
          ],
          "email_drafts": [],
          "transcript": "Speaker 1: Send update."
        }
        """.data(using: .utf8)!

        let detail = try SpeedwagonJSON.decoder.decode(MeetingDetailResponse.self, from: detailJSON)

        XCTAssertEqual(detail.actionItems.first?.displayText, "Send update")
        XCTAssertEqual(detail.keyTopics.first?.displayText, "project update")
        XCTAssertEqual(detail.entities.first?.displayText, "Megan")
        XCTAssertEqual(detail.transcript, "Speaker 1: Send update.")

        let processJSON = """
        {
          "meeting": {
            "id": 13,
            "title": "testMeet",
            "started_at": "2026-06-04T09:00:00",
            "ended_at": "2026-06-04T09:30:00",
            "audio_path": null,
            "transcript_path": "transcripts/bot-1.txt",
            "note_path": "notes/testmeet.md",
            "summary": "Discussed next steps.",
            "source_type": "meeting_bot"
          },
          "transcript_path": "transcripts/bot-1.txt",
          "note_path": "notes/testmeet.md",
          "commitments_path": "notes/commitments.md"
        }
        """.data(using: .utf8)!

        let processed = try SpeedwagonJSON.decoder.decode(MeetingProcessResponse.self, from: processJSON)

        XCTAssertEqual(processed.meeting.id, 13)
        XCTAssertEqual(processed.notePath, "notes/testmeet.md")
    }

    func testDecodesDailyBriefResponse() throws {
        let json = """
        {
          "date": "2026-06-03",
          "overdue": [],
          "today": [],
          "upcoming": [],
          "waiting": [],
          "snoozed": [],
          "uncertain": [],
          "stale": [],
          "unscheduled": [],
          "recommended_followups": [],
          "calendar_today": [
            {
              "id": 1,
              "provider": "google",
              "provider_event_id": "event-1",
              "calendar_id": "primary",
              "title": "DairyMGT review",
              "start_at": "2026-06-03T10:00:00-07:00",
              "end_at": "2026-06-03T10:30:00-07:00",
              "attendees": [
                { "email": "megan@example.com", "display_name": "Megan", "response_status": "accepted" }
              ]
            }
          ],
          "calendar_upcoming": [],
          "meeting_prep": [
            {
              "event": {
                "id": 1,
                "title": "DairyMGT review",
                "start_at": "2026-06-03T10:00:00-07:00",
                "end_at": "2026-06-03T10:30:00-07:00"
              },
              "query": "DairyMGT Megan",
              "contexts": [],
              "tasks": [],
              "meetings": [],
              "decisions": []
            }
          ],
          "notification_candidates": [
            {
              "id": 12,
              "title": "Review overdue task #4",
              "reason": "This task is overdue.",
              "status": "open",
              "confidence": 0.85,
              "context_id": null,
              "context_name": null,
              "context_kind": null,
              "context": null,
              "proposed_action": "search_tasks",
              "payload": { "task_id": 4 },
              "task_ids": [4],
              "meeting_ids": [],
              "notification_reason": "This work is overdue and needs a decision.",
              "notification_status": "candidate"
            }
          ],
          "counts": {
            "overdue": 0,
            "today": 0,
            "waiting": 0,
            "notification_candidates": 1
          }
        }
        """.data(using: .utf8)!

        let response = try SpeedwagonJSON.decoder.decode(DailyBriefResponse.self, from: json)

        XCTAssertEqual(response.date, "2026-06-03")
        XCTAssertEqual(response.counts["today"], 0)
        XCTAssertTrue(response.recommendedFollowups.isEmpty)
        XCTAssertEqual(response.calendarToday?.first?.title, "DairyMGT review")
        XCTAssertEqual(response.calendarToday?.first?.attendees?.first?.displayName, "Megan")
        XCTAssertEqual(response.meetingPrep?.first?.query, "DairyMGT Megan")
        XCTAssertEqual(response.notificationCandidates?.first?.notificationStatus, "candidate")
    }

    func testDecodesCalendarResponses() throws {
        let statusJSON = """
        {
          "enabled": true,
          "provider": "google",
          "status": "configured",
          "note": "Google Calendar read-only sync is configured.",
          "credentials_present": true,
          "token_present": true,
          "calendar_scope_present": true,
          "calendar_ids": ["primary"],
          "sync_days_back": 14,
          "sync_days_forward": 30
        }
        """.data(using: .utf8)!
        let eventsJSON = """
        {
          "events": [
            {
              "id": 2,
              "provider": "google",
              "provider_event_id": "event-2",
              "calendar_id": "primary",
              "title": "Planning",
              "description_snippet": "Discuss next steps",
              "start_at": "2026-06-04T09:00:00-07:00",
              "end_at": "2026-06-04T09:30:00-07:00",
              "meeting_url": "https://meet.google.com/abc-defg-hij",
              "attendees": [],
              "last_synced_at": "2026-06-04T10:00:00Z"
            }
          ]
        }
        """.data(using: .utf8)!
        let syncJSON = """
        {
          "status": "synced",
          "provider": "google",
          "calendar_ids": ["primary"],
          "time_min": "2026-05-21T00:00:00Z",
          "time_max": "2026-07-04T00:00:00Z",
          "synced_count": 1,
          "events": [
            {
              "id": 2,
              "title": "Planning",
              "start_at": "2026-06-04T09:00:00-07:00",
              "end_at": "2026-06-04T09:30:00-07:00"
            }
          ]
        }
        """.data(using: .utf8)!

        let status = try SpeedwagonJSON.decoder.decode(CalendarStatusResponse.self, from: statusJSON)
        let events = try SpeedwagonJSON.decoder.decode(CalendarEventListResponse.self, from: eventsJSON)
        let sync = try SpeedwagonJSON.decoder.decode(CalendarSyncResponse.self, from: syncJSON)

        XCTAssertTrue(status.enabled)
        XCTAssertEqual(status.calendarIds, ["primary"])
        XCTAssertEqual(events.events.first?.meetingUrl, "https://meet.google.com/abc-defg-hij")
        XCTAssertEqual(sync.syncedCount, 1)
    }

    func testDecodesSettingsResponse() throws {
        let json = """
        {
          "db_path": "data/speedwagon.db",
          "notes_dir": "notes",
          "audio_dir": "audio",
          "transcripts_dir": "transcripts",
          "openai_key_present": true,
          "cheap_model": "gpt-cheap",
          "strong_model": "gpt-strong",
          "command_model": "gpt-command",
          "vision_model": "gpt-vision",
          "web_model": "gpt-web",
          "model_cost_labels": {
            "command_parse": "low",
            "vision_context": "medium",
            "web_search": "high"
          },
          "web_search_enabled": false,
          "gmail_credentials_present": true,
          "gmail_token_present": false,
          "capture_profile": "mic",
          "input_device": null,
          "recorder_status": "available",
          "capture_note": "Mic mode records microphone input."
        }
        """.data(using: .utf8)!

        let response = try SpeedwagonJSON.decoder.decode(SettingsResponse.self, from: json)

        XCTAssertEqual(response.captureProfile, "mic")
        XCTAssertEqual(response.recorderStatus, "available")
        XCTAssertEqual(response.gmailTokenPresent, false)
        XCTAssertEqual(response.commandModel, "gpt-command")
        XCTAssertEqual(response.visionModel, "gpt-vision")
        XCTAssertEqual(response.modelCostLabels?["web_search"], "high")
        XCTAssertEqual(response.webSearchEnabled, false)
    }

    func testDecodesPendingActionsAndScreenshotAnalysis() throws {
        let pendingJSON = """
        {
          "actions": [
            {
              "id": 21,
              "command": "screenshot analysis",
              "action": "add_task",
              "category": "tasks",
              "payload": { "text": "Review visible checklist" },
              "confidence": 0.74,
              "source": "screenshot",
              "explanation": "Suggested from screenshot context.",
              "safety_notes": ["Confirm before creating."],
              "status": "pending",
              "created_at": "2026-06-03T10:00:00Z",
              "updated_at": "2026-06-03T10:00:00Z",
              "expires_at": null
            }
          ]
        }
        """.data(using: .utf8)!

        let pending = try SpeedwagonJSON.decoder.decode(PendingActionListResponse.self, from: pendingJSON)

        XCTAssertEqual(pending.actions.first?.id, 21)
        XCTAssertEqual(pending.actions.first?.source, "screenshot")

        let screenshotJSON = """
        {
          "summary": "A checklist is visible.",
          "visible_text": ["Review visible checklist"],
          "suggested_tasks": [
            {
              "text": "Review visible checklist",
              "due_date": null,
              "owner": null,
              "project": "SpeedwagonAI",
              "confidence": 0.74
            }
          ],
          "suggested_context_topics": ["checklist"],
          "suggested_actions": [],
          "pending_actions": [
            {
              "id": 21,
              "command": "screenshot analysis",
              "action": "add_task",
              "category": "tasks",
              "payload": { "text": "Review visible checklist" },
              "confidence": 0.74,
              "source": "screenshot",
              "explanation": "Suggested from screenshot context.",
              "safety_notes": ["Confirm before creating."],
              "status": "pending",
              "created_at": "2026-06-03T10:00:00Z",
              "updated_at": "2026-06-03T10:00:00Z",
              "expires_at": null
            }
          ],
          "confidence": 0.74,
          "provider": "openai"
        }
        """.data(using: .utf8)!

        let screenshot = try SpeedwagonJSON.decoder.decode(ScreenshotAnalysisResponse.self, from: screenshotJSON)

        XCTAssertEqual(screenshot.summary, "A checklist is visible.")
        XCTAssertEqual(screenshot.suggestedTasks.first?.project, "SpeedwagonAI")
        XCTAssertEqual(screenshot.pendingActions.first?.id, 21)
    }

    func testDecodesCommitmentListResponse() throws {
        let json = """
        {
          "items": [
            {
              "id": 5,
              "text": "Review roadmap",
              "owner": "Anish",
              "due_date": null,
              "status": "waiting",
              "source": "meeting",
              "kind": "commitment"
            }
          ],
          "commitments": [
            {
              "id": 5,
              "text": "Review roadmap",
              "owner": "Anish",
              "due_date": null,
              "status": "waiting",
              "source": "meeting",
              "kind": "commitment"
            }
          ]
        }
        """.data(using: .utf8)!

        let response = try SpeedwagonJSON.decoder.decode(CommitmentListResponse.self, from: json)

        XCTAssertEqual(response.items.first?.status, "waiting")
        XCTAssertEqual(response.commitments?.first?.kind, "commitment")
    }

    func testDecodesCaptureStatusAndDiagnostics() throws {
        let statusJSON = """
        {
          "active": true,
          "native": true,
          "status": "recording",
          "session_id": "native-meeting-8",
          "kind": "meeting",
          "mode": "system_mic",
          "title": "Weekly Planning",
          "meeting_id": 8,
          "pid": 12345,
          "audio_path": "audio/meeting-8.wav",
          "system_audio_path": "audio/meeting-8-system.wav",
          "microphone_audio_path": "audio/meeting-8-mic.wav",
          "log_path": "data/recording-meeting-8.log",
          "command": ["rec", "-c", "1", "audio/meeting-8.wav"],
          "capture_profile": "native_screencapturekit",
          "input_device": "",
          "started_at": "2026-06-03T09:00:00",
          "warnings": ["mic unavailable"],
          "file_size": 5000,
          "output_file_ok": true,
          "log_tail": "ok",
          "last_error": null
        }
        """.data(using: .utf8)!

        let status = try SpeedwagonJSON.decoder.decode(CaptureSession.self, from: statusJSON)

        XCTAssertTrue(status.isActive)
        XCTAssertTrue(status.isNative)
        XCTAssertEqual(status.sessionId, "native-meeting-8")
        XCTAssertEqual(status.kind, "meeting")
        XCTAssertEqual(status.mode, "system_mic")
        XCTAssertEqual(status.meetingId, 8)
        XCTAssertEqual(status.systemAudioPath, "audio/meeting-8-system.wav")
        XCTAssertEqual(status.microphoneAudioPath, "audio/meeting-8-mic.wav")
        XCTAssertEqual(status.warnings?.first, "mic unavailable")
        XCTAssertEqual(status.fileSize, 5000)

        let diagnosticsJSON = """
        {
          "capture_profile": "mic",
          "input_device": "",
          "record_cmd": "",
          "tools": {
            "afrecord": null,
            "rec": "/opt/homebrew/bin/rec",
            "ffmpeg": null
          },
          "recorder_status": "available",
          "recorder_command_preview": "/opt/homebrew/bin/rec -c 1 audio/doctor-preview.wav",
          "active_session": {
            "active": false
          },
          "native_capture": {
            "active": false,
            "native": true,
            "status": "completed",
            "session_id": "native-meeting-8"
          },
          "native_capture_note": "Native meeting capture uses ScreenCaptureKit.",
          "recent_log_tail": "",
          "output_file_ok": false,
          "warnings": ["Mic mode records your selected/default microphone only."],
          "smoke_test_hint": "Run speedwagon capture doctor --smoke-test"
        }
        """.data(using: .utf8)!

        let diagnostics = try SpeedwagonJSON.decoder.decode(CaptureDiagnostics.self, from: diagnosticsJSON)

        XCTAssertEqual(diagnostics.captureProfile, "mic")
        XCTAssertEqual(diagnostics.tools["rec"] ?? nil, "/opt/homebrew/bin/rec")
        XCTAssertEqual(diagnostics.recorderStatus, "available")
        XCTAssertFalse(diagnostics.activeSession.isActive)
        XCTAssertEqual(diagnostics.nativeCapture?.sessionId, "native-meeting-8")
        XCTAssertEqual(diagnostics.nativeCaptureNote, "Native meeting capture uses ScreenCaptureKit.")
    }

    func testDecodesMeetingBotPayloads() throws {
        let statusJSON = """
        {
          "enabled": true,
          "provider": "recall",
          "status": "configured",
          "note": "Recall configured.",
          "requires_consent": true,
          "default_bot_name": "SpeedwagonAI Notetaker",
          "cloud_cost_label": "higher",
          "session_count": 1,
          "sessions": [
            {
              "id": 3,
              "provider": "recall",
              "provider_bot_id": "bot-123",
              "meeting_id": 9,
              "meeting_url_display": "https://meet.google.com/abc-defg-hij",
              "title": "Planning",
              "status": "transcript_ready",
              "join_at": null,
              "transcript_path": "transcripts/bot-3.txt",
              "raw_metadata_path": "data/bot_sessions/bot-session-3.json",
              "last_sync_at": "2026-06-04T10:00:00",
              "error": null,
              "consent_confirmed": true,
              "created_at": "2026-06-04T09:00:00",
              "updated_at": "2026-06-04T10:00:00",
              "meeting_title": "Planning",
              "meeting_summary": null,
              "meeting_transcript_path": "transcripts/bot-3.txt",
              "meeting_note_path": null,
              "transcript_ready": true,
              "processed": false
            }
          ]
        }
        """.data(using: .utf8)!

        let status = try SpeedwagonJSON.decoder.decode(BotStatusResponse.self, from: statusJSON)

        XCTAssertTrue(status.enabled)
        XCTAssertEqual(status.provider, "recall")
        XCTAssertEqual(status.sessions?.first?.displayTitle, "Planning")
        XCTAssertEqual(status.sessions?.first?.meetingUrlDisplay, "https://meet.google.com/abc-defg-hij")

        let processJSON = """
        {
          "session": {
            "id": 3,
            "provider": "recall",
            "provider_bot_id": "bot-123",
            "meeting_id": 9,
            "meeting_url_display": "https://meet.google.com/abc-defg-hij",
            "title": "Planning",
            "status": "processed",
            "consent_confirmed": true,
            "transcript_ready": true,
            "processed": true
          },
          "meeting": {
            "id": 9,
            "title": "Planning",
            "started_at": "2026-06-04T09:00:00",
            "ended_at": "2026-06-04T10:00:00",
            "audio_path": null,
            "transcript_path": "transcripts/bot-3.txt",
            "note_path": "notes/planning.md",
            "summary": "Discussed planning.",
            "source_type": "meeting_bot"
          },
          "transcript_path": "transcripts/bot-3.txt",
          "note_path": "notes/planning.md",
          "commitments_path": "notes/commitments.md"
        }
        """.data(using: .utf8)!

        let processed = try SpeedwagonJSON.decoder.decode(BotProcessResponse.self, from: processJSON)

        XCTAssertEqual(processed.session.status, "processed")
        XCTAssertEqual(processed.meeting.sourceType, "meeting_bot")
        XCTAssertEqual(processed.notePath, "notes/planning.md")
    }

    func testDecodesCaptureStopResponseWithProcessedMeeting() throws {
        let json = """
        {
          "session": {
            "active": false,
            "kind": "meeting",
            "title": "Weekly Planning",
            "meeting_id": 8,
            "audio_path": "audio/meeting-8.wav",
            "file_size": 5000,
            "output_file_ok": true
          },
          "meeting_id": 8,
          "meeting": {
            "id": 8,
            "title": "Weekly Planning",
            "started_at": "2026-06-03T09:00:00",
            "ended_at": "2026-06-03T09:30:00",
            "audio_path": "audio/meeting-8.wav",
            "transcript_path": "transcripts/meeting-8.txt",
            "note_path": "notes/weekly.md",
            "summary": "Discussed planning."
          },
          "transcript_path": "transcripts/meeting-8.txt",
          "note_path": "notes/weekly.md",
          "commitments_path": "notes/commitments.md"
        }
        """.data(using: .utf8)!

        let response = try SpeedwagonJSON.decoder.decode(CaptureStopResponse.self, from: json)

        XCTAssertEqual(response.session.kind, "meeting")
        XCTAssertEqual(response.meetingId, 8)
        XCTAssertEqual(response.meeting?.title, "Weekly Planning")
        XCTAssertEqual(response.notePath, "notes/weekly.md")
    }

    func testDecodesAssistantVoiceStopResponse() throws {
        let json = """
        {
          "session": {
            "active": false,
            "kind": "assistant_voice",
            "title": "Assistant voice message",
            "audio_path": "audio/assistant-voice.wav",
            "file_size": 5000,
            "output_file_ok": true
          },
          "audio_path": "audio/assistant-voice.wav",
          "transcript_path": "transcripts/assistant-voice.txt",
          "transcript": "what is overdue",
          "assistant_response": {
            "supported": true,
            "action": "list_overdue_tasks",
            "category": "tasks",
            "requires_confirmation": false,
            "payload": {},
            "summary": "No overdue tasks.",
            "command": "what is overdue",
            "result": {
              "tasks": []
            }
          }
        }
        """.data(using: .utf8)!

        let response = try SpeedwagonJSON.decoder.decode(AssistantVoiceStopResponse.self, from: json)

        XCTAssertEqual(response.session.kind, "assistant_voice")
        XCTAssertEqual(response.transcript, "what is overdue")
        XCTAssertEqual(response.assistantResponse.action, "list_overdue_tasks")
        XCTAssertEqual(response.transcriptPath, "transcripts/assistant-voice.txt")
    }
}
