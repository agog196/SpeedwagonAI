import Foundation

public enum SpeedwagonJSON {
    public static var decoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    public static var encoder: JSONEncoder {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return encoder
    }
}

public struct TaskListResponse: Codable, Equatable {
    public let tasks: [TaskItem]
}

public struct TaskEnvelope: Codable, Equatable {
    public let task: TaskItem
}

public struct ClearDoneTasksResponse: Codable, Equatable {
    public let cleared: Int
}

public struct ClearSuggestionsResponse: Codable, Equatable {
    public let cleared: Int
}

public struct CommitmentListResponse: Codable, Equatable {
    public let items: [TaskItem]
    public let commitments: [TaskItem]?
}

public struct MeetingListResponse: Codable, Equatable {
    public let meetings: [MeetingItem]
}

public struct MeetingDetailResponse: Codable, Equatable {
    public let meeting: MeetingItem
    public let actionItems: [MeetingTextItem]
    public let commitments: [MeetingTextItem]
    public let decisions: [MeetingTextItem]
    public let openQuestions: [MeetingTextItem]
    public let keyTopics: [MeetingTextItem]
    public let entities: [MeetingTextItem]
    public let emailDrafts: [JSONValue]?
    public let transcript: String?
}

public struct MeetingProcessResponse: Codable, Equatable {
    public let meeting: MeetingItem
    public let transcriptPath: String?
    public let notePath: String?
    public let commitmentsPath: String?
}

public struct ContextItem: Codable, Identifiable, Equatable {
    public let id: Int
    public let name: String
    public let normalizedName: String?
    public let kind: String
    public let confidence: Double?
    public let reason: String?
    public let profileEmail: String?
    public let profilePhone: String?
    public let profileRole: String?
    public let profileCompany: String?
    public let profileNotes: String?
    public let createdAt: String?
    public let updatedAt: String?

    public init(
        id: Int,
        name: String,
        normalizedName: String? = nil,
        kind: String,
        confidence: Double? = nil,
        reason: String? = nil,
        profileEmail: String? = nil,
        profilePhone: String? = nil,
        profileRole: String? = nil,
        profileCompany: String? = nil,
        profileNotes: String? = nil,
        createdAt: String? = nil,
        updatedAt: String? = nil
    ) {
        self.id = id
        self.name = name
        self.normalizedName = normalizedName
        self.kind = kind
        self.confidence = confidence
        self.reason = reason
        self.profileEmail = profileEmail
        self.profilePhone = profilePhone
        self.profileRole = profileRole
        self.profileCompany = profileCompany
        self.profileNotes = profileNotes
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }
}

public struct ContextProfileUpdateRequest: Codable, Equatable {
    public let email: String?
    public let phone: String?
    public let role: String?
    public let company: String?
    public let notes: String?

    public init(
        email: String? = nil,
        phone: String? = nil,
        role: String? = nil,
        company: String? = nil,
        notes: String? = nil
    ) {
        self.email = email
        self.phone = phone
        self.role = role
        self.company = company
        self.notes = notes
    }
}

public struct ContextCreateRequest: Codable, Equatable {
    public let name: String
    public let kind: String?
    public let email: String?
    public let phone: String?
    public let role: String?
    public let company: String?
    public let notes: String?

    public init(
        name: String,
        kind: String? = "person",
        email: String? = nil,
        phone: String? = nil,
        role: String? = nil,
        company: String? = nil,
        notes: String? = nil
    ) {
        self.name = name
        self.kind = kind
        self.email = email
        self.phone = phone
        self.role = role
        self.company = company
        self.notes = notes
    }
}

public struct TaskItem: Codable, Identifiable, Equatable {
    public let id: Int
    public let text: String
    public let owner: String?
    public let owedTo: String?
    public let project: String?
    public let dueDate: String?
    public let status: String
    public let source: String?
    public let sourceType: String?
    public let kind: String?
    public let sourceMeetingId: Int?
    public let meetingId: Int?
    public let meetingTitle: String?
    public let reminderSuggestion: String?
    public let isOverdue: Bool?
    public let snoozedUntil: String?
    public let completedAt: String?
    public let createdAt: String?
    public let updatedAt: String?
    public let contexts: [ContextItem]?

