import AppKit
import AVFoundation
import CoreMedia
import ScreenCaptureKit
import SpeedwagonAICore

struct NativeMeetingRecorderResult {
    let audioPath: String
    let warnings: [String]
}

struct NativeCapturePermissionSnapshot: Equatable {
    let nativeAvailable: Bool
    let screenRecordingGranted: Bool
    let microphoneStatus: String

    var rows: [(String, String)] {
        [
            ("Native capture", nativeAvailable ? "Available" : "Unavailable"),
            ("Screen Recording", screenRecordingGranted ? "Allowed" : "Needs permission"),
            ("Microphone", microphoneStatus)
        ]
    }
}

protocol NativeMeetingRecording {
    var isRecording: Bool { get }
    func permissionSnapshot() -> NativeCapturePermissionSnapshot
    func start(session: CaptureSession) async throws
    func stop() async throws -> NativeMeetingRecorderResult
}

enum NativeMeetingRecorderError: LocalizedError {
    case missingPath(String)
    case unsupported
    case alreadyRecording
    case notRecording
    case noDisplay
    case screenRecordingPermission
    case microphonePermission
    case streamOutput(Error)

    var errorDescription: String? {
        switch self {
        case let .missingPath(name):
            return "Native capture is missing \(name)."
        case .unsupported:
            return "Native ScreenCaptureKit capture is unavailable on this Mac."
        case .alreadyRecording:
            return "Native capture is already recording."
        case .notRecording:
            return "Native capture is not recording."
        case .noDisplay:
            return "Could not find the active display for ScreenCaptureKit capture."
        case .screenRecordingPermission:
            return "Screen Recording permission is required for native system audio capture."
        case .microphonePermission:
            return "Microphone permission is required to capture your voice."
        case let .streamOutput(error):
            return "ScreenCaptureKit capture failed: \(error.localizedDescription)"
        }
    }
}

final class ScreenCaptureKitMeetingRecorder: NSObject, NativeMeetingRecording {
    private let outputQueue = DispatchQueue(label: "speedwagon.native.capture.output")
    private var stream: SCStream?
    private var systemWriter: SampleBufferAudioWriter?
    private var fallbackMicRecorder: MicrophoneAudioRecorder?
    private var session: CaptureSession?
    private var warnings: [String] = []

    var isRecording: Bool {
        stream != nil
    }

    func permissionSnapshot() -> NativeCapturePermissionSnapshot {
        let micStatus = AVCaptureDevice.authorizationStatus(for: .audio)
        return NativeCapturePermissionSnapshot(
            nativeAvailable: true,
            screenRecordingGranted: CGPreflightScreenCaptureAccess(),
            microphoneStatus: microphoneStatusText(micStatus)
        )
    }

    func start(session: CaptureSession) async throws {
        guard stream == nil else {
            throw NativeMeetingRecorderError.alreadyRecording
        }
        guard let audioPath = session.audioPath, !audioPath.isEmpty else {
            throw NativeMeetingRecorderError.missingPath("audio_path")
        }
        guard let systemPath = session.systemAudioPath, !systemPath.isEmpty else {
            throw NativeMeetingRecorderError.missingPath("system_audio_path")
        }
        guard let microphonePath = session.microphoneAudioPath, !microphonePath.isEmpty else {
            throw NativeMeetingRecorderError.missingPath("microphone_audio_path")
        }

        try await ensureMicrophonePermission()
        if !CGPreflightScreenCaptureAccess() {
            _ = CGRequestScreenCaptureAccess()
            throw NativeMeetingRecorderError.screenRecordingPermission
        }

        let content: SCShareableContent
        do {
            content = try await SCShareableContent.current
        } catch {
            throw NativeMeetingRecorderError.streamOutput(error)
        }

        let displayID = await MainActor.run { activeDisplayID() }
        guard let display = content.displays.first(where: { $0.displayID == displayID }) ?? content.displays.first else {
            throw NativeMeetingRecorderError.noDisplay
        }

        try prepareFile(path: audioPath)
        try prepareFile(path: systemPath)
        try prepareFile(path: microphonePath)

        let currentProcessID = pid_t(ProcessInfo.processInfo.processIdentifier)
        let currentApps = content.applications.filter { $0.processID == currentProcessID }
        let filter = SCContentFilter(display: display, excludingApplications: currentApps, exceptingWindows: [])

        let configuration = SCStreamConfiguration()
        configuration.width = 2
        configuration.height = 2
        configuration.minimumFrameInterval = CMTime(value: 1, timescale: 2)
        configuration.queueDepth = 3
        configuration.showsCursor = false
        configuration.capturesAudio = true
        configuration.sampleRate = 48_000
        configuration.channelCount = 2
        configuration.excludesCurrentProcessAudio = true

        warnings = []
        fallbackMicRecorder = MicrophoneAudioRecorder(path: microphonePath)
        try fallbackMicRecorder?.start()
        warnings.append("Microphone captured with AVFoundation sidecar recorder for stability.")

        systemWriter = SampleBufferAudioWriter(path: systemPath)
        self.session = session

        let stream = SCStream(filter: filter, configuration: configuration, delegate: self)
        do {
            try stream.addStreamOutput(self, type: .screen, sampleHandlerQueue: outputQueue)
            try stream.addStreamOutput(self, type: .audio, sampleHandlerQueue: outputQueue)
            try await startCapture(stream)
        } catch {
            self.stream = nil
            systemWriter = nil
            fallbackMicRecorder?.stop()
            fallbackMicRecorder = nil
            self.session = nil
            throw NativeMeetingRecorderError.streamOutput(error)
        }
        self.stream = stream
    }

