import AppKit
import SpeedwagonAICore
import SwiftUI

enum NativeSection: String, CaseIterable, Identifiable {
    case assistant = "Today"
    case capture = "Capture"
    case meetings = "Meetings"
    case calendar = "Calendar"
    case notifications = "Notifications"
    case tasks = "Tasks"
    case suggestions = "Suggestions"
    case commitments = "Commitments"
    case connections = "Connections"
    case settings = "Settings"
    case roadmap = "About beta"

    var id: String { rawValue }

    var usesFixedWorkspace: Bool {
        switch self {
        case .meetings, .suggestions, .connections:
            return true
        default:
            return false
        }
    }

    var group: String? {
        switch self {
        case .assistant:
            return nil
        case .suggestions, .tasks, .commitments:
            return "Work"
        case .capture, .meetings, .calendar, .connections:
            return "Capture & Knowledge"
        case .notifications, .settings, .roadmap:
            return "System"
        }
    }

    static var grouped: [(title: String?, sections: [NativeSection])] {
        [
            (nil, [.assistant]),
            ("Work", [.suggestions, .tasks, .commitments]),
            ("Capture & Knowledge", [.capture, .meetings, .calendar, .connections]),
            ("System", [.notifications, .settings, .roadmap])
        ]
    }

    var systemImage: String {
        switch self {
        case .assistant: return "sun.max"
        case .capture: return "waveform"
        case .meetings: return "rectangle.stack"
        case .calendar: return "calendar"
        case .notifications: return "bell"
        case .tasks: return "checklist"
        case .suggestions: return "lightbulb"
        case .commitments: return "person.2"
        case .connections: return "point.3.connected.trianglepath.dotted"
        case .settings: return "gearshape"
        case .roadmap: return "map"
        }
    }
}

struct ConnectionContextRow: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme
    let context: ContextItem
    let selected: Bool

    var body: some View {
        Button {
            Task { await state.loadContextDetail(context) }
        } label: {
            HStack(spacing: 9) {
                Circle()
                    .fill(SpeedwagonTheme.contextKindColor(context.kind))
                    .frame(width: 9, height: 9)
                VStack(alignment: .leading, spacing: 2) {
                    Text(context.name)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(SpeedwagonTheme.primaryText(scheme))
                        .lineLimit(1)
                    Text(context.kind)
                        .font(.caption2)
                        .foregroundStyle(SpeedwagonTheme.tertiaryText(scheme))
                }
                Spacer()
                if let confidence = context.confidence {
                    Text("\(Int(confidence * 100))%")
                        .font(.caption2.monospaced())
                        .foregroundStyle(.secondary)
                }
            }
            .padding(.horizontal, 9)
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(selected ? SpeedwagonTheme.accentSoft(scheme) : SpeedwagonTheme.secondaryPanelBackground(scheme))
            .clipShape(RoundedRectangle(cornerRadius: 7))
            .overlay(
                RoundedRectangle(cornerRadius: 7)
                    .stroke(selected ? SpeedwagonTheme.accent(scheme).opacity(0.7) : SpeedwagonTheme.softLine(scheme))
            )
        }
        .buttonStyle(.plain)
        .speedwagonPointer()
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
        .onChange(of: state.highlightedSuggestionId) { _, id in
            if id != nil {
                selectedSection = .suggestions
            }
        }
        .onChange(of: state.suggestionReviewToken) { _, _ in
            selectedSection = .suggestions
        }
        .onChange(of: state.highlightedContextId) { _, id in
            if id != nil {
                selectedSection = .connections
            }
        }
    }

    private var sidebar: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 9) {
                    ZStack {
                        RoundedRectangle(cornerRadius: 7)
                            .fill(SpeedwagonTheme.accent(scheme))
                            .frame(width: 28, height: 28)
                        Image(systemName: "bolt.fill")
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundStyle(Color.black.opacity(0.78))
                    }
                    VStack(alignment: .leading, spacing: 2) {
                        Text("SpeedwagonAI")
                            .font(.callout.weight(.semibold))
                            .foregroundStyle(SpeedwagonTheme.primaryText(scheme))
                        Text("Private beta")
                            .font(.caption2)
                            .foregroundStyle(SpeedwagonTheme.tertiaryText(scheme))
                    }
                }

                BackendStatusView()
            }
            .padding(.bottom, 14)

            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(Array(NativeSection.grouped.enumerated()), id: \.offset) { _, group in
                        VStack(alignment: .leading, spacing: 3) {
                            if let title = group.title {
                                Text(title.uppercased())
                                    .font(.caption2.weight(.semibold))
                                    .tracking(1.0)
                                    .foregroundStyle(SpeedwagonTheme.tertiaryText(scheme))
                                    .padding(.horizontal, 8)
                                    .padding(.top, 8)
                                    .padding(.bottom, 3)
                            }
                            ForEach(group.sections) { section in
                                SidebarButton(section: section, selectedSection: $selectedSection)
                            }
                        }
                    }
                }
            }

            Button {
                AssistantPanelController.shared.toggle(state: state)
            } label: {
                HStack(spacing: 8) {
                    Image(systemName: "magnifyingglass")
                        .foregroundStyle(SpeedwagonTheme.accent(scheme))
                    Text("Open Assistant")
                        .frame(maxWidth: .infinity, alignment: .leading)
                    Text("⌥Space")
                        .font(.caption2.monospaced().weight(.medium))
                        .foregroundStyle(SpeedwagonTheme.tertiaryText(scheme))
                        .padding(.horizontal, 5)
                        .padding(.vertical, 2)
                        .overlay(RoundedRectangle(cornerRadius: 4).stroke(SpeedwagonTheme.line(scheme)))
                }
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(SpeedwagonTheme.panelBackground(scheme))
            .clipShape(RoundedRectangle(cornerRadius: 7))
            .overlay(RoundedRectangle(cornerRadius: 7).stroke(SpeedwagonTheme.line(scheme)))
            .keyboardShortcut("k", modifiers: .command)

            BackendGuideView()
        }
        .padding(18)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(SpeedwagonTheme.sidebarBackground(scheme))
        .navigationSplitViewColumnWidth(min: 220, ideal: 240)
    }

    private var dashboard: some View {
        VStack(spacing: 0) {
            DashboardToolbar(selectedSection: selectedSection)
            if selectedSection.usesFixedWorkspace {
                sectionContent
                    .padding(22)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 16) {
                        sectionContent
                    }
                    .padding(22)
                }
            }
        }
        .background(SpeedwagonTheme.appBackground(scheme))
    }

    @ViewBuilder
    private var sectionContent: some View {
        switch selectedSection {
        case .assistant:
            TodaySurfaceView(navigate: { selectedSection = $0 })
        case .capture:
            CaptureScreenView()
        case .meetings:
            MeetingsScreenView()
        case .calendar:
            CalendarScreenView()
        case .notifications:
            NotificationsScreenView()
        case .tasks:
            TasksScreenView()
        case .suggestions:
            SuggestionsScreenView()
        case .commitments:
            CommitmentsScreenView()
        case .connections:
            ConnectionsView()
        case .settings:
            SettingsScreenView()
        case .roadmap:
            AboutBetaView()
        }
    }
}

struct DashboardToolbar: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme
    let selectedSection: NativeSection

    var body: some View {
        HStack(alignment: .center) {
            Text(selectedSection.rawValue)
                .font(.title2.weight(.semibold))
                .foregroundStyle(SpeedwagonTheme.primaryText(scheme))
            Spacer()
            Button {
                AssistantPanelController.shared.toggle(state: state)
            } label: {
                HStack(spacing: 7) {
                    Image(systemName: "magnifyingglass")
                    Text("Search & commands")
                    Text("⌘K")
                        .font(.caption2.monospaced().weight(.medium))
                        .padding(.horizontal, 5)
                        .padding(.vertical, 2)
                        .overlay(RoundedRectangle(cornerRadius: 4).stroke(SpeedwagonTheme.line(scheme)))
                }
                .font(.caption.weight(.medium))
            }
            .buttonStyle(.plain)
            .foregroundStyle(SpeedwagonTheme.secondaryText(scheme))
            .padding(.horizontal, 11)
            .padding(.vertical, 7)
            .background(SpeedwagonTheme.panelBackground(scheme))
            .clipShape(RoundedRectangle(cornerRadius: 7))
            .overlay(RoundedRectangle(cornerRadius: 7).stroke(SpeedwagonTheme.line(scheme)))
            .speedwagonPointer()

            Button {
                Task { await state.refreshAll() }
            } label: {
                Label(state.isLoading ? "Refreshing..." : "Refresh", systemImage: "arrow.clockwise")
            }
            .buttonStyle(.bordered)
            .disabled(state.isLoading)
            .speedwagonPointer()
        }
        .padding(.horizontal, 22)
        .frame(height: 52)
        .background(SpeedwagonTheme.toolbarBackground(scheme))
        .overlay(alignment: .bottom) {
            Rectangle()
                .fill(SpeedwagonTheme.line(scheme))
                .frame(height: 1)
        }
    }
}

struct TodaySurfaceView: View {
    @EnvironmentObject private var state: AppState
    let navigate: (NativeSection) -> Void

    private var activeSuggestions: [SuggestionItem] {
        state.suggestions.filter { $0.status == "open" }
    }

    private var attentionTasks: [TaskItem] {
        if let brief = state.dailyBrief {
            return Array((brief.overdue + brief.today).prefix(8))
        }
        return Array(state.tasks.filter { !$0.isDone && $0.status != "canceled" }.prefix(8))
    }

    private var waitingTasks: [TaskItem] {
        if let brief = state.dailyBrief {
            return Array((brief.waiting + brief.uncertain).prefix(5))
        }
        return Array(state.tasks.filter { $0.status == "waiting" || $0.status == "uncertain" }.prefix(5))
    }

    var body: some View {
        HStack(alignment: .top, spacing: 18) {
            VStack(alignment: .leading, spacing: 18) {
                TodayAssistantBar()
                PendingSuggestionStrip(count: activeSuggestions.count) {
                    navigate(.suggestions)
                }
                AttentionStackView(tasks: attentionTasks)
                TopSuggestionsStackView(suggestions: Array(activeSuggestions.prefix(2))) {
                    navigate(.suggestions)
                }
            }
            .frame(maxWidth: .infinity, alignment: .topLeading)

            VStack(alignment: .leading, spacing: 14) {
                DailyBriefRailView()
                WaitingRailView(tasks: waitingTasks)
                ComingUpRailView(events: Array(state.calendarEvents.prefix(3))) {
                    navigate(.calendar)
                }
                QuickCaptureRailView(navigate: navigate)
            }
            .frame(width: 360, alignment: .top)
        }
    }
}

struct TodayAssistantBar: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .center) {
                VStack(alignment: .leading, spacing: 2) {
                    Label("Assistant", systemImage: "sparkle.magnifyingglass")
                        .font(.headline)
                    Text("Ask, retrieve, or prepare local actions across tasks, meetings, people, email drafts, and calendar.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                StatusBadge(text: state.isConnected ? "local app data" : "offline", color: state.isConnected ? SpeedwagonTheme.accent(scheme) : SpeedwagonTheme.danger(scheme))
            }

            AssistantComposerView(compact: true, showShortcut: true)

            FlowRow(spacing: 6) {
                ForEach(assistantStarterCommands, id: \.self) { command in
                    Button(command) {
                        Task { await state.runSuggestedCommand(command) }
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .speedwagonPointer()
                }
            }

            if state.commandResponse != nil || !state.pendingActions.isEmpty || state.lastVoiceTranscript != nil || state.screenshotAnalysis != nil {
                AssistantConversationPreview(compact: true)
            }
        }
        .speedwagonPanel()
    }

    private var assistantStarterCommands: [String] {
        [
            "daily brief",
            "what is overdue",
            "who should I follow up with",
            "what did we decide about onboarding",
            "everything related to Alex",
            "create a calendar event tomorrow at 10am for planning"
        ]
    }
}

struct AssistantComposerView: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme
    @FocusState private var focused: Bool
    let compact: Bool
    let showShortcut: Bool

    private var trimmedPrompt: String {
        state.commandText.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    var body: some View {
        VStack(spacing: 8) {
            ZStack(alignment: .topLeading) {
                TextEditor(text: $state.commandText)
                    .font(.system(size: 14))
                    .scrollContentBackground(.hidden)
                    .focused($focused)
                    .frame(minHeight: compact ? 48 : 74, maxHeight: compact ? 72 : 120)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 8)

                if state.commandText.isEmpty {
                    Text("Ask about tasks, meetings, people, projects, or calendar actions...")
                        .font(.system(size: 14))
                        .foregroundStyle(SpeedwagonTheme.tertiaryText(scheme))
                        .padding(.horizontal, 15)
                        .padding(.vertical, 9)
                        .allowsHitTesting(false)
                }
            }

            HStack(spacing: 7) {
                HStack(spacing: 6) {
                    Image(systemName: "sparkle.magnifyingglass")
                        .foregroundStyle(SpeedwagonTheme.accent(scheme))
                    Text(state.isAssistantVoiceActive ? "Listening" : "Local assistant")
                        .font(.caption.weight(.medium))
                        .foregroundStyle(SpeedwagonTheme.secondaryText(scheme))
                    if showShortcut {
                        Text("⌘K")
                            .font(.caption2.monospaced().weight(.medium))
                            .foregroundStyle(SpeedwagonTheme.tertiaryText(scheme))
                            .padding(.horizontal, 5)
                            .padding(.vertical, 2)
                            .overlay(RoundedRectangle(cornerRadius: 4).stroke(SpeedwagonTheme.line(scheme)))
                    }
                }

                Spacer()

                Button {
                    Task {
                        if state.isAssistantVoiceActive {
                            await state.stopActiveAssistantVoiceFromComposer()
                        } else {
                            await state.startAssistantVoice()
                        }
                    }
                } label: {
                    Image(systemName: state.isAssistantVoiceActive ? "stop.circle.fill" : "mic")
                        .frame(width: 24, height: 24)
                }
                .buttonStyle(.borderless)
                .help(state.isAssistantVoiceActive ? "Stop voice input" : "Record voice input")
                .speedwagonPointer()

                Button {
                    Task { await state.analyzeScreenshot() }
                } label: {
                    Image(systemName: "camera.viewfinder")
                        .frame(width: 24, height: 24)
                }
                .buttonStyle(.borderless)
                .disabled(state.isLoading || !state.isConnected)
                .help("Analyze screenshot context")
                .speedwagonPointer()

                Button {
                    Task { await state.runCommand() }
                } label: {
                    Image(systemName: "paperplane.fill")
                        .frame(width: 26, height: 24)
                }
                .buttonStyle(.borderedProminent)
                .tint(SpeedwagonTheme.accent(scheme))
                .disabled(trimmedPrompt.isEmpty)
                .help("Send to assistant")
                .speedwagonPointer()
            }
            .padding(.horizontal, 9)
            .padding(.bottom, 8)
        }
        .background(SpeedwagonTheme.panelBackground(scheme))
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(focused ? SpeedwagonTheme.accent(scheme).opacity(0.65) : SpeedwagonTheme.line(scheme))
        )
        .shadow(color: focused ? SpeedwagonTheme.accent(scheme).opacity(0.12) : .clear, radius: 8)
    }
}

struct PendingSuggestionStrip: View {
    @Environment(\.colorScheme) private var scheme
    let count: Int
    let action: () -> Void

    var body: some View {
        if count > 0 {
            HStack(spacing: 12) {
                ZStack {
                    RoundedRectangle(cornerRadius: 8)
                        .fill(SpeedwagonTheme.accentSoft(scheme))
                        .frame(width: 32, height: 32)
                    Image(systemName: "lightbulb")
                        .foregroundStyle(SpeedwagonTheme.accent(scheme))
                }
                VStack(alignment: .leading, spacing: 2) {
                    Text("\(count) suggestion\(count == 1 ? "" : "s") waiting for review")
                        .font(.callout.weight(.semibold))
                    Text("Nothing happens until you confirm. Review evidence before acting.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button {
                    action()
                } label: {
                    Label("Review all", systemImage: "arrow.right")
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            }
            .padding(13)
            .background(SpeedwagonTheme.accentSoft(scheme))
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(SpeedwagonTheme.accent(scheme).opacity(0.35)))
        }
    }
}

struct AttentionStackView: View {
    @EnvironmentObject private var state: AppState
    let tasks: [TaskItem]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            GroupLabelView("Needs attention now", count: tasks.count, accent: true)
            VStack(spacing: 7) {
                if tasks.isEmpty {
                    EmptyStateView(text: "Nothing overdue or due today.")
                } else {
                    ForEach(tasks) { task in
                        TaskRow(
                            task: task,
                            highlighted: state.highlightedTaskIds.contains(task.id),
                            onComplete: { task in Task { await state.complete(task) } },
                            onReopen: { task in Task { await state.reopen(task) } }
                        )
                    }
                }
            }
            .speedwagonPanel()
        }
    }
}

struct TopSuggestionsStackView: View {
    let suggestions: [SuggestionItem]
    let showAll: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            GroupLabelView("Top suggestions", count: suggestions.count)
            if suggestions.isEmpty {
                EmptyStateView(text: "No active suggestions right now.")
            } else {
                ForEach(suggestions) { suggestion in
                    SuggestionCard(suggestion: suggestion)
                }
                Button {
                    showAll()
                } label: {
                    Label("See all suggestions", systemImage: "chevron.right")
                }
                .buttonStyle(.plain)
                .foregroundStyle(.secondary)
                .speedwagonPointer()
            }
        }
    }
}

struct DailyBriefRailView: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Daily brief")
                    .font(.headline)
                Spacer()
                Button {
                    Task { await state.refreshDailyIntelligence() }
                } label: {
                    Image(systemName: "sparkles")
                }
                .buttonStyle(.borderless)
                .disabled(state.isRefreshingIntelligence || !state.isConnected)
            }

            if let synthesis = state.dailyBrief?.synthesis {
                Text(synthesis.summary)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                if !synthesis.risks.isEmpty {
                    VStack(alignment: .leading, spacing: 5) {
                        Text("RISKS")
                            .font(.caption2.weight(.semibold))
                            .tracking(0.8)
                            .foregroundStyle(SpeedwagonTheme.danger)
                        ForEach(synthesis.risks.prefix(3), id: \.self) { risk in
                            Label(risk, systemImage: "exclamationmark.triangle")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
                Text("Cached local brief\(synthesis.provider.map { " via \($0)" } ?? "").")
                    .font(.caption2.monospaced())
                    .foregroundStyle(.tertiary)
            } else {
                Text("No cached intelligence yet. Refresh Intelligence runs an explicit synthesis pass.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .speedwagonPanel()
    }
}

struct WaitingRailView: View {
    let tasks: [TaskItem]

    var body: some View {
        if !tasks.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text("Waiting on others")
                    .font(.headline)
                ForEach(tasks) { task in
                    TaskRow(task: task, compact: true)
                }
            }
            .speedwagonPanel()
        }
    }
}

struct ComingUpRailView: View {
    let events: [CalendarEvent]
    let openCalendar: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Coming up")
                    .font(.headline)
                Spacer()
                Button("Calendar") {
                    openCalendar()
                }
                .buttonStyle(.borderless)
            }
            if events.isEmpty {
                EmptyStateView(text: "No synced upcoming events.")
            } else {
                ForEach(events) { event in
                    CalendarEventRow(event: event)
                }
            }
        }
        .speedwagonPanel()
    }
}

struct QuickCaptureRailView: View {
    let navigate: (NativeSection) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Capture")
                .font(.headline)
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                QuickCaptureButton(title: "Meeting", systemImage: "rectangle.stack") { navigate(.capture) }
                QuickCaptureButton(title: "Voice task", systemImage: "mic") { navigate(.capture) }
                QuickCaptureButton(title: "Screenshot", systemImage: "camera.viewfinder") { navigate(.assistant) }
                QuickCaptureButton(title: "Meeting bot", systemImage: "video.badge.waveform") { navigate(.capture) }
            }
        }
        .speedwagonPanel()
    }
}

struct QuickCaptureButton: View {
    @Environment(\.colorScheme) private var scheme
    let title: String
    let systemImage: String
    let action: () -> Void

    var body: some View {
        Button {
            action()
        } label: {
            VStack(alignment: .leading, spacing: 7) {
                Image(systemName: systemImage)
                    .foregroundStyle(SpeedwagonTheme.accent(scheme))
                Text(title)
                    .font(.caption.weight(.medium))
                    .foregroundStyle(SpeedwagonTheme.primaryText(scheme))
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(11)
            .background(SpeedwagonTheme.secondaryPanelBackground(scheme))
            .clipShape(RoundedRectangle(cornerRadius: 6))
            .overlay(RoundedRectangle(cornerRadius: 6).stroke(SpeedwagonTheme.softLine(scheme)))
        }
        .buttonStyle(.plain)
        .speedwagonPointer()
    }
}

struct GroupLabelView: View {
    @Environment(\.colorScheme) private var scheme
    let title: String
    let count: Int?
    let accent: Bool

    init(_ title: String, count: Int? = nil, accent: Bool = false) {
        self.title = title
        self.count = count
        self.accent = accent
    }

