import Combine
import AppKit
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

enum AssistantVoicePurpose {
    case assistant
    case calendarNaturalLanguage
    case calendarDescription
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

private extension String {
    var nilIfEmpty: String? {
        isEmpty ? nil : self
    }
}

@MainActor
final class AppState: ObservableObject {
    static let shared = AppState()

    @Published var tasks: [TaskItem] = []
    @Published var meetings: [MeetingItem] = []
    @Published var selectedMeetingDetail: MeetingDetailResponse?
    @Published var commitments: [TaskItem] = []
    @Published var suggestions: [SuggestionItem] = []
    @Published var followupDrafts: [FollowupDraft] = []
    @Published var selectedFollowupDraft: FollowupDraft?
    @Published var draftRecipient = ""
    @Published var draftSubject = ""
    @Published var draftBody = ""
    @Published var highlightedSuggestionId: Int?
    @Published var suggestionReviewToken = 0
    @Published var highlightedTaskIds: Set<Int> = []
    @Published var selectedReviewSuggestion: SuggestionItem?
    @Published var selectedContextDetail: ContextDetailResponse?
    @Published var highlightedContextId: Int?
    @Published var notificationStatus: NotificationStatusResponse?
    @Published var notificationCandidates: [SuggestionItem] = []
    @Published var notificationPermissionStatus = "notDetermined"
    @Published var dailyBrief: DailyBriefResponse?
    @Published var intelligenceStatus: IntelligenceStatusResponse?
    @Published var isRefreshingIntelligence = false
    @Published var capabilities: [AssistantCapability] = []
    @Published var settings: SettingsResponse?
    @Published var systemLogs: SystemLogsResponse?
    @Published var privacyStatus: PrivacyStatusResponse?
    @Published var calendarStatus: CalendarStatusResponse?
    @Published var calendarEvents: [CalendarEvent] = []
    @Published var calendarCreateTitle = ""
    @Published var calendarCreateStart = "\(tomorrowISODate())T10:00:00-07:00"
    @Published var calendarCreateEnd = "\(tomorrowISODate())T10:30:00-07:00"
    @Published var calendarCreateDescription = ""
    @Published var calendarCreateLocation = ""
    @Published var calendarCreateAttendees = ""
    @Published var calendarCreateSendUpdates = false
    @Published var calendarNaturalLanguageInput = ""
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
    @Published var assistantVoicePurpose: AssistantVoicePurpose?
    @Published var lastScreenshotPNGData: Data?
    @Published var screenshotAnalysis: ScreenshotAnalysisResponse?
    @Published var isConnected = false
    @Published var isLoading = false
    @Published var statusMessage = "Checking backend..."
    @Published var backendState: BackendState = .notStarted
    @Published var backendCommandPreview = ""
    @Published var backendLogPath = ""
    @Published var repoRootInput = ""
    @Published var repoRootDiscoverySource = "not checked"
    @Published var pythonVersionStatus = PythonVersionStatus.notChecked.displayText
    @Published var localTokenPresence = "not checked"
    @Published var openAIKeyPresence = "not checked"
    @Published var localBetaDiagnosticsReport = ""
    @Published var openAIAPIKeyInput = ""
    @Published var exportPathInput = ""
    @Published var wipeConfirmationInput = ""

    let client: SpeedwagonAPIClient
    private let nativeRecorder: NativeMeetingRecording
    private let backendManager: BackendManager
    private let keychain: KeychainStore
    private var notificationPollTask: Task<Void, Never>?
    private var scheduledNotificationIds: Set<Int> = []

