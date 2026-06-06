import XCTest
@testable import SpeedwagonAICore

final class LocalBetaShellTests: XCTestCase {
    func testBackendLaunchConfigurationBuildsExpectedCommandAndEnvironment() {
        let config = BackendLaunchConfiguration(
            repoRoot: "/tmp/SpeedwagonAI",
            apiToken: "local-token",
            openAIAPIKey: "openai-key"
        )

        XCTAssertEqual(config.pythonExecutable, "python3.11")
        XCTAssertEqual(config.arguments, ["-m", "speedwagon_ai.cli", "app", "--host", "127.0.0.1", "--port", "8765"])
        XCTAssertEqual(config.commandPreview, "python3.11 -m speedwagon_ai.cli app --host 127.0.0.1 --port 8765")
        XCTAssertEqual(config.environment["SPEEDWAGON_API_TOKEN"], "local-token")
        XCTAssertEqual(config.environment["OPENAI_API_KEY"], "openai-key")
        XCTAssertTrue(config.logPath.hasSuffix("data/logs/backend.log"))
    }

    func testRepoRootDiscoveryReportsEnvironmentSource() throws {
        let discovery = try BackendManager.discoverRepoRootDetails(
            startingAt: URL(fileURLWithPath: "/tmp"),
            environment: ["SPEEDWAGON_REPO_ROOT": "/tmp/SpeedwagonAI"]
        )

        XCTAssertEqual(discovery.path, "/tmp/SpeedwagonAI")
        XCTAssertEqual(discovery.source, .environment)
        XCTAssertEqual(discovery.displaySource, "SPEEDWAGON_REPO_ROOT")
    }

    func testPythonVersionProbeParsesOutputs() {
        XCTAssertEqual(PythonVersionProbe.arguments(), ["--version"])
        XCTAssertEqual(PythonVersionProbe.commandPreview(), "python3.11 --version")
        XCTAssertEqual(PythonVersionProbe.parse(output: "Python 3.11.9\n", terminationStatus: 0), .available("Python 3.11.9"))
        XCTAssertEqual(PythonVersionProbe.parse(output: "", terminationStatus: 127), .unavailable("exited with status 127"))
    }

    func testLocalBetaDiagnosticsReportRedactsSecrets() {
        let input = LocalBetaDiagnosticsInput(
            repoRoot: "/tmp/SpeedwagonAI",
            repoRootSource: "SPEEDWAGON_REPO_ROOT",
            backendState: "running",
            backendCommand: "python3.11 -m speedwagon_ai.cli app --host 127.0.0.1 --port 8765",
            pythonExecutable: "python3.11",
            pythonVersion: "Python 3.11.9",
            backendLogPath: "/tmp/SpeedwagonAI/data/logs/backend.log",
            localTokenPresent: true,
            openAIKeyPresent: true,
            bundleMode: BundleMode.from(bundlePathExtension: "app").displayText,
            notificationPermission: "authorized"
        )

        let report = LocalBetaDiagnostics.report(
            input: input,
            secrets: ["local-token-secret", "sk-testsecret123456"]
        ) + "\nAuthorization: Bearer local-token-secret\nOpenAI: sk-testsecret123456"
        let redacted = LocalBetaDiagnostics.redact(report, secrets: ["local-token-secret", "sk-testsecret123456"])

        XCTAssertTrue(redacted.contains("SpeedwagonAI Local Beta Diagnostics"))
        XCTAssertTrue(redacted.contains("Bundle mode: app bundle"))
        XCTAssertFalse(redacted.contains("local-token-secret"))
        XCTAssertFalse(redacted.contains("sk-testsecret123456"))
        XCTAssertTrue(redacted.contains("[REDACTED]"))
    }

    func testKeychainStoreCanSaveLoadAndDeleteTestSecret() throws {
        let store = KeychainStore(service: "SpeedwagonAI.Tests.\(UUID().uuidString)")
        let account = "test-secret"

        try store.save("secret-value", account: account)
        XCTAssertEqual(try store.load(account: account), "secret-value")

        try store.delete(account: account)
        XCTAssertNil(try store.load(account: account))
    }

    func testDecodesSystemResponses() throws {
        let logsJSON = """
        {
          "log_dir": "data/logs",
          "app_log_path": "data/logs/speedwagon.log",
          "backend_log_path": "data/logs/backend.log",
          "app_log_exists": true,
          "backend_log_exists": false,
          "log_tail": "line",
          "backend_log_tail": ""
        }
        """.data(using: .utf8)!
        let privacyJSON = """
        {
          "db_path": "data/speedwagon.db",
          "notes_dir": "notes",
          "audio_dir": "audio",
          "transcripts_dir": "transcripts",
          "logs_dir": "data/logs",
          "export_supported": true,
          "wipe_supported": true,
          "wipe_confirmation": "DELETE-SPEEDWAGON-DATA",
          "existing_paths": ["data"],
          "path_visibility_note": "Local paths are shown only in Settings, logs, privacy/debug, and export surfaces.",
          "local_data_dirs": {
            "database": "data/speedwagon.db",
            "notes": "notes"
          },
          "external_services": {
            "openai": {
              "configured": true,
              "purpose": "LLM extraction and assistant answers."
            },
            "web_search": {
              "configured": false,
              "purpose": "Future explicit web search."
            }
          },
          "data_disclosures": [
            {
              "service": "OpenAI",
              "enabled": true,
              "data": "Selected prompts and context.",
              "trigger": "Assistant and intelligence actions."
            }
          ],
          "counts": {"meetings": 2, "tasks": 3}
        }
        """.data(using: .utf8)!
        let exportJSON = """
        {
          "status": "exported",
          "path": "data/exports/speedwagon.zip",
          "file_count": 4
        }
        """.data(using: .utf8)!
        let wipeJSON = """
        {
          "status": "wiped",
          "removed": ["data", "notes"]
        }
        """.data(using: .utf8)!

        let logs = try SpeedwagonJSON.decoder.decode(SystemLogsResponse.self, from: logsJSON)
        let privacy = try SpeedwagonJSON.decoder.decode(PrivacyStatusResponse.self, from: privacyJSON)
        let export = try SpeedwagonJSON.decoder.decode(SystemExportResponse.self, from: exportJSON)
        let wipe = try SpeedwagonJSON.decoder.decode(SystemWipeResponse.self, from: wipeJSON)

        XCTAssertEqual(logs.appLogPath, "data/logs/speedwagon.log")
        XCTAssertEqual(privacy.wipeConfirmation, "DELETE-SPEEDWAGON-DATA")
        XCTAssertEqual(privacy.counts["tasks"], 3)
        XCTAssertEqual(privacy.pathVisibilityNote, "Local paths are shown only in Settings, logs, privacy/debug, and export surfaces.")
        XCTAssertEqual(privacy.localDataDirs?["database"], "data/speedwagon.db")
        XCTAssertEqual(privacy.externalServices?["openai"]?.configured, true)
        XCTAssertEqual(privacy.externalServices?["web_search"]?.configured, false)
        XCTAssertEqual(privacy.dataDisclosures?.first?.service, "OpenAI")
        XCTAssertEqual(export.fileCount, 4)
        XCTAssertEqual(wipe.removed, ["data", "notes"])
    }
}
