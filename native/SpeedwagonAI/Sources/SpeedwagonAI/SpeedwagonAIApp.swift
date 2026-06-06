import AppKit
import Carbon.HIToolbox
import SwiftUI
import UserNotifications

@main
struct SpeedwagonAIApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var state = AppState.shared

    var body: some Scene {
        WindowGroup("SpeedwagonAI", id: "main") {
            ContentView()
                .environmentObject(state)
        }
        .defaultSize(width: 1160, height: 760)

        MenuBarExtra {
            MenuBarContent()
                .environmentObject(state)
        } label: {
            Label("SpeedwagonAI", systemImage: state.isConnected ? "bolt.circle.fill" : "bolt.circle")
        }
        .menuBarExtraStyle(.menu)
    }
}

struct MenuBarContent: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(state.backendStatusLabel, systemImage: state.isConnected ? "checkmark.circle.fill" : "xmark.circle")

            if !state.isConnected {
                Text("Start backend with: speedwagon app")
                    .font(.caption)
            }

            Divider()

            Button("Open Main Window") {
                openWindow(id: "main")
                DispatchQueue.main.async {
                    activateSpeedwagon()
                }
            }

            Button("Open Command Palette") {
                AssistantPanelController.shared.toggle(state: state)
            }
            .keyboardShortcut("k", modifiers: .command)

            Button("Refresh") {
                Task { await state.refreshAll() }
            }

            Divider()

            Button("Quit SpeedwagonAI") {
                NSApplication.shared.terminate(nil)
            }
            .keyboardShortcut("q", modifiers: .command)
        }
        .task {
            await state.refreshAll()
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var hotKey: GlobalHotKey?

    func applicationDidFinishLaunching(_ notification: Notification) {
        if supportsNativeNotifications() {
            UNUserNotificationCenter.current().delegate = self
            AppState.shared.startNotificationPollingIfNeeded()
        } else {
            Task { @MainActor in
                AppState.shared.notificationPermissionStatus = "unsupported"
                AppState.shared.statusMessage = "Native notifications require an app bundle; swift run disables them."
            }
        }
        NSApplication.shared.setActivationPolicy(.regular)
        hotKey = GlobalHotKey(keyCode: kVK_Space, modifiers: optionKey) {
            Task { @MainActor in
                AssistantPanelController.shared.toggle(state: AppState.shared)
            }
        }
        DispatchQueue.main.async {
            activateSpeedwagon()
        }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        activateSpeedwagon()
        return true
    }

    func applicationWillTerminate(_ notification: Notification) {
        AppState.shared.stopManagedBackend()
    }
}

extension AppDelegate: UNUserNotificationCenterDelegate {
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse
    ) async {
        let suggestionId = response.notification.request.content.userInfo["suggestion_id"] as? Int
        await MainActor.run {
            activateSpeedwagon()
            Task {
                if let suggestionId {
                    await AppState.shared.openSuggestionFromNotification(id: suggestionId)
                } else {
                    await AppState.shared.refreshAll(updateStatus: false)
                }
            }
        }
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification
    ) async -> UNNotificationPresentationOptions {
        [.banner, .sound]
    }
}

func activateSpeedwagon() {
    NSApplication.shared.activate(ignoringOtherApps: true)
    NSApplication.shared.windows.first?.makeKeyAndOrderFront(nil)
}
