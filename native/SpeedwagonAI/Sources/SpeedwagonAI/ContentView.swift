import AppKit
import SpeedwagonAICore
import SwiftUI

enum NativeSection: String, CaseIterable, Identifiable {
    case assistant = "Assistant"
    case capture = "Capture"
    case meetings = "Meetings"
    case calendar = "Calendar"
    case notifications = "Notifications"
    case tasks = "Tasks"
    case suggestions = "Suggestions"
    case commitments = "Commitments"
    case roadmap = "Roadmap"

    var id: String { rawValue }

    var systemImage: String {
        switch self {
        case .assistant: return "sparkle.magnifyingglass"
        case .capture: return "waveform"
        case .meetings: return "rectangle.stack"
        case .calendar: return "calendar"
        case .notifications: return "bell"
        case .tasks: return "checklist"
        case .suggestions: return "lightbulb"
        case .commitments: return "person.2"
        case .roadmap: return "map"
        }
    }
}

struct ContentView: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme
    @State private var selectedSection: NativeSection = .assistant

    var body: some View {
        NavigationSplitView {
            sidebar
        } detail: {
            dashboard
        }
        .frame(minWidth: 1120, minHeight: 760)
        .background(SpeedwagonTheme.appBackground(scheme))
        .task {
            activateSpeedwagon()
            await state.refreshAll()
        }
    }

    private var sidebar: some View {
        VStack(alignment: .leading, spacing: 18) {
            VStack(alignment: .leading, spacing: 6) {
                Text("SpeedwagonAI")
                    .font(.title2.weight(.semibold))
                BackendStatusView()
            }

            VStack(alignment: .leading, spacing: 8) {
                ForEach(NativeSection.allCases) { section in
                    SidebarButton(section: section, selectedSection: $selectedSection)
                }
            }

            Button {
                AssistantPanelController.shared.toggle(state: state)
            } label: {
                Label("Open Assistant", systemImage: "command")
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .keyboardShortcut("k", modifiers: .command)

            Spacer()

            BackendGuideView()
        }
        .padding(18)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(SpeedwagonTheme.sidebarBackground(scheme))
        .navigationSplitViewColumnWidth(min: 220, ideal: 240)
    }

    private var dashboard: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                DashboardHeader(selectedSection: selectedSection)
                sectionContent
            }
            .padding(22)
        }
        .background(SpeedwagonTheme.appBackground(scheme))
    }

    @ViewBuilder
    private var sectionContent: some View {
        switch selectedSection {
        case .assistant:
            AssistantSurfaceView(expanded: true)
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 16) {
                CapturePanelView()
                MeetingBotPanelView()
                CalendarPanelView()
                NotificationsPanelView(compact: true)
                BrainCostPanelView()
                DailyBriefView()
                CommitmentsView()
                PlannedCapabilitiesView()
            }
            SuggestionsPanelView()
            TaskInboxView()
        case .capture:
            CapturePanelView()
            MeetingBotPanelView()
        case .meetings:
            MeetingsView()
        case .calendar:
            CalendarPanelView(expanded: true)
        case .notifications:
            NotificationsPanelView()
        case .tasks:
            SuggestionsPanelView()
            TaskInboxView()
        case .suggestions:
            SuggestionsPanelView()
        case .commitments:
            CommitmentsView()
            DailyBriefView()
        case .roadmap:
            PlannedCapabilitiesView()
        }
    }
}

struct DashboardHeader: View {
    @EnvironmentObject private var state: AppState
    let selectedSection: NativeSection

    var body: some View {
        HStack(alignment: .center) {
            VStack(alignment: .leading, spacing: 4) {
                Text(selectedSection.rawValue)
                    .font(.largeTitle.weight(.semibold))
                Text(state.statusMessage)
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Button {
                Task { await state.refreshAll() }
            } label: {
                Label("Refresh", systemImage: "arrow.clockwise")
            }
            .disabled(state.isLoading)
            .speedwagonPointer()
        }
    }
}

struct AssistantSurfaceView: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme
    @FocusState private var commandFocused: Bool
    let expanded: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("Ask SpeedwagonAI", systemImage: "sparkle.magnifyingglass")
                    .font(.title3.weight(.semibold))
                Spacer()
                StatusBadge(text: state.isConnected ? "local" : "offline", color: state.isConnected ? SpeedwagonTheme.accent(scheme) : SpeedwagonTheme.danger(scheme))
            }

            HStack(spacing: 8) {
                TextField("Ask about tasks, meetings, commitments, or context", text: $state.commandText)
                    .textFieldStyle(.roundedBorder)
                    .focused($commandFocused)
                    .onSubmit {
                        Task { await state.runCommand() }
                    }

                Button {
                    Task { await state.runCommand() }
                } label: {
                    Label("Run", systemImage: "return")
                }
                .disabled(state.commandText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                .speedwagonPointer()

                Button {
                    Task {
                        if state.isAssistantVoiceActive {
                            await state.stopAssistantVoice()
                        } else {
                            await state.startAssistantVoice()
                        }
                    }
                } label: {
                    Label(state.isAssistantVoiceActive ? "Stop Voice" : "Voice", systemImage: state.isAssistantVoiceActive ? "stop.circle" : "mic.circle")
                }
                .speedwagonPointer()

                Button {
                    Task { await state.analyzeScreenshot() }
                } label: {
                    Label("Screenshot", systemImage: "camera.viewfinder")
                }
                .disabled(state.isLoading || !state.isConnected)
                .speedwagonPointer()
            }

            if expanded {
                AssistantContextChips()

                PaletteCaptureControlsView()

                if let transcript = state.lastVoiceTranscript, !transcript.isEmpty {
                    Text("Voice: \(transcript)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }

                CommandResultView()

                ScreenshotAnalysisView()

                PendingActionsView()

                SuggestionsPanelView(compact: true)

                SuggestedActionsView()
            }
        }
        .speedwagonPanel()
        .onAppear {
            commandFocused = true
        }
    }
}