    public init(
        id: Int,
        text: String,
        owner: String? = nil,
        owedTo: String? = nil,
        project: String? = nil,
        dueDate: String? = nil,
        status: String,
        source: String? = nil,
        sourceType: String? = nil,
        kind: String? = nil,
        sourceMeetingId: Int? = nil,
        meetingId: Int? = nil,
        meetingTitle: String? = nil,
        reminderSuggestion: String? = nil,
        isOverdue: Bool? = nil,
        snoozedUntil: String? = nil,
        completedAt: String? = nil,
        createdAt: String? = nil,
        updatedAt: String? = nil,
        contexts: [ContextItem]? = nil
    ) {
        self.id = id
        self.text = text
        self.owner = owner
        self.owedTo = owedTo
        self.project = project
        self.dueDate = dueDate
        self.status = status
        self.source = source
        self.sourceType = sourceType
        self.kind = kind
        self.sourceMeetingId = sourceMeetingId
        self.meetingId = meetingId
        self.meetingTitle = meetingTitle
        self.reminderSuggestion = reminderSuggestion
        self.isOverdue = isOverdue
        self.snoozedUntil = snoozedUntil
        self.completedAt = completedAt
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.contexts = contexts
    }

    public var isDone: Bool {
        status == "done"
    }

    public var displayOwner: String {
        owner?.isEmpty == false ? owner! : "Unassigned"
    }

    public var displayDueDate: String {
        dueDate?.isEmpty == false ? dueDate! : "No due date"
    }

    public var displaySource: String {
        if let meetingTitle, !meetingTitle.isEmpty {
            return meetingTitle
        }
        if let source, !source.isEmpty {
            return source.capitalized
        }
        return "SpeedwagonAI"
    }
}

public struct AssistantCommandRequest: Codable, Equatable {
    public let command: String

    public init(command: String) {
        self.command = command
    }
}

public struct AssistantCommandResponse: Codable, Equatable {
    public let supported: Bool
    public let action: String?
    public let category: String?
    public let requiresConfirmation: Bool?
    public let payload: [String: JSONValue]?
    public let confidence: Double?
    public let pendingActionId: Int?
    public let explanation: String?
    public let safetyNotes: [String]?
    public let source: String?
    public let summary: String
    public let command: String?
    public let result: AssistantResult?
    public let suggestedCommands: [String]?

    public init(
        supported: Bool,
        action: String? = nil,
        category: String? = nil,
        requiresConfirmation: Bool? = nil,
        payload: [String: JSONValue]? = nil,
        confidence: Double? = nil,
        pendingActionId: Int? = nil,
        explanation: String? = nil,
        safetyNotes: [String]? = nil,
        source: String? = nil,
        summary: String,
        command: String? = nil,
        result: AssistantResult? = nil,
        suggestedCommands: [String]? = nil
    ) {
        self.supported = supported
        self.action = action
        self.category = category
        self.requiresConfirmation = requiresConfirmation
        self.payload = payload
        self.confidence = confidence
        self.pendingActionId = pendingActionId
        self.explanation = explanation
        self.safetyNotes = safetyNotes
        self.source = source
        self.summary = summary
        self.command = command
        self.result = result
        self.suggestedCommands = suggestedCommands
    }
}

