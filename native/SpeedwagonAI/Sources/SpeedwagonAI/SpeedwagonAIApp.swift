import AppKit
import SwiftUI

@main
struct SpeedwagonAIApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var state = AppState()

    var body: some Scene {
        WindowGroup("SpeedwagonAI", id: "main") {
            ContentView()
                .environmentObject(state)
        }
        .defaultSize(width: 1160, height: 760)

        Window("Command Palette", id: "commandPalette") {
            CommandPaletteView()
                .environmentObject(state)
        }
        .defaultSize(width: 680, height: 460)

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
                openWindow(id: "commandPalette")
                DispatchQueue.main.async {
                    activateSpeedwagon()
                }
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
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApplication.shared.setActivationPolicy(.regular)
        DispatchQueue.main.async {
            activateSpeedwagon()
        }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        activateSpeedwagon()
        return true
    }
}

func activateSpeedwagon() {
    NSApplication.shared.activate(ignoringOtherApps: true)
    NSApplication.shared.windows.first?.makeKeyAndOrderFront(nil)
}