    var body: some View {
        HStack(spacing: 8) {
            Text(title.uppercased())
                .font(.caption2.weight(.semibold))
                .tracking(1.0)
                .foregroundStyle(accent ? SpeedwagonTheme.accent(scheme) : SpeedwagonTheme.tertiaryText(scheme))
            if let count {
                Text("\(count)")
                    .font(.caption2.monospaced().weight(.medium))
                    .foregroundStyle(SpeedwagonTheme.tertiaryText(scheme))
            }
            Rectangle()
                .fill(SpeedwagonTheme.softLine(scheme))
                .frame(height: 1)
        }
        .padding(.horizontal, 2)
    }
}

struct AssistantSurfaceView: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme
    let expanded: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 3) {
                    Label("Assistant", systemImage: "sparkle.magnifyingglass")
                        .font(.title3.weight(.semibold))
                    Text("Chat with your local work context. Reads can answer directly; writes become pending confirmations.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                StatusBadge(text: state.isConnected ? "local" : "offline", color: state.isConnected ? SpeedwagonTheme.accent(scheme) : SpeedwagonTheme.danger(scheme))
            }

            AssistantContextChips()

            AssistantComposerView(compact: !expanded, showShortcut: false)

            AssistantPromptExamplesView()

            AssistantConversationPreview(compact: !expanded)

            if expanded {
                PaletteCaptureControlsView()

                ScreenshotAnalysisView()

                SuggestionsPanelView(compact: true)
            }
        }
        .speedwagonPanel()
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

struct AssistantPromptExamplesView: View {
    @EnvironmentObject private var state: AppState

    private let examples = [
        "what should I do next",
        "who should I follow up with",
        "what changed on Northwind",
        "what did we decide about pricing",
        "show unprocessed meetings",
        "create a calendar event tomorrow at 10am for planning"
    ]

    var body: some View {
        FlowRow(spacing: 6) {
            ForEach(examples, id: \.self) { command in
                Button(command) {
                    Task { await state.runSuggestedCommand(command) }
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .speedwagonPointer()
            }
        }
    }
}

struct AssistantConversationPreview: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme
    let compact: Bool
    var showHeader = true

    private var userPrompt: String? {
        if let command = state.commandResponse?.command, !command.isEmpty {
            return command
        }
        if let transcript = state.lastVoiceTranscript, !transcript.isEmpty {
            return transcript
        }
        return nil
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if showHeader {
                HStack {
                    Text("Current Thread")
                        .font(.headline)
                    Spacer()
                    if state.commandResponse?.requiresConfirmation == true || !state.pendingActions.isEmpty {
                        ToneChip(text: "Needs review", tone: SpeedwagonTheme.warning, systemImage: "checkmark.shield")
                    }
                    Button {
                        state.clearConversation()
                    } label: {
                        Label("Clear", systemImage: "trash")
                            .font(.caption.weight(.medium))
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(SpeedwagonTheme.secondaryText(scheme))
                    .speedwagonPointer()
                }
            }

            if let prompt = userPrompt {
                AssistantBubble(role: "You", systemImage: "person.crop.circle", accent: SpeedwagonTheme.accent(scheme), alignment: .trailing) {
                    Text(prompt)
                        .font(.body)
                        .lineLimit(compact ? 2 : nil)
                }
            }

            if let response = state.commandResponse {
                AssistantBubble(role: "SpeedwagonAI", systemImage: "bolt.fill", accent: SpeedwagonTheme.accent(scheme), alignment: .leading) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(response.summary)
                            .font(.body.weight(.medium))
                        if let explanation = response.explanation, !explanation.isEmpty {
                            Text(explanation)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        ResultContent(response: response)
                        if let context = response.result?.context {
                            ContextReviewButton(context: context)
                        }
                        if let suggestions = response.suggestedCommands, !suggestions.isEmpty {
                            FlowRow(spacing: 6) {
                                ForEach(suggestions.prefix(compact ? 3 : 6), id: \.self) { command in
                                    Button(command) {
                                        Task { await state.runSuggestedCommand(command) }
                                    }
                                    .buttonStyle(.bordered)
                                    .controlSize(.small)
                                    .speedwagonPointer()
                                }
                            }
                        }
                    }
                }
            } else {
                Text("Ask anything about the local app data, or prepare safe actions like creating a Calendar event. Writes stay confirmation-first.")
                    .font(.body)
                    .foregroundStyle(.secondary)
            }

            if let error = state.commandErrorMessage {
                Text(error)
                    .font(.caption)
                    .foregroundStyle(SpeedwagonTheme.danger(scheme))
            }

            PendingActionsView()
        }
        .padding(showHeader ? 12 : 0)
        .background(showHeader ? SpeedwagonTheme.secondaryPanelBackground(scheme) : Color.clear)
        .clipShape(RoundedRectangle(cornerRadius: showHeader ? 8 : 0))
        .overlay(RoundedRectangle(cornerRadius: showHeader ? 8 : 0).stroke(showHeader ? SpeedwagonTheme.softLine(scheme) : Color.clear))
    }
}

enum AssistantBubbleAlignment {
    case leading
    case trailing
}

struct AssistantBubble<Content: View>: View {
    @Environment(\.colorScheme) private var scheme
    let role: String
    let systemImage: String
    let accent: Color
    var alignment: AssistantBubbleAlignment = .leading
    @ViewBuilder let content: Content

    var body: some View {
        HStack(alignment: .bottom, spacing: 9) {
            if alignment == .trailing {
                Spacer(minLength: 110)
            } else {
                avatar
            }

            VStack(alignment: alignment == .trailing ? .trailing : .leading, spacing: 5) {
                if alignment == .leading {
                    Text(role)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(SpeedwagonTheme.secondaryText(scheme))
                }
                content
                    .multilineTextAlignment(alignment == .trailing ? .trailing : .leading)
            }
            .padding(.horizontal, 13)
            .padding(.vertical, 11)
            .background(alignment == .trailing ? SpeedwagonTheme.accentSoft(scheme) : SpeedwagonTheme.panelBackground(scheme))
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(alignment == .trailing ? SpeedwagonTheme.accent(scheme).opacity(0.45) : SpeedwagonTheme.softLine(scheme)))

            if alignment == .leading {
                Spacer(minLength: 120)
            }
        }
        .frame(maxWidth: .infinity, alignment: alignment == .trailing ? .trailing : .leading)
    }

    private var avatar: some View {
        Image(systemName: systemImage)
            .font(.system(size: 14, weight: .semibold))
            .foregroundStyle(accent)
            .frame(width: 32, height: 32)
            .background(accent.opacity(0.16))
            .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

struct SuggestedActionsView: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Suggestions")
                .font(.headline)
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                ForEach(["daily brief", "who should I follow up with", "everything related to Alex", "what did we decide about onboarding", "what changed on DairyMGT", "prep for my next meeting"], id: \.self) { command in
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
    @Environment(\.colorScheme) private var scheme
    @State private var expanded = false

    var body: some View {
        VStack(spacing: 0) {
            PaletteHeaderView(expanded: $expanded)

            if expanded {
                PaletteOverviewBandView()
                    .transition(.opacity.combined(with: .move(edge: .top)))
            }

            ZStack {
                if state.commandResponse != nil || !state.pendingActions.isEmpty || state.lastVoiceTranscript != nil || state.screenshotAnalysis != nil {
                    VStack(spacing: 0) {
                        HStack {
                            Text("Current Thread")
                                .font(.title3.weight(.semibold))
                                .foregroundStyle(SpeedwagonTheme.primaryText(scheme))
                            Spacer()
                            Button {
                                state.clearConversation()
                            } label: {
                                Label("Clear thread", systemImage: "trash")
                                    .font(.caption.weight(.medium))
                            }
                            .buttonStyle(.plain)
                            .foregroundStyle(SpeedwagonTheme.secondaryText(scheme))
                            .speedwagonPointer()
                        }
                        .padding(.horizontal, 22)
                        .padding(.vertical, 8)

                        ScrollView {
                            AssistantConversationPreview(compact: false, showHeader: false)
                                .padding(.horizontal, 22)
                                .padding(.vertical, 20)
                        }
                    }
                } else {
                    PaletteWelcomeView()
                        .padding(.horizontal, 28)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)

            PaletteComposerDockView()
        }
        .frame(width: AssistantPanelController.contentSize.width, height: AssistantPanelController.contentSize.height)
        .background(SpeedwagonTheme.appBackground(scheme))
        .task {
            if !state.isConnected || (state.tasks.isEmpty && state.meetings.isEmpty && state.calendarEvents.isEmpty) {
                await state.refreshAll(updateStatus: false)
            }
        }
    }
}

struct PaletteHeaderView: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme
    @Binding var expanded: Bool

    var body: some View {
        HStack(spacing: 16) {
            ZStack {
                RoundedRectangle(cornerRadius: 8)
                    .fill(SpeedwagonTheme.accent(scheme))
                    .frame(width: 38, height: 38)
                Image(systemName: "bolt.fill")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(Color.black.opacity(0.78))
            }

            Text("SpeedwagonAI")
                .font(.system(size: 22, weight: .semibold))
                .foregroundStyle(SpeedwagonTheme.primaryText(scheme))

            StatusBadge(
                text: state.isConnected ? "Connected" : "Offline",
                color: state.isConnected ? SpeedwagonTheme.success : SpeedwagonTheme.danger(scheme)
            )

            Spacer()

            Button {
                withAnimation(.easeInOut(duration: 0.18)) {
                    expanded.toggle()
                }
            } label: {
                Label(expanded ? "Collapse" : "Overview", systemImage: expanded ? "chevron.down" : "chevron.right")
                    .font(.callout.weight(.medium))
                    .padding(.horizontal, 13)
                    .padding(.vertical, 8)
                    .background(expanded ? SpeedwagonTheme.accentSoft(scheme) : Color.clear)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
            }
            .buttonStyle(.plain)
            .foregroundStyle(expanded ? SpeedwagonTheme.accent(scheme) : SpeedwagonTheme.secondaryText(scheme))
            .speedwagonPointer()

            Button {
                activateSpeedwagon()
                AssistantPanelController.shared.close()
            } label: {
                Label("Open app", systemImage: "arrow.right")
                    .font(.callout.weight(.medium))
            }
            .buttonStyle(.plain)
            .foregroundStyle(SpeedwagonTheme.secondaryText(scheme))
            .speedwagonPointer()

            Text("⌥Space")
                .font(.callout.monospaced().weight(.medium))
                .foregroundStyle(SpeedwagonTheme.tertiaryText(scheme))
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(SpeedwagonTheme.line(scheme)))

            Button {
                AssistantPanelController.shared.close()
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 15, weight: .medium))
                    .frame(width: 28, height: 28)
            }
            .buttonStyle(.plain)
            .foregroundStyle(SpeedwagonTheme.secondaryText(scheme))
            .keyboardShortcut(.escape, modifiers: [])
            .speedwagonPointer()
        }
        .padding(.horizontal, 20)
        .frame(height: 66)
        .background(SpeedwagonTheme.toolbarBackground(scheme))
        .overlay(alignment: .bottom) {
            Rectangle()
                .fill(SpeedwagonTheme.line(scheme))
                .frame(height: 1)
        }
    }
}

struct PaletteOverviewBandView: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme

    private var attentionTasks: [TaskItem] {
        if let brief = state.dailyBrief {
            return Array((brief.overdue + brief.today).prefix(3))
        }
        return Array(state.tasks.filter { !$0.isDone && $0.status != "canceled" }.prefix(3))
    }

    private var topSuggestions: [SuggestionItem] {
        Array(state.suggestions.filter { $0.status == "open" }.prefix(2))
    }

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            VStack(alignment: .leading, spacing: 13) {
                PaletteSectionLabel(title: "Needs attention", count: attentionTasks.count)
                if attentionTasks.isEmpty {
                    Text("Nothing urgent in the local task list.")
                        .font(.callout)
                        .foregroundStyle(SpeedwagonTheme.secondaryText(scheme))
                } else {
                    ForEach(attentionTasks) { task in
                        PaletteTaskLine(task: task)
                    }
                }
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .topLeading)

            Rectangle()
                .fill(SpeedwagonTheme.line(scheme))
                .frame(width: 1)

            VStack(alignment: .leading, spacing: 16) {
                VStack(alignment: .leading, spacing: 12) {
                    PaletteSectionLabel(title: "Top suggestions", count: topSuggestions.count)
                    if topSuggestions.isEmpty {
                        Text("No active suggestions.")
                            .font(.callout)
                            .foregroundStyle(SpeedwagonTheme.secondaryText(scheme))
                    } else {
                        ForEach(topSuggestions) { suggestion in
                            HStack(spacing: 10) {
                                Image(systemName: "lightbulb")
                                    .foregroundStyle(SpeedwagonTheme.tertiaryText(scheme))
                                    .frame(width: 18)
                                Text(suggestion.title)
                                    .lineLimit(1)
                                Spacer()
                                if let confidence = suggestion.confidence {
                                    Text("\(Int(confidence * 100))%")
                                        .font(.callout.monospaced())
                                        .foregroundStyle(SpeedwagonTheme.tertiaryText(scheme))
                                }
                            }
                            .font(.callout)
                            .foregroundStyle(SpeedwagonTheme.secondaryText(scheme))
                        }
                    }
                }

                VStack(alignment: .leading, spacing: 12) {
                    PaletteSectionLabel(title: "Coming up", count: state.calendarEvents.prefix(2).count)
                    if state.calendarEvents.isEmpty {
                        Text("No synced upcoming events.")
                            .font(.callout)
                            .foregroundStyle(SpeedwagonTheme.secondaryText(scheme))
                    } else {
                        ForEach(Array(state.calendarEvents.prefix(2))) { event in
                            HStack(spacing: 10) {
                                Image(systemName: "calendar")
                                    .foregroundStyle(SpeedwagonTheme.tertiaryText(scheme))
                                    .frame(width: 18)
                                Text(event.title)
                                    .lineLimit(1)
                                Spacer()
                                Text(shortPaletteDate(event.startAt))
                                    .font(.callout.monospaced())
                                    .foregroundStyle(SpeedwagonTheme.tertiaryText(scheme))
                            }
                            .font(.callout)
                            .foregroundStyle(SpeedwagonTheme.secondaryText(scheme))
                        }
                    }
                }
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .topLeading)
        }
        .frame(height: 190)
        .background(SpeedwagonTheme.toolbarBackground(scheme).opacity(0.55))
        .overlay(alignment: .bottom) {
            Rectangle()
                .fill(SpeedwagonTheme.line(scheme))
                .frame(height: 1)
        }
    }

    private func shortPaletteDate(_ iso: String) -> String {
        guard iso.count >= 16 else { return iso }
        let monthDay = String(iso.dropFirst(5).prefix(5)).replacingOccurrences(of: "-", with: "/")
        let time = String(iso.dropFirst(11).prefix(5))
        return "\(monthDay) \(time)"
    }
}

struct PaletteWelcomeView: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme

    private let commands = [
        "Daily brief",
        "What's overdue?",
        "Follow-ups needed",
        "Prep next meeting",
        "What did we decide about onboarding?",
        "Everything about Alex"
    ]

    var body: some View {
        VStack(spacing: 20) {
            Spacer(minLength: 12)
            Text("What can I help with?")
                .font(.system(size: 28, weight: .semibold))
                .foregroundStyle(SpeedwagonTheme.primaryText(scheme))
            Text("Ask about tasks, meetings, calendar, or people. Give commands to create events, complete tasks, and more.")
                .font(.system(size: 17))
                .foregroundStyle(SpeedwagonTheme.secondaryText(scheme))
                .multilineTextAlignment(.center)
                .lineLimit(2)
                .frame(maxWidth: 600)
            FlowRow(spacing: 10) {
                ForEach(commands, id: \.self) { title in
                    Button {
                        Task { await state.runSuggestedCommand(commandText(for: title)) }
                    } label: {
                        Text(title)
                            .font(.system(size: 16, weight: .medium))
                            .padding(.horizontal, 18)
                            .padding(.vertical, 10)
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(SpeedwagonTheme.secondaryText(scheme))
                    .background(SpeedwagonTheme.secondaryPanelBackground(scheme))
                    .clipShape(Capsule())
                    .overlay(Capsule().stroke(SpeedwagonTheme.line(scheme)))
                    .speedwagonPointer()
                }
            }
            .frame(maxWidth: 760)
            Spacer(minLength: 12)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func commandText(for title: String) -> String {
        switch title {
        case "Daily brief": return "daily brief"
        case "What's overdue?": return "what is overdue"
        case "Follow-ups needed": return "who should I follow up with"
        case "Prep next meeting": return "prep for my next meeting"
        case "Everything about Alex": return "everything related to Alex"
        default: return title
        }
    }
}

struct PaletteComposerDockView: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            PaletteCommandInputView()
            FlowRow(spacing: 8) {
                ToneChip(text: "\(state.tasks.filter { !$0.isDone }.count) open tasks", tone: nil, systemImage: "checklist")
                ToneChip(text: "\(state.suggestions.filter { $0.status == "open" }.count) suggestions", tone: nil, systemImage: "lightbulb")
                ToneChip(text: state.isAssistantVoiceActive ? "listening" : "mic ready", tone: nil, systemImage: "mic")
                if !state.calendarEvents.isEmpty {
                    ToneChip(text: "\(state.calendarEvents.count) calendar", tone: nil, systemImage: "calendar")
                }
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .background(SpeedwagonTheme.toolbarBackground(scheme))
        .overlay(alignment: .top) {
            Rectangle()
                .fill(SpeedwagonTheme.line(scheme))
                .frame(height: 1)
        }
    }
}

struct PaletteCommandInputView: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme
    @FocusState private var focused: Bool

    private var trimmedPrompt: String {
        state.commandText.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    var body: some View {
        HStack(spacing: 10) {
            TextField("Ask anything about your work, or give a command...", text: $state.commandText)
                .textFieldStyle(.plain)
                .font(.system(size: 16))
                .focused($focused)
                .onSubmit {
                    Task { await state.runCommand() }
                }
                .padding(.horizontal, 14)
                .frame(height: 50)
                .background(SpeedwagonTheme.panelBackground(scheme))
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(focused ? SpeedwagonTheme.accent(scheme).opacity(0.65) : SpeedwagonTheme.line(scheme))
                )

            paletteIconButton(
                systemImage: state.isAssistantVoiceActive ? "stop.circle.fill" : "mic",
                help: state.isAssistantVoiceActive ? "Stop voice input" : "Record voice input"
            ) {
                Task {
                    if state.isAssistantVoiceActive {
                        await state.stopActiveAssistantVoiceFromComposer()
                    } else {
                        await state.startAssistantVoice()
                    }
                }
            }

            paletteIconButton(systemImage: "camera.viewfinder", help: "Analyze screenshot context") {
                Task { await state.analyzeScreenshot() }
            }
            .disabled(state.isLoading || !state.isConnected)

            paletteIconButton(systemImage: "arrow.right", help: "Send to assistant") {
                Task { await state.runCommand() }
            }
            .disabled(trimmedPrompt.isEmpty)
        }
    }

    private func paletteIconButton(systemImage: String, help: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: systemImage)
                .font(.system(size: 16, weight: .semibold))
                .frame(width: 50, height: 50)
                .background(SpeedwagonTheme.panelBackground(scheme))
                .clipShape(RoundedRectangle(cornerRadius: 8))
        }
        .buttonStyle(.plain)
        .foregroundStyle(SpeedwagonTheme.secondaryText(scheme))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(SpeedwagonTheme.softLine(scheme)))
        .help(help)
        .speedwagonPointer()
    }
}

struct PaletteSectionLabel: View {
    @Environment(\.colorScheme) private var scheme
    let title: String
    let count: Int

    var body: some View {
        HStack(spacing: 6) {
            Text(title.uppercased())
            Text("· \(count)")
        }
        .font(.caption.weight(.bold))
        .tracking(1.8)
        .foregroundStyle(SpeedwagonTheme.tertiaryText(scheme))
    }
}

struct PaletteTaskLine: View {
    @Environment(\.colorScheme) private var scheme
    let task: TaskItem

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "clock")
                .foregroundStyle(SpeedwagonTheme.danger(scheme))
                .frame(width: 18)
            Text(task.text)
                .lineLimit(1)
            Spacer()
            Text(dueLabel)
                .font(.callout.monospaced())
                .foregroundStyle(dueLabel.contains("overdue") ? SpeedwagonTheme.danger(scheme) : SpeedwagonTheme.tertiaryText(scheme))
        }
        .font(.callout)
        .foregroundStyle(SpeedwagonTheme.secondaryText(scheme))
    }

    private var dueLabel: String {
        guard let dueDate = task.dueDate, !dueDate.isEmpty else {
            return "unscheduled"
        }
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withFullDate]
        guard let date = formatter.date(from: dueDate) else {
            return dueDate
        }
        let start = Calendar.current.startOfDay(for: Date())
        let due = Calendar.current.startOfDay(for: date)
        let days = Calendar.current.dateComponents([.day], from: due, to: start).day ?? 0
        if days > 0 {
            return "\(days)d overdue"
        }
        if Calendar.current.isDateInToday(due) {
            return "today"
        }
        return dueDate
    }
}

// MARK: - Capture screen

