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
          "counts": {
            "overdue": 0,
            "today": 0,
            "waiting": 0
          }
        }
        """.data(using: .utf8)!

        let response = try SpeedwagonJSON.decoder.decode(DailyBriefResponse.self, from: json)

        XCTAssertEqual(response.date, "2026-06-03")
        XCTAssertEqual(response.counts["today"], 0)
        XCTAssertTrue(response.recommendedFollowups.isEmpty)
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
          "kind": "meeting",
          "title": "Weekly Planning",
          "meeting_id": 8,
          "pid": 12345,
          "audio_path": "audio/meeting-8.wav",
          "log_path": "data/recording-meeting-8.log",
          "command": ["rec", "-c", "1", "audio/meeting-8.wav"],
          "capture_profile": "mic",
          "input_device": "",
          "started_at": "2026-06-03T09:00:00",
          "file_size": 5000,
          "output_file_ok": true,
          "log_tail": "ok",
          "last_error": null
        }
        """.data(using: .utf8)!

        let status = try SpeedwagonJSON.decoder.decode(CaptureSession.self, from: statusJSON)

        XCTAssertTrue(status.isActive)
        XCTAssertEqual(status.kind, "meeting")
        XCTAssertEqual(status.meetingId, 8)
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
