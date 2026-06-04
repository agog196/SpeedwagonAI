import Foundation

public enum SpeedwagonAPIError: Error, LocalizedError, Equatable {
    case invalidResponse
    case httpStatus(Int, String)

    public var errorDescription: String? {
        switch self {
        case .invalidResponse:
            return "SpeedwagonAI returned an invalid response."
        case let .httpStatus(code, message):
            return "SpeedwagonAI returned HTTP \(code): \(message)"
        }
    }
}

public final class SpeedwagonAPIClient {
    public let baseURL: URL
    private let session: URLSession

    public init(
        baseURL: URL = URL(string: "http://127.0.0.1:8765")!,
        session: URLSession = .shared
    ) {
        self.baseURL = baseURL
        self.session = session
    }

    public func fetchTasks() async throws -> [TaskItem] {
        let url = baseURL.appending(path: "/api/tasks")
            .appending(queryItems: [
                URLQueryItem(name: "status", value: ""),
                URLQueryItem(name: "include_done", value: "true")
            ])
        let response: TaskListResponse = try await get(url)
        return response.tasks
    }

    public func fetchMeetings(limit: Int = 30) async throws -> [MeetingItem] {
        let url = baseURL.appending(path: "/api/meetings")
            .appending(queryItems: [URLQueryItem(name: "limit", value: String(limit))])
        let response: MeetingListResponse = try await get(url)
        return response.meetings
    }

    public func fetchMeetingDetail(id: Int) async throws -> MeetingDetailResponse {
        try await get(baseURL.appending(path: "/api/meetings/\(id)"))
    }

    public func processMeeting(id: Int) async throws -> MeetingProcessResponse {
        try await post(baseURL.appending(path: "/api/meetings/\(id)/process"), body: EmptyBody())
    }

    public func fetchSettings() async throws -> SettingsResponse {
        try await get(baseURL.appending(path: "/api/settings"))
    }

    public func fetchDailyBrief() async throws -> DailyBriefResponse {
        try await get(baseURL.appending(path: "/api/daily-brief"))
    }

    public func fetchCalendarStatus() async throws -> CalendarStatusResponse {
        try await get(baseURL.appending(path: "/api/calendar/status"))
    }

    public func syncCalendar() async throws -> CalendarSyncResponse {
        try await post(baseURL.appending(path: "/api/calendar/sync"), body: EmptyBody())
    }

    public func fetchUpcomingCalendarEvents(limit: Int = 10) async throws -> [CalendarEvent] {
        let url = baseURL.appending(path: "/api/calendar/upcoming")
            .appending(queryItems: [URLQueryItem(name: "limit", value: String(limit))])
        let response: CalendarEventListResponse = try await get(url)
        return response.events
    }

    public func fetchCommitments() async throws -> [TaskItem] {
        let response: CommitmentListResponse = try await get(baseURL.appending(path: "/api/commitments"))
        return response.commitments ?? response.items
    }

    public func fetchCapabilities() async throws -> [AssistantCapability] {
        let response: AssistantCapabilitiesResponse = try await get(baseURL.appending(path: "/api/assistant/capabilities"))
        return response.capabilities
    }

    public func fetchPendingActions() async throws -> [PendingAssistantAction] {
        let response: PendingActionListResponse = try await get(baseURL.appending(path: "/api/assistant/actions"))
        return response.actions
    }

    public func fetchSuggestions() async throws -> [SuggestionItem] {
        let response: SuggestionListResponse = try await get(baseURL.appending(path: "/api/suggestions"))
        return response.suggestions
    }

    public func fetchNotificationStatus() async throws -> NotificationStatusResponse {
        try await get(baseURL.appending(path: "/api/notifications/status"))
    }

    public func fetchNotificationCandidates(limit: Int = 20) async throws -> [SuggestionItem] {
        let url = baseURL.appending(path: "/api/notifications/candidates")
            .appending(queryItems: [URLQueryItem(name: "limit", value: String(limit))])
        let response: NotificationCandidateListResponse = try await get(url)
        return response.candidates
    }