struct CaptureScreenView: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme
    private var isActive: Bool { state.captureStatus?.isActive == true }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            // Active recording banner — impossible to miss
            if isActive {
                ActiveRecordingBanner(session: state.captureStatus)
            }

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 18) {
                // Meeting capture
                VStack(alignment: .leading, spacing: 14) {
                    Text("Capture a meeting")
                        .font(.headline)
                    Picker("Mode", selection: $state.meetingCaptureMode) {
                        ForEach(MeetingCaptureMode.allCases) { mode in
                            Text(mode.rawValue).tag(mode)
                        }
                    }
                    .pickerStyle(.segmented)
                    NativeCaptureStatusRows(snapshot: state.nativeCapturePermissions)
                    TextField("Meeting title (optional)", text: $state.meetingCaptureTitle)
                        .textFieldStyle(.roundedBorder)
                    Button {
                        Task { await state.startMeetingCapture() }
                    } label: {
                        Label(
                            state.meetingCaptureMode == .nativeSystemMic ? "Start native capture" : "Start mic capture",
                            systemImage: state.meetingCaptureMode == .nativeSystemMic ? "display.and.arrow.down" : "mic"
                        )
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(SpeedwagonTheme.accent(scheme))
                    .disabled(isActive)
                    .speedwagonPointer()
                    ForEach(state.nativeCaptureWarnings, id: \.self) {
                        Text($0).font(.caption).foregroundStyle(SpeedwagonTheme.danger)
                    }
                }
                .speedwagonPanel()

                // Quick capture column
                VStack(spacing: 14) {
                    VStack(alignment: .leading, spacing: 10) {
                        Text("Quick voice task")
                            .font(.headline)
                        Text("Speak a task. Transcribed locally and added for review.")
                            .font(.caption).foregroundStyle(.secondary)
                        Button {
                            Task { await state.startTaskCapture() }
                        } label: {
                            Label("Record voice task", systemImage: "mic")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                        .disabled(isActive)
                        .speedwagonPointer()
                    }
                    .speedwagonPanel()

                    VStack(alignment: .leading, spacing: 10) {
                        Text("Screenshot capture")
                            .font(.headline)
                        Text("Capture a region; the assistant extracts tasks or context.")
                            .font(.caption).foregroundStyle(.secondary)
                        Button {
                            Task { await state.analyzeScreenshot() }
                        } label: {
                            Label("Capture screenshot", systemImage: "camera.viewfinder")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                        .disabled(!state.isConnected)
                        .speedwagonPointer()
                    }
                    .speedwagonPanel()
                }
            }

            // Meeting bot
            MeetingBotSectionView()
        }
    }
}

struct ActiveRecordingBanner: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme
    let session: CaptureSession?

    var body: some View {
        HStack(spacing: 16) {
            HStack(spacing: 8) {
                Circle()
                    .fill(SpeedwagonTheme.danger)
                    .frame(width: 10, height: 10)
                Text("RECORDING")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(SpeedwagonTheme.danger)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(session?.title ?? "Active capture")
                    .font(.callout.weight(.semibold))
                Text(session?.captureProfile ?? "")
                    .font(.caption.monospaced())
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if session?.kind == "meeting" {
                Button {
                    Task { await state.stopCapture(process: false) }
                } label: {
                    Label("Stop", systemImage: "stop.fill")
                }
                .buttonStyle(.bordered)
                .speedwagonPointer()
                Button {
                    Task { await state.stopCapture(process: true) }
                } label: {
                    Label("Stop + Process", systemImage: "bolt.fill")
                }
                .buttonStyle(.borderedProminent)
                .tint(SpeedwagonTheme.accent(scheme))
                .speedwagonPointer()
            } else if session?.kind == "task_note" {
                Button {
                    Task { await state.stopCapture(process: false) }
                } label: {
                    Label("Stop + Add task", systemImage: "checkmark")
                }
                .buttonStyle(.borderedProminent)
                .tint(SpeedwagonTheme.accent(scheme))
                .speedwagonPointer()
            } else {
                Button {
                    Task { await state.stopAssistantVoice() }
                } label: {
                    Label("Stop + Run", systemImage: "arrow.right")
                }
                .buttonStyle(.borderedProminent)
                .tint(SpeedwagonTheme.accent(scheme))
                .speedwagonPointer()
            }
        }
        .padding(15)
        .background(SpeedwagonTheme.danger.opacity(0.10))
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(SpeedwagonTheme.danger.opacity(0.40)))
    }
}

struct MeetingBotSectionView: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text("Meeting bot")
                    .font(.headline)
                Spacer()
                ToneChip(text: "Beta · cloud", tone: SpeedwagonTheme.info, systemImage: "cube")
            }

            // Cloud/consent warning
            HStack(alignment: .top, spacing: 9) {
                Image(systemName: "info.circle")
                    .foregroundStyle(SpeedwagonTheme.info)
                Text("A bot joins through Recall.ai. **Visible to all participants**, processed in the cloud, not on your Mac. Use only with everyone's consent.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(11)
            .background(SpeedwagonTheme.info.opacity(0.08))
            .clipShape(RoundedRectangle(cornerRadius: 6))

            // Provider info
            HStack(spacing: 20) {
                LabeledValue(label: "Provider", value: state.botStatus?.provider ?? "not configured")
                LabeledValue(label: "Status", value: state.botStatus?.status ?? "unknown")
                LabeledValue(label: "Est. cost", value: state.botStatus?.cloudCostLabel.map { "\($0)/hr" } ?? "—")
            }

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                TextField("Meeting title", text: $state.botMeetingTitle)
                    .textFieldStyle(.roundedBorder)
                TextField("Meeting link (Zoom / Meet)", text: $state.botMeetingURL)
                    .textFieldStyle(.roundedBorder)
            }

            // Consent checkbox — highlighted when checked
            HStack(alignment: .top, spacing: 9) {
                Toggle("", isOn: $state.botConsentConfirmed)
                    .toggleStyle(.checkbox)
                    .labelsHidden()
                Text("I confirm everyone in this meeting is aware a recording bot will join and has consented.")
                    .font(.caption)
                    .foregroundStyle(.primary)
            }
            .padding(11)
            .background(state.botConsentConfirmed ? SpeedwagonTheme.accentSoft(scheme) : SpeedwagonTheme.secondaryPanelBackground(scheme))
            .clipShape(RoundedRectangle(cornerRadius: 6))
            .overlay(RoundedRectangle(cornerRadius: 6).stroke(state.botConsentConfirmed ? SpeedwagonTheme.accent(scheme).opacity(0.35) : SpeedwagonTheme.softLine(scheme)))

            HStack(spacing: 8) {
                Button {
                    Task { await state.joinBotSession() }
                } label: {
                    Label("Join bot", systemImage: "video.badge.waveform")
                }
                .buttonStyle(.bordered)
                .tint(state.botConsentConfirmed ? SpeedwagonTheme.accent(scheme) : SpeedwagonTheme.secondaryText(scheme))
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
                .buttonStyle(.bordered)
                .speedwagonPointer()
                Button {
                    Task { await state.clearBotSessions() }
                } label: {
                    Label("Clear", systemImage: "trash")
                }
                .buttonStyle(.bordered)
                .disabled(state.botSessions.isEmpty)
                .speedwagonPointer()
            }

            if !state.botSessions.isEmpty {
                Divider()
                ForEach(state.botSessions.prefix(5)) { session in
                    BotSessionRow(session: session)
                }
            }
        }
        .speedwagonPanel()
    }
}

struct LabeledValue: View {
    let label: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label.uppercased())
                .font(.caption2.weight(.semibold))
                .tracking(0.7)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.caption.monospaced().weight(.medium))
        }
    }
}

// Legacy alias kept for palette capture controls
struct CapturePanelView: View {
    var body: some View { CaptureScreenView() }
}
struct MeetingBotPanelView: View {
    var body: some View { MeetingBotSectionView() }
}

// MARK: - Calendar screen

struct CalendarScreenView: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme

    // Group events by day prefix
    private var byDay: [(String, [CalendarEvent])] {
        var dict: [(String, [CalendarEvent])] = []
        var keys: [String] = []
        for event in state.calendarEvents {
            let day = String(event.startAt.prefix(10))
            if let idx = keys.firstIndex(of: day) {
                dict[idx].1.append(event)
            } else {
                keys.append(day)
                dict.append((day, [event]))
            }
        }
        return dict
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            // Status panel
            VStack(alignment: .leading, spacing: 0) {
                HStack(spacing: 12) {
                    Circle()
                        .fill(state.calendarStatus?.enabled == true ? SpeedwagonTheme.success : SpeedwagonTheme.warning)
                        .frame(width: 8, height: 8)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(state.calendarStatus?.enabled == true ? "Google Calendar connected" : "Google Calendar not configured")
                            .font(.callout.weight(.semibold))
                        Text("Sync caches a rolling \(state.calendarStatus?.syncDaysBack ?? 14)-day window locally. Event creation is explicit.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    ToneChip(
                        text: state.calendarStatus?.writeEnabled == true ? "Write ready" : "Read sync",
                        tone: state.calendarStatus?.writeEnabled == true ? SpeedwagonTheme.success : SpeedwagonTheme.info,
                        systemImage: state.calendarStatus?.writeEnabled == true ? "square.and.pencil" : "eye"
                    )
                    Button {
                        Task { await state.syncCalendar() }
                    } label: {
                        Label("Sync calendar", systemImage: "arrow.clockwise")
                    }
                    .buttonStyle(.bordered)
                    .disabled(state.calendarStatus?.credentialsPresent == false)
                    .speedwagonPointer()
                }

                Divider().padding(.vertical, 12)

                HStack(spacing: 7) {
                    Image(systemName: "lock.fill")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                    Text("SpeedwagonAI only writes a Calendar event when you press Create event. It does not edit/delete events or schedule bots from Calendar.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .speedwagonPanel()

            CalendarNaturalLanguagePanel()
            CalendarCreateEventPanel()
            PendingActionsView()

            // Events grouped by day
            if state.calendarEvents.isEmpty {
                EmptyStateView(text: state.calendarStatus?.enabled == true
                    ? "No synced events. Run Sync calendar to load the rolling window."
                    : "Connect Google Calendar in Settings to sync events.")
            } else {
                ForEach(byDay, id: \.0) { day, events in
                    VStack(alignment: .leading, spacing: 0) {
                        GroupLabelView(day, count: events.count)
                        VStack(spacing: 0) {
                            ForEach(events) { event in
                                CalendarEventDayRow(event: event)
                                if event.id != events.last?.id {
                                    Divider().padding(.leading, 72)
                                }
                            }
                        }
                        .speedwagonPanel()
                    }
                }
            }
        }
    }
}

struct CalendarNaturalLanguagePanel: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Describe an event")
                        .font(.headline)
                    Text("The assistant turns this into a pending Calendar action for you to confirm.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                ToneChip(text: "Confirmation-first", tone: SpeedwagonTheme.warning, systemImage: "checkmark.shield")
            }

            HStack(spacing: 8) {
                TextField(
                    "Create a calendar event for June 10 at 10am to wish a happy birthday to Raj",
                    text: $state.calendarNaturalLanguageInput
                )
                .textFieldStyle(.roundedBorder)
                .onSubmit { Task { await state.runCalendarNaturalLanguageInput() } }

                Button {
                    Task {
                        if state.isCalendarNaturalLanguageVoiceActive {
                            await state.stopCalendarNaturalLanguageVoice()
                        } else {
                            await state.startCalendarNaturalLanguageVoice()
                        }
                    }
                } label: {
                    Label(
                        state.isCalendarNaturalLanguageVoiceActive ? "Stop" : "Dictate",
                        systemImage: state.isCalendarNaturalLanguageVoiceActive ? "stop.circle.fill" : "mic.circle"
                    )
                }
                .buttonStyle(.bordered)
                .disabled(state.isAssistantVoiceActive && !state.isCalendarNaturalLanguageVoiceActive)
                .help(state.isCalendarNaturalLanguageVoiceActive ? "Stop recording and prepare the calendar action" : "Record a spoken calendar request")
                .speedwagonPointer()

                Button {
                    Task { await state.runCalendarNaturalLanguageInput() }
                } label: {
                    Label("Prepare", systemImage: "wand.and.stars")
                }
                .buttonStyle(.borderedProminent)
                .tint(SpeedwagonTheme.accent(scheme))
                .disabled(state.calendarNaturalLanguageInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                .speedwagonPointer()
            }

            if let transcript = state.lastVoiceTranscript, state.isAssistantVoiceActive == false, !transcript.isEmpty {
                Text("Last voice input: \(transcript)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
        .speedwagonPanel()
    }
}

struct CalendarCreateEventPanel: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Create event")
                        .font(.headline)
                    Text("Writes one event to Google Calendar after you review the fields.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                ToneChip(
                    text: state.calendarStatus?.writeEnabled == true ? "Google write scope" : "Re-auth may be needed",
                    tone: state.calendarStatus?.writeEnabled == true ? SpeedwagonTheme.success : SpeedwagonTheme.warning,
                    systemImage: state.calendarStatus?.writeEnabled == true ? "checkmark.seal" : "key"
                )
            }

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                TextField("Title", text: $state.calendarCreateTitle)
                    .textFieldStyle(.roundedBorder)
                TextField("Location or meeting link", text: $state.calendarCreateLocation)
                    .textFieldStyle(.roundedBorder)
                TextField("Start, e.g. 2026-06-08T10:00:00-07:00", text: $state.calendarCreateStart)
                    .textFieldStyle(.roundedBorder)
                    .font(.system(.body, design: .monospaced))
                TextField("End, e.g. 2026-06-08T10:30:00-07:00", text: $state.calendarCreateEnd)
                    .textFieldStyle(.roundedBorder)
                    .font(.system(.body, design: .monospaced))
            }

            TextField("Attendees, comma-separated emails", text: $state.calendarCreateAttendees)
                .textFieldStyle(.roundedBorder)
            ZStack(alignment: .bottomTrailing) {
                TextEditor(text: $state.calendarCreateDescription)
                    .frame(minHeight: 78)
                    .padding(6)
                    .padding(.trailing, 42)
                    .scrollContentBackground(.hidden)
                    .background(SpeedwagonTheme.secondaryPanelBackground(scheme))
                    .clipShape(RoundedRectangle(cornerRadius: 7))
                    .overlay(RoundedRectangle(cornerRadius: 7).stroke(SpeedwagonTheme.softLine(scheme)))

                if state.calendarCreateDescription.isEmpty {
                    Text("Description")
                        .font(.body)
                        .foregroundStyle(SpeedwagonTheme.tertiaryText(scheme))
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 14)
                        .allowsHitTesting(false)
                }

                Button {
                    Task {
                        if state.isCalendarDescriptionVoiceActive {
                            await state.stopCalendarDescriptionVoice()
                        } else {
                            await state.startCalendarDescriptionVoice()
                        }
                    }
                } label: {
                    Image(systemName: state.isCalendarDescriptionVoiceActive ? "stop.circle.fill" : "mic.circle")
                        .font(.system(size: 18, weight: .semibold))
                        .frame(width: 30, height: 30)
                }
                .buttonStyle(.borderless)
                .foregroundStyle(state.isCalendarDescriptionVoiceActive ? SpeedwagonTheme.danger(scheme) : SpeedwagonTheme.accent(scheme))
                .background(SpeedwagonTheme.panelBackground(scheme))
                .clipShape(RoundedRectangle(cornerRadius: 7))
                .overlay(RoundedRectangle(cornerRadius: 7).stroke(SpeedwagonTheme.softLine(scheme)))
                .padding(8)
                .disabled(state.isAssistantVoiceActive && !state.isCalendarDescriptionVoiceActive)
                .help(state.isCalendarDescriptionVoiceActive ? "Stop dictating event description" : "Dictate event description")
                .speedwagonPointer()
            }

            HStack(alignment: .center, spacing: 10) {
                Toggle("Email attendee updates", isOn: $state.calendarCreateSendUpdates)
                    .toggleStyle(.checkbox)
                Spacer()
                Button {
                    Task { await state.createCalendarEvent() }
                } label: {
                    Label("Create event", systemImage: "calendar.badge.plus")
                }
                .buttonStyle(.borderedProminent)
                .tint(SpeedwagonTheme.accent(scheme))
                .disabled(
                    state.calendarStatus?.credentialsPresent != true ||
                    state.calendarCreateTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ||
                    state.calendarCreateStart.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ||
                    state.calendarCreateEnd.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                )
                .speedwagonPointer()
            }

            if state.calendarStatus?.writeEnabled != true {
                HStack(spacing: 8) {
                    Image(systemName: "info.circle")
                    Text("The first create may open Google OAuth to grant Calendar event write scope. Existing read-only tokens may need re-authorization.")
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }
        }
        .speedwagonPanel()
    }
}

struct CalendarEventDayRow: View {
    let event: CalendarEvent
    @State private var expanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button {
                withAnimation(.easeInOut(duration: 0.16)) { expanded.toggle() }
            } label: {
                HStack(alignment: .top, spacing: 12) {
                    // Time column
                    VStack(alignment: .trailing, spacing: 1) {
                        Text(shortTime(event.startAt))
                            .font(.caption.monospaced().weight(.medium))
                            .foregroundStyle(.secondary)
                        Text(shortTime(event.endAt))
                            .font(.caption.monospaced())
                            .foregroundStyle(.tertiary)
                    }
                    .frame(width: 52)

                    // Accent bar
                    RoundedRectangle(cornerRadius: 2)
                        .fill(event.meetingUrl != nil ? SpeedwagonTheme.accent(.dark) : Color.secondary.opacity(0.35))
                        .frame(width: 3)
                        .padding(.vertical, 2)

                    // Content
                    VStack(alignment: .leading, spacing: 4) {
                        Text(event.title)
                            .font(.body.weight(.medium))
                            .foregroundStyle(.primary)
                            .multilineTextAlignment(.leading)
                        if let attendees = event.attendees, !attendees.isEmpty {
                            HStack(spacing: 4) {
                                Image(systemName: "person.2")
                                    .font(.caption2)
                                Text(attendees.prefix(3).compactMap { $0.displayName ?? $0.email }.joined(separator: ", "))
                                    .font(.caption)
                            }
                            .foregroundStyle(.secondary)
                        }
                    }

                    Spacer()
                    Image(systemName: expanded ? "chevron.up" : "chevron.down")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.tertiary)
                }
                .contentShape(Rectangle())
                .padding(.vertical, 10)
            }
            .buttonStyle(.plain)
            .speedwagonPointer()

            if expanded {
                VStack(alignment: .leading, spacing: 6) {
                    if let snippet = event.descriptionSnippet, !snippet.isEmpty {
                        Text(snippet).font(.caption).foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    if let location = event.location, !location.isEmpty {
                        Label(location, systemImage: "mappin").font(.caption).foregroundStyle(.secondary)
                    }
                    if let url = event.meetingUrl, !url.isEmpty {
                        Label("Video link", systemImage: "video").font(.caption).foregroundStyle(.secondary)
                    }
                }
                .padding(.leading, 68)
                .padding(.bottom, 10)
                .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
    }

    private func shortTime(_ iso: String) -> String {
        // e.g. "2026-06-05T14:30:00" → "2:30 PM"
        guard iso.count >= 16 else { return iso.prefix(10).description }
        let parts = iso.dropFirst(11).prefix(5).split(separator: ":")
        guard parts.count == 2, let h = Int(parts[0]), let m = Int(parts[1]) else { return String(iso.prefix(10)) }
        let ap = h >= 12 ? "PM" : "AM"
        let hr = h % 12 == 0 ? 12 : h % 12
        return "\(hr):\(String(format: "%02d", m)) \(ap)"
    }
}

private extension CalendarAttendee {
    var displayLabel: String { displayName ?? email ?? "attendee" }
}

// Legacy alias for Today rail
struct CalendarPanelView: View {
    var expanded = false
    var body: some View { CalendarScreenView() }
}
struct CalendarEventList: View {
    let events: [CalendarEvent]
    var body: some View {
        VStack(spacing: 8) {
            ForEach(events) { event in
                CalendarEventDayRow(event: event)
            }
        }
    }
}

// CalendarEventRow alias — Today rail uses CalendarEventDayRow directly
struct CalendarEventRow: View {
    let event: CalendarEvent
    var body: some View { CalendarEventDayRow(event: event) }
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
            HStack {
                Text("Daily Brief")
                    .font(.title3.weight(.semibold))
                Spacer()
                Button {
                    Task { await state.refreshDailyIntelligence() }
                } label: {
                    Label(state.isRefreshingIntelligence ? "Refreshing" : "Refresh Intelligence", systemImage: "sparkles")
                }
                .buttonStyle(.bordered)
                .disabled(state.isRefreshingIntelligence || !state.isConnected)
                .speedwagonPointer()
            }

