import Combine
import Foundation
import SpeedwagonAICore
import UserNotifications

enum MeetingCaptureMode: String, CaseIterable, Identifiable {
    case nativeSystemMic = "Native system + mic"
    case micFallback = "Mic fallback"

    var id: String { rawValue }

    var backendMode: String {
        switch self {
        case .nativeSystemMic:
            return "system_mic"
        case .micFallback:
            return "mic"
        }
    }
}

func tomorrowISODate() -> String {
    let tomorrow = Calendar(identifier: .gregorian).date(byAdding: .day, value: 1, to: Date()) ?? Date()
    let formatter = DateFormatter()
    formatter.calendar = Calendar(identifier: .gregorian)
    formatter.timeZone = TimeZone.current
    formatter.dateFormat = "yyyy-MM-dd"
    return formatter.string(from: tomorrow)
}

func supportsNativeNotifications() -> Bool {
    Bundle.main.bundleURL.pathExtension == "app"
}

@MainActor
final class AppState: ObservableObject {
    static let shared = AppState()

    @Published var tasks: [TaskItem] = []
    @Published var meetings: [MeetingItem] = []
    @Published var selectedMeetingDetail: MeetingDetailResponse?
    @Published var commitments: [TaskItem] = []
    @Published var suggestions: [SuggestionItem] = []
    @Published var notificationStatus: NotificationStatusResponse?
    @Published var notificationCandidates: [SuggestionItem] = []
    @Published var notificationPermissionStatus = "notDetermined"
    @Published var dailyBrief: DailyBriefResponse?
    @Published var capabilities: [AssistantCapability] = []
    @Published var settings: SettingsResponse?
    @Published var calendarStatus: CalendarStatusResponse?
    @Published var calendarEvents: [CalendarEvent] = []
    @Published var captureStatus: CaptureSession?
    @Published var captureDiagnostics: CaptureDiagnostics?
    @Published var botStatus: BotStatusResponse?
    @Published var botSessions: [BotSession] = []
    @Published var botMeetingTitle = ""
    @Published var botMeetingURL = ""
    @Published var botConsentConfirmed = false
    @Published var assistantVoiceStatus: CaptureSession?
    @Published var pendingActions: [PendingAssistantAction] = []
    @Published var meetingCaptureTitle = ""
    @Published var meetingCaptureMode: MeetingCaptureMode = .nativeSystemMic
    @Published var nativeCapturePermissions = ScreenCaptureKitMeetingRecorder().permissionSnapshot()
    @Published var nativeCaptureWarnings: [String] = []
    @Published var commandText = ""
    @Published var commandResponse: AssistantCommandResponse?
    @Published var commandErrorMessage: String?
    @Published var lastVoiceTranscript: String?
    @Published var lastScreenshotPNGData: Data?
    @Published var screenshotAnalysis: ScreenshotAnalysisResponse?
    @Published var isConnected = false
    @Published var isLoading = false
    @Published var statusMessage = "Checking backend..."

    let client: SpeedwagonAPIClient
    private let nativeRecorder: NativeMeetingRecording
    private var notificationPollTask: Task<Void, Never>?
    private var scheduledNotificationIds: Set<Int> = []

    init(
        client: SpeedwagonAPIClient = SpeedwagonAPIClient(),
        nativeRecorder: NativeMeetingRecording = ScreenCaptureKitMeetingRecorder()
    ) {
        self.client = client
        self.nativeRecorder = nativeRecorder
        self.nativeCapturePermissions = nativeRecorder.permissionSnapshot()
    }

    deinit {
        notificationPollTask?.cancel()
    }

    var groupedTasks: [TaskGroupKind: [TaskItem]] {
        TaskGrouper.group(tasks)
    }

    var backendStatusLabel: String {
        isConnected ? "Connected" : "Disconnected"
    }

    var isAssistantVoiceActive: Bool {
        assistantVoiceStatus?.isActive == true || captureStatus?.kind == "assistant_voice"
    }

    var isNativeMeetingCaptureActive: Bool {
        captureStatus?.isActive == true && captureStatus?.isNative == true
    }

    func refreshTasks() async {
        await refreshAll()
    }