struct PaletteCaptureControlsView: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Label("Meeting Capture", systemImage: "waveform")
                    .font(.caption.weight(.semibold))
                Spacer()
                Chip(text: state.meetingCaptureMode.rawValue)
            }

            Picker("Mode", selection: $state.meetingCaptureMode) {
                ForEach(MeetingCaptureMode.allCases) { mode in
                    Text(mode.rawValue).tag(mode)
                }
            }
            .pickerStyle(.segmented)

            HStack(spacing: 8) {
                TextField("Meeting title", text: $state.meetingCaptureTitle)
                    .textFieldStyle(.roundedBorder)

                Button(state.meetingCaptureMode == .nativeSystemMic ? "Start Native" : "Start Mic") {
                    Task { await state.startMeetingCapture() }
                }
                .disabled(state.captureStatus?.isActive == true || state.meetingCaptureTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                .speedwagonPointer()

                Button("Stop") {
                    Task { await state.stopCapture(process: false) }
                }
                .disabled(state.captureStatus?.isActive != true || state.captureStatus?.kind != "meeting")
                .speedwagonPointer()

                Button("Stop + Process") {
                    Task { await state.stopCapture(process: true) }
                }
                .disabled(state.captureStatus?.isActive != true || state.captureStatus?.kind != "meeting")
                .speedwagonPointer()
            }

            Text("Native mode records system/headphone audio plus mic for meetings. Voice Task stays mic-only.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .speedwagonSecondaryPanel()
    }
}

struct AssistantContextChips: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        HStack(spacing: 8) {
            Chip(text: "\(state.tasks.filter { !$0.isDone }.count) open tasks")
            Chip(text: "\(state.commitments.count) commitments")
            if let profile = state.captureDiagnostics?.captureProfile {
                Chip(text: "\(profile) capture")
            }
            Chip(text: "\(state.suggestions.count) suggestions")
            Chip(text: state.screenshotAnalysis == nil ? "screenshot ready" : "screenshot analyzed")
        }
    }
}

struct SuggestedActionsView: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Suggestions")
                .font(.headline)
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                ForEach(["daily brief", "what is overdue", "show unprocessed meetings", "what can you do", "what am I waiting on", "search context for onboarding"], id: \.self) { command in
                    Button(command) {
                        state.commandText = command
                        Task { await state.runCommand() }
                    }
                    .buttonStyle(.bordered)
                    .speedwagonPointer()
                }
            }
        }
    }
}

struct CommandPaletteView: View {
    @EnvironmentObject private var state: AppState
    @State private var expanded = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    BackendStatusView()
                    Spacer()
                    Button(expanded ? "Compact" : "Expand") {
                        expanded.toggle()
                    }
                    .speedwagonPointer()
                    Button("Close") {
                        AssistantPanelController.shared.close()
                    }
                    .keyboardShortcut(.escape, modifiers: [])
                    .speedwagonPointer()
                }

                AssistantSurfaceView(expanded: expanded)
            }
            .padding(14)
        }
        .frame(minWidth: expanded ? 760 : 620, minHeight: expanded ? 560 : 220)
        .task {
            await state.refreshAll()
        }
    }
}

struct CapturePanelView: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Capture")
                    .font(.title3.weight(.semibold))
                Spacer()
                if let diagnostics = state.captureDiagnostics {
                    StatusBadge(text: diagnostics.recorderStatus, color: diagnostics.recorderStatus == "available" ? SpeedwagonTheme.accent(scheme) : SpeedwagonTheme.danger(scheme))
                }
            }

            if state.captureStatus?.isActive == true {
                ActiveCaptureView(session: state.captureStatus)
            } else {
                Text("No active recording.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }

            Picker("Meeting capture mode", selection: $state.meetingCaptureMode) {
                ForEach(MeetingCaptureMode.allCases) { mode in
                    Text(mode.rawValue).tag(mode)
                }
            }
            .pickerStyle(.segmented)

            NativeCaptureStatusRows(snapshot: state.nativeCapturePermissions)

            HStack(spacing: 8) {
                TextField("Meeting title", text: $state.meetingCaptureTitle)
                    .textFieldStyle(.roundedBorder)
                Button(state.meetingCaptureMode == .nativeSystemMic ? "Start Native" : "Start Mic") {
                    Task { await state.startMeetingCapture() }
                }
                .disabled(state.captureStatus?.isActive == true || state.meetingCaptureTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                .speedwagonPointer()
            }

            HStack(spacing: 8) {
                Button("Voice Task (mic)") {
                    Task { await state.startTaskCapture() }
                }
                .disabled(state.captureStatus?.isActive == true)
                .speedwagonPointer()

                captureStopButtons
            }

            Text(captureModeNote)
                .font(.caption)
                .foregroundStyle(.secondary)

            ForEach(state.nativeCaptureWarnings, id: \.self) { warning in
                Text(warning)
                    .font(.caption)
                    .foregroundStyle(SpeedwagonTheme.danger(scheme))
            }
        }
        .speedwagonPanel()
    }

    private var captureModeNote: String {
        switch state.meetingCaptureMode {
        case .nativeSystemMic:
            return "Native system + mic applies to meeting recording only. Voice Task and assistant voice are mic-only in V14."
        case .micFallback:
            return state.captureDiagnostics?.warnings.first
                ?? "Mic fallback records your selected/default microphone only."
        }
    }

    @ViewBuilder
    private var captureStopButtons: some View {
        if state.captureStatus?.isActive == true {
            switch state.captureStatus?.kind {
            case "meeting":
                Button("Stop") {
                    Task { await state.stopCapture(process: false) }
                }
                .speedwagonPointer()
                Button("Stop + Process") {
                    Task { await state.stopCapture(process: true) }
                }
                .speedwagonPointer()
            case "task_note":
                Button("Stop + Add Task") {
                    Task { await state.stopCapture(process: false) }
                }
                .speedwagonPointer()
            case "assistant_voice":
                Button("Stop + Run") {
                    Task { await state.stopAssistantVoice() }
                }
                .speedwagonPointer()
            default:
                Button("Stop") {
                    Task { await state.stopCapture(process: false) }
                }
                .speedwagonPointer()
            }
        } else {
            Button("Stop") {}
                .disabled(true)
        }
    }
}