public struct AssistantResult: Codable, Equatable {
    public let assistantMessage: String?
    public let evidence: [AssistantEvidenceItem]?
    public let draftPreview: EmailDraftPreview?
    public let clarificationRequired: Bool?
    public let tasks: [TaskItem]?
    public let task: TaskItem?
    public let capabilities: [AssistantCapability]?
    public let meetings: [MeetingItem]?
    public let meeting: MeetingItem?
    public let draft: EmailDraftPreview?
    public let topic: String?
    public let markdown: String?
    public let date: String?
    public let overdue: [TaskItem]?
    public let today: [TaskItem]?
    public let upcoming: [TaskItem]?
    public let waiting: [TaskItem]?
    public let snoozed: [TaskItem]?
    public let uncertain: [TaskItem]?
    public let stale: [TaskItem]?
    public let unscheduled: [TaskItem]?
    public let recommendedFollowups: [TaskItem]?
    public let counts: [String: Int]?
    public let message: String?
    public let transcriptPath: String?
    public let notePath: String?
    public let commitmentsPath: String?
    public let actionItems: Int?
    public let commitments: Int?
    public let pendingAction: PendingAssistantAction?
    public let pendingActions: [PendingAssistantAction]?
    public let contexts: [ContextItem]?
    public let context: ContextItem?
    public let relationships: [ContextRelationshipItem]?
    public let decisions: [MeetingTextItem]?
    public let suggestedCommands: [String]?
    public let suggestions: [SuggestionItem]?
    public let suggestion: SuggestionItem?
    public let followupDraft: FollowupDraft?
    public let drafts: [FollowupDraft]?
    public let created: Bool?
    public let reused: Bool?
    public let nextStep: String?
    public let query: String?
    public let enabled: Bool?
    public let results: [JSONValue]?
    public let sessions: [BotSession]?
    public let session: BotSession?
    public let event: CalendarEvent?
    public let events: [CalendarEvent]?

    public var hasTaskMutation: Bool {
        task != nil
    }
}

public struct AssistantEvidenceItem: Codable, Equatable {
    public let kind: String
    public let id: Int?
    public let title: String
    public let subtitle: String?

    public var idValue: String {
        "\(kind):\(id.map(String.init) ?? title)"
    }

    public var displayLine: String {
        var prefix = kind.replacingOccurrences(of: "_", with: " ")
        if let id {
            prefix += " #\(id)"
        }
        if let subtitle, !subtitle.isEmpty {
            return "\(prefix): \(title) · \(subtitle)"
        }
        return "\(prefix): \(title)"
    }
}

public struct AssistantCapabilitiesResponse: Codable, Equatable {
    public let capabilities: [AssistantCapability]
}

public struct AssistantCapability: Codable, Identifiable, Equatable {
    public let category: String
    public let command: String
    public let description: String

    public var id: String {
        "\(category):\(command)"
    }
}

public struct MeetingItem: Codable, Identifiable, Equatable {
    public let id: Int
    public let title: String
    public let startedAt: String?
    public let endedAt: String?
    public let audioPath: String?
    public let transcriptPath: String?
    public let notePath: String?
    public let summary: String?
    public let sourceType: String?
}

public struct MeetingTextItem: Codable, Identifiable, Equatable {
    public let id: Int
    public let meetingId: Int?
    public let text: String?
    public let topic: String?
    public let name: String?
    public let owner: String?
    public let deadline: String?
    public let status: String?
    public let createdAt: String?
    public let updatedAt: String?

    public var displayText: String {
        text ?? topic ?? name ?? ""
    }
}

public struct SuggestionListResponse: Codable, Equatable {
    public let suggestions: [SuggestionItem]
}

public struct NotificationCandidateListResponse: Codable, Equatable {
    public let candidates: [SuggestionItem]
}

public struct NotificationStatusResponse: Codable, Equatable {
    public let enabled: Bool
    public let delivery: String
    public let runtime: String
    public let permissionOwner: String?
    public let candidateCount: Int
    public let deliveredCount: Int
    public let dismissedCount: Int
    public let snoozedCount: Int
    public let note: String
}

public struct NotificationEnvelope: Codable, Equatable {
    public let suggestion: SuggestionItem
    public let notification: NotificationAuditItem?
}

public struct NotificationAuditItem: Codable, Equatable, Identifiable {
    public let id: Int
    public let suggestionId: Int
    public let sourceFingerprint: String?
    public let scheduledAt: String?
    public let deliveredAt: String?
    public let status: String
    public let reason: String?
    public let actionTaken: String?
    public let createdAt: String?
    public let updatedAt: String?
}

public struct SuggestionEnvelope: Codable, Equatable {
    public let suggestion: SuggestionItem
    public let actionResult: AssistantResult?
    public let relatedTasks: [TaskItem]?
    public let followupDraft: FollowupDraft?
    public let reviewStatus: String?
}

public struct ContextGraphResponse: Codable, Equatable {
    public let query: String
    public let contexts: [ContextItem]
    public let tasks: [TaskItem]
    public let meetings: [MeetingItem]
    public let relationships: [ContextRelationshipItem]?
    public let suggestions: [SuggestionItem]
}