    func refreshAll(updateStatus: Bool = true) async {
        isLoading = true
        defer { isLoading = false }

        var failures: [String] = []

        do {
            settings = try await client.fetchSettings()
            isConnected = true
        } catch {
            isConnected = false
            settings = nil
            if updateStatus {
                statusMessage = "Backend disconnected. Start it with: speedwagon app"
            }
            return
        }

        do {
            meetings = try await client.fetchMeetings()
        } catch {
            failures.append("meetings")
        }

        do {
            tasks = try await client.fetchTasks()
        } catch {
            failures.append("tasks")
        }

        do {
            commitments = try await client.fetchCommitments()
        } catch {
            failures.append("commitments")
        }

        do {
            dailyBrief = try await client.fetchDailyBrief()
        } catch {
            failures.append("daily brief")
        }

        do {
            calendarStatus = try await client.fetchCalendarStatus()
        } catch {
            failures.append("calendar status")
        }

        do {
            calendarEvents = try await client.fetchUpcomingCalendarEvents()
        } catch {
            failures.append("calendar")
        }

        do {
            capabilities = try await client.fetchCapabilities()
        } catch {
            failures.append("capabilities")
        }

        do {
            captureStatus = try await client.fetchCaptureStatus()
        } catch {
            failures.append("capture")
        }

        do {
            captureDiagnostics = try await client.fetchCaptureDiagnostics()
            nativeCapturePermissions = nativeRecorder.permissionSnapshot()
        } catch {
            failures.append("diagnostics")
        }

        do {
            botStatus = try await client.fetchBotStatus()
        } catch {
            failures.append("bot status")
        }

        do {
            botSessions = try await client.fetchBotSessions()
        } catch {
            failures.append("bot sessions")
        }

        do {
            assistantVoiceStatus = try await client.fetchAssistantVoiceStatus()
        } catch {
            failures.append("voice")
        }

        do {
            pendingActions = try await client.fetchPendingActions()
        } catch {
            failures.append("pending actions")
        }

        do {
            suggestions = try await client.fetchSuggestions()
        } catch {
            failures.append("suggestions")
        }

        do {
            notificationStatus = try await client.fetchNotificationStatus()
            notificationCandidates = try await client.fetchNotificationCandidates()
            await refreshNotificationPermissionStatus()
            await scheduleNotificationCandidates()
        } catch {
            failures.append("notifications")
        }

        if updateStatus {
            if failures.isEmpty {
                statusMessage = "Connected to SpeedwagonAI backend."
            } else {
                statusMessage = "Connected. Could not refresh: \(failures.joined(separator: ", "))."
            }
        }
    }

    func runCommand() async {
        let command = commandText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !command.isEmpty else { return }

        isLoading = true
        commandErrorMessage = nil
        defer { isLoading = false }

        do {
            if await runNativeCaptureCommandIfNeeded(command) {
                commandText = ""
                isConnected = true
                return
            }

            let response = try await client.runCommand(command)
            commandResponse = response
            isConnected = true
            commandText = ""
            await refreshAll(updateStatus: false)
            statusMessage = response.supported ? "Command finished." : "Command not supported."
        } catch {
            commandErrorMessage = error.localizedDescription
            commandResponse = AssistantCommandResponse(
                supported: false,
                category: "system_status",
                summary: "Command failed: \(error.localizedDescription)",
                command: command
            )
            statusMessage = "Command failed."
        }
    }