struct MeetingBotPanelView: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Meeting Bot Beta")
                    .font(.title3.weight(.semibold))
                Spacer()
                StatusBadge(
                    text: state.botStatus?.enabled == true ? "configured" : "not configured",
                    color: state.botStatus?.enabled == true ? SpeedwagonTheme.accent(scheme) : SpeedwagonTheme.line(scheme)
                )
            }

            Text("Optional cloud/provider capture for Zoom, Meet, Teams, and similar meeting links. Bots join visibly and should only be used when capture is allowed and disclosed. Refresh can request provider transcription for completed recordings.")
                .font(.caption)
                .foregroundStyle(.secondary)

            VStack(alignment: .leading, spacing: 8) {
                InfoRow(label: "Provider", value: state.botStatus?.provider ?? state.settings?.botProvider ?? "not configured")
                InfoRow(label: "Status", value: state.botStatus?.status ?? "unknown")
                InfoRow(label: "Cost", value: state.botStatus?.cloudCostLabel ?? "higher")
            }
            .speedwagonSecondaryPanel()

            VStack(spacing: 8) {
                TextField("Meeting title", text: $state.botMeetingTitle)
                    .textFieldStyle(.roundedBorder)
                TextField("Meeting link", text: $state.botMeetingURL)
                    .textFieldStyle(.roundedBorder)
                Toggle("Capture is allowed and disclosed for this meeting", isOn: $state.botConsentConfirmed)
                    .toggleStyle(.checkbox)
                    .font(.caption)
            }

            HStack(spacing: 8) {
                Button {
                    Task { await state.joinBotSession() }
                } label: {
                    Label("Join Bot", systemImage: "video.badge.waveform")
                }
                .disabled(
                    state.botStatus?.enabled != true ||
                    state.botMeetingTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ||
                    state.botMeetingURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ||
                    !state.botConsentConfirmed
                )
                .speedwagonPointer()

                Button {
                    Task { await state.refreshAll(updateStatus: false) }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
                .speedwagonPointer()
            }

            if let note = state.botStatus?.note ?? state.settings?.botNote {
                Text(note)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if state.botSessions.isEmpty {
                EmptyStateView(text: "No bot sessions yet.")
            } else {
                VStack(spacing: 8) {
                    ForEach(state.botSessions.prefix(5)) { session in
                        BotSessionRow(session: session)
                    }
                }
            }
        }
        .speedwagonPanel()
    }
}

struct CalendarPanelView: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme
    var expanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Google Calendar")
                    .font(.title3.weight(.semibold))
                Spacer()
                StatusBadge(
                    text: state.calendarStatus?.status ?? state.settings?.calendarStatus ?? "unknown",
                    color: state.calendarStatus?.enabled == true ? SpeedwagonTheme.accent(scheme) : SpeedwagonTheme.line(scheme)
                )
            }

            Text("Read-only sync for daily brief and meeting prep. Events are cached locally in a limited rolling window.")
                .font(.caption)
                .foregroundStyle(.secondary)

            VStack(alignment: .leading, spacing: 8) {
                InfoRow(label: "Calendars", value: (state.calendarStatus?.calendarIds ?? state.settings?.calendarIds ?? ["primary"]).joined(separator: ", "))
                InfoRow(label: "Window", value: "\(state.calendarStatus?.syncDaysBack ?? state.settings?.calendarSyncDaysBack ?? 14) back / \(state.calendarStatus?.syncDaysForward ?? state.settings?.calendarSyncDaysForward ?? 30) forward")
                InfoRow(label: "Note", value: state.calendarStatus?.note ?? state.settings?.calendarNote ?? "Calendar status not loaded.")
            }
            .speedwagonSecondaryPanel()

            HStack(spacing: 8) {
                Button {
                    Task { await state.syncCalendar() }
                } label: {
                    Label("Sync Calendar", systemImage: "arrow.clockwise")
                }
                .disabled(state.calendarStatus?.credentialsPresent == false)
                .speedwagonPointer()

                Button {
                    Task { await state.refreshAll(updateStatus: false) }
                } label: {
                    Label("Refresh", systemImage: "calendar")
                }
                .speedwagonPointer()
            }

            if expanded {
                Text("Upcoming")
                    .font(.headline)
                CalendarEventList(events: state.calendarEvents)
            } else {
                CalendarEventList(events: Array(state.calendarEvents.prefix(3)))
            }
        }
        .speedwagonPanel()
    }
}

struct CalendarEventList: View {
    let events: [CalendarEvent]

    var body: some View {
        if events.isEmpty {
            EmptyStateView(text: "No synced upcoming events.")
        } else {
            VStack(spacing: 8) {
                ForEach(events) { event in
                    CalendarEventRow(event: event)
                }
            }
        }
    }
}

struct CalendarEventRow: View {
    let event: CalendarEvent

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(event.title)
                .font(.callout.weight(.medium))
                .lineLimit(2)
            Text("\(event.startAt) -> \(event.endAt)")
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
            if let meetingURL = event.meetingUrl, !meetingURL.isEmpty {
                Text(meetingURL)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            if let location = event.location, !location.isEmpty {
                Text(location)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
        }
        .speedwagonSecondaryPanel()
    }
}