public struct ContextDetailResponse: Codable, Equatable {
    public let context: ContextItem
    public let relatedContexts: [ContextItem]
    public let relationships: [ContextRelationshipItem]
    public let tasks: [TaskItem]
    public let meetings: [MeetingItem]
    public let decisions: [MeetingTextItem]
    public let suggestions: [SuggestionItem]
    public let followupDrafts: [FollowupDraft]
}

public struct ContextRelationshipItem: Codable, Identifiable, Equatable {
    public let id: Int
    public let sourceContext: ContextItem
    public let targetContext: ContextItem
    public let relationshipType: String
    public let evidence: String?
    public let confidence: Double?
    public let sourceMeetingId: Int?
    public let sourceMeetingTitle: String?
    public let createdAt: String?
    public let updatedAt: String?

    public var displayLine: String {
        let relation = relationshipType.replacingOccurrences(of: "_", with: " ")
        return "\(sourceContext.name) \(relation) \(targetContext.name)"
    }
}

public struct SuggestionItem: Codable, Identifiable, Equatable {
    public let id: Int
    public let title: String
    public let reason: String
    public let status: String
    public let confidence: Double?
    public let contextId: Int?
    public let contextName: String?
    public let contextKind: String?
    public let context: ContextItem?
    public let proposedAction: String
    public let payload: [String: JSONValue]?
    public let taskIds: [Int]
    public let meetingIds: [Int]
    public let sourceFingerprint: String?
    public let retiredAt: String?
    public let nextNotifyAt: String?
    public let lastNotifiedAt: String?
    public let notificationReason: String?
    public let notificationStatus: String?
    public let snoozedUntil: String?
    public let createdAt: String?
    public let updatedAt: String?

    public init(
        id: Int,
        title: String,
        reason: String,
        status: String,
        confidence: Double? = nil,
        contextId: Int? = nil,
        contextName: String? = nil,
        contextKind: String? = nil,
        context: ContextItem? = nil,
        proposedAction: String,
        payload: [String: JSONValue]? = nil,
        taskIds: [Int] = [],
        meetingIds: [Int] = [],
        sourceFingerprint: String? = nil,
        retiredAt: String? = nil,
        nextNotifyAt: String? = nil,
        lastNotifiedAt: String? = nil,
        notificationReason: String? = nil,
        notificationStatus: String? = nil,
        snoozedUntil: String? = nil,
        createdAt: String? = nil,
        updatedAt: String? = nil
    ) {
        self.id = id
        self.title = title
        self.reason = reason
        self.status = status
        self.confidence = confidence
        self.contextId = contextId
        self.contextName = contextName
        self.contextKind = contextKind
        self.context = context
        self.proposedAction = proposedAction
        self.payload = payload
        self.taskIds = taskIds
        self.meetingIds = meetingIds
        self.sourceFingerprint = sourceFingerprint
        self.retiredAt = retiredAt
        self.nextNotifyAt = nextNotifyAt
        self.lastNotifiedAt = lastNotifiedAt
        self.notificationReason = notificationReason
        self.notificationStatus = notificationStatus
        self.snoozedUntil = snoozedUntil
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }

    public var displayContext: String? {
        if let context, !context.name.isEmpty {
            return context.name
        }
        if let contextName, !contextName.isEmpty {
            return contextName
        }
        return nil
    }
}

public struct EmailDraftPreview: Codable, Equatable {
    public let subject: String?
    public let body: String?
    public let tone: String?
    public let provider: String?
    public let includedItems: [String]?
    public let to: String?
}

public struct FollowupDraftListResponse: Codable, Equatable {
    public let drafts: [FollowupDraft]
}

public struct FollowupDraftEnvelope: Codable, Equatable {
    public let draft: FollowupDraft
    public let draftId: String?
}

public struct FollowupDraft: Codable, Identifiable, Equatable {
    public let id: Int
    public let suggestionId: Int?
    public let taskId: Int?
    public let contextId: Int?
    public let meetingId: Int?
    public let provider: String?
    public let providerDraftId: String?
    public let recipient: String?
    public let subject: String
    public let body: String
    public let status: String
    public let source: String?
    public let contextName: String?
    public let taskText: String?
    public let meetingTitle: String?
    public let createdAt: String?
    public let updatedAt: String?
}