    func stop() async throws -> NativeMeetingRecorderResult {
        guard let stream, let session else {
            throw NativeMeetingRecorderError.notRecording
        }
        try await stopCapture(stream)
        fallbackMicRecorder?.stop()
        self.stream = nil
        systemWriter = nil
        fallbackMicRecorder = nil
        self.session = nil

        guard let audioPath = session.audioPath else {
            throw NativeMeetingRecorderError.missingPath("audio_path")
        }
        let result = try SpeedwagonAudioFileMixer.mixWAV(
            systemPath: session.systemAudioPath,
            microphonePath: session.microphoneAudioPath,
            outputPath: audioPath
        )
        return NativeMeetingRecorderResult(audioPath: result.outputPath, warnings: warnings + result.warnings)
    }

    private func startCapture(_ stream: SCStream) async throws {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            stream.startCapture { error in
                if let error {
                    continuation.resume(throwing: error)
                } else {
                    continuation.resume()
                }
            }
        }
    }

    private func stopCapture(_ stream: SCStream) async throws {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            stream.stopCapture { error in
                if let error {
                    continuation.resume(throwing: error)
                } else {
                    continuation.resume()
                }
            }
        }
    }
}

extension ScreenCaptureKitMeetingRecorder: SCStreamOutput, SCStreamDelegate {
    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        switch type {
        case .audio:
            systemWriter?.write(sampleBuffer)
        case .screen:
            return
        default:
            return
        }
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        warnings.append("ScreenCaptureKit stopped unexpectedly: \(error.localizedDescription)")
    }
}

private final class SampleBufferAudioWriter {
    private let path: String
    private var file: AVAudioFile?

    init(path: String) {
        self.path = path
    }

    func write(_ sampleBuffer: CMSampleBuffer) {
        guard sampleBuffer.isValid,
              CMSampleBufferDataIsReady(sampleBuffer),
              CMSampleBufferGetNumSamples(sampleBuffer) > 0,
              let formatDescription = CMSampleBufferGetFormatDescription(sampleBuffer)
        else {
            return
        }
        let format = AVAudioFormat(cmAudioFormatDescription: formatDescription)
        guard let lease = makePCMBuffer(sampleBuffer: sampleBuffer, format: format) else {
            return
        }
        guard let ownedBuffer = ownedCopy(of: lease.buffer) else {
            return
        }

        do {
            if file == nil {
                file = try AVAudioFile(forWriting: URL(fileURLWithPath: path), settings: format.settings)
            }
            try file?.write(from: ownedBuffer)
        } catch {
            return
        }
    }