struct BotSessionRow: View {
    @EnvironmentObject private var state: AppState
    let session: BotSession

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(session.displayTitle)
                        .font(.callout.weight(.medium))
                    Text("Session \(session.id) · meeting \(session.meetingId) · \(session.status)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Chip(text: transcriptChipText)
            }

            if let display = session.meetingUrlDisplay, !display.isEmpty {
                Text(display)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            if let error = session.error, !error.isEmpty {
                Text(error)
                    .font(.caption)
                    .foregroundStyle(.red)
            } else if session.transcriptReady != true && session.meetingTranscriptPath == nil {
                Text(transcriptHelpText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            HStack(spacing: 8) {
                Button("Sync") {
                    Task { await state.syncBotSession(session) }
                }
                .speedwagonPointer()
                Button("Process") {
                    Task { await state.processBotSession(session) }
                }
                .disabled(session.transcriptReady != true && session.meetingTranscriptPath == nil)
                .speedwagonPointer()
            }
        }
        .speedwagonSecondaryPanel()
    }

    private var transcriptChipText: String {
        if session.transcriptReady == true || session.meetingTranscriptPath != nil {
            return "transcript ready"
        }
        if session.status == "transcript_requested" {
            return "transcript requested"
        }
        if session.status.hasPrefix("transcript_processing") {
            return "transcript processing"
        }
        return "no transcript yet"
    }

    private var transcriptHelpText: String {
        if session.status == "transcript_requested" {
            return "Recall transcription has been requested. Sync again after it finishes."
        }
        if session.status.hasPrefix("transcript_processing") {
            return "Recall is still processing the transcript. Sync again in a few minutes."
        }
        return "Process unlocks after Sync imports a transcript."
    }
}

struct NativeCaptureStatusRows: View {
    let snapshot: NativeCapturePermissionSnapshot

    var body: some View {
        VStack(spacing: 5) {
            ForEach(snapshot.rows, id: \.0) { row in
                HStack {
                    Text(row.0)
                        .foregroundStyle(.secondary)
                    Spacer()
                    Text(row.1)
                        .font(.caption.weight(.medium))
                }
                .font(.caption)
            }
        }
        .speedwagonSecondaryPanel()
    }
}

struct ActiveCaptureView: View {
    let session: CaptureSession?

    var body: some View {
        if let session {
            VStack(alignment: .leading, spacing: 5) {
                Text(activeTitle(session))
                    .font(.body.weight(.medium))
                HStack(spacing: 12) {
                    Label(session.startedAt ?? "unknown start", systemImage: "clock")
                    Label("\(session.fileSize ?? 0) bytes", systemImage: "waveform")
                    Label(session.captureProfile ?? "profile", systemImage: session.isNative ? "display.and.arrow.down" : "mic")
                }
                .font(.caption)
                .foregroundStyle(.secondary)
                if let warning = session.warnings?.first {
                    Text(warning)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
                if let audioPath = session.audioPath {
                    Text(audioPath)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
            .speedwagonSecondaryPanel()
        }
    }

    private func activeTitle(_ session: CaptureSession) -> String {
        switch session.kind {
        case "meeting":
            return "Recording meeting: \(session.title ?? "Untitled")"
        case "assistant_voice":
            return "Recording assistant voice"
        default:
            return "Recording voice task"
        }
    }
}

struct DailyBriefView: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Daily Brief")
                .font(.title3.weight(.semibold))

            if let brief = state.dailyBrief {
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                    BriefCard(title: "Overdue", tasks: brief.overdue)
                    BriefCard(title: "Today", tasks: brief.today)
                    BriefCard(title: "Waiting", tasks: brief.waiting)
                    BriefCard(title: "Follow-ups", tasks: brief.recommendedFollowups)
                }
                if let today = brief.calendarToday, !today.isEmpty {
                    CalendarBriefCard(title: "Calendar Today", events: today)
                }
                if let upcoming = brief.calendarUpcoming, !upcoming.isEmpty {
                    CalendarBriefCard(title: "Upcoming Meetings", events: Array(upcoming.prefix(4)))
                }
                if let prep = brief.meetingPrep, !prep.isEmpty {
                    MeetingPrepList(prep: prep)
                }
            } else {
                EmptyStateView(text: state.isConnected ? "No brief loaded." : "Connect backend to load brief.")
            }
        }
        .speedwagonPanel()
    }
}

struct BriefCard: View {
    let title: String
    let tasks: [TaskItem]

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack {
                Text(title)
                    .font(.headline)
                Spacer()
                Text("\(tasks.count)")
                    .font(.caption.weight(.medium))
                    .foregroundStyle(.secondary)
            }
            ForEach(tasks.prefix(2)) { task in
                Text("#\(task.id) \(task.text)")
                    .font(.caption)
                    .lineLimit(2)
                    .foregroundStyle(.secondary)
            }
            if tasks.isEmpty {
                Text("Nothing here.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .speedwagonSecondaryPanel()
    }
}

struct CalendarBriefCard: View {
    let title: String
    let events: [CalendarEvent]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(title)
                    .font(.headline)
                Spacer()
                Text("\(events.count)")
                    .font(.caption.weight(.medium))
                    .foregroundStyle(.secondary)
            }
            ForEach(events.prefix(3)) { event in
                Text("\(event.startAt) \(event.title)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
        .speedwagonSecondaryPanel()
    }
}

struct MeetingPrepList: View {
    let prep: [MeetingPrepItem]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Meeting Prep")
                .font(.headline)
            ForEach(Array(prep.prefix(3).enumerated()), id: \.offset) { _, item in
                VStack(alignment: .leading, spacing: 4) {
                    Text(item.event.title)
                        .font(.caption.weight(.semibold))
                    Text("\((item.tasks ?? []).count) related tasks · \((item.meetings ?? []).count) related meetings")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .speedwagonSecondaryPanel()
            }
        }
    }
}

