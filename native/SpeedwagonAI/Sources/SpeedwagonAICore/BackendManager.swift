import Foundation

public enum BackendState: String, Equatable {
    case notStarted
    case starting
    case running
    case stopped
    case failed
}

public struct BackendLaunchConfiguration: Equatable {
    public let repoRoot: String
    public let pythonExecutable: String
    public let host: String
    public let port: Int
    public let logPath: String
    public let apiToken: String
    public let openAIAPIKey: String?

    public init(
        repoRoot: String,
        pythonExecutable: String = "python3.11",
        host: String = "127.0.0.1",
        port: Int = 8765,
        logPath: String? = nil,
        apiToken: String,
        openAIAPIKey: String? = nil
    ) {
        self.repoRoot = repoRoot
        self.pythonExecutable = pythonExecutable
        self.host = host
        self.port = port
        self.logPath = logPath ?? URL(fileURLWithPath: repoRoot).appending(path: "data/logs/backend.log").path
        self.apiToken = apiToken
        self.openAIAPIKey = openAIAPIKey
    }

    public var arguments: [String] {
        ["-m", "speedwagon_ai.cli", "app", "--host", host, "--port", String(port)]
    }

    public var commandPreview: String {
        ([pythonExecutable] + arguments).joined(separator: " ")
    }

    public var environment: [String: String] {
        var values = ProcessInfo.processInfo.environment
        values["SPEEDWAGON_API_TOKEN"] = apiToken
        values["SPEEDWAGON_API_TOKEN_PATH"] = URL(fileURLWithPath: repoRoot).appending(path: "data/local_api_token").path
        if let openAIAPIKey, !openAIAPIKey.isEmpty {
            values["OPENAI_API_KEY"] = openAIAPIKey
        }
        return values
    }
}

public final class BackendManager {
    public private(set) var state: BackendState = .notStarted
    public private(set) var lastError: String?
    public private(set) var startedProcessIdentifier: Int32?

    private var process: Process?

    public init() {}

    deinit {
        stop()
    }

    public func makeConfiguration(
        repoRoot: String? = nil,
        keychain: KeychainStore = .shared
    ) throws -> BackendLaunchConfiguration {
        let root = try repoRoot ?? Self.discoverRepoRoot()
        let token = try keychain.ensureLocalAPIToken()
        let openAIKey = try keychain.load(account: KeychainAccount.openAIAPIKey)
        return BackendLaunchConfiguration(repoRoot: root, apiToken: token, openAIAPIKey: openAIKey)
    }

    public func start(configuration: BackendLaunchConfiguration) throws {
        guard process == nil || process?.isRunning == false else {
            state = .running
            return
        }
        state = .starting
        lastError = nil

        let logURL = URL(fileURLWithPath: configuration.logPath)
        try FileManager.default.createDirectory(at: logURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        FileManager.default.createFile(atPath: logURL.path, contents: nil)
        let handle = try FileHandle(forWritingTo: logURL)
        try handle.seekToEnd()

        let launched = Process()
        launched.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        launched.arguments = [configuration.pythonExecutable] + configuration.arguments
        launched.currentDirectoryURL = URL(fileURLWithPath: configuration.repoRoot)
        launched.environment = configuration.environment
        launched.standardOutput = handle
        launched.standardError = handle
        launched.terminationHandler = { [weak self] process in
            guard let self else { return }
            self.state = process.terminationStatus == 0 ? .stopped : .failed
            self.lastError = process.terminationStatus == 0 ? nil : "Backend exited with status \(process.terminationStatus)."
            try? handle.close()
        }

        do {
            try launched.run()
            process = launched
            startedProcessIdentifier = launched.processIdentifier
            state = .running
        } catch {
            state = .failed
            lastError = error.localizedDescription
            try? handle.close()
            throw error
        }
    }

    public func stop() {
        guard let process, process.isRunning else {
            return
        }
        process.terminate()
        self.process = nil
        state = .stopped
    }

    public static func discoverRepoRoot(startingAt start: URL = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)) throws -> String {
        try discoverRepoRootDetails(startingAt: start).path
    }

    public static func discoverRepoRootDetails(
        startingAt start: URL = URL(fileURLWithPath: FileManager.default.currentDirectoryPath),
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) throws -> RepoRootDiscovery {
        if let configured = environment["SPEEDWAGON_REPO_ROOT"], !configured.isEmpty {
            return RepoRootDiscovery(path: configured, source: .environment)
        }
        var directory = start
        for _ in 0..<8 {
            if FileManager.default.fileExists(atPath: directory.appending(path: "pyproject.toml").path),
               FileManager.default.fileExists(atPath: directory.appending(path: "speedwagon_ai").path) {
                return RepoRootDiscovery(path: directory.path, source: directory == start ? .currentDirectory : .ancestor)
            }
            directory.deleteLastPathComponent()
        }
        throw BackendManagerError.repoRootNotFound
    }
}

public struct RepoRootDiscovery: Equatable {
    public let path: String
    public let source: RepoRootDiscoverySource

    public init(path: String, source: RepoRootDiscoverySource) {
        self.path = path
        self.source = source
    }

    public var displaySource: String {
        switch source {
        case .environment:
            return "SPEEDWAGON_REPO_ROOT"
        case .currentDirectory:
            return "current directory"
        case .ancestor:
            return "parent directory search"
        }
    }
}

public enum RepoRootDiscoverySource: String, Equatable {
    case environment
    case currentDirectory
    case ancestor
}

public enum BackendManagerError: Error, LocalizedError, Equatable {
    case repoRootNotFound

    public var errorDescription: String? {
        switch self {
        case .repoRootNotFound:
            return "Could not find SpeedwagonAI repo root. Set SPEEDWAGON_REPO_ROOT."
        }
    }
}