            if let brief = state.dailyBrief {
                if let synthesis = brief.synthesis {
                    DailySynthesisView(synthesis: synthesis)
                } else {
                    Text("No cached intelligence yet. Refresh Intelligence runs an explicit synthesis pass.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
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

struct DailySynthesisView: View {
    let synthesis: DailySynthesis

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(synthesis.summary)
                    .font(.body.weight(.medium))
                    .fixedSize(horizontal: false, vertical: true)
                Spacer()
                Chip(text: synthesis.provider ?? "cached")
            }

            synthesisBullets("Risks", synthesis.risks)
            synthesisBullets("Dropped Threads", synthesis.droppedThreads)
            synthesisBullets("Follow-ups", synthesis.followups)
            synthesisBullets("Recent Changes", synthesis.recentChanges)

            if let generatedAt = synthesis.generatedAt {
                Text("Generated \(generatedAt)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .speedwagonSecondaryPanel()
    }

    @ViewBuilder
    private func synthesisBullets(_ title: String, _ values: [String]) -> some View {
        if !values.isEmpty {
            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.caption.weight(.semibold))
                ForEach(values.prefix(4), id: \.self) { value in
                    Text(value)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
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

// MARK: - Commitments screen

struct CommitmentsScreenView: View {
    @EnvironmentObject private var state: AppState

    private var youOwe: [TaskItem] {
        state.commitments.filter { ($0.owner ?? "").lowercased().contains("you") || $0.owner == nil }
    }
    private var owedToYou: [TaskItem] {
        state.commitments.filter { $0.status == "waiting" }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            // Daily brief synthesis at top
            if let synthesis = state.dailyBrief?.synthesis {
                VStack(alignment: .leading, spacing: 10) {
                    HStack {
                        Text("Daily brief")
                            .font(.headline)
                        Spacer()
                        if !synthesis.droppedThreads.isEmpty {
                            ToneChip(text: "\(synthesis.droppedThreads.count) dropped thread\(synthesis.droppedThreads.count == 1 ? "" : "s")", tone: SpeedwagonTheme.warning, dot: true)
                        }
                    }
                    Text(synthesis.summary)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .speedwagonPanel()
            }

            // You owe
            VStack(alignment: .leading, spacing: 8) {
                GroupLabelView("You owe", count: youOwe.count, accent: true)
                if youOwe.isEmpty {
                    EmptyStateView(text: "No open commitments.")
                } else {
                    VStack(spacing: 0) {
                        ForEach(youOwe) { task in
                            CommitmentRow(task: task)
                            if task.id != youOwe.last?.id {
                                Divider().padding(.leading, 50)
                            }
                        }
                    }
                    .speedwagonPanel()
                }
            }

            // Owed to you
            VStack(alignment: .leading, spacing: 8) {
                GroupLabelView("Owed to you", count: owedToYou.count)
                if owedToYou.isEmpty {
                    EmptyStateView(text: "Nothing outstanding.")
                } else {
                    VStack(spacing: 0) {
                        ForEach(owedToYou) { task in
                            CommitmentRow(task: task)
                            if task.id != owedToYou.last?.id {
                                Divider().padding(.leading, 50)
                            }
                        }
                    }
                    .speedwagonPanel()
                }
            }
        }
    }
}

struct CommitmentRow: View {
    @EnvironmentObject private var state: AppState
    let task: TaskItem

    var body: some View {
        HStack(spacing: 11) {
            // Avatar circle with initials
            ZStack {
                Circle()
                    .fill(SpeedwagonTheme.context.opacity(0.20))
                Text(initials)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(SpeedwagonTheme.context)
            }
            .frame(width: 30, height: 30)

            VStack(alignment: .leading, spacing: 4) {
                Text(task.text)
                    .font(.body.weight(.medium))
                HStack(spacing: 7) {
                    if let owedTo = task.owedTo {
                        ToneChip(text: "Owed to \(owedTo)", tone: SpeedwagonTheme.context)
                    }
                    if let project = task.project {
                        ToneChip(text: project, tone: SpeedwagonTheme.info, systemImage: "cube")
                    }
                    if let due = task.dueDate {
                        Text(due).font(.caption.monospaced())
                            .foregroundStyle(task.isOverdue == true ? SpeedwagonTheme.danger : .secondary)
                    }
                }
            }
            Spacer()
        }
        .padding(.vertical, 10)
        .padding(.horizontal, 14)
    }

    private var initials: String {
        let name = task.owedTo ?? task.owner ?? "?"
        return name.split(separator: " ").prefix(2).compactMap { $0.first }.map(String.init).joined()
    }
}

// Legacy alias for Today rail
struct CommitmentsView: View {
    var body: some View { CommitmentsScreenView() }
}

// MARK: - Meetings screen

struct MeetingsScreenView: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme
    @State private var searchText = ""

    private var filteredMeetings: [MeetingItem] {
        let text = searchText.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !text.isEmpty else { return state.meetings }
        return state.meetings.filter { meeting in
            meeting.title.lowercased().contains(text)
                || String(meeting.id).contains(text)
                || (meeting.summary ?? "").lowercased().contains(text)
                || (meeting.startedAt ?? "").lowercased().contains(text)
        }
    }

    private var groupedMeetings: [(key: String, label: String, meetings: [MeetingItem])] {
        let groups = Dictionary(grouping: filteredMeetings) { meeting in
            String((meeting.startedAt ?? "Unknown").prefix(7))
        }
        return groups.keys.sorted(by: >).map { key in
            (key, monthLabel(for: key), groups[key] ?? [])
        }
    }

    private var unprocessedCount: Int {
        filteredMeetings.filter { $0.notePath == nil }.count
    }

    var body: some View {
        ZStack {
            Color.clear
                .contentShape(Rectangle())
                .onTapGesture {
                    state.clearMeetingSelection()
                }

            HStack(alignment: .top, spacing: 18) {
                VStack(alignment: .leading, spacing: 0) {
                    HStack(spacing: 8) {
                        Image(systemName: "magnifyingglass")
                            .foregroundStyle(SpeedwagonTheme.tertiaryText(scheme))
                        TextField("Filter meetings", text: $searchText)
                            .textFieldStyle(.plain)
                    }
                    .padding(10)
                    .background(SpeedwagonTheme.secondaryPanelBackground(scheme))
                    .clipShape(RoundedRectangle(cornerRadius: 7))
                    .overlay(RoundedRectangle(cornerRadius: 7).stroke(SpeedwagonTheme.softLine(scheme)))
                    .padding([.horizontal, .top], 10)

                    if filteredMeetings.isEmpty {
                        EmptyStateView(text: state.isConnected ? "No meetings match this filter." : "Connect backend to load meetings.")
                            .padding(10)
                            .frame(maxHeight: .infinity, alignment: .top)
                    } else {
                        ScrollView {
                            LazyVStack(alignment: .leading, spacing: 0, pinnedViews: [.sectionHeaders]) {
                                ForEach(groupedMeetings, id: \.key) { group in
                                    Section {
                                        ForEach(group.meetings) { meeting in
                                            MeetingListRow(meeting: meeting)
                                            if meeting.id != group.meetings.last?.id {
                                                Divider().padding(.horizontal, 8)
                                            }
                                        }
                                    } header: {
                                        MeetingMonthHeader(label: group.label, count: group.meetings.count)
                                    }
                                }
                            }
                        }
                    }

                    HStack {
                        Text("\(filteredMeetings.count) meetings")
                        Text("·")
                        Text("\(unprocessedCount) unprocessed")
                        Spacer()
                    }
                    .font(.caption.monospaced())
                    .foregroundStyle(SpeedwagonTheme.secondaryText(scheme))
                    .padding(.horizontal, 12)
                    .padding(.vertical, 9)
                    .background(SpeedwagonTheme.secondaryPanelBackground(scheme))
                    .overlay(alignment: .top) {
                        Rectangle().fill(SpeedwagonTheme.softLine(scheme)).frame(height: 1)
                    }
                }
                .frame(minWidth: 266, idealWidth: 290, maxWidth: 320)
                .frame(minHeight: 420, maxHeight: .infinity)
                .background(SpeedwagonTheme.panelBackground(scheme))
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(SpeedwagonTheme.line(scheme)))

                ScrollView {
                    MeetingDetailPanel()
                        .padding(.bottom, 2)
                }
                .frame(minHeight: 420, maxHeight: .infinity)
                    .frame(maxWidth: .infinity, alignment: .topLeading)
            }
        }
        .frame(maxHeight: .infinity, alignment: .top)
    }

    private func monthLabel(for key: String) -> String {
        guard key.count == 7 else { return "Unknown date" }
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM"
        guard let date = formatter.date(from: key) else { return key }
        let output = DateFormatter()
        output.dateFormat = "MMMM yyyy"
        return output.string(from: date)
    }
}

struct MeetingMonthHeader: View {
    @Environment(\.colorScheme) private var scheme
    let label: String
    let count: Int

    var body: some View {
        HStack {
            Text(label.uppercased())
                .font(.caption2.weight(.semibold))
                .tracking(0.9)
                .foregroundStyle(SpeedwagonTheme.tertiaryText(scheme))
            Spacer()
            Text("\(count)")
                .font(.caption2.monospaced())
                .foregroundStyle(SpeedwagonTheme.tertiaryText(scheme))
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 7)
        .background(SpeedwagonTheme.panelBackground(scheme))
        .overlay(alignment: .bottom) {
            Rectangle().fill(SpeedwagonTheme.softLine(scheme)).frame(height: 1)
        }
    }
}

struct MeetingListRow: View {
    @EnvironmentObject private var state: AppState
    let meeting: MeetingItem

    var body: some View {
        let active = state.selectedMeetingDetail?.meeting.id == meeting.id
        Button {
            Task { await state.loadMeeting(meeting) }
        } label: {
            VStack(alignment: .leading, spacing: 5) {
                HStack(alignment: .firstTextBaseline) {
                    Text(meeting.title)
                        .font(.callout.weight(.semibold))
                        .lineLimit(2)
                        .foregroundStyle(.primary)
                    Spacer()
                    if meeting.sourceType == "meeting_bot" {
                        ToneChip(text: "bot", tone: SpeedwagonTheme.info, systemImage: "cube")
                    }
                }
                Text("\(String((meeting.startedAt ?? "").prefix(10))) · #\(meeting.id)")
                    .font(.caption.monospaced())
                    .foregroundStyle(.secondary)
                HStack(spacing: 5) {
                    ToneChip(
                        text: meeting.transcriptPath == nil ? "no transcript" : "transcript",
                        tone: meeting.transcriptPath == nil ? nil : SpeedwagonTheme.success,
                        dot: true
                    )
                    ToneChip(
                        text: meeting.notePath == nil ? "unprocessed" : "processed",
                        tone: meeting.notePath == nil ? SpeedwagonTheme.warning : SpeedwagonTheme.success,
                        dot: true
                    )
                }
            }
            .padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(active ? SpeedwagonTheme.accentSoft(.dark) : Color.clear)
        }
        .buttonStyle(.plain)
        .speedwagonPointer()
    }
}

struct MeetingDetailPanel: View {
    @EnvironmentObject private var state: AppState
    @State private var showTranscript = false

    var body: some View {
        if let detail = state.selectedMeetingDetail {
            let processed = detail.meeting.notePath != nil
            VStack(alignment: .leading, spacing: 16) {
                // Header
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(detail.meeting.title)
                            .font(.title3.weight(.semibold))
                        HStack(spacing: 8) {
                            Text("\(String((detail.meeting.startedAt ?? "").prefix(10))) · #\(detail.meeting.id)")
                                .font(.caption.monospaced())
                                .foregroundStyle(.secondary)
                            ToneChip(
                                text: processed ? "Processed" : "Needs processing",
                                tone: processed ? SpeedwagonTheme.success : SpeedwagonTheme.warning,
                                dot: true
                            )
                        }
                    }
                    Spacer()
                    Button {
                        Task { await state.processMeeting(detail.meeting) }
                    } label: {
                        Label("Process meeting", systemImage: "bolt.fill")
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(SpeedwagonTheme.accent(.dark))
                    .speedwagonPointer()
                }

                if !processed {
                    // Unprocessed state
                    VStack(alignment: .center, spacing: 14) {
                        ToneChip(text: "Transcript ready · not processed", tone: SpeedwagonTheme.warning, dot: true)
                        Text("Processing extracts tasks, decisions, commitments, relationships, and follow-up suggestions from this transcript.")
                            .font(.callout)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                        Button {
                            Task { await state.processMeeting(detail.meeting) }
                        } label: {
                            Label("Process meeting", systemImage: "bolt.fill")
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(SpeedwagonTheme.accent(.dark))
                    }
                    .frame(maxWidth: .infinity)
                    .speedwagonPanel()
                } else {
                    // Summary
                    VStack(alignment: .leading, spacing: 10) {
                        Text(detail.meeting.summary ?? "No summary yet.")
                            .font(.callout)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .speedwagonPanel()

                    // Decisions + Open Questions / Action Items + Commitments
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 14) {
                        MeetingSection(title: "Decisions", icon: "checkmark.circle.fill", iconColor: SpeedwagonTheme.accent(.dark), items: detail.decisions.map { $0.displayText })
                        MeetingSection(title: "Open questions", icon: "questionmark.circle", iconColor: SpeedwagonTheme.warning, items: detail.openQuestions.map { $0.displayText })
                        MeetingSection(title: "Action items", icon: "square.and.pencil", iconColor: SpeedwagonTheme.info, items: detail.actionItems.map { i in "\(i.displayText)\(i.owner.map { " · \($0)" } ?? "")\(i.deadline.map { " · \($0)" } ?? "")" })
                        MeetingSection(title: "Commitments", icon: "person.2.fill", iconColor: SpeedwagonTheme.context, items: detail.commitments.map { $0.displayText })
                    }
                }

                // Collapsible transcript
                Button {
                    withAnimation(.easeInOut(duration: 0.16)) { showTranscript.toggle() }
                } label: {
                    HStack {
                        Image(systemName: showTranscript ? "chevron.down" : "chevron.right")
                            .font(.caption.weight(.semibold))
                        Text("Transcript")
                            .font(.callout.weight(.medium))
                        Spacer()
                        Text(detail.transcript?.isEmpty == false ? "available" : "none")
                            .font(.caption.monospaced())
                            .foregroundStyle(.secondary)
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .speedwagonPointer()
                .padding(12)
                .background(SpeedwagonTheme.secondaryPanelBackground(.dark))
                .clipShape(RoundedRectangle(cornerRadius: 6))

                if showTranscript, let transcript = detail.transcript, !transcript.isEmpty {
                    ScrollView {
                        Text(transcript)
                            .font(.system(.caption, design: .monospaced))
                            .foregroundStyle(.secondary)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(12)
                    }
                    .frame(maxHeight: 220)
                    .background(SpeedwagonTheme.secondaryPanelBackground(.dark))
                    .clipShape(RoundedRectangle(cornerRadius: 6))
                    .transition(.opacity.combined(with: .move(edge: .top)))
                }
            }
            .speedwagonPanel()
        } else {
            EmptyStateView(text: state.meetings.isEmpty ? "No meetings yet. Record a meeting to get started." : "Select a meeting to review its summary, decisions, tasks, and notes.")
                .speedwagonPanel()
        }
    }
}

struct MeetingSection: View {
    let title: String
    let icon: String
    let iconColor: Color
    let items: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(title, systemImage: icon)
                .font(.caption.weight(.semibold))
                .foregroundStyle(iconColor)
            if items.isEmpty {
                Text("None captured.").font(.caption).foregroundStyle(.secondary)
            } else {
                VStack(alignment: .leading, spacing: 5) {
                    ForEach(Array(items.prefix(6).enumerated()), id: \.offset) { _, item in
                        HStack(alignment: .top, spacing: 6) {
                            RoundedRectangle(cornerRadius: 1).fill(iconColor.opacity(0.5))
                                .frame(width: 3, height: 14).padding(.top, 2)
                            Text(item).font(.caption).foregroundStyle(.primary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
            }
        }
        .speedwagonPanel()
    }
}

// Keep for any lingering references
struct MeetingsView: View { var body: some View { MeetingsScreenView() } }
struct MeetingDetailView: View { var body: some View { MeetingDetailPanel() } }
struct MeetingItemsBlock: View {
    let title: String; let items: [MeetingTextItem]
    var body: some View {
        MeetingSection(title: title, icon: "list.bullet", iconColor: SpeedwagonTheme.info, items: items.map { $0.displayText })
    }
}

// MARK: - About beta

struct AboutBetaView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 12) {
                    ZStack {
                        RoundedRectangle(cornerRadius: 9)
                            .fill(SpeedwagonTheme.accent(.dark))
                            .frame(width: 40, height: 40)
                        Image(systemName: "bolt.fill")
                            .font(.system(size: 20, weight: .semibold))
                            .foregroundStyle(Color.black.opacity(0.75))
                    }
                    VStack(alignment: .leading, spacing: 2) {
                        Text("SpeedwagonAI")
                            .font(.title3.weight(.semibold))
                        Text("Private beta · local-first")
                            .font(.caption.monospaced())
                            .foregroundStyle(.secondary)
                    }
                }
                Text("A local-first follow-through assistant. It captures meetings, tasks, and commitments, then surfaces what needs attention — always asking before it acts.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .speedwagonPanel()

            GroupLabelView("On the roadmap")
            VStack(spacing: 0) {
                ForEach([
                    ("cube", "Meeting bot", "Recall.ai cloud capture with consent — in beta"),
                    ("camera", "Window & region screenshots", "Targeted capture beyond full screen"),
                    ("calendar", "Richer meeting prep", "Tie calendar context into pre-meeting briefs"),
                    ("shield", "Signed build & notifications", "Resolves UNErrorDomain on unsigned builds"),
                ], id: \.1) { icon, title, desc in
                    HStack(alignment: .top, spacing: 11) {
                        Image(systemName: icon)
                            .foregroundStyle(.secondary)
                            .frame(width: 18)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(title).font(.callout.weight(.medium))
                            Text(desc).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    .padding(.vertical, 9)
                    .padding(.horizontal, 13)
                    if title != "Signed build & notifications" { Divider().padding(.leading, 42) }
                }
            }
            .speedwagonPanel()
        }
    }
}

// Legacy aliases kept for assistant dashboard
struct PlannedCapabilitiesView: View { var body: some View { AboutBetaView() } }
struct BrainCostPanelView: View {
    @EnvironmentObject private var state: AppState
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            InfoRow(label: "Command parser", value: state.settings?.commandModel ?? "—")
            InfoRow(label: "Web search", value: state.settings?.webSearchEnabled == true ? "Enabled" : "Disabled")
        }.speedwagonSecondaryPanel()
    }
}
struct PlannedTile: View {
    let title: String; let subtitle: String
    var body: some View { EmptyView() }
}

struct InfoRow: View {
    let label: String
    let value: String

    var body: some View {
        HStack {
            Text(label).foregroundStyle(.secondary)
            Spacer()
            Text(value).font(.caption.weight(.medium)).multilineTextAlignment(.trailing)
        }
        .font(.caption)
    }
}

// MARK: - Settings screen

enum SettingsSection: String, CaseIterable, Identifiable {
    case setup = "Setup & readiness"
    case secrets = "Secrets"
    case permissions = "Permissions"
    case privacy = "Privacy & data"
    case logs = "Logs & debug"
    var id: String { rawValue }
    var systemImage: String {
        switch self {
        case .setup: return "checkmark.circle"
        case .secrets: return "lock"
        case .permissions: return "shield"
        case .privacy: return "folder"
        case .logs: return "doc.text"
        }
    }
}

struct SettingsScreenView: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme
    @State private var section: SettingsSection = .setup

    var body: some View {
        HStack(alignment: .top, spacing: 22) {
            // Sub-nav
            VStack(alignment: .leading, spacing: 2) {
                ForEach(SettingsSection.allCases) { s in
                    Button {
                        section = s
                    } label: {
                        HStack(spacing: 9) {
                            Image(systemName: s.systemImage)
                                .font(.system(size: 14))
                                .foregroundStyle(section == s ? SpeedwagonTheme.accent(scheme) : SpeedwagonTheme.tertiaryText(scheme))
                                .frame(width: 18)
                            Text(s.rawValue)
                                .font(section == s ? .callout.weight(.semibold) : .callout)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 8)
                        .background(section == s ? SpeedwagonTheme.accentSoft(scheme) : Color.clear)
                        .clipShape(RoundedRectangle(cornerRadius: 6))
                        .overlay(
                            HStack {
                                Rectangle().fill(section == s ? SpeedwagonTheme.accent(scheme) : .clear).frame(width: 2)
                                Spacer()
                            }.clipShape(RoundedRectangle(cornerRadius: 6))
                        )
                    }
                    .buttonStyle(.plain)
                    .speedwagonPointer()
                }
            }
            .frame(width: 200)

            // Content
            VStack(alignment: .leading, spacing: 16) {
                switch section {
                case .setup: SettingsSetupSection()
                case .secrets: SettingsSecretsSection()
                case .permissions: SettingsPermissionsSection()
                case .privacy: SettingsPrivacySection()
                case .logs: SettingsLogsSection()
                }
            }
            .frame(maxWidth: .infinity, alignment: .topLeading)
        }
    }
}

struct SettingsSetupSection: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            // Readiness panel
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("First-run readiness")
                        .font(.headline)
                    Spacer()
                    Button {
                        Task { await state.refreshLocalBetaDiagnostics() }
                    } label: {
                        Label("Check readiness", systemImage: "arrow.clockwise")
                    }
                    .buttonStyle(.bordered)
                    .speedwagonPointer()
                }
                SettingsRow(label: "Python 3.11 runtime", value: state.pythonVersionStatus,
                            ok: !state.pythonVersionStatus.contains("not found"))
                SettingsRow(label: "Local API token present", value: state.localTokenPresence,
                            ok: state.localTokenPresence == "present")
                SettingsRow(label: "OpenAI API key in Keychain", value: state.openAIKeyPresence,
                            ok: state.openAIKeyPresence == "present")
                SettingsRow(label: "App bundle (signed)", value: supportsNativeNotifications() ? "bundled" : "swift run · unsigned",
                            ok: supportsNativeNotifications())
                HStack(spacing: 8) {
                    Button {
                        Task { await state.copyLocalBetaDiagnosticsReport() }
                    } label: {
                        Label("Copy diagnostics", systemImage: "doc.on.doc")
                    }
                    .buttonStyle(.bordered)
                    .speedwagonPointer()
                }
                if !state.localBetaDiagnosticsReport.isEmpty {
                    Text(state.localBetaDiagnosticsReport)
                        .font(.caption.monospaced())
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(10)
                        .background(SpeedwagonTheme.secondaryPanelBackground(scheme))
                        .clipShape(RoundedRectangle(cornerRadius: 6))
                }
            }
            .speedwagonPanel()

            // Backend
            VStack(alignment: .leading, spacing: 12) {
                Text("Local backend")
                    .font(.headline)
                SettingsRow(label: "State", value: state.backendState.rawValue,
                            ok: state.backendState.rawValue == "running")
                SettingsRow(label: "Address", value: "http://127.0.0.1:8765", mono: true)
                if !state.backendLogPath.isEmpty {
                    SettingsRow(label: "Log path", value: state.backendLogPath, mono: true)
                }
                TextField("Repo root", text: $state.repoRootInput)
                    .textFieldStyle(.roundedBorder)
                HStack(spacing: 8) {
                    Button {
                        Task { await state.startBackendIfNeeded() }
                    } label: {
                        Label("Start backend", systemImage: "play.circle")
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(SpeedwagonTheme.accent(scheme))
                    .speedwagonPointer()
                    Button {
                        state.stopManagedBackend()
                    } label: {
                        Label("Stop managed backend", systemImage: "stop.circle")
                    }
                    .buttonStyle(.bordered)
                    .speedwagonPointer()
                }
            }
            .speedwagonPanel()
        }
    }
}