    private func runNativeCaptureCommandIfNeeded(_ command: String) async -> Bool {
        let normalized = command.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        if let title = nativeMeetingTitle(from: normalized) {
            if normalized.contains("native") {
                meetingCaptureMode = .nativeSystemMic
            }
            meetingCaptureTitle = title
            await startMeetingCapture()
            let started = captureStatus?.isActive == true
            commandResponse = AssistantCommandResponse(
                supported: started,
                action: meetingCaptureMode == .nativeSystemMic ? "start_native_meeting_recording" : "start_meeting_recording",
                category: "capture",
                requiresConfirmation: false,
                confidence: 1.0,
                source: "native",
                summary: started ? "Started \(meetingCaptureMode.rawValue) recording: \(title)." : statusMessage,
                command: command
            )
            return true
        }

        if ["finish meeting", "finish recording", "stop and process meeting", "stop meeting and process"].contains(normalized) {
            let wasNative = isNativeMeetingCaptureActive
            guard captureStatus?.isActive == true else {
                commandResponse = AssistantCommandResponse(
                    supported: false,
                    action: "finish_meeting_recording",
                    category: "capture",
                    requiresConfirmation: false,
                    source: "native",
                    summary: "No active meeting recording to finish.",
                    command: command
                )
                return true
            }
            await stopCapture(process: true)
            commandResponse = AssistantCommandResponse(
                supported: true,
                action: wasNative ? "finish_native_meeting_recording" : "finish_meeting_recording",
                category: "capture",
                requiresConfirmation: false,
                confidence: 1.0,
                source: "native",
                summary: "Stopped and processed the active meeting recording.",
                command: command
            )
            return true
        }

        if normalized == "stop meeting without processing" || normalized == "stop recording without processing" {
            let wasNative = isNativeMeetingCaptureActive
            guard captureStatus?.isActive == true else {
                commandResponse = AssistantCommandResponse(
                    supported: false,
                    action: "stop_meeting_recording",
                    category: "capture",
                    requiresConfirmation: false,
                    source: "native",
                    summary: "No active meeting recording to stop.",
                    command: command
                )
                return true
            }
            await stopCapture(process: false)
            commandResponse = AssistantCommandResponse(
                supported: true,
                action: wasNative ? "stop_native_meeting_recording" : "stop_meeting_recording",
                category: "capture",
                requiresConfirmation: false,
                confidence: 1.0,
                source: "native",
                summary: "Stopped the active meeting recording without processing.",
                command: command
            )
            return true
        }

        return false
    }

    private func nativeMeetingTitle(from normalizedCommand: String) -> String? {
        let patterns = [
            #"^start native meeting recording called (.+)$"#,
            #"^start native meeting capture called (.+)$"#,
            #"^start native meeting called (.+)$"#,
            #"^start meeting recording called (.+)$"#,
            #"^start meeting capture called (.+)$"#
        ]
        for pattern in patterns {
            guard let regex = try? NSRegularExpression(pattern: pattern) else {
                continue
            }
            let range = NSRange(normalizedCommand.startIndex..<normalizedCommand.endIndex, in: normalizedCommand)
            guard let match = regex.firstMatch(in: normalizedCommand, range: range),
                  match.numberOfRanges > 1,
                  let titleRange = Range(match.range(at: 1), in: normalizedCommand)
            else {
                continue
            }
            let title = normalizedCommand[titleRange].trimmingCharacters(in: .whitespacesAndNewlines)
            return title.isEmpty ? nil : title
        }
        return nil
    }

    func complete(_ task: TaskItem) async {
        do {
            _ = try await client.completeTask(id: task.id)
            await refreshAll()
        } catch {
            statusMessage = "Could not complete task \(task.id)."
        }
    }

    func reopen(_ task: TaskItem) async {
        do {
            _ = try await client.reopenTask(id: task.id)
            await refreshAll()
        } catch {
            statusMessage = "Could not reopen task \(task.id)."
        }
    }

    func loadMeeting(_ meeting: MeetingItem) async {
        do {
            selectedMeetingDetail = try await client.fetchMeetingDetail(id: meeting.id)
            statusMessage = "Loaded meeting \(meeting.id)."
        } catch {
            statusMessage = "Could not load meeting \(meeting.id): \(error.localizedDescription)"
        }
    }

    func processMeeting(_ meeting: MeetingItem) async {
        do {
            _ = try await client.processMeeting(id: meeting.id)
            selectedMeetingDetail = try await client.fetchMeetingDetail(id: meeting.id)
            statusMessage = "Processed meeting \(meeting.id)."
            await refreshAll(updateStatus: false)
        } catch {
            statusMessage = "Could not process meeting \(meeting.id): \(error.localizedDescription)"
        }
    }

    func startMeetingCapture() async {
        let title = meetingCaptureTitle.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !title.isEmpty else {
            statusMessage = "Meeting title is required."
            return
        }
        if meetingCaptureMode == .nativeSystemMic {
            await startNativeMeetingCapture(title: title)
            return
        }
        do {
            captureStatus = try await client.startCapture(kind: "meeting", title: title)
            statusMessage = "Recording meeting."
            meetingCaptureTitle = ""
            await refreshAll(updateStatus: false)
        } catch {
            statusMessage = "Could not start meeting capture: \(error.localizedDescription)"
        }
    }