struct CommitmentsView: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Commitments")
                .font(.title3.weight(.semibold))

            if state.commitments.isEmpty {
                EmptyStateView(text: state.isConnected ? "No open commitments." : "Connect backend to load commitments.")
            } else {
                VStack(spacing: 8) {
                    ForEach(state.commitments.prefix(5)) { task in
                        TaskRow(task: task)
                    }
                }
            }
        }
        .speedwagonPanel()
    }
}

struct MeetingsView: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        HStack(alignment: .top, spacing: 16) {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text("Meetings")
                        .font(.title3.weight(.semibold))
                    Spacer()
                    Chip(text: "\(state.meetings.count)")
                }

                if state.meetings.isEmpty {
                    EmptyStateView(text: state.isConnected ? "No meetings yet." : "Connect backend to load meetings.")
                } else {
                    ScrollView {
                        VStack(spacing: 8) {
                            ForEach(state.meetings) { meeting in
                                MeetingListRow(meeting: meeting)
                            }
                        }
                    }
                    .frame(minHeight: 420)
                }
            }
            .speedwagonPanel()
            .frame(minWidth: 320, idealWidth: 360, maxWidth: 420)

            MeetingDetailView()
                .frame(maxWidth: .infinity, alignment: .topLeading)
        }
    }
}

struct MeetingListRow: View {
    @EnvironmentObject private var state: AppState
    let meeting: MeetingItem

    var body: some View {
        Button {
            Task { await state.loadMeeting(meeting) }
        } label: {
            VStack(alignment: .leading, spacing: 6) {
                HStack(alignment: .firstTextBaseline) {
                    Text(meeting.title)
                        .font(.body.weight(.semibold))
                        .lineLimit(2)
                    Spacer()
                    if meeting.sourceType == "meeting_bot" {
                        Chip(text: "bot")
                    }
                }
                Text("\((meeting.startedAt ?? "").prefix(10)) · meeting \(meeting.id)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                HStack(spacing: 6) {
                    Chip(text: meeting.transcriptPath == nil ? "no transcript" : "transcript")
                    Chip(text: meeting.notePath == nil ? "no note" : "note")
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .buttonStyle(.plain)
        .speedwagonSecondaryPanel()
        .speedwagonPointer()
    }
}

struct MeetingDetailView: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let detail = state.selectedMeetingDetail {
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(detail.meeting.title)
                            .font(.title3.weight(.semibold))
                        Text("meeting \(detail.meeting.id) · \((detail.meeting.startedAt ?? "").prefix(10))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button("Process") {
                        Task { await state.processMeeting(detail.meeting) }
                    }
                    .speedwagonPointer()
                }

                Text(detail.meeting.summary ?? "No summary yet.")
                    .font(.callout)
                    .foregroundStyle(detail.meeting.summary == nil ? .secondary : .primary)

                MeetingItemsBlock(title: "Decisions", items: detail.decisions)
                MeetingItemsBlock(title: "Action Items", items: detail.actionItems)
                MeetingItemsBlock(title: "Commitments", items: detail.commitments)
                MeetingItemsBlock(title: "Open Questions", items: detail.openQuestions)

                if let transcript = detail.transcript, !transcript.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Transcript")
                            .font(.headline)
                        Text(transcript)
                            .font(.system(.caption, design: .monospaced))
                            .foregroundStyle(.secondary)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(10)
                            .background(.quaternary.opacity(0.4))
                            .clipShape(RoundedRectangle(cornerRadius: 6))
                    }
                }

                VStack(alignment: .leading, spacing: 4) {
                    if let transcriptPath = detail.meeting.transcriptPath {
                        Text("Transcript: \(transcriptPath)")
                    }
                    if let notePath = detail.meeting.notePath {
                        Text("Note: \(notePath)")
                    }
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            } else {
                EmptyStateView(text: state.meetings.isEmpty ? "No meetings yet." : "Select a meeting to review transcript, decisions, tasks, and notes.")
            }
        }
        .speedwagonPanel()
    }
}

struct MeetingItemsBlock: View {
    let title: String
    let items: [MeetingTextItem]

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.headline)
            if items.isEmpty {
                Text("None captured.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(items) { item in
                        HStack(alignment: .firstTextBaseline, spacing: 6) {
                            Text("•")
                            Text(item.displayText)
                            if let deadline = item.deadline, !deadline.isEmpty {
                                Text("due \(deadline)")
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .font(.caption)
                    }
                }
            }
        }
    }
}

struct PlannedCapabilitiesView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Next Surfaces")
                .font(.title3.weight(.semibold))
            PlannedTile(title: "Meeting Bot", subtitle: "Zoom, Meet, Teams beta")
            PlannedTile(title: "Window/Region Screenshots", subtitle: "Full-screen analysis works first")
            PlannedTile(title: "Calendar + Reminders", subtitle: "Confirmed follow-through")
            PlannedTile(title: "Privacy + Security", subtitle: "Policy, terms, Keychain, export")
        }
        .speedwagonPanel()
    }
}

struct BrainCostPanelView: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Brain + Cost")
                .font(.title3.weight(.semibold))
            InfoRow(label: "Command parser", value: modelLine(state.settings?.commandModel, key: "command_parse"))
            InfoRow(label: "Vision context", value: modelLine(state.settings?.visionModel, key: "vision_context"))
            InfoRow(label: "Web search", value: state.settings?.webSearchEnabled == true ? "Enabled" : "Disabled")
            Text("Mutating interpreted actions require confirmation.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .speedwagonPanel()
    }

    private func modelLine(_ model: String?, key: String) -> String {
        let label = state.settings?.modelCostLabels?[key] ?? "unknown"
        return "\(model ?? "not set") · \(label)"
    }
}

