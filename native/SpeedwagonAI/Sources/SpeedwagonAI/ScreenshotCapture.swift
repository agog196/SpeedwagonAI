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
    guard let image = CGDisplayCreateImage(CGMainDisplayID()) else {
        throw ScreenshotCaptureError.captureFailed
    }
    let bitmap = NSBitmapImageRep(cgImage: image)
    guard let data = bitmap.representation(using: .png, properties: [:]) else {
        throw ScreenshotCaptureError.pngEncodingFailed
    }
    return data
}

@MainActor
func captureMainDisplayPNGExcludingSpeedwagonWindows() async throws -> Data {
    let windows = NSApplication.shared.windows.filter { $0.isVisible }
    windows.forEach { $0.orderOut(nil) }
    defer {
        windows.forEach { $0.makeKeyAndOrderFront(nil) }
        activateSpeedwagon()
    }
    try await Task.sleep(nanoseconds: 250_000_000)
    return try captureMainDisplayPNG()
}