    init(
        client: SpeedwagonAPIClient = SpeedwagonAPIClient(),
        nativeRecorder: NativeMeetingRecording = ScreenCaptureKitMeetingRecorder(),
        backendManager: BackendManager = BackendManager(),
        keychain: KeychainStore = .shared
    ) {
        self.client = client
        self.nativeRecorder = nativeRecorder
        self.backendManager = backendManager
        self.keychain = keychain
        self.nativeCapturePermissions = nativeRecorder.permissionSnapshot()
        if let discovery = try? BackendManager.discoverRepoRootDetails() {
            self.repoRootInput = discovery.path
            self.repoRootDiscoverySource = discovery.displaySource
        }
        self.backendState = backendManager.state
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

    var isCalendarNaturalLanguageVoiceActive: Bool {
        isAssistantVoiceActive && assistantVoicePurpose == .calendarNaturalLanguage
    }

    var isCalendarDescriptionVoiceActive: Bool {
        isAssistantVoiceActive && assistantVoicePurpose == .calendarDescription
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
            if await startBackendIfNeeded(updateStatus: updateStatus) {
                do {
                    settings = try await client.fetchSettings()
                    isConnected = true
                } catch {
                    isConnected = false
                    settings = nil
                    if updateStatus {
                        statusMessage = "Backend starting failed or is still unavailable: \(error.localizedDescription)"
                    }
                    return
                }
            } else {
                isConnected = false
                settings = nil
                if updateStatus {
                    statusMessage = "Backend disconnected. Start it with: speedwagon app"
                }
                return
            }
        }

        // Fetch all data in parallel — was sequential, causing ~17 round-trips in series.
        async let fetchedMeetings = try? client.fetchMeetings()
        async let fetchedTasks = try? client.fetchTasks()
        async let fetchedCommitments = try? client.fetchCommitments()
        async let fetchedBrief = try? client.fetchDailyBrief()
        async let fetchedCalendarStatus = try? client.fetchCalendarStatus()
        async let fetchedCalendarEvents = try? client.fetchUpcomingCalendarEvents()
        async let fetchedCapture = try? client.fetchCaptureStatus()
        async let fetchedCaptureDiag = try? client.fetchCaptureDiagnostics()
        async let fetchedBotStatus = try? client.fetchBotStatus()
        async let fetchedBotSessions = try? client.fetchBotSessions()
        async let fetchedVoiceStatus = try? client.fetchAssistantVoiceStatus()
        async let fetchedPendingActions = try? client.fetchPendingActions()
        async let fetchedSuggestions = try? client.fetchSuggestions()
        async let fetchedDrafts = try? client.fetchFollowupDrafts()
        async let fetchedLogs = try? client.fetchSystemLogs()
        async let fetchedPrivacy = try? client.fetchPrivacyStatus()
        async let fetchedNotifStatus = try? client.fetchNotificationStatus()
        async let fetchedNotifCandidates = try? client.fetchNotificationCandidates()

        let (m, t, c, b, cs, ce, cap, cd, bs, bss, av, pa, sg, dr, sl, pv, ns, nc) = await (
            fetchedMeetings, fetchedTasks, fetchedCommitments, fetchedBrief,
            fetchedCalendarStatus, fetchedCalendarEvents,
            fetchedCapture, fetchedCaptureDiag,
            fetchedBotStatus, fetchedBotSessions, fetchedVoiceStatus,
            fetchedPendingActions, fetchedSuggestions, fetchedDrafts,
            fetchedLogs, fetchedPrivacy, fetchedNotifStatus, fetchedNotifCandidates
        )

        if let m { meetings = m } else { failures.append("meetings") }
        if let t { tasks = t } else { failures.append("tasks") }
        if let c { commitments = c } else { failures.append("commitments") }
        if let b {
            dailyBrief = b
            intelligenceStatus = try? await client.fetchIntelligenceStatus(date: b.date)
        } else { failures.append("daily brief") }
        if let cs { calendarStatus = cs } else { failures.append("calendar status") }
        if let ce { calendarEvents = ce } else { failures.append("calendar") }
        if let cap { captureStatus = cap } else { failures.append("capture") }
        if let cd { captureDiagnostics = cd; nativeCapturePermissions = nativeRecorder.permissionSnapshot() } else { failures.append("diagnostics") }
        if let bs { botStatus = bs } else { failures.append("bot status") }
        if let bss { botSessions = bss } else { failures.append("bot sessions") }
        if let av { assistantVoiceStatus = av } else { failures.append("voice") }
        if let pa { pendingActions = pa } else { failures.append("pending actions") }
        if let sg { suggestions = sg } else { failures.append("suggestions") }
        if let dr { followupDrafts = dr } else { failures.append("drafts") }
        if let sl {
            systemLogs = sl
            backendLogPath = sl.backendLogPath.isEmpty ? (settings?.backendLogPath ?? "") : sl.backendLogPath
        } else { failures.append("system") }
        if let pv { privacyStatus = pv }
        if let ns { notificationStatus = ns }
        if let nc {
            notificationCandidates = nc
            suggestions = Self.mergeSuggestions(suggestions, with: nc)
            await refreshNotificationPermissionStatus()
            await scheduleNotificationCandidates()
        } else { failures.append("notifications") }

        if updateStatus {
            if failures.isEmpty {
                statusMessage = "Connected to SpeedwagonAI backend."
            } else {
                statusMessage = "Connected. Could not refresh: \(failures.joined(separator: ", "))."
            }
        }
    }

