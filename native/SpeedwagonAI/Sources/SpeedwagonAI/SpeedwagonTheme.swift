import AppKit
import SwiftUI

enum SpeedwagonTheme {
    static func appBackground(_ scheme: ColorScheme) -> Color {
        scheme == .dark ? Color(red: 0.10, green: 0.11, blue: 0.10) : Color(red: 0.96, green: 0.96, blue: 0.93)
    }

    static func sidebarBackground(_ scheme: ColorScheme) -> Color {
        scheme == .dark ? Color(red: 0.13, green: 0.14, blue: 0.13) : Color(red: 0.92, green: 0.93, blue: 0.91)
    }

    static func panelBackground(_ scheme: ColorScheme) -> Color {
        scheme == .dark ? Color(red: 0.16, green: 0.17, blue: 0.16) : Color.white
    }

    static func secondaryPanelBackground(_ scheme: ColorScheme) -> Color {
        scheme == .dark ? Color(red: 0.19, green: 0.20, blue: 0.19) : Color(red: 0.98, green: 0.98, blue: 0.96)
    }

    static func line(_ scheme: ColorScheme) -> Color {
        scheme == .dark ? Color(red: 0.30, green: 0.32, blue: 0.30) : Color(red: 0.85, green: 0.85, blue: 0.82)
    }

    static func accent(_ scheme: ColorScheme) -> Color {
        scheme == .dark ? Color(red: 0.36, green: 0.72, blue: 0.65) : Color(red: 0.09, green: 0.42, blue: 0.36)
    }

    static func danger(_ scheme: ColorScheme) -> Color {
        scheme == .dark ? Color(red: 0.92, green: 0.46, blue: 0.50) : Color(red: 0.61, green: 0.24, blue: 0.27)
    }
}

struct SpeedwagonPanel: ViewModifier {
    @Environment(\.colorScheme) private var scheme

    func body(content: Content) -> some View {
        content
            .padding(16)
            .background(SpeedwagonTheme.panelBackground(scheme))
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(SpeedwagonTheme.line(scheme)))
    }
}

struct SpeedwagonSecondaryPanel: ViewModifier {
    @Environment(\.colorScheme) private var scheme

    func body(content: Content) -> some View {
        content
            .padding(12)
            .background(SpeedwagonTheme.secondaryPanelBackground(scheme))
            .clipShape(RoundedRectangle(cornerRadius: 6))
            .overlay(RoundedRectangle(cornerRadius: 6).stroke(SpeedwagonTheme.line(scheme)))
    }
}

extension View {
    func speedwagonPanel() -> some View {
        modifier(SpeedwagonPanel())
    }

    func speedwagonSecondaryPanel() -> some View {
        modifier(SpeedwagonSecondaryPanel())
    }

    func speedwagonPointer() -> some View {
        onHover { inside in
            if inside {
                NSCursor.pointingHand.push()
            } else {
                NSCursor.pop()
            }
        }
    }
}