    public func searchContextGraph(query: String) async throws -> ContextGraphResponse {
        let url = baseURL.appending(path: "/api/context-graph")
            .appending(queryItems: [URLQueryItem(name: "query", value: query)])
        return try await get(url)
    }

    public func fetchCaptureStatus() async throws -> CaptureSession {
        try await get(baseURL.appending(path: "/api/capture/status"))
    }

    public func fetchCaptureDiagnostics() async throws -> CaptureDiagnostics {
        try await get(baseURL.appending(path: "/api/capture/diagnostics"))
    }

    public func fetchBotStatus() async throws -> BotStatusResponse {
        try await get(baseURL.appending(path: "/api/capture/bot/status"))
    }

    public func fetchBotSessions() async throws -> [BotSession] {
        let response: BotSessionListResponse = try await get(baseURL.appending(path: "/api/capture/bot/sessions"))
        return response.sessions
    }

    public func joinBotSession(meetingUrl: String, title: String, consentConfirmed: Bool) async throws -> BotJoinResponse {
        try await post(
            baseURL.appending(path: "/api/capture/bot/join"),
            body: BotJoinRequest(meetingUrl: meetingUrl, title: title, consentConfirmed: consentConfirmed)
        )
    }

    public func syncBotSession(id: Int) async throws -> BotSessionEnvelope {
        try await post(baseURL.appending(path: "/api/capture/bot/sessions/\(id)/sync"), body: EmptyBody())
    }

    public func processBotSession(id: Int) async throws -> BotProcessResponse {
        try await post(baseURL.appending(path: "/api/capture/bot/sessions/\(id)/process"), body: EmptyBody())
    }

    public func startCapture(kind: String, title: String? = nil) async throws -> CaptureSession {
        let url = baseURL.appending(path: "/api/capture/local/start")
        let response: CaptureStartResponse = try await post(url, body: CaptureStartRequest(kind: kind, title: title))
        return response.session
    }

    public func stopCapture(process: Bool = false, taskMetadata: [String: String]? = nil) async throws -> CaptureStopResponse {
        let url = baseURL.appending(path: "/api/capture/local/stop")
        return try await post(url, body: CaptureStopRequest(process: process, taskMetadata: taskMetadata))
    }

    public func prepareNativeCapture(title: String, mode: String = "system_mic") async throws -> CaptureSession {
        let url = baseURL.appending(path: "/api/capture/native/prepare")
        let response: CaptureStartResponse = try await post(
            url,
            body: NativeCapturePrepareRequest(kind: "meeting", title: title, mode: mode)
        )
        return response.session
    }

    public func completeNativeCapture(
        sessionId: String,
        audioPath: String,
        process: Bool = false,
        warnings: [String] = []
    ) async throws -> CaptureStopResponse {
        let url = baseURL.appending(path: "/api/capture/native/complete")
        return try await post(
            url,
            body: NativeCaptureCompleteRequest(
                sessionId: sessionId,
                audioPath: audioPath,
                process: process,
                warnings: warnings
            )
        )
    }

    public func failNativeCapture(sessionId: String, error: String) async throws -> CaptureSession {
        let url = baseURL.appending(path: "/api/capture/native/fail")
        let response: CaptureStartResponse = try await post(url, body: NativeCaptureFailRequest(sessionId: sessionId, error: error))
        return response.session
    }

    public func fetchAssistantVoiceStatus() async throws -> CaptureSession {
        try await get(baseURL.appending(path: "/api/assistant/voice/status"))
    }

    public func startAssistantVoice() async throws -> CaptureSession {
        let url = baseURL.appending(path: "/api/assistant/voice/start")
        let response: AssistantVoiceStartResponse = try await post(url, body: EmptyBody())
        return response.session
    }

    public func stopAssistantVoice() async throws -> AssistantVoiceStopResponse {
        try await post(baseURL.appending(path: "/api/assistant/voice/stop"), body: EmptyBody())
    }

    public func runCommand(_ command: String) async throws -> AssistantCommandResponse {
        let url = baseURL.appending(path: "/api/assistant/command")
        return try await post(url, body: AssistantCommandRequest(command: command))
    }

