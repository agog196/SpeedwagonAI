import Foundation

public enum BundleMode: String, Equatable {
    case appBundle
    case swiftRun

    public var displayText: String {
        switch self {
        case .appBundle:
            return "app bundle"
        case .swiftRun:
            return "swift run"
        }
    }

    public static func from(bundlePathExtension: String) -> BundleMode {
        bundlePathExtension == "app" ? .appBundle : .swiftRun
    }
}

public enum PythonVersionStatus: Equatable {
    case notChecked
    case available(String)
    case unavailable(String)

    public var displayText: String {
        switch self {
        case .notChecked:
            return "not checked"
        case let .available(version):
            return version
        case let .unavailable(message):
            return "unavailable: \(message)"
        }
    }
}

public enum PythonVersionProbe {
    public static func arguments() -> [String] {
        ["--version"]
    }

    public static func commandPreview(executable: String = "python3.11") -> String {
        ([executable] + arguments()).joined(separator: " ")
    }

    public static func parse(output: String, terminationStatus: Int32) -> PythonVersionStatus {
        let text = output.trimmingCharacters(in: .whitespacesAndNewlines)
        guard terminationStatus == 0 else {
            return .unavailable(text.isEmpty ? "exited with status \(terminationStatus)" : text)
        }
        guard !text.isEmpty else {
            return .unavailable("no version output")
        }
        return .available(text)
    }
}

public struct LocalBetaDiagnosticsInput: Equatable {
    public let repoRoot: String
    public let repoRootSource: String
    public let backendState: String
    public let backendCommand: String
    public let pythonExecutable: String
    public let pythonVersion: String
    public let backendLogPath: String
    public let localTokenPresent: Bool
    public let openAIKeyPresent: Bool
    public let bundleMode: String
    public let notificationPermission: String

    public init(
        repoRoot: String,
        repoRootSource: String,
        backendState: String,
        backendCommand: String,
        pythonExecutable: String,
        pythonVersion: String,
        backendLogPath: String,
        localTokenPresent: Bool,
        openAIKeyPresent: Bool,
        bundleMode: String,
        notificationPermission: String
    ) {
        self.repoRoot = repoRoot
        self.repoRootSource = repoRootSource
        self.backendState = backendState
        self.backendCommand = backendCommand
        self.pythonExecutable = pythonExecutable
        self.pythonVersion = pythonVersion
        self.backendLogPath = backendLogPath
        self.localTokenPresent = localTokenPresent
        self.openAIKeyPresent = openAIKeyPresent
        self.bundleMode = bundleMode
        self.notificationPermission = notificationPermission
    }
}

public enum LocalBetaDiagnostics {
    public static func report(input: LocalBetaDiagnosticsInput, secrets: [String] = []) -> String {
        let lines = [
            "SpeedwagonAI Local Beta Diagnostics",
            "Repo root: \(input.repoRoot.isEmpty ? "missing" : input.repoRoot)",
            "Repo root source: \(input.repoRootSource)",
            "Backend state: \(input.backendState)",
            "Backend command: \(input.backendCommand.isEmpty ? "not started by app" : input.backendCommand)",
            "Python executable: \(input.pythonExecutable)",
            "Python version: \(input.pythonVersion)",
            "Backend log: \(input.backendLogPath.isEmpty ? "not available" : input.backendLogPath)",
            "Local API token: \(input.localTokenPresent ? "present" : "missing")",
            "OpenAI API key: \(input.openAIKeyPresent ? "present" : "missing")",
            "Bundle mode: \(input.bundleMode)",
            "Notification permission: \(input.notificationPermission)"
        ]
        return redact(lines.joined(separator: "\n"), secrets: secrets)
    }

    public static func redact(_ text: String, secrets: [String]) -> String {
        var output = text
        for secret in secrets where !secret.isEmpty {
            output = output.replacingOccurrences(of: secret, with: "[REDACTED]")
        }
        return output
            .replacingOccurrences(
                of: #"sk-[A-Za-z0-9_\-]{12,}"#,
                with: "sk-[REDACTED]",
                options: .regularExpression
            )
            .replacingOccurrences(
                of: #"Bearer\s+[A-Za-z0-9_\.\-]{12,}"#,
                with: "Bearer [REDACTED]",
                options: .regularExpression
            )
    }
}