    func startBackendIfNeeded(updateStatus: Bool = true) async -> Bool {
        do {
            let config = try backendManager.makeConfiguration(repoRoot: repoRootInput.isEmpty ? nil : repoRootInput, keychain: keychain)
            backendCommandPreview = config.commandPreview
            backendLogPath = config.logPath
            try backendManager.start(configuration: config)
            backendState = backendManager.state
            if updateStatus {
                statusMessage = "Starting local backend..."
            }
            try? await Task.sleep(nanoseconds: 900_000_000)
            return true
        } catch {
            backendState = backendManager.state
            statusMessage = "Could not start backend: \(error.localizedDescription)"
            return false
        }
    }

    func stopManagedBackend() {
        backendManager.stop()
        backendState = backendManager.state
        statusMessage = "Stopped managed backend."
    }

    func saveCoreSecrets() async {
        do {
            if !openAIAPIKeyInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                try keychain.save(openAIAPIKeyInput.trimmingCharacters(in: .whitespacesAndNewlines), account: KeychainAccount.openAIAPIKey)
            }
            _ = try keychain.ensureLocalAPIToken()
            statusMessage = "Saved local beta secrets."
        } catch {
            statusMessage = "Could not save secrets: \(error.localizedDescription)"
        }
    }

    func refreshLocalBetaDiagnostics() async {
        if let discovery = try? BackendManager.discoverRepoRootDetails() {
            repoRootInput = repoRootInput.isEmpty ? discovery.path : repoRootInput
            repoRootDiscoverySource = discovery.displaySource
        } else {
            repoRootDiscoverySource = "missing"
        }
        let executable = backendCommandPreview.split(separator: " ").first.map(String.init) ?? "python3.11"
        pythonVersionStatus = await runPythonVersionCheck(executable: executable).displayText
        let localToken = try? keychain.load(account: KeychainAccount.localAPIToken)
        let openAIKey = try? keychain.load(account: KeychainAccount.openAIAPIKey)
        localTokenPresence = (localToken?.isEmpty == false) ? "present" : "missing"
        openAIKeyPresence = (openAIKey?.isEmpty == false) ? "present" : "missing"
        localBetaDiagnosticsReport = LocalBetaDiagnostics.report(
            input: diagnosticsInput(
                localTokenPresent: localToken?.isEmpty == false,
                openAIKeyPresent: openAIKey?.isEmpty == false
            ),
            secrets: [localToken, openAIKey].compactMap { $0 }
        )
        statusMessage = "Refreshed local beta diagnostics."
    }

    func copyLocalBetaDiagnosticsReport() async {
        await refreshLocalBetaDiagnostics()
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(localBetaDiagnosticsReport, forType: .string)
        statusMessage = "Copied redacted local beta diagnostics."
    }

    private func diagnosticsInput(localTokenPresent: Bool, openAIKeyPresent: Bool) -> LocalBetaDiagnosticsInput {
        LocalBetaDiagnosticsInput(
            repoRoot: repoRootInput,
            repoRootSource: repoRootDiscoverySource,
            backendState: backendState.rawValue,
            backendCommand: backendCommandPreview,
            pythonExecutable: backendCommandPreview.split(separator: " ").first.map(String.init) ?? "python3.11",
            pythonVersion: pythonVersionStatus,
            backendLogPath: backendLogPath,
            localTokenPresent: localTokenPresent,
            openAIKeyPresent: openAIKeyPresent,
            bundleMode: BundleMode.from(bundlePathExtension: Bundle.main.bundleURL.pathExtension).displayText,
            notificationPermission: notificationPermissionStatus
        )
    }

