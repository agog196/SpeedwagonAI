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

public struct CommitmentListResponse: Codable, Equatable {
    public let items: [TaskItem]
    public let commitments: [TaskItem]?
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
        updatedAt: String? = nil
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
        result: AssistantResult? = nil
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
    }
}

public struct AssistantResult: Codable, Equatable {
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
    public let query: String?
    public let enabled: Bool?
    public let results: [JSONValue]?

    public var hasTaskMutation: Bool {
        task != nil
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
}

public struct EmailDraftPreview: Codable, Equatable {
    public let subject: String?
    public let body: String?
    public let tone: String?
    public let provider: String?
    public let includedItems: [String]?
    public let to: String?
}

public struct DailyBriefResponse: Codable, Equatable {
    public let date: String
    public let overdue: [TaskItem]
    public let today: [TaskItem]
    public let upcoming: [TaskItem]
    public let waiting: [TaskItem]
    public let snoozed: [TaskItem]
    public let uncertain: [TaskItem]
    public let stale: [TaskItem]
    public let unscheduled: [TaskItem]
    public let recommendedFollowups: [TaskItem]
    public let counts: [String: Int]
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
    public let gmailCredentialsPresent: Bool?
    public let gmailTokenPresent: Bool?
    public let captureProfile: String?
    public let inputDevice: String?
    public let recorderStatus: String?
    public let captureNote: String?
}

public struct CaptureSession: Codable, Equatable {
    public let active: Bool?
    public let kind: String?
    public let title: String?
    public let meetingId: Int?
    public let pid: Int?
    public let audioPath: String?
    public let logPath: String?
    public let command: [String]?
    public let captureProfile: String?
    public let inputDevice: String?
    public let startedAt: String?
    public let fileSize: Int?
    public let outputFileOk: Bool?
    public let logTail: String?
    public let lastError: String?

    public var isActive: Bool {
        active == true
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