    func stopCapture(process: Bool) async {
        if isNativeMeetingCaptureActive {
            await stopNativeMeetingCapture(process: process)
            return
        }
        do {
            let response = try await client.stopCapture(process: process)
            if response.task != nil {
                statusMessage = "Added voice task."
            } else if process {
                statusMessage = "Stopped and processed meeting."
            } else {
                statusMessage = "Stopped capture."
            }
            await refreshAll(updateStatus: false)
        } catch {
            statusMessage = "Could not stop capture: \(error.localizedDescription)"
        }
    }

    private func startNativeMeetingCapture(title: String) async {
        do {
            nativeCaptureWarnings = []
            let prepared = try await client.prepareNativeCapture(title: title, mode: meetingCaptureMode.backendMode)
            captureStatus = prepared
            do {
                try await nativeRecorder.start(session: prepared)
                statusMessage = "Recording meeting with native system + mic capture."
                meetingCaptureTitle = ""
                await refreshAll(updateStatus: false)
            } catch {
                if let sessionId = prepared.sessionId {
                    _ = try? await client.failNativeCapture(sessionId: sessionId, error: error.localizedDescription)
                }
                captureStatus = try? await client.fetchCaptureStatus()
                statusMessage = "Native capture could not start: \(error.localizedDescription) Use Mic fallback if needed."
            }
        } catch {
            statusMessage = "Could not prepare native capture: \(error.localizedDescription)"
        }
    }

    private func stopNativeMeetingCapture(process: Bool) async {
        guard let session = captureStatus, let sessionId = session.sessionId else {
            statusMessage = "Native capture session is missing its id."
            return
        }
        do {
            let result = try await nativeRecorder.stop()
            nativeCaptureWarnings = result.warnings
            let response = try await client.completeNativeCapture(
                sessionId: sessionId,
                audioPath: result.audioPath,
                process: process,
                warnings: result.warnings
            )
            if process {
                statusMessage = "Stopped native capture and processed meeting."
            } else if result.warnings.isEmpty {
                statusMessage = "Stopped native capture."
            } else {
                statusMessage = "Stopped native capture with warning: \(result.warnings.joined(separator: " "))"
            }
            captureStatus = response.session
            await refreshAll(updateStatus: false)
        } catch {
            nativeCaptureWarnings = [error.localizedDescription]
            _ = try? await client.failNativeCapture(sessionId: sessionId, error: error.localizedDescription)
            captureStatus = try? await client.fetchCaptureStatus()
            statusMessage = "Native capture failed: \(error.localizedDescription)"
        }
    }

    func startTaskCapture() async {
        do {
            captureStatus = try await client.startCapture(kind: "task_note")
            statusMessage = "Recording voice task."
            await refreshAll(updateStatus: false)
        } catch {
            statusMessage = "Could not start voice task capture: \(error.localizedDescription)"
        }
    }

    func startAssistantVoice() async {
        do {
            assistantVoiceStatus = try await client.startAssistantVoice()
            captureStatus = assistantVoiceStatus
            statusMessage = "Recording assistant voice message."
        } catch {
            statusMessage = "Could not start assistant voice: \(error.localizedDescription)"
        }
    }

    func joinBotSession() async {
        let title = botMeetingTitle.trimmingCharacters(in: .whitespacesAndNewlines)
        let meetingURL = botMeetingURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !title.isEmpty else {
            statusMessage = "Bot meeting title is required."
            return
        }
        guard !meetingURL.isEmpty else {
            statusMessage = "Meeting link is required."
            return
        }
        guard botConsentConfirmed else {
            statusMessage = "Confirm bot disclosure/consent before joining."
            return
        }
        do {
            let response = try await client.joinBotSession(
                meetingUrl: meetingURL,
                title: title,
                consentConfirmed: true
            )
            statusMessage = "Joined bot session \(response.session.id)."
            botMeetingURL = ""
            botConsentConfirmed = false
            await refreshAll(updateStatus: false)
        } catch {
            statusMessage = "Could not join meeting bot: \(error.localizedDescription)"
        }
    }

    func syncBotSession(_ session: BotSession) async {
        do {
            _ = try await client.syncBotSession(id: session.id)
            statusMessage = "Synced bot session \(session.id)."
            await refreshAll(updateStatus: false)
        } catch {
            statusMessage = "Could not sync bot session \(session.id): \(error.localizedDescription)"
        }
    }