    public func confirmPendingAction(id: Int) async throws -> AssistantCommandResponse {
        let url = baseURL.appending(path: "/api/assistant/actions/\(id)/confirm")
        return try await post(url, body: EmptyBody())
    }

    public func cancelPendingAction(id: Int) async throws -> AssistantCommandResponse {
        let url = baseURL.appending(path: "/api/assistant/actions/\(id)/cancel")
        return try await post(url, body: EmptyBody())
    }

    public func confirmSuggestion(id: Int) async throws -> SuggestionItem {
        let url = baseURL.appending(path: "/api/suggestions/\(id)/confirm")
        let response: SuggestionEnvelope = try await post(url, body: EmptyBody())
        return response.suggestion
    }

    public func dismissSuggestion(id: Int) async throws -> SuggestionItem {
        let url = baseURL.appending(path: "/api/suggestions/\(id)/dismiss")
        let response: SuggestionEnvelope = try await post(url, body: EmptyBody())
        return response.suggestion
    }

    public func snoozeSuggestion(id: Int, until: String? = nil) async throws -> SuggestionItem {
        let url = baseURL.appending(path: "/api/suggestions/\(id)/snooze")
        let response: SuggestionEnvelope = try await post(url, body: SuggestionSnoozeRequest(until: until))
        return response.suggestion
    }

    public func markNotificationDelivered(id: Int) async throws -> NotificationEnvelope {
        try await post(baseURL.appending(path: "/api/notifications/\(id)/mark-delivered"), body: EmptyBody())
    }

    public func dismissNotification(id: Int) async throws -> SuggestionItem {
        let response: SuggestionEnvelope = try await post(
            baseURL.appending(path: "/api/notifications/\(id)/dismiss"),
            body: EmptyBody()
        )
        return response.suggestion
    }

    public func snoozeNotification(id: Int, until: String? = nil) async throws -> SuggestionItem {
        let response: SuggestionEnvelope = try await post(
            baseURL.appending(path: "/api/notifications/\(id)/snooze"),
            body: SuggestionSnoozeRequest(until: until)
        )
        return response.suggestion
    }

    public func analyzeScreenshot(imageBase64: String, instruction: String? = nil) async throws -> ScreenshotAnalysisResponse {
        let url = baseURL.appending(path: "/api/assistant/screenshot/analyze")
        return try await post(url, body: ScreenshotAnalyzeRequest(imageBase64: imageBase64, instruction: instruction))
    }

    public func completeTask(id: Int) async throws -> TaskItem {
        let url = baseURL.appending(path: "/api/tasks/\(id)/complete")
        let response: TaskEnvelope = try await post(url, body: EmptyBody())
        return response.task
    }

    public func reopenTask(id: Int) async throws -> TaskItem {
        let url = baseURL.appending(path: "/api/tasks/\(id)/reopen")
        let response: TaskEnvelope = try await post(url, body: EmptyBody())
        return response.task
    }

    private func get<T: Decodable>(_ url: URL) async throws -> T {
        let (data, response) = try await session.data(from: url)
        try validate(response: response, data: data)
        return try SpeedwagonJSON.decoder.decode(T.self, from: data)
    }

    private func post<T: Decodable, Body: Encodable>(_ url: URL, body: Body) async throws -> T {
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try SpeedwagonJSON.encoder.encode(body)

        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        return try SpeedwagonJSON.decoder.decode(T.self, from: data)
    }

    private func validate(response: URLResponse, data: Data) throws {
        guard let httpResponse = response as? HTTPURLResponse else {
            throw SpeedwagonAPIError.invalidResponse
        }

        guard (200..<300).contains(httpResponse.statusCode) else {
            let message = String(data: data, encoding: .utf8) ?? "No response body"
            throw SpeedwagonAPIError.httpStatus(httpResponse.statusCode, message)
        }
    }
}

private struct EmptyBody: Encodable {}

private struct SuggestionSnoozeRequest: Encodable {
    let until: String?
}

private extension URL {
    func appending(queryItems: [URLQueryItem]) -> URL {
        guard var components = URLComponents(url: self, resolvingAgainstBaseURL: false) else {
            return self
        }
        components.queryItems = queryItems
        return components.url ?? self
    }
}
