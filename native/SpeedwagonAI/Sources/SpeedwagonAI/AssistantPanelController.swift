import AppKit
import SwiftUI

@MainActor
final class AssistantPanelController {
    static let shared = AssistantPanelController()

    static let contentSize = NSSize(width: 860, height: 560)

    private var panel: AssistantPanel?
    private var hostingController: NSHostingController<AnyView>?

    private init() {}

    var isVisible: Bool {
        panel?.isVisible == true
    }

    func toggle(state: AppState) {
        if isVisible {
            close()
        } else {
            show(state: state)
        }
    }

    func show(state: AppState) {
        let panel = panel ?? makePanel(state: state)
        self.panel = panel
        panel.setContentSize(Self.contentSize)
        if let screen = targetScreen(excluding: panel) {
            position(panel, on: screen)
        }
        panel.orderFrontRegardless()
        panel.makeKey()
    }

    func close() {
        panel?.orderOut(nil)
    }

    private func makePanel(state: AppState) -> AssistantPanel {
        let root = CommandPaletteView()
            .environmentObject(state)
        let hosting = NSHostingController(rootView: AnyView(root))
        hostingController = hosting

        let panel = AssistantPanel(
            contentRect: NSRect(origin: .zero, size: Self.contentSize),
            styleMask: [.nonactivatingPanel, .titled, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        panel.title = "SpeedwagonAI"
        panel.contentViewController = hosting
        panel.isFloatingPanel = true
        panel.level = .floating
        panel.hidesOnDeactivate = false
        panel.isReleasedWhenClosed = false
        panel.isMovableByWindowBackground = true
        panel.titleVisibility = .hidden
        panel.titlebarAppearsTransparent = true
        panel.standardWindowButton(.closeButton)?.isHidden = true
        panel.standardWindowButton(.miniaturizeButton)?.isHidden = true
        panel.standardWindowButton(.zoomButton)?.isHidden = true
        panel.collectionBehavior = [
            .canJoinAllSpaces,
            .fullScreenAuxiliary,
            .transient,
            .ignoresCycle,
            .stationary,
        ]
        return panel
    }

    private func targetScreen(excluding panel: NSPanel) -> NSScreen? {
        NSApplication.shared.windows.first { window in
            window !== panel && window.isVisible && window.screen != nil
        }?.screen ?? NSScreen.main
    }

    private func position(_ panel: NSPanel, on screen: NSScreen) {
        let frame = screen.visibleFrame
        let size = panel.frame.size
        let x = frame.midX - size.width / 2
        let y = frame.midY - size.height / 2
        panel.setFrameOrigin(NSPoint(x: max(frame.minX + 16, x), y: max(frame.minY + 16, y)))
    }
}

final class AssistantPanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }

    override func cancelOperation(_ sender: Any?) {
        orderOut(nil)
    }
}
