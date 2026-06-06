import AppKit
import SwiftUI

// Color system ported from the Claude Design token set (oklch → sRGB).
// Dark-primary, muted teal accent, semantic status hues shared across themes.
enum SpeedwagonTheme {
    // MARK: Surfaces

    static func appBackground(_ scheme: ColorScheme) -> Color {
        scheme == .dark
            ? Color(red: 0.082, green: 0.094, blue: 0.087)
            : Color(red: 0.954, green: 0.964, blue: 0.955)
    }

    static func sidebarBackground(_ scheme: ColorScheme) -> Color {
        scheme == .dark
            ? Color(red: 0.107, green: 0.122, blue: 0.113)
            : Color(red: 0.920, green: 0.932, blue: 0.921)
    }

    static func toolbarBackground(_ scheme: ColorScheme) -> Color {
        scheme == .dark
            ? Color(red: 0.116, green: 0.131, blue: 0.123)
            : Color(red: 0.975, green: 0.983, blue: 0.976)
    }

    static func panelBackground(_ scheme: ColorScheme) -> Color {
        scheme == .dark
            ? Color(red: 0.126, green: 0.141, blue: 0.132)
            : Color.white
    }

    static func secondaryPanelBackground(_ scheme: ColorScheme) -> Color {
        scheme == .dark
            ? Color(red: 0.162, green: 0.180, blue: 0.169)
            : Color(red: 0.960, green: 0.971, blue: 0.962)
    }

    static func elevatedBackground(_ scheme: ColorScheme) -> Color {
        scheme == .dark
            ? Color(red: 0.194, green: 0.215, blue: 0.203)
            : Color(red: 0.926, green: 0.939, blue: 0.928)
    }

    // MARK: Borders

    static func line(_ scheme: ColorScheme) -> Color {
        scheme == .dark
            ? Color.white.opacity(0.09)
            : Color.black.opacity(0.11)
    }

    static func softLine(_ scheme: ColorScheme) -> Color {
        scheme == .dark
            ? Color.white.opacity(0.05)
            : Color.black.opacity(0.06)
    }

    static func strongLine(_ scheme: ColorScheme) -> Color {
        scheme == .dark
            ? Color.white.opacity(0.15)
            : Color.black.opacity(0.20)
    }

    // MARK: Text

    static func primaryText(_ scheme: ColorScheme) -> Color {
        scheme == .dark
            ? Color(red: 0.898, green: 0.913, blue: 0.904)
            : Color(red: 0.126, green: 0.147, blue: 0.135)
    }

    static func secondaryText(_ scheme: ColorScheme) -> Color {
        scheme == .dark
            ? Color(red: 0.629, green: 0.651, blue: 0.638)
            : Color(red: 0.327, green: 0.352, blue: 0.337)
    }

    static func tertiaryText(_ scheme: ColorScheme) -> Color {
        scheme == .dark
            ? Color(red: 0.442, green: 0.462, blue: 0.450)
            : Color(red: 0.484, green: 0.510, blue: 0.494)
    }

    // MARK: Accent

    static func accent(_ scheme: ColorScheme) -> Color {
        scheme == .dark
            ? Color(red: 0.348, green: 0.689, blue: 0.659)
            : Color(red: 0.000, green: 0.458, blue: 0.430)
    }

    static func accentSoft(_ scheme: ColorScheme) -> Color {
        accent(scheme).opacity(scheme == .dark ? 0.15 : 0.13)
    }

    // MARK: Semantic status hues (shared across themes)

    static let danger = Color(red: 0.847, green: 0.384, blue: 0.361)   // overdue
    static let warning = Color(red: 0.869, green: 0.649, blue: 0.322)  // waiting / due-today
    static let snoozed = Color(red: 0.468, green: 0.612, blue: 0.762)  // snoozed
    static let success = Color(red: 0.460, green: 0.715, blue: 0.514)  // done
    static let info = Color(red: 0.370, green: 0.663, blue: 0.799)     // info / unscheduled
    static let context = Color(red: 0.658, green: 0.565, blue: 0.830)  // person/project/topic

    /// Back-compat: callers passing a scheme still resolve to the danger hue.
    static func danger(_ scheme: ColorScheme) -> Color { danger }

    /// Maps a task/suggestion status string to its semantic color.
    static func statusColor(_ status: String) -> Color {
        switch status.lowercased() {
        case "overdue", "canceled": return danger
        case "waiting", "uncertain", "due-today", "due_today": return warning
        case "snoozed", "stale": return snoozed
        case "done", "accepted": return success
        default: return info
        }
    }

    /// Maps a context kind to its avatar/chip hue.
    static func contextKindColor(_ kind: String) -> Color {
        switch kind.lowercased() {
        case "person": return context
        case "project": return Color(red: 0.348, green: 0.689, blue: 0.659)
        case "topic": return warning
        default: return info
        }
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
            .overlay(RoundedRectangle(cornerRadius: 6).stroke(SpeedwagonTheme.softLine(scheme)))
    }
}

/// A small capsule tag with an optional semantic tone, matching the design's Chip.
struct ToneChip: View {
    @Environment(\.colorScheme) private var scheme
    let text: String
    var tone: Color?
    var systemImage: String?
    var dot: Bool = false

    var body: some View {
        HStack(spacing: 4) {
            if dot, let tone {
                Circle().fill(tone).frame(width: 6, height: 6)
            }
            if let systemImage {
                Image(systemName: systemImage).font(.system(size: 9, weight: .semibold))
            }
            Text(text).font(.system(size: 11, weight: .medium))
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 2.5)
        .foregroundStyle(tone ?? SpeedwagonTheme.secondaryText(scheme))
        .background((tone ?? SpeedwagonTheme.secondaryText(scheme)).opacity(tone == nil ? 0.10 : 0.15))
        .overlay(
            Capsule().stroke((tone ?? SpeedwagonTheme.line(scheme)).opacity(tone == nil ? 0.5 : 0.30))
        )
        .clipShape(Capsule())
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
        modifier(SpeedwagonHoverPointerModifier())
    }
}

private struct SpeedwagonHoverPointerModifier: ViewModifier {
    @Environment(\.colorScheme) private var scheme
    @State private var hovering = false

    func body(content: Content) -> some View {
        content
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(hovering ? SpeedwagonTheme.elevatedBackground(scheme).opacity(0.70) : Color.clear)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .stroke(hovering ? SpeedwagonTheme.strongLine(scheme).opacity(0.65) : Color.clear)
            )
            .animation(.easeInOut(duration: 0.12), value: hovering)
            .onHover { inside in
                hovering = inside
                if inside {
                    NSCursor.pointingHand.push()
                } else {
                    NSCursor.pop()
                }
            }
    }
}
