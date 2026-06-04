import AppKit
import CoreGraphics
import Foundation

enum ScreenshotCaptureError: LocalizedError {
    case captureFailed
    case pngEncodingFailed

    var errorDescription: String? {
        switch self {
        case .captureFailed:
            return "Could not capture the main display. macOS Screen Recording permission may be required."
        case .pngEncodingFailed:
            return "Could not encode the screenshot as PNG."
        }
    }
}

func captureMainDisplayPNG() throws -> Data {
    try captureDisplayPNG(displayID: CGMainDisplayID())
}

func captureDisplayPNG(displayID: CGDirectDisplayID) throws -> Data {
    guard let image = CGDisplayCreateImage(displayID) else {
        throw ScreenshotCaptureError.captureFailed
    }
    let bitmap = NSBitmapImageRep(cgImage: image)
    guard let data = bitmap.representation(using: .png, properties: [:]) else {
        throw ScreenshotCaptureError.pngEncodingFailed
    }
    return data
}

@MainActor
func activeDisplayID() -> CGDirectDisplayID {
    let mouseLocation = NSEvent.mouseLocation
    let screen = NSScreen.screens.first { screen in
        screen.frame.contains(mouseLocation)
    } ?? NSScreen.main
    let key = NSDeviceDescriptionKey("NSScreenNumber")
    if let number = screen?.deviceDescription[key] as? NSNumber {
        return CGDirectDisplayID(number.uint32Value)
    }
    return CGMainDisplayID()
}

@MainActor
func captureMainDisplayPNGExcludingSpeedwagonWindows() async throws -> Data {
    let windows = NSApplication.shared.windows.filter { $0.isVisible }
    let keyWindow = NSApplication.shared.keyWindow
    windows.forEach { $0.orderOut(nil) }
    defer {
        windows.forEach { $0.orderFront(nil) }
        keyWindow?.makeKey()
    }
    try await Task.sleep(nanoseconds: 250_000_000)
    return try captureDisplayPNG(displayID: activeDisplayID())
}