public struct FollowupDraftUpdateRequest: Codable, Equatable {
    public let to: String?
    public let subject: String?
    public let body: String?

    public init(to: String? = nil, subject: String? = nil, body: String? = nil) {
        self.to = to
        self.subject = subject
        self.body = body
    }
}

public struct DailyBriefResponse: Codable, Equatable {
    public let date: String
    public let synthesis: DailySynthesis?
    public let overdue: [TaskItem]
    public let today: [TaskItem]
    public let upcoming: [TaskItem]
    public let waiting: [TaskItem]
    public let snoozed: [TaskItem]
    public let uncertain: [TaskItem]
    public let stale: [TaskItem]
    public let unscheduled: [TaskItem]
    public let recommendedFollowups: [TaskItem]
    public let calendarToday: [CalendarEvent]?
    public let calendarUpcoming: [CalendarEvent]?
    public let meetingPrep: [MeetingPrepItem]?
    public let notificationCandidates: [SuggestionItem]?
    public let counts: [String: Int]
}

public struct DailySynthesis: Codable, Equatable {
    public let id: Int?
    public let date: String
    public let summary: String
    public let risks: [String]
    public let droppedThreads: [String]
    public let followups: [String]
    public let recentChanges: [String]
    public let provider: String?
    public let model: String?
    public let generatedAt: String?
    public let inputFingerprint: String?
    public let createdAt: String?
    public let updatedAt: String?
}

public struct IntelligenceStatusResponse: Codable, Equatable {
    public let date: String
    public let cached: DailySynthesis?
    public let latest: DailySynthesis?
    public let manualRefreshRequired: Bool?
    public let note: String?

    public init(
        date: String,
        cached: DailySynthesis? = nil,
        latest: DailySynthesis? = nil,
        manualRefreshRequired: Bool? = nil,
        note: String? = nil
    ) {
        self.date = date
        self.cached = cached
        self.latest = latest
        self.manualRefreshRequired = manualRefreshRequired
        self.note = note
    }
}

public struct IntelligenceRefreshRequest: Codable, Equatable {
    public let date: String?
    public let topSuggestionLimit: Int?

    public init(date: String? = nil, topSuggestionLimit: Int? = nil) {
        self.date = date
        self.topSuggestionLimit = topSuggestionLimit
    }
}

public struct IntelligenceRefreshResponse: Codable, Equatable {
    public let status: String
    public let date: String
    public let synthesis: DailySynthesis
    public let updatedSuggestions: [SuggestionItem]
    public let inputFingerprint: String?
}

public struct CalendarStatusResponse: Codable, Equatable {
    public let enabled: Bool
    public let provider: String?
    public let status: String
    public let note: String
    public let credentialsPresent: Bool?
    public let tokenPresent: Bool?
    public let calendarScopePresent: Bool?
    public let calendarWriteScopePresent: Bool?
    public let writeEnabled: Bool?
    public let calendarIds: [String]?
    public let syncDaysBack: Int?
    public let syncDaysForward: Int?
}

public struct CalendarEventListResponse: Codable, Equatable {
    public let events: [CalendarEvent]
}

public struct CalendarSyncResponse: Codable, Equatable {
    public let status: String
    public let provider: String?
    public let calendarIds: [String]?
    public let timeMin: String?
    public let timeMax: String?
    public let syncedCount: Int
    public let removedCount: Int?
    public let events: [CalendarEvent]
}

public struct CalendarCreateEventRequest: Codable, Equatable {
    public let title: String
    public let startAt: String
    public let endAt: String
    public let calendarId: String?
    public let timezone: String?
    public let description: String?
    public let location: String?
    public let attendees: [String]
    public let sendUpdates: String?

