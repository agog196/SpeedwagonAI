import Combine
import Foundation
import SpeedwagonAICore

@MainActor
final class AppState: ObservableObject {
    @Published var tasks: [TaskItem] = []
    @Published var commitments: [TaskItem] = []
    @Published var dailyBrief: DailyBriefResponse?
    @Published var capabilities: [AssistantCapability] = []
    @Published var settings: SettingsResponse?
    @Published var captureStatus: CaptureSession?
    @Published var captureDiagnostics: CaptureDiagnostics?
    @Published var assistantVoiceStatus: CaptureSession?
    @Published var pendingActions: [PendingAssistantAction] = []
    @Published var meetingCaptureTitle = ""
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

    init(client: SpeedwagonAPIClient = SpeedwagonAPIClient()) {
        self.client = client
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
        } catch {
            failures.append("diagnostics")
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

    func startMeetingCapture() async {
        let title = meetingCaptureTitle.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !title.isEmpty else {
            statusMessage = "Meeting title is required."
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
}