struct SettingsSecretsSection: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            // Keychain explanation
            HStack(alignment: .top, spacing: 9) {
                Image(systemName: "lock.fill")
                    .foregroundStyle(SpeedwagonTheme.accent(scheme))
                Text("SpeedwagonAI stores keys in your Mac Keychain. When macOS asks for a password to unlock it, that's your **Mac login password** — not an account with us.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(12)
            .background(SpeedwagonTheme.accentSoft(scheme))
            .clipShape(RoundedRectangle(cornerRadius: 6))

            VStack(alignment: .leading, spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("OPENAI API KEY".uppercased())
                        .font(.caption2.weight(.semibold))
                        .tracking(0.7)
                        .foregroundStyle(.secondary)
                    SecureField("sk-…", text: $state.openAIAPIKeyInput)
                        .textFieldStyle(.roundedBorder)
                    Text("Used only for LLM-backed features: synthesis, extraction, drafts, assistant fallback.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                VStack(alignment: .leading, spacing: 4) {
                    Text("GOOGLE (OPTIONAL)".uppercased())
                        .font(.caption2.weight(.semibold))
                        .tracking(0.7)
                        .foregroundStyle(.secondary)
                    Text(state.settings?.gmailCredentialsPresent == true ? "Credentials file present" : "Not connected — set up via docs")
                        .font(.caption).foregroundStyle(.secondary)
                }
                VStack(alignment: .leading, spacing: 4) {
                    Text("RECALL.AI (OPTIONAL)".uppercased())
                        .font(.caption2.weight(.semibold))
                        .tracking(0.7)
                        .foregroundStyle(.secondary)
                    Text(state.settings?.botProvider.flatMap { $0.isEmpty ? nil : $0 } ?? "Not connected — meeting bot")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Button {
                    Task { await state.saveCoreSecrets() }
                } label: {
                    Label("Save secrets to Keychain", systemImage: "lock.fill")
                }
                .buttonStyle(.borderedProminent)
                .tint(SpeedwagonTheme.accent(scheme))
                .speedwagonPointer()
            }
            .speedwagonPanel()
        }
    }
}

struct SettingsPermissionsSection: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 0) {
                SettingsRow(label: "Microphone", value: "Grant in System Settings if needed", ok: true)
                Divider()
                SettingsRow(label: "Screen recording (system audio)", value: "Grant in System Settings if needed", ok: true)
                Divider()
                SettingsRow(label: "Notifications", value: state.notificationPermissionStatus)
            }
            .speedwagonPanel()

            VStack(alignment: .leading, spacing: 10) {
                Text("What leaves your device")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                ForEach([
                    ("OpenAI", "LLM features only — transcripts & prompts for synthesis/extraction", state.settings?.openaiKeyPresent == true),
                    ("Google", "Gmail draft creation + Calendar sync/event creation — optional", state.settings?.gmailCredentialsPresent == true),
                    ("Recall.ai", "Meeting-bot audio, cloud-processed, consent required — optional", !(state.settings?.botProvider ?? "").isEmpty),
                ], id: \.0) { service, desc, configured in
                    HStack(alignment: .top, spacing: 10) {
                        Circle()
                            .fill(configured ? SpeedwagonTheme.success : SpeedwagonTheme.tertiaryText(.dark))
                            .frame(width: 7, height: 7)
                            .padding(.top, 5)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(service).font(.callout.weight(.medium))
                            Text(desc).font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                        ToneChip(text: configured ? "Configured" : "Not configured", tone: configured ? SpeedwagonTheme.success : nil, dot: true)
                    }
                    .padding(.vertical, 8)
                    if service != "Recall.ai" { Divider() }
                }
            }
            .speedwagonPanel()
        }
    }
}

struct SettingsPrivacySection: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            if let privacy = state.privacyStatus {
                VStack(alignment: .leading, spacing: 12) {
                    Text("Local data")
                        .font(.headline)
                    HStack(spacing: 22) {
                        ForEach([
                            ("Meetings", privacy.counts["meetings"] ?? 0),
                            ("Tasks", privacy.counts["tasks"] ?? 0),
                            ("Suggestions", privacy.counts["suggestions"] ?? 0),
                            ("Drafts", privacy.counts["drafts"] ?? 0),
                            ("Contexts", privacy.counts["contexts"] ?? 0),
                        ], id: \.0) { label, count in
                            VStack(alignment: .leading, spacing: 2) {
                                Text("\(count)").font(.title3.weight(.semibold).monospaced())
                                Text(label).font(.caption2).foregroundStyle(.secondary)
                            }
                        }
                    }
                    Divider()
                    if let note = privacy.pathVisibilityNote {
                        Text(note).font(.caption).foregroundStyle(.secondary)
                    }
                    HStack(spacing: 8) {
                        Button {
                            Task { await state.exportLocalData() }
                        } label: {
                            Label("Export local data (.zip)", systemImage: "archivebox")
                        }
                        .buttonStyle(.bordered)
                        .speedwagonPointer()
                    }
                }
                .speedwagonPanel()
            }

            // Wipe — isolated danger zone
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 8) {
                    Image(systemName: "trash").foregroundStyle(SpeedwagonTheme.danger)
                    Text("Wipe local data")
                        .font(.headline)
                        .foregroundStyle(SpeedwagonTheme.danger)
                }
                Text("This permanently deletes all local meetings, tasks, suggestions, drafts, and context. It cannot be undone. Type **wipe my local data** to confirm.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                TextField("wipe my local data", text: $state.wipeConfirmationInput)
                    .textFieldStyle(.roundedBorder)
                    .frame(maxWidth: 320)
                Button(role: .destructive) {
                    Task { await state.wipeLocalData() }
                } label: {
                    Label("Wipe local data", systemImage: "trash")
                }
                .disabled(state.wipeConfirmationInput != "wipe my local data")
                .speedwagonPointer()
            }
            .padding(14)
            .background(SpeedwagonTheme.danger.opacity(0.06))
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(SpeedwagonTheme.danger.opacity(0.30)))
        }
    }
}

struct SettingsLogsSection: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text("Logs")
                    .font(.headline)
                Spacer()
                ToneChip(text: "Advanced", tone: SpeedwagonTheme.info)
                Button {
                    Task { await state.copyLocalBetaDiagnosticsReport() }
                } label: {
                    Label("Copy diagnostics", systemImage: "doc.on.doc")
                }
                .buttonStyle(.bordered)
                .speedwagonPointer()
            }
            ScrollView {
                let logText = [
                    state.systemLogs?.logTail,
                    state.systemLogs?.backendLogTail,
                ].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: "\n")
                Text(logText.isEmpty ? "No log entries yet." : logText)
                    .font(.caption.monospaced())
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(12)
            }
            .frame(maxHeight: 400)
            .background(SpeedwagonTheme.secondaryPanelBackground(scheme))
            .clipShape(RoundedRectangle(cornerRadius: 6))
        }
        .speedwagonPanel()
    }
}

struct SettingsRow: View {
    let label: String
    var value: String? = nil
    var ok: Bool? = nil
    var mono: Bool = false

    var body: some View {
        HStack(spacing: 10) {
            Text(label).font(.callout)
            Spacer()
            if let value {
                Text(value)
                    .font(mono ? .caption.monospaced() : .caption)
                    .foregroundStyle(.secondary)
            }
            if let ok {
                ToneChip(text: ok ? "Ready" : "Action needed", tone: ok ? SpeedwagonTheme.success : SpeedwagonTheme.warning, dot: true)
            }
        }
        .padding(.vertical, 10)
    }
}

// Legacy alias
struct LocalBetaSettingsView: View { var body: some View { SettingsScreenView() } }

struct DisclosureLine: View {
    let title: String
    let text: String

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(.caption.weight(.semibold))
            Text(text)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

// MARK: - Tasks screen

struct TasksScreenView: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme
    @State private var filter = "all"

    private let filters = [("all", "All"), ("open", "Open"), ("waiting", "Waiting"), ("done", "Done")]

    private let groups: [(key: String, label: String, tone: Color?)] = [
        ("overdue", "Overdue", SpeedwagonTheme.danger),
        ("today", "Today", SpeedwagonTheme.warning),
        ("upcoming", "Upcoming", nil),
        ("unscheduled", "Unscheduled", nil),
        ("waiting", "Waiting / Uncertain", SpeedwagonTheme.snoozed),
        ("done", "Done", SpeedwagonTheme.success),
    ]

    private func tasksFor(_ key: String) -> [TaskItem] {
        let today = Date()
        let cal = Calendar.current
        switch key {
        case "overdue":
            return state.tasks.filter { t in
                guard t.status == "open", let due = t.dueDate, let d = iso(due) else { return false }
                return d < cal.startOfDay(for: today)
            }
        case "today":
            return state.tasks.filter { t in
                guard t.status == "open", let due = t.dueDate, let d = iso(due) else { return false }
                return cal.isDateInToday(d)
            }
        case "upcoming":
            return state.tasks.filter { t in
                guard t.status == "open", let due = t.dueDate, let d = iso(due) else { return false }
                return d > today && !cal.isDateInToday(d)
            }
        case "unscheduled":
            return state.tasks.filter { $0.status == "open" && $0.dueDate == nil }
        case "waiting":
            return state.tasks.filter { $0.status == "waiting" || $0.status == "uncertain" || $0.status == "snoozed" }
        case "done":
            return state.tasks.filter { $0.status == "done" }
        default:
            return []
        }
    }

    private func visibleGroup(_ key: String) -> Bool {
        switch filter {
        case "open": return ["overdue", "today", "upcoming", "unscheduled"].contains(key)
        case "waiting": return key == "waiting"
        case "done": return key == "done"
        default: return true
        }
    }

    private func iso(_ s: String) -> Date? {
        let fmt = ISO8601DateFormatter()
        fmt.formatOptions = [.withFullDate]
        return fmt.date(from: s)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            // Filter pills
            HStack(spacing: 8) {
                HStack(spacing: 2) {
                    ForEach(filters, id: \.0) { key, label in
                        Button(label) { filter = key }
                            .buttonStyle(.plain)
                            .font(filter == key ? .callout.weight(.semibold) : .callout)
                            .foregroundStyle(filter == key ? SpeedwagonTheme.primaryText(scheme) : SpeedwagonTheme.tertiaryText(scheme))
                            .padding(.horizontal, 11)
                            .padding(.vertical, 5)
                            .background(filter == key ? SpeedwagonTheme.elevatedBackground(scheme) : Color.clear)
                            .clipShape(RoundedRectangle(cornerRadius: 6))
                            .speedwagonPointer()
                    }
                }
                .padding(3)
                .background(SpeedwagonTheme.secondaryPanelBackground(scheme))
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(SpeedwagonTheme.softLine(scheme)))
                Spacer()
            }

            LazyVStack(alignment: .leading, spacing: 16) {
                ForEach(groups, id: \.key) { group in
                    if visibleGroup(group.key) {
                        let items = tasksFor(group.key)
                        if !items.isEmpty {
                            VStack(alignment: .leading, spacing: 8) {
                                HStack {
                                    GroupLabelView(group.label, count: items.count, accent: group.tone == SpeedwagonTheme.danger)
                                    Spacer()
                                    if group.key == "done" {
                                        Button {
                                            Task { await state.clearDoneTasks() }
                                        } label: {
                                            Label("Clear done", systemImage: "archivebox")
                                        }
                                        .buttonStyle(.bordered)
                                        .controlSize(.small)
                                        .speedwagonPointer()
                                    }
                                }
                                LazyVStack(spacing: 0) {
                                    ForEach(items) { task in
                                        TaskRow(
                                            task: task,
                                            highlighted: state.highlightedTaskIds.contains(task.id),
                                            onComplete: { t in Task { await state.complete(t) } },
                                            onReopen: { t in Task { await state.reopen(t) } }
                                        )
                                        if task.id != items.last?.id {
                                            Divider().padding(.leading, 12)
                                        }
                                    }
                                }
                                .speedwagonPanel()
                            }
                        }
                    }
                }
            }

            if state.tasks.isEmpty {
                EmptyStateView(text: state.isConnected ? "No tasks yet. Add one manually or process a meeting." : "Connect backend to load tasks.")
            }
        }
    }
}

// Legacy alias kept for palette/compact usage
struct TaskInboxView: View {
    var body: some View { TasksScreenView() }
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

                if let context = response.result?.context {
                    ContextReviewButton(context: context)
                }
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

// MARK: - Suggestions screen

struct SuggestionsScreenView: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme
    @State private var filter: SuggestionFilter = .active

    private var visibleSuggestions: [SuggestionItem] {
        state.suggestions.filter { filter.contains($0) }
    }

    var body: some View {
        ZStack {
            Color.clear
                .contentShape(Rectangle())
                .onTapGesture {
                    state.clearSuggestionSelection()
                }

            HStack(alignment: .top, spacing: 20) {
                VStack(alignment: .leading, spacing: 14) {
                    HStack(alignment: .center, spacing: 8) {
                        HStack(spacing: 2) {
                            ForEach(SuggestionFilter.allCases) { f in
                                Button(f.title) { filter = f }
                                    .buttonStyle(.plain)
                                    .font(filter == f ? .callout.weight(.semibold) : .callout)
                                    .foregroundStyle(filter == f ? SpeedwagonTheme.primaryText(scheme) : SpeedwagonTheme.secondaryText(scheme))
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 5)
                                    .background(filter == f ? SpeedwagonTheme.elevatedBackground(scheme) : Color.clear)
                                    .clipShape(RoundedRectangle(cornerRadius: 6))
                                    .speedwagonPointer()
                            }
                        }
                        .padding(3)
                        .background(SpeedwagonTheme.secondaryPanelBackground(scheme))
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                        .overlay(RoundedRectangle(cornerRadius: 8).stroke(SpeedwagonTheme.softLine(scheme)))

                        Spacer()

                        if filter == .reviewed && !visibleSuggestions.isEmpty {
                            Button {
                                Task { await state.clearReviewedSuggestions() }
                            } label: {
                                Label("Clear reviewed", systemImage: "archivebox")
                            }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                            .speedwagonPointer()
                        }
                    }

                    ScrollView {
                        ZStack(alignment: .top) {
                            Color.clear
                                .contentShape(Rectangle())
                                .onTapGesture {
                                    state.clearSuggestionSelection()
                                }

                            if visibleSuggestions.isEmpty {
                                VStack(spacing: 8) {
                                    EmptyStateView(text: state.isConnected ? filter.emptyText : "Connect backend to load suggestions.")
                                    if state.isConnected && state.suggestions.isEmpty {
                                        Text("Suggestions are generated when meetings are processed. Process a meeting to see follow-up suggestions here.")
                                            .font(.caption)
                                            .foregroundStyle(SpeedwagonTheme.tertiaryText(scheme))
                                            .multilineTextAlignment(.center)
                                            .padding(.horizontal, 20)
                                    }
                                }
                                .padding(.top, 8)
                            } else {
                                LazyVStack(spacing: 13) {
                                    ForEach(visibleSuggestions) { suggestion in
                                        SuggestionCard(suggestion: suggestion)
                                    }
                                }
                                .padding(.bottom, 8)
                            }
                        }
                        .frame(maxWidth: .infinity, minHeight: 420, alignment: .top)
                    }

                    HStack(spacing: 6) {
                        Text("\(visibleSuggestions.count) \(filter.footerLabel)")
                        Text("·")
                        Text("\(state.suggestions.filter { $0.status == "open" }.count) active")
                        Text("·")
                        Text("\(state.suggestions.filter { ["accepted", "dismissed", "retired"].contains($0.status) }.count) reviewed")
                        Spacer()
                    }
                    .font(.caption.monospaced())
                    .foregroundStyle(SpeedwagonTheme.secondaryText(scheme))
                    .padding(.horizontal, 4)
                }
                .frame(maxWidth: .infinity, alignment: .topLeading)
                .frame(minHeight: 420, maxHeight: .infinity)

                ScrollView {
                    SuggestionReviewSidePanel()
                        .padding(.bottom, 2)
                }
                .frame(width: 400, alignment: .top)
                .frame(minHeight: 420, maxHeight: .infinity, alignment: .top)
            }
        }
        .frame(maxHeight: .infinity, alignment: .top)
        .onChange(of: state.highlightedSuggestionId) { _, id in
            if let id, let suggestion = state.suggestions.first(where: { $0.id == id }) {
                filter = .bucket(for: suggestion)
            }
        }
    }
}

// Legacy alias for Today compact usage
struct SuggestionsPanelView: View {
    var compact = false
    var body: some View { SuggestionsScreenView() }
}

enum SuggestionFilter: String, CaseIterable, Identifiable {
    case active
    case snoozed
    case reviewed

    var id: String { rawValue }

    var title: String {
        switch self {
        case .active: return "Active"
        case .snoozed: return "Snoozed"
        case .reviewed: return "Reviewed / retired"
        }
    }

    var footerLabel: String {
        switch self {
        case .active: return "active"
        case .snoozed: return "snoozed"
        case .reviewed: return "reviewed"
        }
    }

    var emptyText: String {
        switch self {
        case .active: return "No active suggestions right now."
        case .snoozed: return "No snoozed suggestions."
        case .reviewed: return "No reviewed or retired suggestions."
        }
    }

    func contains(_ suggestion: SuggestionItem) -> Bool {
        switch self {
        case .active:
            return suggestion.status == "open"
        case .snoozed:
            return suggestion.status == "snoozed"
        case .reviewed:
            return suggestion.status == "accepted" || suggestion.status == "dismissed" || suggestion.status == "retired"
        }
    }

    static func bucket(for suggestion: SuggestionItem) -> SuggestionFilter {
        if suggestion.status == "snoozed" {
            return .snoozed
        }
        if suggestion.status == "accepted" || suggestion.status == "dismissed" || suggestion.status == "retired" || suggestion.retiredAt != nil {
            return .reviewed
        }
        return .active
    }
}

private extension View {
    func positionStickyIfAvailable() -> some View {
        self
    }
}

struct SuggestionReviewSidePanel: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        if let suggestion = state.selectedReviewSuggestion {
            if let draft = state.selectedFollowupDraft, draft.suggestionId == suggestion.id {
                FollowupDraftEditorView()
            } else {
                SuggestionEvidencePanelView(suggestion: suggestion)
            }
        } else if state.selectedFollowupDraft != nil {
            FollowupDraftEditorView()
        } else {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text("Review")
                        .font(.headline)
                    Spacer()
                    Chip(text: "local only")
                }
                EmptyStateView(text: "Click Review evidence on a suggestion to inspect source, related tasks, meetings, and the confirmation outcome.")
            }
            .speedwagonPanel()
        }
    }
}