    public init(
        title: String,
        startAt: String,
        endAt: String,
        calendarId: String? = nil,
        timezone: String? = nil,
        description: String? = nil,
        location: String? = nil,
        attendees: [String] = [],
        sendUpdates: String? = "none"
    ) {
        self.title = title
        self.startAt = startAt
        self.endAt = endAt
        self.calendarId = calendarId
        self.timezone = timezone
        self.description = description
        self.location = location
        self.attendees = attendees
        self.sendUpdates = sendUpdates
    }
}

public struct CalendarCreateEventResponse: Codable, Equatable {
    public let status: String
    public let provider: String?
    public let calendarId: String?
    public let event: CalendarEvent
    public let htmlLink: String?
    public let sendUpdates: String?
}

public struct CalendarEvent: Codable, Identifiable, Equatable {
    public let id: Int
    public let provider: String?
    public let providerEventId: String?
    public let calendarId: String?
    public let title: String
    public let descriptionSnippet: String?
    public let startAt: String
    public let endAt: String
    public let timezone: String?
    public let location: String?
    public let meetingUrl: String?
    public let attendees: [CalendarAttendee]?
    public let status: String?
    public let htmlLink: String?
    public let rawJsonPath: String?
    public let lastSyncedAt: String?
}

public struct CalendarAttendee: Codable, Equatable {
    public let email: String?
    public let displayName: String?
    public let responseStatus: String?
}

public struct MeetingPrepItem: Codable, Equatable {
    public let event: CalendarEvent
    public let query: String?
    public let contexts: [ContextItem]?
    public let tasks: [TaskItem]?
    public let meetings: [MeetingItem]?
    public let decisions: [JSONValue]?
}

public struct SettingsResponse: Codable, Equatable {
    public let dbPath: String?
    public let notesDir: String?
    public let audioDir: String?
    public let transcriptsDir: String?
    public let openaiKeyPresent: Bool?
    public let cheapModel: String?
    public let strongModel: String?
    public let commandModel: String?
    public let visionModel: String?
    public let webModel: String?
    public let modelCostLabels: [String: String]?
    public let webSearchEnabled: Bool?
    public let apiTokenPath: String?
    public let logDir: String?
    public let appLogPath: String?
    public let backendLogPath: String?
    public let gmailCredentialsPresent: Bool?
    public let gmailTokenPresent: Bool?
    public let calendarStatus: String?
    public let calendarEnabled: Bool?
    public let calendarNote: String?
    public let calendarIds: [String]?
    public let calendarSyncDaysBack: Int?
    public let calendarSyncDaysForward: Int?
    public let captureProfile: String?
    public let inputDevice: String?
    public let recorderStatus: String?
    public let captureNote: String?
    public let nativeCaptureAvailable: Bool?
    public let nativeCaptureDefault: String?
    public let nativeCaptureNote: String?
    public let botProvider: String?
    public let botConfigured: Bool?
    public let botNote: String?
}

public struct SystemLogsResponse: Codable, Equatable {
    public let logDir: String
    public let appLogPath: String
    public let backendLogPath: String
    public let appLogExists: Bool
    public let backendLogExists: Bool
    public let logTail: String
    public let backendLogTail: String
}

public struct PrivacyStatusResponse: Codable, Equatable {
    public let dbPath: String
    public let notesDir: String
    public let audioDir: String
    public let transcriptsDir: String
    public let logsDir: String
    public let exportSupported: Bool
    public let wipeSupported: Bool
    public let wipeConfirmation: String
    public let existingPaths: [String]
    public let counts: [String: Int]
    public let pathVisibilityNote: String?
    public let localDataDirs: [String: String]?
    public let externalServices: [String: ExternalServiceStatus]?
    public let dataDisclosures: [DataDisclosure]?
}

public struct ExternalServiceStatus: Codable, Equatable {
    public let configured: Bool
    public let purpose: String
}

public struct DataDisclosure: Codable, Equatable {
    public let service: String
    public let enabled: Bool
    public let data: String
    public let trigger: String
}

public struct SystemExportRequest: Codable, Equatable {
    public let outputPath: String?

    public init(outputPath: String? = nil) {
        self.outputPath = outputPath
    }
}

public struct SystemExportResponse: Codable, Equatable {
    public let status: String
    public let path: String
    public let fileCount: Int
}

public struct SystemWipeRequest: Codable, Equatable {
    public let confirm: String