    private nonisolated func runPythonVersionCheck(executable: String) async -> PythonVersionStatus {
        await Task.detached {
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
            process.arguments = [executable] + PythonVersionProbe.arguments()
            let pipe = Pipe()
            process.standardOutput = pipe
            process.standardError = pipe
            do {
                try process.run()
                process.waitUntilExit()
                let data = pipe.fileHandleForReading.readDataToEndOfFile()
                let output = String(data: data, encoding: .utf8) ?? ""
                return PythonVersionProbe.parse(output: output, terminationStatus: process.terminationStatus)
            } catch {
                return .unavailable(error.localizedDescription)
            }
        }.value
    }

    func exportLocalData() async {
        do {
            let output = exportPathInput.trimmingCharacters(in: .whitespacesAndNewlines)
            let result = try await client.exportData(outputPath: output.isEmpty ? nil : output)
            statusMessage = "Exported \(result.fileCount) files to \(result.path)."
            await refreshAll(updateStatus: false)
        } catch {
            statusMessage = "Could not export data: \(error.localizedDescription)"
        }
    }

    func wipeLocalData() async {
        do {
            let result = try await client.wipeData(confirm: wipeConfirmationInput)
            wipeConfirmationInput = ""
            statusMessage = "Wiped local data paths: \(result.removed.count)."
            await refreshAll(updateStatus: false)
        } catch {
            statusMessage = "Could not wipe data: \(error.localizedDescription)"
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
            if Self.isMutatingAction(response.action) {
                await refreshAll(updateStatus: false)
            }
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

    func runSuggestedCommand(_ command: String) async {
        commandText = command
        await runCommand()
    }

    func clearConversation() {
        commandResponse = nil
        commandErrorMessage = nil
        lastVoiceTranscript = nil
        screenshotAnalysis = nil
        commandText = ""
    }

    private static let mutatingActions: Set<String> = [
        "add_task", "complete_task", "reopen_task", "snooze_task", "cancel_task",
        "mark_task_waiting", "mark_task_uncertain",
        "confirm_suggestion", "dismiss_suggestion", "snooze_suggestion",
        "process_meeting", "process_latest_meeting",
        "start_meeting_recording", "finish_meeting_recording", "stop_meeting_recording",
        "join_meeting_bot", "sync_bot_session", "process_bot_session",
        "create_calendar_event", "sync_calendar",
        "draft_meeting_followup", "draft_followup", "draft_email_from_context", "create_local_email_draft",
    ]

    static func isMutatingAction(_ action: String?) -> Bool {
        guard let action else { return false }
        return mutatingActions.contains(action)
    }

    func stopActiveAssistantVoiceFromComposer() async {
        switch assistantVoicePurpose {
        case .calendarNaturalLanguage:
            await stopCalendarNaturalLanguageVoice()
        case .calendarDescription:
            await stopCalendarDescriptionVoice()
        default:
            await stopAssistantVoice()
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
            let completed = try await client.completeTask(id: task.id)
            if let index = tasks.firstIndex(where: { $0.id == completed.id }) {
                tasks[index] = completed
            }
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

    func clearDoneTasks() async {
        do {
            let response = try await client.clearDoneTasks()
            tasks.removeAll { $0.status == "done" }
            statusMessage = response.cleared == 1
                ? "Cleared 1 completed task."
                : "Cleared \(response.cleared) completed tasks."
            await refreshAll(updateStatus: false)
        } catch {
            statusMessage = "Could not clear completed tasks: \(error.localizedDescription)"
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

    func loadContextDetail(_ context: ContextItem) async {
        await loadContextDetail(id: context.id, name: context.name)
    }

    func loadContextDetail(id: Int, name: String? = nil) async {
        do {
            selectedContextDetail = try await client.fetchContextDetail(id: id)
            highlightedContextId = id
            statusMessage = "Loaded review for \(selectedContextDetail?.context.name ?? name ?? "context #\(id)")."
        } catch {
            statusMessage = "Could not load context \(name ?? "#\(id)"): \(error.localizedDescription)"
        }
    }

    @discardableResult
    func createContext(name: String, kind: String = "person") async -> ContextDetailResponse? {
        let trimmedName = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedName.isEmpty else {
            statusMessage = "Person name is required."
            return nil
        }
        do {
            let detail = try await client.createContext(request: ContextCreateRequest(name: trimmedName, kind: kind))
            selectedContextDetail = detail
            highlightedContextId = detail.context.id
            statusMessage = "Added \(detail.context.name)."
            return detail
        } catch {
            statusMessage = "Could not add person: \(error.localizedDescription)"
            return nil
        }
    }

    @discardableResult
    func saveContextProfile(id: Int, email: String, phone: String, role: String, company: String, notes: String) async -> Bool {
        do {
            selectedContextDetail = try await client.updateContextProfile(
                id: id,
                request: ContextProfileUpdateRequest(
                    email: email.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty,
                    phone: phone.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty,
                    role: role.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty,
                    company: company.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty,
                    notes: notes.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty
                )
            )
            highlightedContextId = id
            statusMessage = "Saved profile for \(selectedContextDetail?.context.name ?? "context #\(id)")."
            return true
        } catch {
            statusMessage = "Could not save profile: \(error.localizedDescription)"
            return false
        }
    }

    func clearContextSelection() {
        selectedContextDetail = nil
        highlightedContextId = nil
    }

    func clearMeetingSelection() {
        selectedMeetingDetail = nil
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

    func startAssistantVoice(purpose: AssistantVoicePurpose = .assistant) async {
        do {
            assistantVoiceStatus = try await client.startAssistantVoice()
            captureStatus = assistantVoiceStatus
            assistantVoicePurpose = purpose
            switch purpose {
            case .assistant:
                statusMessage = "Recording assistant voice message."
            case .calendarNaturalLanguage:
                statusMessage = "Recording calendar event description."
            case .calendarDescription:
                statusMessage = "Recording Calendar event notes."
            }
        } catch {
            statusMessage = "Could not start assistant voice: \(error.localizedDescription)"
        }
    }

    func startCalendarNaturalLanguageVoice() async {
        await startAssistantVoice(purpose: .calendarNaturalLanguage)
    }

    func startCalendarDescriptionVoice() async {
        await startAssistantVoice(purpose: .calendarDescription)
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

    func clearBotSessions() async {
        do {
            let response = try await client.clearBotSessions()
            botSessions = response.sessions
            statusMessage = response.clearedCount == 1 ? "Cleared 1 bot session." : "Cleared \(response.clearedCount) bot sessions."
        } catch {
            statusMessage = "Could not clear bot sessions: \(error.localizedDescription)"
        }
    }

    func syncCalendar() async {
        do {
            let response = try await client.syncCalendar()
            if let removed = response.removedCount, removed > 0 {
                statusMessage = "Synced \(response.syncedCount) calendar events and removed \(removed) deleted event(s)."
            } else {
                statusMessage = "Synced \(response.syncedCount) calendar events."
            }
            await refreshAll(updateStatus: false)
        } catch {
            statusMessage = "Could not sync calendar: \(error.localizedDescription)"
        }
    }

    func createCalendarEvent() async {
        let title = calendarCreateTitle.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !title.isEmpty else {
            statusMessage = "Calendar event title is required."
            return
        }
        do {
            let request = CalendarCreateEventRequest(
                title: title,
                startAt: calendarCreateStart.trimmingCharacters(in: .whitespacesAndNewlines),
                endAt: calendarCreateEnd.trimmingCharacters(in: .whitespacesAndNewlines),
                calendarId: calendarStatus?.calendarIds?.first ?? "primary",
                timezone: TimeZone.current.identifier,
                description: calendarCreateDescription.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty,
                location: calendarCreateLocation.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty,
                attendees: calendarCreateAttendees
                    .split(whereSeparator: { $0 == "," || $0 == "\n" || $0 == ";" })
                    .map { String($0).trimmingCharacters(in: .whitespacesAndNewlines) }
                    .filter { !$0.isEmpty },
                sendUpdates: calendarCreateSendUpdates ? "all" : "none"
            )
            let response = try await client.createCalendarEvent(request)
            calendarEvents.insert(response.event, at: 0)
            calendarCreateTitle = ""
            calendarCreateDescription = ""
            calendarCreateLocation = ""
            calendarCreateAttendees = ""
            statusMessage = response.htmlLink?.isEmpty == false
                ? "Created Google Calendar event. Review it in Google Calendar."
                : "Created Google Calendar event."
            await refreshAll(updateStatus: false)
        } catch {
            statusMessage = "Could not create calendar event: \(error.localizedDescription)"
        }
    }

    func runCalendarNaturalLanguageInput() async {
        let command = calendarNaturalLanguageInput.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !command.isEmpty else { return }
        calendarNaturalLanguageInput = ""
        commandText = command
        await runCommand()
    }

    func stopCalendarNaturalLanguageVoice() async {
        do {
            let response = try await client.stopAssistantVoice()
            lastVoiceTranscript = response.transcript
            calendarNaturalLanguageInput = response.transcript
            commandResponse = response.assistantResponse
            assistantVoicePurpose = nil
            assistantVoiceStatus = response.session
            captureStatus = response.session
            statusMessage = response.assistantResponse.requiresConfirmation == true
                ? "Calendar event prepared. Review the pending confirmation."
                : "Calendar voice message finished."
            await refreshAll(updateStatus: false)
        } catch {
            assistantVoicePurpose = nil
            commandErrorMessage = error.localizedDescription
            commandResponse = AssistantCommandResponse(
                supported: false,
                category: "system_status",
                summary: "Calendar voice input failed: \(error.localizedDescription)",
                result: nil
            )
            statusMessage = "Calendar voice input failed."
        }
    }

    func stopCalendarDescriptionVoice() async {
        do {
            let response = try await client.transcribeAssistantVoice()
            lastVoiceTranscript = response.transcript
            let transcript = response.transcript.trimmingCharacters(in: .whitespacesAndNewlines)
            if !transcript.isEmpty {
                let existing = calendarCreateDescription.trimmingCharacters(in: .whitespacesAndNewlines)
                calendarCreateDescription = existing.isEmpty ? transcript : "\(existing)\n\(transcript)"
            }
            assistantVoicePurpose = nil
            assistantVoiceStatus = response.session
            captureStatus = response.session
            statusMessage = "Added voice notes to the Calendar description."
            await refreshAll(updateStatus: false)
        } catch {
            assistantVoicePurpose = nil
            commandErrorMessage = error.localizedDescription
            statusMessage = "Calendar description dictation failed: \(error.localizedDescription)"
        }
    }

    func refreshDailyIntelligence() async {
        guard !isRefreshingIntelligence else { return }
        isRefreshingIntelligence = true
        defer { isRefreshingIntelligence = false }
        do {
            let response = try await client.refreshDailyIntelligence(date: dailyBrief?.date, topSuggestionLimit: 8)
            intelligenceStatus = IntelligenceStatusResponse(
                date: response.date,
                cached: response.synthesis,
                latest: response.synthesis,
                manualRefreshRequired: true,
                note: "Daily intelligence is generated only when explicitly refreshed."
            )
            statusMessage = "Refreshed daily intelligence for \(response.date)."
            await refreshAll(updateStatus: false)
        } catch {
            statusMessage = "Could not refresh daily intelligence: \(error.localizedDescription)"
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
            suggestions = Self.mergeSuggestions(suggestions, with: notificationCandidates)
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
            assistantVoicePurpose = nil
            assistantVoiceStatus = response.session
            captureStatus = response.session
            statusMessage = response.assistantResponse.supported ? "Voice command finished." : "Voice command not supported."
            await refreshAll(updateStatus: false)
        } catch {
            assistantVoicePurpose = nil
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
            if let draft = response.result?.followupDraft {
                if !followupDrafts.contains(where: { $0.id == draft.id }) {
                    followupDrafts.insert(draft, at: 0)
                }
                selectFollowupDraft(draft)
                statusMessage = "Created local draft \(draft.id). Review it before creating it in Gmail."
            }
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
            let response = try await client.confirmSuggestionEnvelope(id: suggestion.id)
            upsertSuggestion(response.suggestion)
            selectedReviewSuggestion = response.suggestion
            highlightedSuggestionId = response.suggestion.id
            if let draft = response.actionResult?.followupDraft {
                selectFollowupDraft(draft)
                statusMessage = response.actionResult?.nextStep ?? "Accepted suggestion \(response.suggestion.id). Review the draft before creating it in Gmail."
            } else if response.actionResult?.task != nil {
                statusMessage = response.actionResult?.nextStep ?? "Accepted suggestion \(response.suggestion.id). Review the task."
            } else {
                statusMessage = response.actionResult?.nextStep ?? "Accepted suggestion \(response.suggestion.id)."
            }
            await refreshSuggestionState()
        } catch {
            statusMessage = "Could not accept suggestion \(suggestion.id): \(error.localizedDescription)"
        }
    }

    func clearReviewedSuggestions() async {
        do {
            let response = try await client.clearReviewedSuggestions()
            suggestions.removeAll { ["accepted", "dismissed", "retired"].contains($0.status) }
            if let selected = selectedReviewSuggestion,
               ["accepted", "dismissed", "retired"].contains(selected.status) {
                selectedReviewSuggestion = nil
            }
            statusMessage = response.cleared == 1
                ? "Cleared 1 reviewed suggestion."
                : "Cleared \(response.cleared) reviewed suggestions."
            await refreshSuggestionState()
        } catch {
            statusMessage = "Could not clear reviewed suggestions: \(error.localizedDescription)"
        }
    }

    func clearSuggestionSelection() {
        highlightedSuggestionId = nil
        highlightedTaskIds = []
        selectedReviewSuggestion = nil
        clearSelectedFollowupDraft()
    }

    private func upsertSuggestion(_ suggestion: SuggestionItem) {
        if let index = suggestions.firstIndex(where: { $0.id == suggestion.id }) {
            suggestions[index] = suggestion
        } else {
            suggestions.insert(suggestion, at: 0)
        }
    }

    func refreshSuggestionState() async {
        do {
            async let fetchedSuggestions = client.fetchSuggestions()
            async let fetchedDrafts = client.fetchFollowupDrafts()
            async let fetchedCandidates = try? client.fetchNotificationCandidates()
            suggestions = try await fetchedSuggestions
            followupDrafts = try await fetchedDrafts
            if let candidates = await fetchedCandidates {
                notificationCandidates = candidates
                suggestions = Self.mergeSuggestions(suggestions, with: candidates)
            }
        } catch {
            statusMessage = "Could not refresh suggestions: \(error.localizedDescription)"
        }
    }

    private static func mergeSuggestions(_ base: [SuggestionItem], with candidates: [SuggestionItem]) -> [SuggestionItem] {
        var merged = base
        var existing = Set(base.map(\.id))
        for candidate in candidates where !existing.contains(candidate.id) {
            merged.insert(candidate, at: 0)
            existing.insert(candidate.id)
        }
        return merged
    }

    func selectFollowupDraft(_ draft: FollowupDraft) {
        selectedFollowupDraft = draft
        draftRecipient = draft.recipient ?? ""
        draftSubject = draft.subject
        draftBody = draft.body
    }

    func clearSelectedFollowupDraft() {
        selectedFollowupDraft = nil
        draftRecipient = ""
        draftSubject = ""
        draftBody = ""
    }

    func saveSelectedFollowupDraft() async {
        guard let draft = selectedFollowupDraft else { return }
        do {
            let updated = try await client.updateFollowupDraft(
                id: draft.id,
                to: draftRecipient,
                subject: draftSubject,
                body: draftBody
            )
            selectFollowupDraft(updated)
            statusMessage = "Saved local draft \(updated.id)."
            await refreshAll(updateStatus: false)
        } catch {
            statusMessage = "Could not save draft \(draft.id): \(error.localizedDescription)"
        }
    }

    func createGmailDraftFromSelectedFollowupDraft() async {
        guard let draft = selectedFollowupDraft else { return }
        do {
            let envelope = try await client.createGmailDraftFromFollowupDraft(
                id: draft.id,
                to: draftRecipient,
                subject: draftSubject,
                body: draftBody
            )
            selectFollowupDraft(envelope.draft)
            let draftId = envelope.draftId ?? envelope.draft.providerDraftId ?? ""
            statusMessage = draftId.isEmpty
                ? "Gmail draft created. Review it in Gmail before sending."
                : "Gmail draft created (\(draftId)). Review it in Gmail before sending."
            await refreshSuggestionState()
        } catch {
            statusMessage = "Could not create Gmail draft from draft \(draft.id): \(error.localizedDescription)"
        }
    }

    func openSuggestionFromNotification(id: Int) async {
        highlightedSuggestionId = id
        suggestionReviewToken += 1
        highlightedTaskIds = []
        if selectedFollowupDraft?.suggestionId != id {
            clearSelectedFollowupDraft()
        }
        await refreshAll(updateStatus: false)
        if let draft = followupDrafts.first(where: { $0.suggestionId == id }) {
            selectFollowupDraft(draft)
        }
        if let suggestion = suggestions.first(where: { $0.id == id }) ?? notificationCandidates.first(where: { $0.id == id }) {
            upsertSuggestion(suggestion)
            selectedReviewSuggestion = suggestion
            highlightedTaskIds = Set(suggestion.taskIds)
            if selectedFollowupDraft?.suggestionId != id,
               let envelope = try? await client.fetchSuggestionEnvelope(id: id) {
                upsertSuggestion(envelope.suggestion)
                selectedReviewSuggestion = envelope.suggestion
                if let draft = envelope.followupDraft {
                    if !followupDrafts.contains(where: { $0.id == draft.id }) {
                        followupDrafts.insert(draft, at: 0)
                    }
                    selectFollowupDraft(draft)
                }
                if let relatedTasks = envelope.relatedTasks, !relatedTasks.isEmpty {
                    highlightedTaskIds = Set(relatedTasks.map(\.id))
                }
            }
            statusMessage = reviewMessage(for: suggestion, draftSelected: selectedFollowupDraft?.suggestionId == id)
            return
        }
        do {
            let envelope = try await client.fetchSuggestionEnvelope(id: id)
            upsertSuggestion(envelope.suggestion)
            selectedReviewSuggestion = envelope.suggestion
            if let relatedTasks = envelope.relatedTasks, !relatedTasks.isEmpty {
                highlightedTaskIds = Set(relatedTasks.map(\.id))
            } else {
                highlightedTaskIds = Set(envelope.suggestion.taskIds)
            }
            if let draft = envelope.followupDraft {
                if !followupDrafts.contains(where: { $0.id == draft.id }) {
                    followupDrafts.insert(draft, at: 0)
                }
                selectFollowupDraft(draft)
            } else if let drafts = try? await client.fetchFollowupDrafts(status: "", limit: 100),
                      let match = drafts.first(where: { $0.suggestionId == id }) {
                followupDrafts = drafts
                selectFollowupDraft(match)
            }
            statusMessage = reviewMessage(for: envelope.suggestion, draftSelected: selectedFollowupDraft?.suggestionId == id)
        } catch {
            statusMessage = "Could not load suggestion \(id): \(error.localizedDescription)"
        }
    }

    private func reviewMessage(for suggestion: SuggestionItem, draftSelected: Bool) -> String {
        if suggestion.status == "dismissed" || suggestion.status == "retired" || suggestion.retiredAt != nil {
            return "Suggestion \(suggestion.id) is \(suggestion.status)."
        }
        if suggestion.status == "snoozed" {
            return "Suggestion \(suggestion.id) is snoozed. Review before taking action."
        }
        if draftSelected {
            return "Reviewing suggestion \(suggestion.id) with its local draft selected."
        }
        if suggestion.taskIds.count == 1 {
            return "Reviewing suggestion \(suggestion.id) and highlighted task \(suggestion.taskIds[0])."
        }
        if suggestion.taskIds.count > 1 {
            return "Reviewing suggestion \(suggestion.id) with \(suggestion.taskIds.count) related tasks."
        }
        return "Reviewing suggestion \(suggestion.id)."
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