struct SuggestionEvidencePanelView: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme
    let suggestion: SuggestionItem

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Review evidence")
                        .font(.headline)
                    Text("#\(suggestion.id) \(suggestion.title)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
                Spacer()
                ToneChip(text: suggestion.status, tone: SpeedwagonTheme.statusColor(suggestion.status), dot: true)
            }

            VStack(alignment: .leading, spacing: 8) {
                Text("Why this surfaced")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                Text(suggestion.reason)
                    .font(.callout)
                    .foregroundStyle(SpeedwagonTheme.secondaryText(scheme))
                    .fixedSize(horizontal: false, vertical: true)
            }
            .speedwagonSecondaryPanel()

            VStack(alignment: .leading, spacing: 8) {
                Text("If confirmed")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: "arrow.right")
                        .foregroundStyle(SpeedwagonTheme.accent(scheme))
                    Text(confirmationDescription)
                        .font(.callout.weight(.medium))
                        .fixedSize(horizontal: false, vertical: true)
                }
                Text(confirmationSafetyNote)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .speedwagonSecondaryPanel()

            if hasRelatedObjects {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Related objects")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    FlowRow(spacing: 6) {
                        if let context = suggestion.context {
                            ContextChipButton(context: context)
                        } else if let context = suggestion.displayContext {
                            Chip(text: context)
                        }
                        ForEach(suggestion.taskIds.prefix(8), id: \.self) { taskId in
                            Chip(text: "task #\(taskId)")
                        }
                        ForEach(suggestion.meetingIds.prefix(8), id: \.self) { meetingId in
                            Chip(text: "meeting #\(meetingId)")
                        }
                    }
                }
                .speedwagonSecondaryPanel()
            }

            VStack(alignment: .leading, spacing: 8) {
                InfoRow(label: "Action type", value: suggestion.proposedAction.replacingOccurrences(of: "_", with: " "))
                if let confidence = suggestion.confidence {
                    InfoRow(label: "Confidence", value: "\(Int(confidence * 100))%")
                }
                if let nextNotifyAt = suggestion.nextNotifyAt, !nextNotifyAt.isEmpty {
                    InfoRow(label: "Next notification", value: nextNotifyAt)
                }
                if let snoozedUntil = suggestion.snoozedUntil, !snoozedUntil.isEmpty {
                    InfoRow(label: "Snoozed until", value: snoozedUntil)
                }
            }
            .speedwagonSecondaryPanel()

            HStack(spacing: 8) {
                Button {
                    Task { await state.confirm(suggestion) }
                } label: {
                    Label("Confirm", systemImage: "checkmark")
                }
                .buttonStyle(.borderedProminent)
                .tint(SpeedwagonTheme.accent(scheme))

                Button {
                    Task { await state.snooze(suggestion) }
                } label: {
                    Label("Snooze", systemImage: "clock")
                }
                .buttonStyle(.bordered)
            }
        }
        .speedwagonPanel()
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(SpeedwagonTheme.accent(scheme).opacity(0.45), lineWidth: 1.5)
        )
    }

    private var hasRelatedObjects: Bool {
        suggestion.context != nil || suggestion.displayContext != nil || !suggestion.taskIds.isEmpty || !suggestion.meetingIds.isEmpty
    }

    private var confirmationDescription: String {
        let action = suggestion.proposedAction.replacingOccurrences(of: "_", with: " ")
        if suggestion.proposedAction.contains("draft") || suggestion.proposedAction.contains("email") {
            return "Create or reuse a local follow-up draft for review."
        }
        if suggestion.proposedAction.contains("add_task") || suggestion.proposedAction.contains("task") {
            return "Create or reuse the related local task."
        }
        if suggestion.proposedAction.contains("process") || suggestion.proposedAction.contains("meeting") {
            return "Process the related local meeting or imported transcript."
        }
        if suggestion.proposedAction.contains("calendar") {
            return "Open review for calendar-related context. Create Calendar events from the Calendar tab only."
        }
        return action
    }

    private var confirmationSafetyNote: String {
        if suggestion.proposedAction.contains("draft") || suggestion.proposedAction.contains("email") {
            return "Gmail draft creation remains a separate explicit step. SpeedwagonAI never sends email automatically."
        }
        if suggestion.proposedAction.contains("calendar") {
            return "Suggestion confirmation does not create or edit Calendar events. Use the Calendar tab for explicit event creation."
        }
        return "Review is local and confirmation-first. Nothing external happens from opening this panel."
    }
}