    public init(confirm: String) {
        self.confirm = confirm
    }
}

public struct SystemWipeResponse: Codable, Equatable {
    public let status: String
    public let removed: [String]
}

public struct BotStatusResponse: Codable, Equatable {
    public let enabled: Bool
    public let provider: String?
    public let status: String?
    public let note: String?
    public let requiresConsent: Bool?
    public let defaultBotName: String?
    public let botName: String?
    public let cloudCostLabel: String?
    public let sessions: [BotSession]?
    public let sessionCount: Int?
}

public struct BotSessionListResponse: Codable, Equatable {
    public let sessions: [BotSession]
}

public struct BotSessionClearResponse: Codable, Equatable {
    public let clearedCount: Int
    public let sessions: [BotSession]
}

public struct BotSessionEnvelope: Codable, Equatable {
    public let session: BotSession
}

public struct BotJoinResponse: Codable, Equatable {
    public let session: BotSession
    public let meeting: MeetingItem?
    public let providerResponse: JSONValue?
}

public struct BotProcessResponse: Codable, Equatable {
    public let session: BotSession
    public let meeting: MeetingItem
    public let transcriptPath: String?
    public let notePath: String?
    public let commitmentsPath: String?
}

public struct BotSession: Codable, Identifiable, Equatable {
    public let id: Int
    public let provider: String
    public let providerBotId: String?
    public let meetingId: Int
    public let meetingUrlDisplay: String?
    public let title: String
    public let status: String
    public let joinAt: String?
    public let transcriptPath: String?
    public let rawMetadataPath: String?
    public let lastSyncAt: String?
    public let error: String?
    public let consentConfirmed: Bool?
    public let createdAt: String?
    public let updatedAt: String?
    public let meetingTitle: String?
    public let meetingSummary: String?
    public let meetingTranscriptPath: String?
    public let meetingNotePath: String?
    public let transcriptReady: Bool?
    public let processed: Bool?

    public var displayTitle: String {
        title.isEmpty ? (meetingTitle ?? "Bot session \(id)") : title
    }
}

public struct BotJoinRequest: Codable, Equatable {
    public let meetingUrl: String
    public let title: String
    public let joinAt: String?
    public let botName: String?
    public let consentConfirmed: Bool

    public init(meetingUrl: String, title: String, joinAt: String? = nil, botName: String? = nil, consentConfirmed: Bool) {
        self.meetingUrl = meetingUrl
        self.title = title
        self.joinAt = joinAt
        self.botName = botName
        self.consentConfirmed = consentConfirmed
    }
}

public struct CaptureSession: Codable, Equatable {
    public let active: Bool?
    public let native: Bool?
    public let status: String?
    public let sessionId: String?
    public let kind: String?
    public let mode: String?
    public let title: String?
    public let meetingId: Int?
    public let pid: Int?
    public let audioPath: String?
    public let systemAudioPath: String?
    public let microphoneAudioPath: String?
    public let logPath: String?
    public let command: [String]?
    public let captureProfile: String?
    public let inputDevice: String?
    public let startedAt: String?
    public let endedAt: String?
    public let fileSize: Int?
    public let outputFileOk: Bool?
    public let logTail: String?
    public let warnings: [String]?
    public let lastError: String?

    public var isActive: Bool {
        active == true
    }

    public var isNative: Bool {
        native == true || captureProfile == "native_screencapturekit"
    }
}

public struct CaptureStartRequest: Codable, Equatable {
    public let kind: String
    public let title: String?
    public let metadata: [String: String]?

    public init(kind: String, title: String? = nil, metadata: [String: String]? = nil) {
        self.kind = kind
        self.title = title
        self.metadata = metadata
    }
}

public struct CaptureStopRequest: Codable, Equatable {
    public let process: Bool
    public let taskMetadata: [String: String]?

    public init(process: Bool = false, taskMetadata: [String: String]? = nil) {
        self.process = process
        self.taskMetadata = taskMetadata
    }
}

public struct CaptureStartResponse: Codable, Equatable {
    public let session: CaptureSession
}

public struct NativeCapturePrepareRequest: Codable, Equatable {
    public let kind: String
    public let title: String
    public let mode: String