struct InfoRow: View {
    let label: String
    let value: String

    var body: some View {
        HStack {
            Text(label)
                .foregroundStyle(.secondary)
            Spacer()
            Text(value)
                .font(.caption.weight(.medium))
                .multilineTextAlignment(.trailing)
        }
        .font(.caption)
    }
}

struct PlannedTile: View {
    let title: String
    let subtitle: String

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.callout.weight(.medium))
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Chip(text: "planned")
        }
        .speedwagonSecondaryPanel()
    }
}

struct TaskInboxView: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text("Task Inbox")
                    .font(.title3.weight(.semibold))
                Spacer()
                Button {
                    Task { await state.refreshAll() }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
                .disabled(state.isLoading)
                .speedwagonPointer()
            }

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 14) {
                ForEach(TaskGroupKind.allCases) { kind in
                    TaskGroupView(
                        title: kind.rawValue,
                        tasks: state.groupedTasks[kind] ?? [],
                        onComplete: { task in Task { await state.complete(task) } },
                        onReopen: { task in Task { await state.reopen(task) } }
                    )
                }
            }
        }
        .speedwagonPanel()
    }
}

struct CommandResultView: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Result")
                .font(.headline)

            if let response = state.commandResponse {
                Text(resultTitle(response))
                    .font(.body.weight(.medium))

                if let error = state.commandErrorMessage {
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.red)
                }

                ResultContent(response: response)
            } else {
                Text("Ask a question or run a command.")
                    .font(.body)
                    .foregroundStyle(.secondary)
            }
        }
        .speedwagonSecondaryPanel()
    }

    private func resultTitle(_ response: AssistantCommandResponse) -> String {
        if let category = response.category, !category.isEmpty {
            return "[\(category)] \(response.summary)"
        }
        return response.summary
    }
}

struct ScreenshotAnalysisView: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        if state.screenshotAnalysis != nil || state.lastScreenshotPNGData != nil {
            VStack(alignment: .leading, spacing: 8) {
                Text("Screenshot Context")
                    .font(.headline)

                if let data = state.lastScreenshotPNGData, let image = NSImage(data: data) {
                    Image(nsImage: image)
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .frame(maxHeight: 160)
                        .clipShape(RoundedRectangle(cornerRadius: 6))
                        .overlay(RoundedRectangle(cornerRadius: 6).stroke(.quaternary))
                }

                if let analysis = state.screenshotAnalysis {
                    Text(analysis.summary)
                        .font(.body.weight(.medium))
                    if !analysis.visibleText.isEmpty {
                        Text("Visible text: \(analysis.visibleText.prefix(3).joined(separator: " · "))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                    }
                    if !analysis.suggestedContextTopics.isEmpty {
                        HStack {
                            ForEach(analysis.suggestedContextTopics.prefix(4), id: \.self) { topic in
                                Chip(text: topic)
                            }
                        }
                    }
                }
            }
            .speedwagonSecondaryPanel()
        }
    }
}

struct PendingActionsView: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        if !state.pendingActions.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text("Pending Confirmation")
                    .font(.headline)
                ForEach(state.pendingActions.prefix(5)) { action in
                    PendingActionCard(action: action)
                }
            }
        }
    }
}

struct PendingActionCard: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme
    let action: PendingAssistantAction

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(actionTitle)
                        .font(.body.weight(.semibold))
                    Text(payloadSummary(action.payload))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    if let explanation = action.explanation, !explanation.isEmpty {
                        Text(explanation)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                    }
                }
                Spacer()
                if let confidence = action.confidence {
                    Chip(text: "\(Int(confidence * 100))%")
                }
            }

            HStack {
                Button {
                    Task { await state.confirm(action) }
                } label: {
                    Label("Confirm", systemImage: "checkmark.circle.fill")
                }
                .buttonStyle(.borderedProminent)
                .tint(SpeedwagonTheme.accent(scheme))
                .speedwagonPointer()

                Button(role: .cancel) {
                    Task { await state.cancel(action) }
                } label: {
                    Label("Cancel", systemImage: "xmark.circle")
                }
                .buttonStyle(.bordered)
                .speedwagonPointer()
            }
        }
        .padding(10)
        .background(SpeedwagonTheme.panelBackground(scheme))
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(SpeedwagonTheme.danger(scheme).opacity(0.45)))
    }

    private var actionTitle: String {
        "#\(action.id) \(action.action.replacingOccurrences(of: "_", with: " "))"
    }
}

struct SuggestionsPanelView: View {
    @EnvironmentObject private var state: AppState
    var compact = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Follow-Through Suggestions")
                    .font(compact ? .headline : .title3.weight(.semibold))
                Spacer()
                Chip(text: "\(state.suggestions.count)")
            }

            if state.suggestions.isEmpty {
                EmptyStateView(text: state.isConnected ? "No suggestions right now." : "Connect backend to load suggestions.")
            } else {
                VStack(spacing: 8) {
                    ForEach(state.suggestions.prefix(compact ? 3 : 12)) { suggestion in
                        SuggestionCard(suggestion: suggestion)
                    }
                }
            }
        }
        .speedwagonPanel()
    }
}

