import AVFoundation
import Foundation

public struct AudioMixResult: Equatable {
    public let outputPath: String
    public let warnings: [String]
    public let usedSystemAudio: Bool
    public let usedMicrophoneAudio: Bool
}

public enum AudioFileMixerError: LocalizedError, Equatable {
    case noSystemAudio
    case noUsableInput
    case conversionFailed

    public var errorDescription: String? {
        switch self {
        case .noSystemAudio:
            return "Native system audio capture did not produce usable audio. Use Mic fallback for now, or check Screen Recording permission."
        case .noUsableInput:
            return "No usable native audio tracks were created."
        case .conversionFailed:
            return "Could not convert captured audio into the final WAV format."
        }
    }
}

public enum SpeedwagonAudioFileMixer {
    public static let minimumUsableBytes = 4096

    public static func mixWAV(
        systemPath: String?,
        microphonePath: String?,
        outputPath: String
    ) throws -> AudioMixResult {
        guard let systemPath, isUsableAudioFile(systemPath) else {
            throw AudioFileMixerError.noSystemAudio
        }

        let micUsable = microphonePath.map(isUsableAudioFile) ?? false
        var warnings: [String] = []
        if !micUsable {
            warnings.append("Microphone audio was unavailable; saved system audio only.")
            try copyAudio(from: systemPath, to: outputPath)
            return AudioMixResult(
                outputPath: outputPath,
                warnings: warnings,
                usedSystemAudio: true,
                usedMicrophoneAudio: false
            )
        }

        guard let microphonePath else {
            throw AudioFileMixerError.noUsableInput
        }
        try mix(systemPath: systemPath, microphonePath: microphonePath, outputPath: outputPath)
        return AudioMixResult(
            outputPath: outputPath,
            warnings: warnings,
            usedSystemAudio: true,
            usedMicrophoneAudio: true
        )
    }

    public static func isUsableAudioFile(_ path: String) -> Bool {
        let url = URL(fileURLWithPath: path)
        guard let attrs = try? FileManager.default.attributesOfItem(atPath: url.path),
              let size = attrs[.size] as? NSNumber
        else {
            return false
        }
        return size.intValue >= minimumUsableBytes
    }

    private static func copyAudio(from sourcePath: String, to outputPath: String) throws {
        let sourceURL = URL(fileURLWithPath: sourcePath)
        let outputURL = URL(fileURLWithPath: outputPath)
        try FileManager.default.createDirectory(at: outputURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        if FileManager.default.fileExists(atPath: outputURL.path) {
            try FileManager.default.removeItem(at: outputURL)
        }
        try FileManager.default.copyItem(at: sourceURL, to: outputURL)
    }

    private static func mix(systemPath: String, microphonePath: String, outputPath: String) throws {
        let outputURL = URL(fileURLWithPath: outputPath)
        try FileManager.default.createDirectory(at: outputURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        if FileManager.default.fileExists(atPath: outputURL.path) {
            try FileManager.default.removeItem(at: outputURL)
        }

        let outputFormat = AVAudioFormat(
            commonFormat: .pcmFormatFloat32,
            sampleRate: 48_000,
            channels: 2,
            interleaved: false
        )!

        let systemFile = try AVAudioFile(forReading: URL(fileURLWithPath: systemPath))
        let microphoneFile = try AVAudioFile(forReading: URL(fileURLWithPath: microphonePath))
        let engine = AVAudioEngine()
        let systemNode = AVAudioPlayerNode()
        let microphoneNode = AVAudioPlayerNode()

        engine.attach(systemNode)
        engine.attach(microphoneNode)
        engine.connect(systemNode, to: engine.mainMixerNode, format: systemFile.processingFormat)
        engine.connect(microphoneNode, to: engine.mainMixerNode, format: microphoneFile.processingFormat)
        try engine.enableManualRenderingMode(.offline, format: outputFormat, maximumFrameCount: 4096)

        let writer = try AVAudioFile(
            forWriting: outputURL,
            settings: wavSettings(sampleRate: outputFormat.sampleRate, channels: outputFormat.channelCount),
            commonFormat: .pcmFormatFloat32,
            interleaved: false
        )
        let renderBuffer = AVAudioPCMBuffer(
            pcmFormat: engine.manualRenderingFormat,
            frameCapacity: engine.manualRenderingMaximumFrameCount
        )!
        let outputFrames = max(
            scaledFrameCount(systemFile, outputSampleRate: outputFormat.sampleRate),
            scaledFrameCount(microphoneFile, outputSampleRate: outputFormat.sampleRate)
        )

        systemNode.scheduleFile(systemFile, at: nil)
        microphoneNode.scheduleFile(microphoneFile, at: nil)
        try engine.start()
        systemNode.play()
        microphoneNode.play()
        defer {
            systemNode.stop()
            microphoneNode.stop()
            engine.stop()
            engine.disableManualRenderingMode()
        }

        while engine.manualRenderingSampleTime < outputFrames {
            let remaining = AVAudioFrameCount(outputFrames - engine.manualRenderingSampleTime)
            let frameCount = min(engine.manualRenderingMaximumFrameCount, remaining)
            switch try engine.renderOffline(frameCount, to: renderBuffer) {
            case .success:
                try writer.write(from: renderBuffer)
            case .insufficientDataFromInputNode, .cannotDoInCurrentContext:
                continue
            case .error:
                throw AudioFileMixerError.conversionFailed
            @unknown default:
                throw AudioFileMixerError.conversionFailed
            }
        }
    }

    private static func makeSilentBuffer(format: AVAudioFormat, capacity: AVAudioFrameCount) -> AVAudioPCMBuffer {
        let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: capacity)!
        buffer.frameLength = 0
        return buffer
    }

    private static func add(_ source: AVAudioPCMBuffer?, into target: AVAudioPCMBuffer) {
        guard let source, let sourceData = source.floatChannelData, let targetData = target.floatChannelData else {
            return
        }
        let frames = Int(source.frameLength)
        if target.frameLength < source.frameLength {
            for channel in 0..<Int(target.format.channelCount) {
                let channelData = targetData[channel]
                for frame in Int(target.frameLength)..<frames {
                    channelData[frame] = 0
                }
            }
            target.frameLength = source.frameLength
        }
        let channelCount = min(Int(source.format.channelCount), Int(target.format.channelCount))
        for channel in 0..<channelCount {
            let sourceChannel = sourceData[channel]
            let targetChannel = targetData[channel]
            for frame in 0..<frames {
                targetChannel[frame] = max(-1.0, min(1.0, targetChannel[frame] + sourceChannel[frame] * 0.75))
            }
        }
    }

    private static func wavSettings(sampleRate: Double, channels: AVAudioChannelCount) -> [String: Any] {
        [
            AVFormatIDKey: kAudioFormatLinearPCM,
            AVSampleRateKey: sampleRate,
            AVNumberOfChannelsKey: Int(channels),
            AVLinearPCMBitDepthKey: 32,
            AVLinearPCMIsFloatKey: true,
            AVLinearPCMIsBigEndianKey: false,
            AVLinearPCMIsNonInterleaved: false
        ]
    }

    private static func scaledFrameCount(_ file: AVAudioFile, outputSampleRate: Double) -> AVAudioFramePosition {
        let sourceRate = file.fileFormat.sampleRate
        if sourceRate <= 0 {
            return file.length
        }
        return AVAudioFramePosition(ceil(Double(file.length) * outputSampleRate / sourceRate))
    }
}