    public init(kind: String = "meeting", title: String, mode: String = "system_mic") {
        self.kind = kind
        self.title = title
        self.mode = mode
    }
}

public struct NativeCaptureCompleteRequest: Codable, Equatable {
    public let sessionId: String
    public let audioPath: String
    public let process: Bool
    public let warnings: [String]

    public init(sessionId: String, audioPath: String, process: Bool = false, warnings: [String] = []) {
        self.sessionId = sessionId
        self.audioPath = audioPath
        self.process = process
        self.warnings = warnings
    }
}

public struct NativeCaptureFailRequest: Codable, Equatable {
    public let sessionId: String
    public let error: String

    public init(sessionId: String, error: String) {
        self.sessionId = sessionId
        self.error = error
    }
}

public struct CaptureStopResponse: Codable, Equatable {
    public let session: CaptureSession
    public let meetingId: Int?
    public let meeting: MeetingItem?
    public let transcriptPath: String?
    public let notePath: String?
    public let commitmentsPath: String?
    public let task: TaskItem?
    public let audioPath: String?
    public let transcript: String?
}

public struct CaptureDiagnostics: Codable, Equatable {
    public let captureProfile: String
    public let inputDevice: String?
    public let recordCmd: String?
    public let tools: [String: String?]
    public let recorderStatus: String
    public let recorderCommandPreview: String
    public let activeSession: CaptureSession
    public let nativeCapture: CaptureSession?
    public let nativeCaptureNote: String?
    public let recentLogTail: String
    public let outputFileOk: Bool
    public let warnings: [String]
    public let smokeTestHint: String
}

public struct AssistantVoiceStartResponse: Codable, Equatable {
    public let session: CaptureSession
}

public struct AssistantVoiceStopResponse: Codable, Equatable {
    public let session: CaptureSession
    public let transcript: String
    public let assistantResponse: AssistantCommandResponse
    public let audioPath: String
    public let transcriptPath: String
}

public struct AssistantVoiceTranscriptResponse: Codable, Equatable {
    public let session: CaptureSession
    public let transcript: String
    public let audioPath: String
    public let transcriptPath: String
}

public struct PendingAssistantAction: Codable, Identifiable, Equatable {
    public let id: Int
    public let command: String
    public let action: String
    public let category: String
    public let payload: [String: JSONValue]?
    public let confidence: Double?
    public let source: String?
    public let explanation: String?
    public let safetyNotes: [String]?
    public let status: String
    public let createdAt: String?
    public let updatedAt: String?
    public let expiresAt: String?
}

public struct PendingActionListResponse: Codable, Equatable {
    public let actions: [PendingAssistantAction]
}

public struct ScreenshotAnalyzeRequest: Codable, Equatable {
    public let imageBase64: String
    public let instruction: String?

    public init(imageBase64: String, instruction: String? = nil) {
        self.imageBase64 = imageBase64
        self.instruction = instruction
    }
}

public struct ScreenshotAnalysisResponse: Codable, Equatable {
    public let summary: String
    public let visibleText: [String]
    public let suggestedTasks: [ScreenshotSuggestedTask]
    public let suggestedContextTopics: [String]
    public let suggestedActions: [ScreenshotSuggestedAction]
    public let pendingActions: [PendingAssistantAction]
    public let confidence: Double?
    public let provider: String?
}

public struct ScreenshotSuggestedTask: Codable, Equatable {
    public let text: String
    public let dueDate: String?
    public let owner: String?
    public let project: String?
    public let confidence: Double?
}

public struct ScreenshotSuggestedAction: Codable, Equatable {
    public let action: String?
    public let payload: [String: JSONValue]?
    public let confidence: Double?
    public let explanation: String?
}

public enum JSONValue: Codable, Equatable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([JSONValue].self) {
            self = .array(value)
        } else {
            self = .object(try container.decode([String: JSONValue].self))
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case let .string(value):
            try container.encode(value)
        case let .number(value):
            try container.encode(value)
        case let .bool(value):
            try container.encode(value)
        case let .object(value):
            try container.encode(value)
        case let .array(value):
            try container.encode(value)
        case .null:
            try container.encodeNil()
        }
    }
}