struct NotificationsPanelView: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme
    var compact = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Notifications")
                    .font(compact ? .headline : .title3.weight(.semibold))
                Spacer()
                Chip(text: state.notificationPermissionStatus)
            }

            if let status = state.notificationStatus {
                Text(status.note)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                HStack(spacing: 8) {
                    Chip(text: "\(status.candidateCount) candidates")
                    Chip(text: "\(status.deliveredCount) delivered")
                    Chip(text: "\(status.snoozedCount) snoozed")
                }
            } else {
                Text("Notification status has not loaded yet.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            HStack(spacing: 8) {
                Button {
                    Task { await state.requestNotificationPermission() }
                } label: {
                    Label("Allow Notifications", systemImage: "bell.badge")
                }
                .buttonStyle(.borderedProminent)
                .tint(SpeedwagonTheme.accent(scheme))
                .disabled(state.notificationPermissionStatus == "authorized")
                .speedwagonPointer()

                Button {
                    Task { await state.refreshNotificationsOnly() }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
                .buttonStyle(.bordered)
                .speedwagonPointer()
            }

            if state.notificationCandidates.isEmpty {
                EmptyStateView(text: state.isConnected ? "No notification candidates right now." : "Connect backend to load notifications.")
            } else {
                VStack(spacing: 8) {
                    ForEach(state.notificationCandidates.prefix(compact ? 2 : 10)) { suggestion in
                        NotificationCandidateCard(suggestion: suggestion)
                    }
                }
            }
        }
        .speedwagonPanel()
    }
}

struct NotificationCandidateCard: View {
    @EnvironmentObject private var state: AppState
    let suggestion: SuggestionItem

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 5) {
                    Text("#\(suggestion.id) \(suggestion.title)")
                        .font(.body.weight(.semibold))
                        .fixedSize(horizontal: false, vertical: true)
                    Text(suggestion.notificationReason ?? suggestion.reason)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer()
                Chip(text: suggestion.notificationStatus ?? "candidate")
            }

            HStack(spacing: 8) {
                Button {
                    Task { await state.markNotificationDelivered(suggestion) }
                } label: {
                    Label("Mark Delivered", systemImage: "paperplane")
                }
                .buttonStyle(.bordered)
                .speedwagonPointer()

                Button {
                    Task { await state.snoozeNotification(suggestion) }
                } label: {
                    Label("Snooze", systemImage: "clock")
                }
                .buttonStyle(.bordered)
                .speedwagonPointer()

                Button(role: .cancel) {
                    Task { await state.dismissNotification(suggestion) }
                } label: {
                    Label("Dismiss", systemImage: "xmark.circle")
                }
                .buttonStyle(.bordered)
                .speedwagonPointer()
            }
        }
        .padding(10)
        .background(.quaternary.opacity(0.25))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

struct SuggestionCard: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme
    let suggestion: SuggestionItem

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 5) {
                    HStack(spacing: 6) {
                        Text("#\(suggestion.id) \(suggestion.title)")
                            .font(.body.weight(.semibold))
                            .fixedSize(horizontal: false, vertical: true)
                        if let context = suggestion.displayContext {
                            Chip(text: context)
                        }
                    }
                    Text(suggestion.reason)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                    Text(suggestion.proposedAction.replacingOccurrences(of: "_", with: " "))
                        .font(.caption.weight(.medium))
                        .foregroundStyle(.secondary)
                }
                Spacer()
                if let confidence = suggestion.confidence {
                    Chip(text: "\(Int(confidence * 100))%")
                }
            }

            HStack(spacing: 8) {
                Button {
                    Task { await state.confirm(suggestion) }
                } label: {
                    Label("Confirm", systemImage: "checkmark.circle.fill")
                }
                .buttonStyle(.borderedProminent)
                .tint(SpeedwagonTheme.accent(scheme))
                .speedwagonPointer()

                Button {
                    Task { await state.snooze(suggestion) }
                } label: {
                    Label("Snooze", systemImage: "clock")
                }
                .buttonStyle(.bordered)
                .speedwagonPointer()

                Button(role: .cancel) {
                    Task { await state.dismiss(suggestion) }
                } label: {
                    Label("Dismiss", systemImage: "xmark.circle")
                }
                .buttonStyle(.bordered)
                .speedwagonPointer()
            }
        }
        .speedwagonSecondaryPanel()
    }
}