    private func makePCMBuffer(sampleBuffer: CMSampleBuffer, format: AVAudioFormat) -> AudioBufferLease? {
        var sizeNeeded = 0
        var blockBuffer: CMBlockBuffer?
        var status = CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(
            sampleBuffer,
            bufferListSizeNeededOut: &sizeNeeded,
            bufferListOut: nil,
            bufferListSize: 0,
            blockBufferAllocator: kCFAllocatorDefault,
            blockBufferMemoryAllocator: kCFAllocatorDefault,
            flags: kCMSampleBufferFlag_AudioBufferList_Assure16ByteAlignment,
            blockBufferOut: &blockBuffer
        )
        guard status == noErr, sizeNeeded > 0 else {
            return nil
        }

        let rawPointer = UnsafeMutableRawPointer.allocate(
            byteCount: sizeNeeded,
            alignment: MemoryLayout<AudioBufferList>.alignment
        )
        let audioBufferList = rawPointer.bindMemory(to: AudioBufferList.self, capacity: 1)
        status = CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(
            sampleBuffer,
            bufferListSizeNeededOut: nil,
            bufferListOut: audioBufferList,
            bufferListSize: sizeNeeded,
            blockBufferAllocator: kCFAllocatorDefault,
            blockBufferMemoryAllocator: kCFAllocatorDefault,
            flags: kCMSampleBufferFlag_AudioBufferList_Assure16ByteAlignment,
            blockBufferOut: &blockBuffer
        )
        guard status == noErr,
              let pcmBuffer = AVAudioPCMBuffer(pcmFormat: format, bufferListNoCopy: audioBufferList)
        else {
            rawPointer.deallocate()
            return nil
        }
        pcmBuffer.frameLength = AVAudioFrameCount(CMSampleBufferGetNumSamples(sampleBuffer))
        return AudioBufferLease(buffer: pcmBuffer, rawPointer: rawPointer, blockBuffer: blockBuffer)
    }

    private func ownedCopy(of source: AVAudioPCMBuffer) -> AVAudioPCMBuffer? {
        guard let copy = AVAudioPCMBuffer(pcmFormat: source.format, frameCapacity: source.frameLength) else {
            return nil
        }
        copy.frameLength = source.frameLength
        let sourceBuffers = UnsafeMutableAudioBufferListPointer(source.mutableAudioBufferList)
        let copyBuffers = UnsafeMutableAudioBufferListPointer(copy.mutableAudioBufferList)
        for index in 0..<min(sourceBuffers.count, copyBuffers.count) {
            guard let sourceData = sourceBuffers[index].mData,
                  let copyData = copyBuffers[index].mData
            else {
                continue
            }
            let byteCount = min(Int(sourceBuffers[index].mDataByteSize), Int(copyBuffers[index].mDataByteSize))
            memcpy(copyData, sourceData, byteCount)
            copyBuffers[index].mDataByteSize = UInt32(byteCount)
        }
        return copy
    }
}

private final class AudioBufferLease {
    let buffer: AVAudioPCMBuffer
    private let rawPointer: UnsafeMutableRawPointer
    private let blockBuffer: CMBlockBuffer?

    init(buffer: AVAudioPCMBuffer, rawPointer: UnsafeMutableRawPointer, blockBuffer: CMBlockBuffer?) {
        self.buffer = buffer
        self.rawPointer = rawPointer
        self.blockBuffer = blockBuffer
    }

    deinit {
        _ = blockBuffer
        rawPointer.deallocate()
    }
}

private final class MicrophoneAudioRecorder {
    private let path: String
    private let engine = AVAudioEngine()
    private var file: AVAudioFile?

    init(path: String) {
        self.path = path
    }

    func start() throws {
        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        file = try AVAudioFile(forWriting: URL(fileURLWithPath: path), settings: format.settings)
        input.installTap(onBus: 0, bufferSize: 4096, format: format) { [weak self] buffer, _ in
            guard let self else { return }
            try? self.file?.write(from: buffer)
        }
        engine.prepare()
        try engine.start()
    }

    func stop() {
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        file = nil
    }
}

private func prepareFile(path: String) throws {
    let url = URL(fileURLWithPath: path)
    try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
    if FileManager.default.fileExists(atPath: path) {
        try FileManager.default.removeItem(at: url)
    }
}

private func ensureMicrophonePermission() async throws {
    switch AVCaptureDevice.authorizationStatus(for: .audio) {
    case .authorized:
        return
    case .notDetermined:
        let granted = await AVCaptureDevice.requestAccess(for: .audio)
        if !granted {
            throw NativeMeetingRecorderError.microphonePermission
        }
    default:
        throw NativeMeetingRecorderError.microphonePermission
    }
}

private func microphoneStatusText(_ status: AVAuthorizationStatus) -> String {
    switch status {
    case .authorized:
        return "Allowed"
    case .notDetermined:
        return "Not requested"
    case .denied:
        return "Denied"
    case .restricted:
        return "Restricted"
    @unknown default:
        return "Unknown"
    }
}
