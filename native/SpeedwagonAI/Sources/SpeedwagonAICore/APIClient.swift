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
    private let apiToken: String?

    public init(
        baseURL: URL = URL(string: "http://127.0.0.1:8765")!,
        session: URLSession = .shared,
        apiToken: String? = nil
    ) {
        self.baseURL = baseURL
        self.session = session
        self.apiToken = apiToken ?? SpeedwagonAPIClient.loadLocalAPIToken()
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

    public func fetchSystemLogs() async throws -> SystemLogsResponse {
        try await get(baseURL.appending(path: "/api/system/logs"))
    }

    public func fetchPrivacyStatus() async throws -> PrivacyStatusResponse {
        try await get(baseURL.appending(path: "/api/system/privacy-status"))
    }

    public func exportData(outputPath: String? = nil) async throws -> SystemExportResponse {
        try await post(baseURL.appending(path: "/api/system/export"), body: SystemExportRequest(outputPath: outputPath))
    }

    public func wipeData(confirm: String) async throws -> SystemWipeResponse {
        try await post(baseURL.appending(path: "/api/system/wipe"), body: SystemWipeRequest(confirm: confirm))
    }

    public func fetchDailyBrief() async throws -> DailyBriefResponse {
        try await get(baseURL.appending(path: "/api/daily-brief"))
    }

    public func fetchIntelligenceStatus(date: String? = nil) async throws -> IntelligenceStatusResponse {
        var url = baseURL.appending(path: "/api/intelligence/daily")
        if let date, !date.isEmpty {
            url = url.appending(queryItems: [URLQueryItem(name: "date", value: date)])
        }
        return try await get(url)
    }

    public func refreshDailyIntelligence(date: String? = nil, topSuggestionLimit: Int = 8) async throws -> IntelligenceRefreshResponse {
        try await post(
            baseURL.appending(path: "/api/intelligence/daily/refresh"),
            body: IntelligenceRefreshRequest(date: date, topSuggestionLimit: topSuggestionLimit)
        )
    }

    public func fetchCalendarStatus() async throws -> CalendarStatusResponse {
        try await get(baseURL.appending(path: "/api/calendar/status"))
    }

    public func syncCalendar() async throws -> CalendarSyncResponse {
        try await post(baseURL.appending(path: "/api/calendar/sync"), body: EmptyBody())
    }

    public func createCalendarEvent(_ request: CalendarCreateEventRequest) async throws -> CalendarCreateEventResponse {
        try await post(baseURL.appending(path: "/api/calendar/events"), body: request)
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
        let url = baseURL.appending(path: "/api/suggestions")
            .appending(queryItems: [
                URLQueryItem(name: "status", value: ""),
                URLQueryItem(name: "limit", value: "100")
            ])
        let response: SuggestionListResponse = try await get(url)
        return response.suggestions
    }

    public func fetchSuggestion(id: Int) async throws -> SuggestionItem {
        (try await fetchSuggestionEnvelope(id: id)).suggestion
    }

    public func fetchSuggestionEnvelope(id: Int) async throws -> SuggestionEnvelope {
        try await get(baseURL.appending(path: "/api/suggestions/\(id)"))
    }

    public func fetchFollowupDrafts(status: String? = nil, limit: Int = 40) async throws -> [FollowupDraft] {
        let url = baseURL.appending(path: "/api/email/drafts")
            .appending(queryItems: [
                URLQueryItem(name: "status", value: status ?? ""),
                URLQueryItem(name: "limit", value: String(limit))
            ])
        let response: FollowupDraftListResponse = try await get(url)
        return response.drafts
    }

    public func updateFollowupDraft(id: Int, to: String?, subject: String?, body: String?) async throws -> FollowupDraft {
        let response: FollowupDraftEnvelope = try await post(
            baseURL.appending(path: "/api/email/drafts/\(id)/update"),
            body: FollowupDraftUpdateRequest(to: to, subject: subject, body: body)
        )
        return response.draft
    }

    public func createGmailDraftFromFollowupDraft(id: Int, to: String?, subject: String?, body: String?) async throws -> FollowupDraftEnvelope {
        try await post(
            baseURL.appending(path: "/api/email/drafts/\(id)/gmail-draft"),
            body: FollowupDraftUpdateRequest(to: to, subject: subject, body: body)
        )
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

    public func fetchContextDetail(id: Int) async throws -> ContextDetailResponse {
        try await get(baseURL.appending(path: "/api/contexts/\(id)/detail"))
    }

    public func createContext(request: ContextCreateRequest) async throws -> ContextDetailResponse {
        try await post(baseURL.appending(path: "/api/contexts"), body: request)
    }

    public func updateContextProfile(id: Int, request: ContextProfileUpdateRequest) async throws -> ContextDetailResponse {
        try await post(baseURL.appending(path: "/api/contexts/\(id)/profile"), body: request)
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

    public func clearBotSessions() async throws -> BotSessionClearResponse {
        try await post(baseURL.appending(path: "/api/capture/bot/sessions/clear"), body: EmptyBody())
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

    public func transcribeAssistantVoice() async throws -> AssistantVoiceTranscriptResponse {
        try await post(baseURL.appending(path: "/api/assistant/voice/transcribe"), body: EmptyBody())
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

    public func confirmSuggestionEnvelope(id: Int) async throws -> SuggestionEnvelope {
        try await post(baseURL.appending(path: "/api/suggestions/\(id)/confirm"), body: EmptyBody())
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

    public func clearReviewedSuggestions() async throws -> ClearSuggestionsResponse {
        try await post(baseURL.appending(path: "/api/suggestions/reviewed/clear"), body: EmptyBody())
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

    public func clearDoneTasks() async throws -> ClearDoneTasksResponse {
        try await post(baseURL.appending(path: "/api/tasks/done/clear"), body: EmptyBody())
    }

    private func get<T: Decodable>(_ url: URL) async throws -> T {
        let (data, response) = try await session.data(for: request(url: url, method: "GET"))
        try validate(response: response, data: data)
        return try SpeedwagonJSON.decoder.decode(T.self, from: data)
    }

    private func post<T: Decodable, Body: Encodable>(_ url: URL, body: Body) async throws -> T {
        var request = request(url: url, method: "POST")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try SpeedwagonJSON.encoder.encode(body)

        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        return try SpeedwagonJSON.decoder.decode(T.self, from: data)
    }

    private func request(url: URL, method: String) -> URLRequest {
        var request = URLRequest(url: url)
        request.httpMethod = method
        let token = apiToken ?? SpeedwagonAPIClient.loadLocalAPIToken()
        if let token, !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        return request
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

    static func loadLocalAPIToken() -> String? {
        let environment = ProcessInfo.processInfo.environment
        if let token = environment["SPEEDWAGON_API_TOKEN"]?.trimmingCharacters(in: .whitespacesAndNewlines), !token.isEmpty {
            return token
        }

        var candidates: [String] = []
        if let configuredPath = environment["SPEEDWAGON_API_TOKEN_PATH"], !configuredPath.isEmpty {
            candidates.append(configuredPath)
        }
        var directory = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        for _ in 0..<6 {
            candidates.append(directory.appending(path: "data/local_api_token").path)
            directory.deleteLastPathComponent()
        }

        for path in candidates {
            if let value = try? String(contentsOfFile: path, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines),
               !value.isEmpty {
                return value
            }
        }
        if let token = try? KeychainStore.shared.load(account: KeychainAccount.localAPIToken),
           !token.isEmpty {
            return token
        }
        return nil
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