struct ResultContent: View {
    let response: AssistantCommandResponse

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if response.requiresConfirmation == true {
                Text("Requires confirmation before running.")
                    .font(.caption.weight(.medium))
                    .foregroundStyle(.orange)
            }
            if let confidence = response.confidence {
                Text("Confidence: \(Int(confidence * 100))%")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            if let explanation = response.explanation, !explanation.isEmpty {
                Text(explanation)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            if let notes = response.safetyNotes, !notes.isEmpty {
                Text(notes.joined(separator: " "))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if let pending = response.result?.pendingAction {
                Text("Pending #\(pending.id): \(pending.action)")
                    .font(.caption.weight(.medium))
                    .foregroundStyle(.orange)
            }

            if let capabilities = response.result?.capabilities, !capabilities.isEmpty {
                ForEach(capabilities.prefix(8)) { capability in
                    Text("[\(capability.category)] \(capability.command)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            if let tasks = response.result?.tasks, !tasks.isEmpty {
                ForEach(tasks.prefix(20)) { task in
                    Text(taskResultLine(task))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                if tasks.count > 20 {
                    Text("\(tasks.count - 20) more in Tasks.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            if let contexts = response.result?.contexts, !contexts.isEmpty {
                HStack {
                    ForEach(contexts.prefix(6)) { context in
                        Chip(text: context.name)
                    }
                }
            }

            if let suggestions = response.result?.suggestions, !suggestions.isEmpty {
                ForEach(suggestions.prefix(5)) { suggestion in
                    Text("#\(suggestion.id) \(suggestion.title)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            if let suggestion = response.result?.suggestion {
                Text("#\(suggestion.id) \(suggestion.title) [\(suggestion.status)]")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if let meetings = response.result?.meetings, !meetings.isEmpty {
                ForEach(meetings.prefix(6)) { meeting in
                    Text("#\(meeting.id) \(meeting.title)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            if let sessions = response.result?.sessions, !sessions.isEmpty {
                ForEach(sessions.prefix(6)) { session in
                    Text("#\(session.id) \(session.displayTitle) · \(session.status)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            if let task = response.result?.task {
                Text("#\(task.id) \(task.text)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if let meeting = response.result?.meeting {
                Text("#\(meeting.id) \(meeting.title)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if let session = response.result?.session {
                Text("#\(session.id) \(session.displayTitle) · \(session.status)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if let draft = response.result?.draft {
                Text(draft.subject ?? "Draft")
                    .font(.caption.weight(.medium))
                Text(draft.body ?? "")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(8)
            }

            if let markdown = response.result?.markdown, !markdown.isEmpty {
                Text(markdown)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(8)
            }

            if let message = response.result?.message, !message.isEmpty {
                Text(message)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }
}

private func payloadSummary(_ payload: [String: JSONValue]?) -> String {
    guard let payload, !payload.isEmpty else {
        return "No payload"
    }
    return payload
        .sorted { $0.key < $1.key }
        .map { "\($0.key): \(jsonValueSummary($0.value))" }
        .joined(separator: " · ")
}

private func taskResultLine(_ task: TaskItem) -> String {
    var parts = ["#\(task.id)", task.text]
    if let dueDate = task.dueDate, !dueDate.isEmpty {
        parts.append("due \(dueDate)")
    } else {
        parts.append("no due date")
    }
    if let owner = task.owner, !owner.isEmpty {
        parts.append(owner)
    }
    return parts.joined(separator: " · ")
}

private func jsonValueSummary(_ value: JSONValue) -> String {
    switch value {
    case let .string(text):
        return text
    case let .number(number):
        if number.rounded() == number {
            return String(Int(number))
        }
        return String(number)
    case let .bool(flag):
        return flag ? "true" : "false"
    case let .object(object):
        return "{\(object.keys.sorted().joined(separator: ", "))}"
    case let .array(values):
        return "\(values.count) item(s)"
    case .null:
        return "none"
    }
}

struct TaskGroupView: View {
    let title: String
    let tasks: [TaskItem]
    let onComplete: (TaskItem) -> Void
    let onReopen: (TaskItem) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(title)
                    .font(.headline)
                Chip(text: "\(tasks.count)")
            }

            if tasks.isEmpty {
                Text("No tasks here.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .padding(.vertical, 8)
            } else {
                VStack(spacing: 8) {
                    ForEach(tasks) { task in
                        TaskRow(task: task, onComplete: onComplete, onReopen: onReopen)
                    }
                }
            }
        }
        .speedwagonSecondaryPanel()
    }
}

struct TaskRow: View {
    let task: TaskItem
    var onComplete: ((TaskItem) -> Void)? = nil
    var onReopen: ((TaskItem) -> Void)? = nil

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 6) {
                Text(task.text)
                    .font(.body.weight(.medium))
                    .fixedSize(horizontal: false, vertical: true)

                HStack(spacing: 10) {
                    Label(task.displayOwner, systemImage: "person")
                    Label(task.displayDueDate, systemImage: "calendar")
                    Label(task.displaySource, systemImage: "doc.text")
                }
                .font(.caption)
                .foregroundStyle(.secondary)

                if let suggestion = task.reminderSuggestion, !suggestion.isEmpty, !task.isDone {
                    Text(suggestion)
                        .font(.caption)
                        .foregroundStyle(.orange)
                }

                if let contexts = task.contexts, !contexts.isEmpty {
                    HStack(spacing: 6) {
                        ForEach(contexts.prefix(4)) { context in
                            Chip(text: context.name)
                        }
                    }
                }
            }

            Spacer()

            if let onComplete, let onReopen {
                if task.isDone {
                    Button("Reopen") {
                        onReopen(task)
                    }
                    .speedwagonPointer()
                } else {
                    Button("Complete") {
                        onComplete(task)
                    }
                    .speedwagonPointer()
                }
            }
        }
        .speedwagonSecondaryPanel()
    }
}

struct SidebarButton: View {
    @Environment(\.colorScheme) private var scheme
    let section: NativeSection
    @Binding var selectedSection: NativeSection

    var body: some View {
        Button {
            selectedSection = section
            activateSpeedwagon()
        } label: {
            Label(section.rawValue, systemImage: section.systemImage)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .buttonStyle(.plain)
        .padding(.horizontal, 10)
        .padding(.vertical, 7)
        .foregroundStyle(selectedSection == section ? SpeedwagonTheme.accent(scheme) : .secondary)
        .background(selectedSection == section ? SpeedwagonTheme.panelBackground(scheme) : Color.clear)
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(selectedSection == section ? SpeedwagonTheme.line(scheme) : Color.clear)
        )
        .speedwagonPointer()
    }
}

struct StatusBadge: View {
    let text: String
    let color: Color

    var body: some View {
        Text(text)
            .font(.caption.weight(.medium))
            .foregroundStyle(color)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(color.opacity(0.12))
            .clipShape(Capsule())
    }
}

struct Chip: View {
    @Environment(\.colorScheme) private var scheme
    let text: String

    var body: some View {
        Text(text)
            .font(.caption)
            .foregroundStyle(.secondary)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(SpeedwagonTheme.secondaryPanelBackground(scheme))
            .clipShape(Capsule())
            .overlay(Capsule().stroke(SpeedwagonTheme.line(scheme)))
    }
}

struct BackendStatusView: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(state.isConnected ? SpeedwagonTheme.accent(scheme) : SpeedwagonTheme.danger(scheme))
                .frame(width: 8, height: 8)
            Text(state.backendStatusLabel)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }
}

struct BackendGuideView: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        if !state.isConnected {
            VStack(alignment: .leading, spacing: 8) {
                Text("Backend Required")
                    .font(.headline)
                Text("speedwagon app")
                    .font(.system(.body, design: .monospaced))
                    .padding(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .speedwagonSecondaryPanel()
            }
        }
    }
}

struct EmptyStateView: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.callout)
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, alignment: .leading)
            .speedwagonSecondaryPanel()
    }
}