struct FollowupDraftEditorView: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme

    private var draftWasCreatedInGmail: Bool {
        state.selectedFollowupDraft?.status == "gmail_draft"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(draftWasCreatedInGmail ? "Gmail draft created" : "Draft Review")
                    .font(.headline)
                Spacer()
                if let draft = state.selectedFollowupDraft {
                    ToneChip(
                        text: draftWasCreatedInGmail ? "Draft created" : draft.status,
                        tone: draftWasCreatedInGmail ? SpeedwagonTheme.success : nil,
                        systemImage: draftWasCreatedInGmail ? "checkmark.circle" : nil
                    )
                }
            }

            if state.selectedFollowupDraft == nil {
                if state.followupDrafts.isEmpty {
                    EmptyStateView(text: "Confirm a follow-up suggestion to create a local draft.")
                } else {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            ForEach(state.followupDrafts.prefix(8)) { draft in
                                Button {
                                    state.selectFollowupDraft(draft)
                                } label: {
                                    Label(draft.subject, systemImage: "doc.text")
                                }
                                .buttonStyle(.bordered)
                            }
                        }
                    }
                }
            } else {
                VStack(alignment: .leading, spacing: 8) {
                    if draftWasCreatedInGmail {
                        HStack(alignment: .top, spacing: 8) {
                            Image(systemName: "checkmark.shield")
                                .foregroundStyle(SpeedwagonTheme.success)
                            VStack(alignment: .leading, spacing: 3) {
                                Text("Draft created in Gmail.")
                                    .font(.callout.weight(.semibold))
                                Text("SpeedwagonAI created the Gmail draft only. It has not sent the email.")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                if let providerDraftId = state.selectedFollowupDraft?.providerDraftId, !providerDraftId.isEmpty {
                                    Text("Gmail draft ID: \(providerDraftId)")
                                        .font(.caption.monospaced())
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                        .speedwagonSecondaryPanel()
                    }
                    TextField("Recipient", text: $state.draftRecipient)
                        .textFieldStyle(.roundedBorder)
                        .disabled(draftWasCreatedInGmail)
                    TextField("Subject", text: $state.draftSubject)
                        .textFieldStyle(.roundedBorder)
                        .disabled(draftWasCreatedInGmail)
                    TextEditor(text: $state.draftBody)
                        .font(.body)
                        .frame(minHeight: 180)
                        .padding(6)
                        .background(.background.opacity(0.65))
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                        .disabled(draftWasCreatedInGmail)

                    HStack(spacing: 8) {
                        Button {
                            Task { await state.saveSelectedFollowupDraft() }
                        } label: {
                            Label("Save", systemImage: "square.and.arrow.down")
                        }
                        .buttonStyle(.bordered)
                        .disabled(draftWasCreatedInGmail)
                        .speedwagonPointer()

                        Button {
                            Task { await state.createGmailDraftFromSelectedFollowupDraft() }
                        } label: {
                            Label(draftWasCreatedInGmail ? "Gmail draft created" : "Create Gmail Draft", systemImage: draftWasCreatedInGmail ? "checkmark.circle" : "envelope.badge")
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(SpeedwagonTheme.accent(scheme))
                        .disabled(draftWasCreatedInGmail)
                        .speedwagonPointer()
                    }
                }
            }
        }
        .padding(10)
        .background(.quaternary.opacity(0.25))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

struct ContextDetailReviewPanel: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        if let detail = state.selectedContextDetail {
            VStack(alignment: .leading, spacing: 12) {
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(detail.context.name)
                            .font(.title3.weight(.semibold))
                        Text("\(detail.context.kind) review")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Chip(text: "\(detail.tasks.count) tasks")
                    Chip(text: "\(detail.meetings.count) meetings")
                    Chip(text: "\(detail.suggestions.count) suggestions")
                }

                if !detail.relatedContexts.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Related Context")
                            .font(.headline)
                        Text("This review includes direct matches for \(detail.context.name) plus one-hop related items. Items marked “via related context” may belong to a connected person/project rather than directly to \(detail.context.name).")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                        FlowRow(spacing: 6) {
                            ForEach(detail.relatedContexts.prefix(12)) { context in
                                ContextChipButton(context: context)
                            }
                        }
                    }
                }

                if !detail.relationships.isEmpty {
                    ContextReviewBlock(title: "Relationships") {
                        ForEach(detail.relationships.prefix(8)) { relationship in
                            VStack(alignment: .leading, spacing: 3) {
                                Text(relationship.displayLine)
                                    .font(.caption.weight(.medium))
                                if let evidence = relationship.evidence, !evidence.isEmpty {
                                    Text(evidence)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }

                if !detail.decisions.isEmpty {
                    ContextReviewBlock(title: "Decisions") {
                        ForEach(detail.decisions.prefix(8)) { decision in
                            Text(decision.displayText)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }

                if !detail.tasks.isEmpty {
                    ContextReviewBlock(title: "Tasks") {
                        ForEach(detail.tasks.prefix(10)) { task in
                            HStack(alignment: .firstTextBaseline) {
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(task.text)
                                        .font(.caption.weight(.medium))
                                    Text("\(task.status) · \(task.displayDueDate) · \(taskDirectness(task))")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                Button {
                                    state.highlightedTaskIds = [task.id]
                                    state.statusMessage = "Highlighted task \(task.id)."
                                } label: {
                                    Label("Open", systemImage: "checklist")
                                }
                                .buttonStyle(.bordered)
                            }
                        }
                    }
                }

                if !detail.meetings.isEmpty {
                    ContextReviewBlock(title: "Meetings") {
                        ForEach(detail.meetings.prefix(8)) { meeting in
                            HStack(alignment: .firstTextBaseline) {
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(meeting.title)
                                        .font(.caption.weight(.medium))
                                    Text("\((meeting.startedAt ?? "").prefix(10)) · meeting \(meeting.id)")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                Button {
                                    Task { await state.loadMeeting(meeting) }
                                } label: {
                                    Label("Open", systemImage: "rectangle.stack")
                                }
                                .buttonStyle(.bordered)
                            }
                        }
                    }
                }

                if !detail.suggestions.isEmpty {
                    ContextReviewBlock(title: "Suggestions") {
                        ForEach(detail.suggestions.prefix(8)) { suggestion in
                            HStack(alignment: .firstTextBaseline) {
                                VStack(alignment: .leading, spacing: 3) {
                                    Text("#\(suggestion.id) \(suggestion.title)")
                                        .font(.caption.weight(.medium))
                                    Text(suggestion.status)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                Button {
                                    Task { await state.openSuggestionFromNotification(id: suggestion.id) }
                                } label: {
                                    Label("Review", systemImage: "arrowshape.turn.up.right")
                                }
                                .buttonStyle(.bordered)
                            }
                        }
                    }
                }

                if !detail.followupDrafts.isEmpty {
                    ContextReviewBlock(title: "Drafts") {
                        ForEach(detail.followupDrafts.prefix(8)) { draft in
                            HStack(alignment: .firstTextBaseline) {
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(draft.subject)
                                        .font(.caption.weight(.medium))
                                    Text(draft.status)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                Button {
                                    state.selectFollowupDraft(draft)
                                    state.statusMessage = "Selected draft \(draft.id)."
                                } label: {
                                    Label("Edit", systemImage: "doc.text")
                                }
                                .buttonStyle(.bordered)
                            }
                        }
                    }
                }
            }
            .speedwagonPanel()
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(state.highlightedContextId == detail.context.id ? SpeedwagonTheme.accent(scheme) : .clear, lineWidth: 2)
            )
        }
    }

    private func taskDirectness(_ task: TaskItem) -> String {
        if task.contexts?.contains(where: { $0.id == state.selectedContextDetail?.context.id }) == true {
            return "direct"
        }
        return "via related context"
    }
}

struct ContextReviewBlock<Content: View>: View {
    let title: String
    let content: () -> Content

    init(title: String, @ViewBuilder content: @escaping () -> Content) {
        self.title = title
        self.content = content
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            Text(title)
                .font(.headline)
            content()
        }
        .padding(10)
        .background(.quaternary.opacity(0.22))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

struct ContextReviewButton: View {
    @EnvironmentObject private var state: AppState
    let context: ContextItem

    var body: some View {
        Button {
            Task { await state.loadContextDetail(context) }
        } label: {
            Label("Review \(context.name)", systemImage: "point.3.connected.trianglepath.dotted")
        }
        .buttonStyle(.bordered)
        .speedwagonPointer()
    }
}

struct ContextChipButton: View {
    @EnvironmentObject private var state: AppState
    let context: ContextItem

    var body: some View {
        Button {
            Task { await state.loadContextDetail(context) }
        } label: {
            Chip(text: context.name)
        }
        .buttonStyle(.plain)
        .speedwagonPointer()
    }
}

struct FlowRow<Content: View>: View {
    let spacing: CGFloat
    let content: () -> Content

    init(spacing: CGFloat, @ViewBuilder content: @escaping () -> Content) {
        self.spacing = spacing
        self.content = content
    }

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: spacing) {
                content()
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

// MARK: - Notifications screen

struct NotificationsScreenView: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme

    private var candidateCount: Int { state.notificationStatus?.candidateCount ?? state.notificationCandidates.count }
    private var deliveredCount: Int { state.notificationStatus?.deliveredCount ?? 0 }
    private var snoozedCount: Int { state.notificationStatus?.snoozedCount ?? 0 }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            // Permission / status panel
            VStack(alignment: .leading, spacing: 0) {
                permissionHeader
                Divider().padding(.vertical, 12)
                HStack(spacing: 22) {
                    ForEach([("Candidates", candidateCount), ("Delivered", deliveredCount), ("Snoozed", snoozedCount)], id: \.0) { label, count in
                        VStack(alignment: .leading, spacing: 2) {
                            Text("\(count)").font(.title3.weight(.semibold).monospaced())
                            Text(label).font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                    Spacer()
                    Button {
                        Task { await state.refreshNotificationsOnly() }
                    } label: {
                        Label("Refresh", systemImage: "arrow.clockwise")
                    }
                    .buttonStyle(.bordered)
                    .speedwagonPointer()
                }
            }
            .speedwagonPanel()

            // Candidate cards
            GroupLabelView("Reminder candidates", count: candidateCount)
            if state.notificationCandidates.isEmpty {
                EmptyStateView(text: state.isConnected ? "No notification candidates right now." : "Connect backend to load notifications.")
            } else {
                VStack(spacing: 10) {
                    ForEach(state.notificationCandidates.prefix(20)) { suggestion in
                        NotificationCandidateRow(suggestion: suggestion)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var permissionHeader: some View {
        let perm = state.notificationPermissionStatus
        if perm == "authorized" || perm == "provisional" {
            HStack(spacing: 12) {
                Circle().fill(SpeedwagonTheme.success).frame(width: 8, height: 8)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Notifications allowed")
                        .font(.callout.weight(.semibold))
                    Text("Reminders open review only. They never complete tasks or send email.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
            }
        } else if perm == "denied" || perm == "error" {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundStyle(SpeedwagonTheme.warning)
                VStack(alignment: .leading, spacing: 4) {
                    Text("macOS hasn't granted notification permission")
                        .font(.callout.weight(.semibold))
                    Text("This can happen with unsigned beta builds (UNErrorDomain 1). Open System Settings › Notifications › SpeedwagonAI to allow, or continue — in-app review still works.")
                        .font(.caption).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                    HStack(spacing: 8) {
                        Button {
                            Task { await state.requestNotificationPermission() }
                        } label: { Text("Try again") }
                        .buttonStyle(.bordered).speedwagonPointer()
                    }
                    .padding(.top, 4)
                }
            }
        } else {
            HStack(spacing: 12) {
                Circle().fill(SpeedwagonTheme.warning).frame(width: 8, height: 8)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Notifications not yet enabled")
                        .font(.callout.weight(.semibold))
                    Text("Allow notifications to get gentle reminders to review work.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Button {
                    Task { await state.requestNotificationPermission() }
                } label: {
                    Label("Allow notifications", systemImage: "bell.badge")
                }
                .buttonStyle(.borderedProminent)
                .tint(SpeedwagonTheme.accent(scheme))
                .speedwagonPointer()
            }
        }
    }
}

struct NotificationCandidateRow: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme
    let suggestion: SuggestionItem

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 8)
                    .fill(SpeedwagonTheme.secondaryPanelBackground(scheme))
                    .frame(width: 34, height: 34)
                Image(systemName: "bell")
                    .font(.system(size: 15))
                    .foregroundStyle(SpeedwagonTheme.accent(scheme))
            }

            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 8) {
                    Text(suggestion.title)
                        .font(.callout.weight(.semibold))
                    ToneChip(
                        text: suggestion.notificationStatus ?? "candidate",
                        tone: suggestion.notificationStatus == "delivered" ? SpeedwagonTheme.info
                            : suggestion.notificationStatus == "snoozed" ? SpeedwagonTheme.snoozed : SpeedwagonTheme.warning,
                        dot: true
                    )
                }
                Text(suggestion.notificationReason ?? suggestion.reason)
                    .font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Spacer()

            VStack(alignment: .trailing, spacing: 6) {
                Button {
                    Task { await state.openSuggestionFromNotification(id: suggestion.id) }
                } label: {
                    Label("Review", systemImage: "eye")
                }
                .buttonStyle(.borderedProminent)
                .tint(SpeedwagonTheme.accent(scheme))
                .controlSize(.small)
                .speedwagonPointer()

                HStack(spacing: 4) {
                    Button {
                        Task { await state.markNotificationDelivered(suggestion) }
                    } label: {
                        Text("Delivered")
                    }
                    .buttonStyle(.bordered).controlSize(.mini).speedwagonPointer()

                    Button {
                        Task { await state.snoozeNotification(suggestion) }
                    } label: {
                        Image(systemName: "clock")
                    }
                    .buttonStyle(.bordered).controlSize(.mini).speedwagonPointer()

                    Button {
                        Task { await state.dismissNotification(suggestion) }
                    } label: {
                        Image(systemName: "xmark")
                    }
                    .buttonStyle(.bordered).controlSize(.mini).speedwagonPointer()
                }
            }
        }
        .padding(13)
        .background(SpeedwagonTheme.panelBackground(scheme))
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(SpeedwagonTheme.line(scheme)))
    }
}

// Legacy alias
struct NotificationsPanelView: View {
    var compact = false
    var body: some View { NotificationsScreenView() }
}

struct NotificationCandidateCard: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme
    let suggestion: SuggestionItem
    @State private var expanded = false

    var body: some View {
        ExpandableReviewCard(expanded: $expanded, tint: SpeedwagonTheme.statusColor(suggestion.notificationStatus ?? suggestion.status)) {
            VStack(alignment: .leading, spacing: 5) {
                HStack(spacing: 7) {
                    Text("#\(suggestion.id) \(suggestion.title)")
                        .font(.body.weight(.semibold))
                        .fixedSize(horizontal: false, vertical: true)
                    ToneChip(text: suggestion.notificationStatus ?? "candidate", tone: SpeedwagonTheme.statusColor(suggestion.notificationStatus ?? suggestion.status))
                }
                Text(suggestion.notificationReason ?? suggestion.reason)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        } details: {
            VStack(alignment: .leading, spacing: 7) {
                InfoRow(label: "Suggestion", value: "#\(suggestion.id)")
                InfoRow(label: "Status", value: suggestion.status)
                InfoRow(label: "Action", value: suggestion.proposedAction.replacingOccurrences(of: "_", with: " "))
                if let confidence = suggestion.confidence {
                    InfoRow(label: "Confidence", value: "\(Int(confidence * 100))%")
                }
                if !suggestion.taskIds.isEmpty {
                    FlowRow(spacing: 6) {
                        ForEach(suggestion.taskIds.prefix(6), id: \.self) { taskId in
                            Chip(text: "task #\(taskId)")
                        }
                    }
                }
                if !suggestion.meetingIds.isEmpty {
                    FlowRow(spacing: 6) {
                        ForEach(suggestion.meetingIds.prefix(6), id: \.self) { meetingId in
                            Chip(text: "meeting #\(meetingId)")
                        }
                    }
                }
                Text("Review opens the related suggestion/draft/task. It never confirms, sends, completes, or dismisses anything by itself.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        } actions: {
            HStack(spacing: 8) {
                Button {
                    Task { await state.openSuggestionFromNotification(id: suggestion.id) }
                } label: {
                    Label("Review", systemImage: "arrowshape.turn.up.right")
                }
                .buttonStyle(.borderedProminent)
                .tint(SpeedwagonTheme.accent(scheme))
                .speedwagonPointer()

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
    }
}

struct SuggestionCard: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme
    let suggestion: SuggestionItem
    @State private var expanded = false

    private var isMuted: Bool { ["snoozed", "dismissed", "retired"].contains(suggestion.status) }
    private var isAccepted: Bool { suggestion.status == "accepted" }
    private var isHighlighted: Bool { state.highlightedSuggestionId == suggestion.id }
    private var isReviewing: Bool { state.selectedReviewSuggestion?.id == suggestion.id || isHighlighted }
    private var isExpanded: Bool { expanded || isReviewing }

    private var kindLabel: String {
        let action = suggestion.proposedAction
        if action.contains("draft") || action.contains("email") { return "Follow-up ready" }
        if action.contains("task") { return "Task" }
        if action.contains("process") || action.contains("meeting") { return "Unprocessed" }
        if suggestion.status == "open", !suggestion.taskIds.isEmpty { return "Overdue" }
        return "Suggestion"
    }

    private var kindColor: Color {
        if isMuted { return SpeedwagonTheme.snoozed }
        if isAccepted { return SpeedwagonTheme.success }
        let action = suggestion.proposedAction
        if action.contains("draft") || action.contains("email") { return SpeedwagonTheme.accent(scheme) }
        return SpeedwagonTheme.info
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Card body
            VStack(alignment: .leading, spacing: 10) {
                // Header row
                HStack(spacing: 8) {
                    ToneChip(text: kindLabel, tone: kindColor, dot: true)
                    Text("#\(suggestion.id)")
                        .font(.caption.monospaced())
                        .foregroundStyle(.tertiary)
                    if let context = suggestion.context {
                        ContextChipButton(context: context)
                    } else if let name = suggestion.displayContext {
                        Chip(text: name)
                    }
                    Spacer()
                    Button {
                        withAnimation(.easeInOut(duration: 0.16)) {
                            expanded.toggle()
                        }
                    } label: {
                        Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                    .speedwagonPointer()
                    if let confidence = suggestion.confidence {
                        HStack(spacing: 5) {
                            RoundedRectangle(cornerRadius: 99)
                                .fill(SpeedwagonTheme.secondaryPanelBackground(scheme))
                                .frame(width: 38, height: 4)
                                .overlay(alignment: .leading) {
                                    RoundedRectangle(cornerRadius: 99)
                                        .fill(SpeedwagonTheme.accent(scheme))
                                        .frame(width: 38 * confidence)
                                }
                            Text("\(Int(confidence * 100))%")
                                .font(.caption2.monospaced())
                                .foregroundStyle(.secondary)
                        }
                    }
                }

                // Title
                Text(suggestion.title)
                    .font(.system(size: 15, weight: .semibold))
                    .fixedSize(horizontal: false, vertical: true)

                if isExpanded {
                    // Why surfaced
                    HStack(alignment: .top, spacing: 7) {
                        Image(systemName: "info.circle")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .padding(.top, 2)
                        Text(suggestion.reason)
                            .font(.callout)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }

                    // If confirmed box
                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: "arrow.right")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(kindColor)
                        VStack(alignment: .leading, spacing: 3) {
                            Text("If confirmed: ")
                                .font(.caption.weight(.semibold))
                                + Text(confirmationText)
                                .font(.caption)
                        }
                        Spacer()
                        if suggestion.proposedAction.contains("draft") {
                            ToneChip(text: "Draft ready", tone: SpeedwagonTheme.accent(scheme), systemImage: "doc.text")
                        }
                    }
                    .padding(9)
                    .background(SpeedwagonTheme.secondaryPanelBackground(scheme))
                    .clipShape(RoundedRectangle(cornerRadius: 6))
                    .overlay(RoundedRectangle(cornerRadius: 6).stroke(SpeedwagonTheme.softLine(scheme)))

                    // Evidence chips
                    FlowRow(spacing: 6) {
                        ForEach(suggestion.meetingIds.prefix(4), id: \.self) { mid in
                            Chip(text: "Meeting #\(mid)")
                        }
                        if suggestion.taskIds.count > 0 {
                            Chip(text: "\(suggestion.taskIds.count) task\(suggestion.taskIds.count == 1 ? "" : "s")")
                        }
                        if isMuted {
                            ToneChip(
                                text: suggestion.status == "snoozed" ? "Snoozed\(suggestion.snoozedUntil.map { " · \($0)" } ?? "")" : suggestion.status.capitalized,
                                tone: SpeedwagonTheme.snoozed, dot: true
                            )
                        }
                        if isAccepted {
                            ToneChip(text: "Accepted", tone: SpeedwagonTheme.success, systemImage: "checkmark")
                        }
                    }
                } else {
                    Text(suggestion.reason)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
            }
            .padding(14)
            .opacity(isMuted ? 0.62 : 1)

            // Action bar
            HStack(spacing: 8) {
                if !isMuted && !isAccepted {
                    Button {
                        Task { await state.confirm(suggestion) }
                    } label: {
                        Label("Confirm", systemImage: "checkmark")
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(kindColor)
                    .controlSize(.small)
                    .speedwagonPointer()

                    Button {
                        Task { await state.openSuggestionFromNotification(id: suggestion.id) }
                    } label: {
                        Label("Review evidence", systemImage: "eye")
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .speedwagonPointer()

                    Spacer()

                    Button {
                        Task { await state.snooze(suggestion) }
                    } label: {
                        Label("Snooze", systemImage: "clock")
                    }
                    .buttonStyle(.bordered).controlSize(.small).speedwagonPointer()

                    Button {
                        Task { await state.dismiss(suggestion) }
                    } label: {
                        Label("Dismiss", systemImage: "xmark")
                    }
                    .buttonStyle(.bordered).controlSize(.small).speedwagonPointer()
                } else {
                    Text(isAccepted ? "Confirmed — reversible from history." : "Not active. Reopen to bring back.")
                        .font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    Button {
                        Task { await state.confirm(suggestion) }
                    } label: {
                        Label("Reopen", systemImage: "arrow.uturn.left")
                    }
                    .buttonStyle(.bordered).controlSize(.small).speedwagonPointer()
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 9)
            .background(SpeedwagonTheme.secondaryPanelBackground(scheme))
            .overlay(alignment: .top) {
                Rectangle().fill(SpeedwagonTheme.softLine(scheme)).frame(height: 1)
            }
        }
        .background(SpeedwagonTheme.panelBackground(scheme))
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(isReviewing ? SpeedwagonTheme.accent(scheme).opacity(0.70) : SpeedwagonTheme.line(scheme), lineWidth: isReviewing ? 1.5 : 1)
        )
        .shadow(color: isReviewing ? SpeedwagonTheme.accent(scheme).opacity(0.18) : .clear, radius: 6)
        .onChange(of: state.suggestionReviewToken) { _, _ in
            if isReviewing {
                expanded = true
            }
        }
    }

    private var confirmationText: String {
        let action = suggestion.proposedAction
        if action.contains("draft") || action.contains("email") {
            return "Create or reuse a local follow-up draft for review."
        }
        if action.contains("add_task") { return "Create the related local task." }
        if action.contains("process") || action.contains("meeting") { return "Process the related meeting or transcript." }
        if action.contains("search") { return "Open context search results." }
        return action.replacingOccurrences(of: "_", with: " ")
    }
}

struct ResultContent: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme
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

            if response.result?.clarificationRequired == true {
                Text("Clarification needed.")
                    .font(.caption.weight(.medium))
                    .foregroundStyle(.orange)
            }

            if let assistantMessage = response.result?.assistantMessage,
               !assistantMessage.isEmpty,
               assistantMessage != response.summary {
                Text(assistantMessage)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if let pending = response.result?.pendingAction {
                Text("Pending #\(pending.id): \(pending.action)")
                    .font(.caption.weight(.medium))
                    .foregroundStyle(.orange)
            }

            if let evidence = response.result?.evidence, !evidence.isEmpty {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Evidence")
                        .font(.caption.weight(.semibold))
                    ForEach(evidence.prefix(6), id: \.idValue) { item in
                        Text(item.displayLine)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                    }
                }
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
                        ContextChipButton(context: context)
                    }
                }
            }

            if let relationships = response.result?.relationships, !relationships.isEmpty {
                ForEach(relationships.prefix(6)) { relationship in
                    Text(relationship.displayLine)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            if let decisions = response.result?.decisions, !decisions.isEmpty {
                ForEach(decisions.prefix(6)) { decision in
                    Text(decision.displayText)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            let suggestedCommands = response.suggestedCommands ?? response.result?.suggestedCommands ?? []
            if !suggestedCommands.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Try this")
                        .font(.caption.weight(.semibold))
                    FlowRow(spacing: 6) {
                        ForEach(suggestedCommands.prefix(4), id: \.self) { command in
                            Button {
                                Task { await state.runSuggestedCommand(command) }
                            } label: {
                                Label(command, systemImage: "arrow.turn.down.right")
                            }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                            .speedwagonPointer()
                        }
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

            if let event = response.result?.event {
                Text("#\(event.id) \(event.title) · \(event.startAt)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if let events = response.result?.events, !events.isEmpty {
                ForEach(events.prefix(8)) { event in
                    Text("\(event.startAt) · \(event.title)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                if events.count > 8 {
                    Text("\(events.count - 8) more in Calendar.")
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

            if let draft = response.result?.draftPreview ?? response.result?.draft {
                VStack(alignment: .leading, spacing: 5) {
                    Text("Draft preview")
                        .font(.caption.weight(.semibold))
                    Text(draft.subject ?? "Draft")
                        .font(.caption.weight(.medium))
                    if let recipient = draft.to, !recipient.isEmpty {
                        Text("To: \(recipient)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Text(draft.body ?? "")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(8)
                }
                .padding(9)
                .background(SpeedwagonTheme.secondaryPanelBackground(scheme))
                .clipShape(RoundedRectangle(cornerRadius: 7))
                .overlay(RoundedRectangle(cornerRadius: 7).stroke(SpeedwagonTheme.softLine(scheme)))
            }

            if let draft = response.result?.followupDraft {
                VStack(alignment: .leading, spacing: 5) {
                    Text("Local draft #\(draft.id)")
                        .font(.caption.weight(.semibold))
                    Text(draft.subject)
                        .font(.caption.weight(.medium))
                    if let recipient = draft.recipient, !recipient.isEmpty {
                        Text("To: \(recipient)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Text(draft.body)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(8)
                }
                .padding(9)
                .background(SpeedwagonTheme.secondaryPanelBackground(scheme))
                .clipShape(RoundedRectangle(cornerRadius: 7))
                .overlay(RoundedRectangle(cornerRadius: 7).stroke(SpeedwagonTheme.softLine(scheme)))
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
    let highlightedTaskIds: Set<Int>
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
                        TaskRow(
                            task: task,
                            highlighted: highlightedTaskIds.contains(task.id),
                            onComplete: onComplete,
                            onReopen: onReopen
                        )
                    }
                }
            }
        }
        .speedwagonSecondaryPanel()
    }
}

struct TaskRow: View {
    @Environment(\.colorScheme) private var scheme
    let task: TaskItem
    var highlighted = false
    var compact = false
    var onComplete: ((TaskItem) -> Void)? = nil
    var onReopen: ((TaskItem) -> Void)? = nil
    @State private var expanded = false

    var body: some View {
        ExpandableReviewCard(
            expanded: compact ? .constant(false) : $expanded,
            highlighted: highlighted,
            tint: SpeedwagonTheme.statusColor(task.isOverdue == true ? "overdue" : task.status)
        ) {
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 7) {
                    Text(task.text)
                        .font(.body.weight(.medium))
                        .fixedSize(horizontal: false, vertical: true)
                    ToneChip(
                        text: task.isOverdue == true && !task.isDone ? "overdue" : task.status,
                        tone: SpeedwagonTheme.statusColor(task.isOverdue == true ? "overdue" : task.status)
                    )
                }

                HStack(spacing: 10) {
                    Label(task.displayOwner, systemImage: "person")
                    Label(task.displayDueDate, systemImage: "calendar")
                    if !compact {
                        Label(task.displaySource, systemImage: "doc.text")
                    }
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }
        } details: {
            VStack(alignment: .leading, spacing: 7) {
                if let suggestion = task.reminderSuggestion, !suggestion.isEmpty, !task.isDone {
                    Text(suggestion)
                        .font(.caption)
                        .foregroundStyle(SpeedwagonTheme.warning)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let contexts = task.contexts, !contexts.isEmpty {
                    VStack(alignment: .leading, spacing: 5) {
                        Text("Context")
                            .font(.caption.weight(.semibold))
                        FlowRow(spacing: 6) {
                            ForEach(contexts.prefix(6)) { context in
                                ContextChipButton(context: context)
                            }
                        }
                    }
                }
                HStack(spacing: 6) {
                    Chip(text: "task #\(task.id)")
                    if let kind = task.kind, !kind.isEmpty {
                        Chip(text: kind)
                    }
                    if let project = task.project, !project.isEmpty {
                        Chip(text: project)
                    }
                    if let meetingId = task.meetingId ?? task.sourceMeetingId {
                        Chip(text: "meeting #\(meetingId)")
                    }
                }
                if let snoozedUntil = task.snoozedUntil, !snoozedUntil.isEmpty {
                    Label("Snoozed until \(snoozedUntil)", systemImage: "clock")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                if let updatedAt = task.updatedAt, !updatedAt.isEmpty {
                    Label("Updated \(updatedAt)", systemImage: "clock.arrow.circlepath")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        } actions: {
            if compact {
                EmptyView()
            } else if let onComplete, let onReopen {
                HStack(spacing: 8) {
                    if task.isDone {
                        Button {
                            onReopen(task)
                        } label: {
                            Label("Reopen", systemImage: "arrow.uturn.backward")
                        }
                        .buttonStyle(.bordered)
                        .speedwagonPointer()
                    } else {
                        Button {
                            onComplete(task)
                        } label: {
                            Label("Complete", systemImage: "checkmark.circle.fill")
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(SpeedwagonTheme.accent(scheme))
                        .speedwagonPointer()
                    }
                }
            } else {
                EmptyView()
            }
        }
    }
}

struct SidebarButton: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme
    let section: NativeSection
    @Binding var selectedSection: NativeSection

    var body: some View {
        Button {
            selectedSection = section
            activateSpeedwagon()
        } label: {
            HStack(spacing: 10) {
                Image(systemName: section.systemImage)
                    .font(.system(size: 15, weight: .medium))
                    .frame(width: 18)
                    .foregroundStyle(selectedSection == section ? SpeedwagonTheme.accent(scheme) : SpeedwagonTheme.tertiaryText(scheme))
                Text(section.rawValue)
                    .frame(maxWidth: .infinity, alignment: .leading)
                if let badge = badgeText {
                    Text(badge)
                        .font(.caption2.monospaced().weight(.semibold))
                        .foregroundStyle(selectedSection == section ? SpeedwagonTheme.accent(scheme) : SpeedwagonTheme.tertiaryText(scheme))
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(selectedSection == section ? SpeedwagonTheme.accentSoft(scheme) : SpeedwagonTheme.secondaryPanelBackground(scheme))
                        .clipShape(Capsule())
                }
            }
        }
        .buttonStyle(.plain)
        .padding(.horizontal, 10)
        .padding(.vertical, 7)
        .foregroundStyle(selectedSection == section ? SpeedwagonTheme.primaryText(scheme) : SpeedwagonTheme.secondaryText(scheme))
        .background(selectedSection == section ? SpeedwagonTheme.accentSoft(scheme) : Color.clear)
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .overlay(
            HStack {
                Rectangle()
                    .fill(selectedSection == section ? SpeedwagonTheme.accent(scheme) : .clear)
                    .frame(width: 2)
                Spacer()
            }
            .clipShape(RoundedRectangle(cornerRadius: 6))
        )
        .speedwagonPointer()
    }

    private var badgeText: String? {
        switch section {
        case .suggestions:
            let count = state.suggestions.filter { $0.status == "open" }.count
            return count > 0 ? "\(count)" : nil
        case .tasks:
            let count = state.tasks.filter { !$0.isDone && $0.status != "canceled" }.count
            return count > 0 ? "\(count)" : nil
        case .notifications:
            let count = state.notificationCandidates.count
            return count > 0 ? "\(count)" : nil
        default:
            return nil
        }
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

struct ExpandableReviewCard<Header: View, Details: View, Actions: View>: View {
    @Environment(\.colorScheme) private var scheme
    @Binding var expanded: Bool
    var highlighted = false
    var tint: Color? = nil
    let header: () -> Header
    let details: () -> Details
    let actions: () -> Actions

    init(
        expanded: Binding<Bool>,
        highlighted: Bool = false,
        tint: Color? = nil,
        @ViewBuilder header: @escaping () -> Header,
        @ViewBuilder details: @escaping () -> Details,
        @ViewBuilder actions: @escaping () -> Actions
    ) {
        self._expanded = expanded
        self.highlighted = highlighted
        self.tint = tint
        self.header = header
        self.details = details
        self.actions = actions
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            Button {
                withAnimation(.easeInOut(duration: 0.16)) {
                    expanded.toggle()
                }
            } label: {
                HStack(alignment: .top, spacing: 10) {
                    header()
                    Spacer(minLength: 8)
                    Image(systemName: expanded ? "chevron.up" : "chevron.down")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                        .padding(.top, 2)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .speedwagonPointer()

            if expanded {
                Divider()
                details()
                    .transition(.opacity.combined(with: .move(edge: .top)))
            }

            actions()
        }
        .padding(12)
        .background(SpeedwagonTheme.secondaryPanelBackground(scheme))
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(highlighted ? (tint ?? SpeedwagonTheme.accent(scheme)) : SpeedwagonTheme.softLine(scheme), lineWidth: highlighted ? 2 : 1)
        )
    }
}

// MARK: - Connections (context graph)

enum ConnectionsMode: String, CaseIterable, Identifiable {
    case graph = "Graph"
    case directory = "Directory"

    var id: String { rawValue }
}

enum ConnectionDirectoryKind: String, CaseIterable, Identifiable {
    case person = "People"
    case project = "Projects"
    case topic = "Topics"

    var id: String { rawValue }
    var kind: String {
        switch self {
        case .person: return "person"
        case .project: return "project"
        case .topic: return "topic"
        }
    }
    var singular: String {
        switch self {
        case .person: return "person"
        case .project: return "project"
        case .topic: return "topic"
        }
    }
}

enum ConnectionDetailTab: String, CaseIterable, Identifiable {
    case profile = "Profile"
    case tasks = "Tasks"
    case suggestions = "Suggestions"
    case meetings = "Meetings"
    case connections = "Connections"

    var id: String { rawValue }
}

struct ConnectionsView: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme
    @State private var graph: ContextGraphResponse?
    @State private var query = ""
    @State private var loading = false
    @State private var mode: ConnectionsMode = .graph
    @State private var directoryKind: ConnectionDirectoryKind = .person
    @State private var detailTab: ConnectionDetailTab = .profile

    private var contexts: [ContextItem] { graph?.contexts ?? [] }
    private var relationships: [ContextRelationshipItem] { graph?.relationships ?? [] }
    private var selectedDetail: ContextDetailResponse? { state.selectedContextDetail }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Picker("", selection: $mode) {
                    ForEach(ConnectionsMode.allCases) { item in
                        Text(item.rawValue).tag(item)
                    }
                }
                .pickerStyle(.segmented)
                .frame(width: 170)

                Spacer()

                Button {
                    addPerson()
                } label: {
                    Label("Add person", systemImage: "plus")
                }
                .buttonStyle(.bordered)
                .speedwagonPointer()
            }

            if mode == .graph {
                graphWorkspace
            } else {
                directoryWorkspace
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .task {
            if graph == nil { await load() }
        }
        .onChange(of: mode) { _, newMode in
            if newMode == .graph {
                state.clearContextSelection()
                detailTab = .profile
            }
        }
    }

    private var graphWorkspace: some View {
        ZStack {
            Color.clear
                .contentShape(Rectangle())
                .onTapGesture {
                    state.clearContextSelection()
                }

            HStack(alignment: .top, spacing: 18) {
                VStack(alignment: .leading, spacing: 12) {
                    HStack(alignment: .firstTextBaseline, spacing: 28) {
                        graphMetric("People", count: count(kind: "person"))
                        graphMetric("Projects", count: count(kind: "project"))
                        graphMetric("Topics", count: count(kind: "topic"))
                        graphMetric("Connections", count: relationships.count)
                        Spacer()
                        graphLegend
                    }

                    ConnectionGraphCanvas(
                        contexts: contexts,
                        relationships: relationships,
                        selectedId: state.highlightedContextId
                    )
                    .frame(minHeight: 360, maxHeight: .infinity)
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(SpeedwagonTheme.line(scheme)))

                    Text("Relationships are extracted from meetings and tasks. Dashed lines are inferred; confidence reflects how strongly evidence supports each link.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)

                graphInspector
                    .frame(width: 360, alignment: .top)
                    .frame(maxHeight: .infinity, alignment: .top)
            }
        }
    }

    private var directoryWorkspace: some View {
        ZStack {
            Color.clear
                .contentShape(Rectangle())
                .onTapGesture {
                    state.clearContextSelection()
                }

            HStack(alignment: .top, spacing: 18) {
                VStack(spacing: 0) {
                HStack(spacing: 0) {
                    ForEach(ConnectionDirectoryKind.allCases) { kind in
                        Button {
                            directoryKind = kind
                        } label: {
                            Text("\(kind.rawValue) (\(count(kind: kind.kind)))")
                                .font(.callout.weight(directoryKind == kind ? .semibold : .regular))
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 10)
                                .foregroundStyle(directoryKind == kind ? SpeedwagonTheme.primaryText(scheme) : SpeedwagonTheme.secondaryText(scheme))
                        }
                        .buttonStyle(.plain)
                        .background(directoryKind == kind ? SpeedwagonTheme.accentSoft(scheme) : Color.clear)
                        .speedwagonPointer()
                    }
                }
                .background(SpeedwagonTheme.secondaryPanelBackground(scheme))

                HStack(spacing: 8) {
                    Image(systemName: "magnifyingglass")
                        .foregroundStyle(SpeedwagonTheme.tertiaryText(scheme))
                    TextField("Filter \(directoryKind.singular)s...", text: $query)
                        .textFieldStyle(.plain)
                        .onSubmit { Task { await load() } }
                }
                .padding(10)
                .background(SpeedwagonTheme.panelBackground(scheme))
                .overlay(alignment: .bottom) {
                    Rectangle().fill(SpeedwagonTheme.softLine(scheme)).frame(height: 1)
                }

                ScrollView {
                    ZStack(alignment: .top) {
                        Color.clear
                            .contentShape(Rectangle())
                            .onTapGesture {
                                state.clearContextSelection()
                            }
                        LazyVStack(spacing: 6) {
                            ForEach(directoryItems) { context in
                                DirectoryContextRow(
                                    context: context,
                                    detail: state.selectedContextDetail?.context.id == context.id ? state.selectedContextDetail : nil,
                                    selected: state.highlightedContextId == context.id
                                )
                            }
                        }
                        .padding(10)
                    }
                    .frame(maxWidth: .infinity, minHeight: 360, alignment: .top)
                }

                Button {
                    addPerson()
                } label: {
                    Label("Add person", systemImage: "plus")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.plain)
                .padding(12)
                .background(SpeedwagonTheme.secondaryPanelBackground(scheme))
                .speedwagonPointer()
            }
            .frame(minWidth: 290, idealWidth: 320, maxWidth: 360)
            .frame(maxHeight: .infinity)
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(SpeedwagonTheme.line(scheme)))

                DirectoryDetailPanel(detail: selectedDetail, selectedTab: $detailTab)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            }
        }
    }

    private var directoryItems: [ContextItem] {
        contexts
            .filter { $0.kind.lowercased() == directoryKind.kind }
            .filter { context in
                let needle = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
                return needle.isEmpty || context.name.lowercased().contains(needle)
            }
    }

    private var graphInspector: some View {
        Group {
            if let detail = selectedDetail {
                DirectoryDetailPanel(detail: detail, selectedTab: $detailTab)
            } else {
                VStack(spacing: 12) {
                    Image(systemName: "link")
                        .font(.title2)
                        .foregroundStyle(SpeedwagonTheme.secondaryText(scheme))
                        .padding(16)
                        .background(SpeedwagonTheme.secondaryPanelBackground(scheme))
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                    Text("Select a node")
                        .font(.headline)
                    Text("Click any person, project, or topic in the graph to see what SpeedwagonAI knows about them.")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity, minHeight: 220)
                .speedwagonPanel()
            }
        }
    }

    private var graphLegend: some View {
        HStack(spacing: 14) {
            Label("Person", systemImage: "circle.fill")
                .foregroundStyle(SpeedwagonTheme.context)
            Label("Project", systemImage: "square.fill")
                .foregroundStyle(SpeedwagonTheme.accent(scheme))
            Label("Topic", systemImage: "diamond.fill")
                .foregroundStyle(SpeedwagonTheme.warning)
            Text("---- inferred")
                .foregroundStyle(.secondary)
        }
        .font(.caption)
    }

    private func graphMetric(_ label: String, count: Int) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text("\(count)")
                .font(.title3.weight(.semibold))
            Text(label.uppercased())
                .font(.caption2.weight(.semibold))
                .tracking(1.1)
                .foregroundStyle(.secondary)
        }
    }

    private func count(kind: String) -> Int {
        contexts.filter { $0.kind.lowercased() == kind }.count
    }

    private func load() async {
        loading = true
        defer { loading = false }
        do {
            graph = try await state.client.searchContextGraph(query: query.trimmingCharacters(in: .whitespacesAndNewlines))
            state.isConnected = true
        } catch {
            state.statusMessage = "Could not load connections: \(error.localizedDescription)"
        }
    }

    private func addPerson() {
        let alert = NSAlert()
        alert.messageText = "Add person"
        alert.informativeText = "Create a local person profile for assistant context and future drafts."
        alert.addButton(withTitle: "Add")
        alert.addButton(withTitle: "Cancel")
        let input = NSTextField(frame: NSRect(x: 0, y: 0, width: 280, height: 24))
        input.placeholderString = "Name"
        alert.accessoryView = input
        alert.window.initialFirstResponder = input
        let response = alert.runModal()
        let name = input.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard response == .alertFirstButtonReturn else { return }
        guard !name.isEmpty else {
            state.statusMessage = "Person name is required."
            return
        }
        query = ""
        mode = .directory
        directoryKind = .person
        detailTab = .profile
        Task {
            if await state.createContext(name: name, kind: "person") != nil {
                await load()
            }
        }
    }
}

struct ConnectionGraphCanvas: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme
    let contexts: [ContextItem]
    let relationships: [ContextRelationshipItem]
    let selectedId: Int?

    var body: some View {
        GeometryReader { proxy in
            let points = pointMap(size: proxy.size)
            ZStack {
                Color.clear
                    .contentShape(Rectangle())
                    .onTapGesture {
                        state.clearContextSelection()
                    }

                Canvas { context, _ in
                    for relationship in relationships {
                        guard let source = points[relationship.sourceContext.id],
                              let target = points[relationship.targetContext.id] else { continue }
                        var path = Path()
                        path.move(to: source)
                        path.addLine(to: target)
                        context.stroke(
                            path,
                            with: .color(SpeedwagonTheme.secondaryText(scheme).opacity(0.45)),
                            style: StrokeStyle(lineWidth: 1.2, dash: [5, 5])
                        )
                    }
                }

                ForEach(Array(contexts.prefix(18).enumerated()), id: \.element.id) { _, context in
                    let point = points[context.id] ?? CGPoint(x: proxy.size.width / 2, y: proxy.size.height / 2)
                    ConnectionGraphNode(context: context, selected: selectedId == context.id)
                        .position(point)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(
                GridBackground()
                    .foregroundStyle(SpeedwagonTheme.softLine(scheme).opacity(0.55))
            )
            .clipShape(RoundedRectangle(cornerRadius: 8))
        }
    }

    private func pointMap(size: CGSize) -> [Int: CGPoint] {
        let visible = Array(contexts.prefix(18))
        guard !visible.isEmpty else { return [:] }
        let center = CGPoint(x: size.width * 0.50, y: size.height * 0.50)
        let radiusX = max(size.width * 0.33, 100)
        let radiusY = max(size.height * 0.28, 90)
        return Dictionary(uniqueKeysWithValues: visible.enumerated().map { index, context in
            let angle = (Double(index) / Double(max(visible.count, 1))) * Double.pi * 2 - Double.pi / 2
            let jitter = Double((context.id % 5) - 2) * 0.035
            let x = center.x + cos(angle + jitter) * radiusX
            let y = center.y + sin(angle + jitter) * radiusY
            return (context.id, CGPoint(x: x, y: y))
        })
    }
}

struct GridBackground: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        let step: CGFloat = 42
        var x = rect.minX
        while x <= rect.maxX {
            path.move(to: CGPoint(x: x, y: rect.minY))
            path.addLine(to: CGPoint(x: x, y: rect.maxY))
            x += step
        }
        var y = rect.minY
        while y <= rect.maxY {
            path.move(to: CGPoint(x: rect.minX, y: y))
            path.addLine(to: CGPoint(x: rect.maxX, y: y))
            y += step
        }
        return path
    }
}

struct ConnectionGraphNode: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme
    let context: ContextItem
    let selected: Bool

    var body: some View {
        Button {
            Task { await state.loadContextDetail(context) }
        } label: {
            VStack(spacing: 6) {
                nodeBadge
                    .frame(width: nodeSize, height: nodeSize)
                Text(context.name)
                    .font(.caption)
                    .foregroundStyle(SpeedwagonTheme.secondaryText(scheme))
                    .lineLimit(2)
                    .multilineTextAlignment(.center)
                    .frame(width: 92)
            }
        }
        .buttonStyle(.plain)
        .speedwagonPointer()
    }

    private var nodeSize: CGFloat {
        context.kind.lowercased() == "person" ? 56 : 48
    }

    private var nodeBadge: some View {
        ZStack {
            switch context.kind.lowercased() {
            case "project":
                RoundedRectangle(cornerRadius: 8)
                    .fill(SpeedwagonTheme.accent(scheme))
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(selected ? SpeedwagonTheme.accent(scheme) : Color.clear, lineWidth: 3))
            case "topic":
                Diamond()
                    .fill(SpeedwagonTheme.warning)
                    .overlay(Diamond().stroke(selected ? SpeedwagonTheme.accent(scheme) : Color.clear, lineWidth: 3))
            default:
                Circle()
                    .fill(SpeedwagonTheme.context)
                    .overlay(Circle().stroke(selected ? SpeedwagonTheme.accent(scheme) : Color.clear, lineWidth: 3))
            }
            Text(initials(context.name))
                .font(.caption.weight(.bold))
                .foregroundStyle(nodeTextColor)
        }
    }

    private var nodeTextColor: Color {
        context.kind.lowercased() == "topic" ? .black.opacity(0.75) : SpeedwagonTheme.primaryText(scheme)
    }
}

struct Diamond: InsettableShape {
    var insetAmount: CGFloat = 0

    func path(in rect: CGRect) -> Path {
        let rect = rect.insetBy(dx: insetAmount, dy: insetAmount)
        var path = Path()
        path.move(to: CGPoint(x: rect.midX, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.midY))
        path.addLine(to: CGPoint(x: rect.midX, y: rect.maxY))
        path.addLine(to: CGPoint(x: rect.minX, y: rect.midY))
        path.closeSubpath()
        return path
    }

    func inset(by amount: CGFloat) -> some InsettableShape {
        var copy = self
        copy.insetAmount += amount
        return copy
    }
}

struct DirectoryContextRow: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme
    let context: ContextItem
    let detail: ContextDetailResponse?
    let selected: Bool

    var body: some View {
        Button {
            Task { await state.loadContextDetail(context) }
        } label: {
            HStack(spacing: 12) {
                Circle()
                    .fill(SpeedwagonTheme.contextKindColor(context.kind))
                    .frame(width: 42, height: 42)
                    .overlay {
                        Text(initials(context.name))
                            .font(.callout.weight(.bold))
                            .foregroundStyle(SpeedwagonTheme.primaryText(scheme))
                    }
                VStack(alignment: .leading, spacing: 3) {
                    Text(context.name)
                        .font(.callout.weight(.semibold))
                        .foregroundStyle(SpeedwagonTheme.primaryText(scheme))
                    Text(directorySubtitle)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Text("\((detail?.relatedContexts.count ?? 0) + (detail?.relationships.count ?? 0))")
                    .font(.caption.monospaced().weight(.semibold))
                    .foregroundStyle(.secondary)
                    .padding(6)
                    .background(SpeedwagonTheme.secondaryPanelBackground(scheme))
                    .clipShape(Capsule())
            }
            .padding(10)
            .background(selected ? SpeedwagonTheme.accentSoft(scheme) : Color.clear)
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(selected ? SpeedwagonTheme.accent(scheme).opacity(0.7) : Color.clear)
            )
        }
        .buttonStyle(.plain)
        .speedwagonPointer()
    }

    private var directorySubtitle: String {
        if context.kind.lowercased() == "person" {
            return context.reason ?? "Person"
        }
        return context.kind.capitalized
    }
}

struct DirectoryDetailPanel: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.colorScheme) private var scheme
    let detail: ContextDetailResponse?
    @Binding var selectedTab: ConnectionDetailTab
    @State private var email = ""
    @State private var phone = ""
    @State private var role = ""
    @State private var company = ""
    @State private var notes = ""
    @State private var profileSaveMessage = ""

    var body: some View {
        if let detail {
            VStack(alignment: .leading, spacing: 0) {
                HStack(spacing: 16) {
                    Circle()
                        .fill(SpeedwagonTheme.contextKindColor(detail.context.kind))
                        .frame(width: 58, height: 58)
                        .overlay {
                            Text(initials(detail.context.name))
                                .font(.title3.weight(.bold))
                                .foregroundStyle(SpeedwagonTheme.primaryText(scheme))
                        }
                    VStack(alignment: .leading, spacing: 3) {
                        Text(detail.context.name)
                            .font(.title2.weight(.semibold))
                        Text(profileSubtitle(detail))
                            .font(.callout)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    ToneChip(text: detail.context.kind.capitalized, tone: SpeedwagonTheme.contextKindColor(detail.context.kind), dot: true)
                }
                .padding(18)

                HStack(spacing: 0) {
                    ForEach(ConnectionDetailTab.allCases) { tab in
                        Button {
                            selectedTab = tab
                        } label: {
                            Text(tabTitle(tab, detail: detail))
                                .font(.callout.weight(selectedTab == tab ? .semibold : .regular))
                                .foregroundStyle(selectedTab == tab ? SpeedwagonTheme.primaryText(scheme) : SpeedwagonTheme.secondaryText(scheme))
                                .padding(.horizontal, 14)
                                .padding(.vertical, 10)
                                .overlay(alignment: .bottom) {
                                    Rectangle()
                                        .fill(selectedTab == tab ? SpeedwagonTheme.accent(scheme) : Color.clear)
                                        .frame(height: 2)
                                }
                        }
                        .buttonStyle(.plain)
                        .speedwagonPointer()
                    }
                    Spacer()
                }
                .background(SpeedwagonTheme.secondaryPanelBackground(scheme))
                .overlay(alignment: .top) {
                    Rectangle().fill(SpeedwagonTheme.softLine(scheme)).frame(height: 1)
                }
                .overlay(alignment: .bottom) {
                    Rectangle().fill(SpeedwagonTheme.softLine(scheme)).frame(height: 1)
                }

                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        switch selectedTab {
                        case .profile:
                            profileForm(detail)
                        case .tasks:
                            contextList(title: "Tasks", empty: "No tasks linked yet.") {
                                ForEach(detail.tasks.prefix(30)) { task in
                                    InfoRow(label: "#\(task.id)", value: "\(task.text) · \(task.status) · \(task.displayDueDate)")
                                }
                            }
                        case .suggestions:
                            contextList(title: "Suggestions", empty: "No suggestions linked yet.") {
                                ForEach(detail.suggestions.prefix(30)) { suggestion in
                                    InfoRow(label: "#\(suggestion.id)", value: "\(suggestion.title) · \(suggestion.status)")
                                }
                            }
                        case .meetings:
                            contextList(title: "Meetings", empty: "No meetings linked yet.") {
                                ForEach(detail.meetings.prefix(30)) { meeting in
                                    InfoRow(label: "#\(meeting.id)", value: "\(meeting.title) · \((meeting.startedAt ?? "").prefix(10))")
                                }
                            }
                        case .connections:
                            connectionEvidence(detail)
                        }
                    }
                    .padding(18)
                }
            }
            .background(SpeedwagonTheme.panelBackground(scheme))
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(SpeedwagonTheme.line(scheme)))
            .onAppear {
                loadProfileFields(detail.context)
            }
            .onChange(of: detail.context.id) { _, _ in
                loadProfileFields(detail.context)
            }
        } else {
            EmptyStateView(text: "Select a node or directory item to inspect its profile, tasks, meetings, suggestions, and relationship evidence.")
                .speedwagonPanel()
        }
    }

    private func profileForm(_ detail: ContextDetailResponse) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 14) {
                labeledField("Name", text: .constant(detail.context.name))
                labeledField("Role", text: $role, placeholder: detail.context.kind == "person" ? "role" : "classification")
            }
            HStack(spacing: 14) {
                labeledField("Email", text: $email, placeholder: "name@company.com")
                labeledField("Phone", text: $phone, placeholder: "+1 555 ...")
            }
            labeledField("Company", text: $company, placeholder: "company")
                .frame(maxWidth: 360)
            VStack(alignment: .leading, spacing: 6) {
                Text("NOTES")
                    .font(.caption2.weight(.semibold))
                    .tracking(1.2)
                    .foregroundStyle(.secondary)
                TextEditor(text: $notes)
                    .frame(minHeight: 120)
                    .padding(6)
                    .background(SpeedwagonTheme.secondaryPanelBackground(scheme))
                    .clipShape(RoundedRectangle(cornerRadius: 7))
                    .overlay(RoundedRectangle(cornerRadius: 7).stroke(SpeedwagonTheme.softLine(scheme)))
            }
            HStack(spacing: 10) {
                Button {
                    Task {
                        let saved = await state.saveContextProfile(
                            id: detail.context.id,
                            email: email,
                            phone: phone,
                            role: role,
                            company: company,
                            notes: notes
                        )
                        profileSaveMessage = saved ? "Saved locally." : state.statusMessage
                    }
                } label: {
                    Label("Save profile", systemImage: "checkmark.circle")
                }
                .buttonStyle(.borderedProminent)
                .tint(SpeedwagonTheme.accent(scheme))
                .speedwagonPointer()
                VStack(alignment: .leading, spacing: 2) {
                    Text("Stored locally for assistant context, draft metadata, and future contact workflows.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    if !profileSaveMessage.isEmpty {
                        Label(profileSaveMessage, systemImage: profileSaveMessage == "Saved locally." ? "checkmark.circle.fill" : "exclamationmark.triangle")
                            .font(.caption.weight(.medium))
                            .foregroundStyle(profileSaveMessage == "Saved locally." ? SpeedwagonTheme.success : SpeedwagonTheme.warning)
                    }
                }
            }
        }
    }

    private func loadProfileFields(_ context: ContextItem) {
        role = context.profileRole ?? ""
        company = context.profileCompany ?? ""
        email = context.profileEmail ?? ""
        phone = context.profilePhone ?? ""
        notes = context.profileNotes ?? ""
        profileSaveMessage = ""
    }

    private func labeledField(_ label: String, text: Binding<String>, placeholder: String = "") -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label.uppercased())
                .font(.caption2.weight(.semibold))
                .tracking(1.2)
                .foregroundStyle(.secondary)
            TextField(placeholder, text: text)
                .textFieldStyle(.plain)
                .padding(10)
                .background(SpeedwagonTheme.secondaryPanelBackground(scheme))
                .clipShape(RoundedRectangle(cornerRadius: 7))
                .overlay(RoundedRectangle(cornerRadius: 7).stroke(SpeedwagonTheme.softLine(scheme)))
        }
    }

    private func contextList<Content: View>(title: String, empty: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(.headline)
            content()
        }
    }

    private func connectionEvidence(_ detail: ContextDetailResponse) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            if detail.relationships.isEmpty {
                EmptyStateView(text: "No explicit relationships captured yet.")
            } else {
                ForEach(detail.relationships) { relationship in
                    HStack(spacing: 12) {
                        Text(relationship.targetContext.id == detail.context.id ? initials(relationship.sourceContext.name) : initials(relationship.targetContext.name))
                            .font(.callout.weight(.bold))
                            .frame(width: 44, height: 44)
                            .background(SpeedwagonTheme.contextKindColor(relationship.targetContext.id == detail.context.id ? relationship.sourceContext.kind : relationship.targetContext.kind))
                            .clipShape(RoundedRectangle(cornerRadius: 8))
                        VStack(alignment: .leading, spacing: 4) {
                            Text(relationship.displayLine)
                                .font(.callout.weight(.semibold))
                            HStack(spacing: 8) {
                                ToneChip(text: relationship.relationshipType.replacingOccurrences(of: "_", with: " "), tone: SpeedwagonTheme.accent(scheme))
                                if let evidence = relationship.evidence, !evidence.isEmpty {
                                    Text("Evidence: \(evidence)")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                        Spacer()
                        if let confidence = relationship.confidence {
                            VStack(alignment: .trailing) {
                                Text("\(Int(confidence * 100))%")
                                    .font(.headline)
                                    .foregroundStyle(SpeedwagonTheme.accent(scheme))
                                Text("confidence")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                    .padding(12)
                    .background(SpeedwagonTheme.secondaryPanelBackground(scheme))
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(SpeedwagonTheme.softLine(scheme)))
                }
                Button {
                    state.statusMessage = "Manual relationship editing is planned with persistent contact/context profiles."
                } label: {
                    Label("Add connection manually", systemImage: "plus")
                }
                .buttonStyle(.plain)
                .foregroundStyle(SpeedwagonTheme.secondaryText(scheme))
                .speedwagonPointer()
            }
        }
    }

    private func tabTitle(_ tab: ConnectionDetailTab, detail: ContextDetailResponse) -> String {
        switch tab {
        case .profile: return "Profile"
        case .tasks: return "Tasks (\(detail.tasks.count))"
        case .suggestions: return "Suggestions (\(detail.suggestions.count))"
        case .meetings: return "Meetings (\(detail.meetings.count))"
        case .connections: return "Connections (\(detail.relationships.count))"
        }
    }

    private func profileSubtitle(_ detail: ContextDetailResponse) -> String {
        if let related = detail.relatedContexts.first(where: { $0.kind.lowercased() == "project" }) {
            return "\(detail.context.kind.capitalized) · \(related.name)"
        }
        return detail.context.kind.capitalized
    }
}

private func initials(_ name: String) -> String {
    let parts = name
        .split(separator: " ")
        .prefix(2)
        .compactMap { $0.first }
    let value = String(parts).uppercased()
    return value.isEmpty ? "?" : value
}