    func syncCalendar() async {
        do {
            let response = try await client.syncCalendar()
            statusMessage = "Synced \(response.syncedCount) calendar events."
            await refreshAll(updateStatus: false)
        } catch {
            statusMessage = "Could not sync calendar: \(error.localizedDescription)"
        }
    }

    func startNotificationPollingIfNeeded() {
        guard notificationPollTask == nil else { return }
        notificationPollTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 15 * 60 * 1_000_000_000)
                await self?.refreshNotificationsOnly()
            }
        }
    }

    func requestNotificationPermission() async {
        guard supportsNativeNotifications() else {
            notificationPermissionStatus = "unsupported"
            statusMessage = "Native notifications require running SpeedwagonAI as an app bundle; swift run disables them."
            return
        }
        do {
            let allowed = try await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge])
            notificationPermissionStatus = allowed ? "authorized" : "denied"
            statusMessage = allowed ? "Notifications allowed." : "Notifications not allowed."
            if allowed {
                await scheduleNotificationCandidates()
            }
        } catch {
            notificationPermissionStatus = "error"
            statusMessage = "Could not request notifications: \(error.localizedDescription)"
        }
    }

    func refreshNotificationsOnly() async {
        do {
            notificationStatus = try await client.fetchNotificationStatus()
            notificationCandidates = try await client.fetchNotificationCandidates()
            await refreshNotificationPermissionStatus()
            await scheduleNotificationCandidates()
        } catch {
            statusMessage = "Could not refresh notifications: \(error.localizedDescription)"
        }
    }

    func markNotificationDelivered(_ suggestion: SuggestionItem) async {
        do {
            _ = try await client.markNotificationDelivered(id: suggestion.id)
            await refreshNotificationsOnly()
        } catch {
            statusMessage = "Could not mark notification delivered: \(error.localizedDescription)"
        }
    }

    func dismissNotification(_ suggestion: SuggestionItem) async {
        do {
            _ = try await client.dismissNotification(id: suggestion.id)
            statusMessage = "Dismissed notification \(suggestion.id)."
            await refreshAll(updateStatus: false)
        } catch {
            statusMessage = "Could not dismiss notification \(suggestion.id): \(error.localizedDescription)"
        }
    }

    func snoozeNotification(_ suggestion: SuggestionItem) async {
        do {
            let until = tomorrowISODate()
            _ = try await client.snoozeNotification(id: suggestion.id, until: until)
            statusMessage = "Snoozed notification \(suggestion.id)."
            await refreshAll(updateStatus: false)
        } catch {
            statusMessage = "Could not snooze notification \(suggestion.id): \(error.localizedDescription)"
        }
    }

    func refreshNotificationPermissionStatus() async {
        guard supportsNativeNotifications() else {
            notificationPermissionStatus = "unsupported"
            return
        }
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        switch settings.authorizationStatus {
        case .authorized:
            notificationPermissionStatus = "authorized"
        case .denied:
            notificationPermissionStatus = "denied"
        case .notDetermined:
            notificationPermissionStatus = "notDetermined"
        case .provisional:
            notificationPermissionStatus = "provisional"
        case .ephemeral:
            notificationPermissionStatus = "ephemeral"
        @unknown default:
            notificationPermissionStatus = "unknown"
        }
    }

    private func scheduleNotificationCandidates() async {
        guard supportsNativeNotifications() else { return }
        guard notificationPermissionStatus == "authorized" || notificationPermissionStatus == "provisional" else { return }
        for candidate in notificationCandidates.prefix(8) where !scheduledNotificationIds.contains(candidate.id) {
            let content = UNMutableNotificationContent()
            content.title = candidate.title
            content.body = candidate.notificationReason ?? candidate.reason
            content.sound = .default
            content.userInfo = ["suggestion_id": candidate.id]
            let request = UNNotificationRequest(
                identifier: "speedwagon-suggestion-\(candidate.id)",
                content: content,
                trigger: UNTimeIntervalNotificationTrigger(timeInterval: 2, repeats: false)
            )
            do {
                try await UNUserNotificationCenter.current().add(request)
                scheduledNotificationIds.insert(candidate.id)
                _ = try? await client.markNotificationDelivered(id: candidate.id)
            } catch {
                statusMessage = "Could not schedule notification \(candidate.id): \(error.localizedDescription)"
            }
        }
    }

    func processBotSession(_ session: BotSession) async {
        do {
            let response = try await client.processBotSession(id: session.id)
            statusMessage = "Processed bot meeting \(response.meeting.id)."
            await refreshAll(updateStatus: false)
        } catch {
            statusMessage = "Could not process bot session \(session.id): \(error.localizedDescription)"
        }
    }

    func stopAssistantVoice() async {
        do {
            let response = try await client.stopAssistantVoice()
            lastVoiceTranscript = response.transcript
            commandResponse = response.assistantResponse
            statusMessage = response.assistantResponse.supported ? "Voice command finished." : "Voice command not supported."
            await refreshAll(updateStatus: false)
        } catch {
            commandErrorMessage = error.localizedDescription
            commandResponse = AssistantCommandResponse(
                supported: false,
                category: "system_status",
                summary: "Voice command failed: \(error.localizedDescription)",
                result: nil
            )
            statusMessage = "Voice command failed."
        }
    }

    func analyzeScreenshot() async {
        isLoading = true
        commandErrorMessage = nil
        defer { isLoading = false }

        do {
            let data = try await captureMainDisplayPNGExcludingSpeedwagonWindows()
            lastScreenshotPNGData = data
            let instruction = commandText.trimmingCharacters(in: .whitespacesAndNewlines)
            let response = try await client.analyzeScreenshot(
                imageBase64: data.base64EncodedString(),
                instruction: instruction.isEmpty ? nil : instruction
            )
            screenshotAnalysis = response
            pendingActions = response.pendingActions
            commandResponse = AssistantCommandResponse(
                supported: true,
                action: "analyze_screenshot",
                category: "context",
                requiresConfirmation: false,
                confidence: response.confidence,
                source: response.provider,
                summary: response.summary,
                command: instruction.isEmpty ? "screenshot" : instruction
            )
            if !instruction.isEmpty {
                commandText = ""
            }
            statusMessage = response.pendingActions.isEmpty
                ? "Screenshot analyzed."
                : "Screenshot analyzed. Review \(response.pendingActions.count) pending action(s)."
            await refreshAll(updateStatus: false)
        } catch {
            commandErrorMessage = error.localizedDescription
            commandResponse = AssistantCommandResponse(
                supported: false,
                category: "context",
                summary: "Screenshot analysis failed: \(error.localizedDescription)",
                result: nil
            )
            statusMessage = "Screenshot analysis failed."
        }
    }

    func confirm(_ action: PendingAssistantAction) async {
        do {
            let response = try await client.confirmPendingAction(id: action.id)
            commandResponse = response
            statusMessage = response.summary
            await refreshAll(updateStatus: false)
        } catch {
            statusMessage = "Could not confirm action \(action.id): \(error.localizedDescription)"
        }
    }

    func cancel(_ action: PendingAssistantAction) async {
        do {
            let response = try await client.cancelPendingAction(id: action.id)
            commandResponse = response
            statusMessage = response.summary
            await refreshAll(updateStatus: false)
        } catch {
            statusMessage = "Could not cancel action \(action.id): \(error.localizedDescription)"
        }
    }

    func confirm(_ suggestion: SuggestionItem) async {
        do {
            let updated = try await client.confirmSuggestion(id: suggestion.id)
            statusMessage = "Accepted suggestion \(updated.id)."
            await refreshAll(updateStatus: false)
        } catch {
            statusMessage = "Could not accept suggestion \(suggestion.id): \(error.localizedDescription)"
        }
    }

    func dismiss(_ suggestion: SuggestionItem) async {
        do {
            let updated = try await client.dismissSuggestion(id: suggestion.id)
            statusMessage = "Dismissed suggestion \(updated.id)."
            await refreshAll(updateStatus: false)
        } catch {
            statusMessage = "Could not dismiss suggestion \(suggestion.id): \(error.localizedDescription)"
        }
    }

    func snooze(_ suggestion: SuggestionItem) async {
        do {
            let updated = try await client.snoozeSuggestion(id: suggestion.id)
            statusMessage = "Snoozed suggestion \(updated.id)."
            await refreshAll(updateStatus: false)
        } catch {
            statusMessage = "Could not snooze suggestion \(suggestion.id): \(error.localizedDescription)"
        }
    }
}
