import AVFoundation
import XCTest
@testable import SpeedwagonAICore

final class AudioFileMixerTests: XCTestCase {
    func testMixesSystemAndMicrophoneWAVFiles() throws {
        let root = try makeTemporaryDirectory()
        let systemPath = root.appendingPathComponent("meeting-1-system.wav").path
        let microphonePath = root.appendingPathComponent("meeting-1-mic.wav").path
        let outputPath = root.appendingPathComponent("meeting-1.wav").path
        try writeTone(path: systemPath, frequency: 440, amplitude: 0.2)
        try writeTone(path: microphonePath, frequency: 880, amplitude: 0.2)

        let result = try SpeedwagonAudioFileMixer.mixWAV(
            systemPath: systemPath,
            microphonePath: microphonePath,
            outputPath: outputPath
        )

        XCTAssertEqual(result.outputPath, outputPath)
        XCTAssertTrue(result.usedSystemAudio)
        XCTAssertTrue(result.usedMicrophoneAudio)
        XCTAssertTrue(result.warnings.isEmpty)
        XCTAssertTrue(SpeedwagonAudioFileMixer.isUsableAudioFile(outputPath))
    }

    func testProducesSystemOnlyOutputWhenMicIsUnavailable() throws {
        let root = try makeTemporaryDirectory()
        let systemPath = root.appendingPathComponent("meeting-2-system.wav").path
        let outputPath = root.appendingPathComponent("meeting-2.wav").path
        try writeTone(path: systemPath, frequency: 440, amplitude: 0.2)

        let result = try SpeedwagonAudioFileMixer.mixWAV(
            systemPath: systemPath,
            microphonePath: root.appendingPathComponent("missing-mic.wav").path,
            outputPath: outputPath
        )

        XCTAssertTrue(result.usedSystemAudio)
        XCTAssertFalse(result.usedMicrophoneAudio)
        XCTAssertEqual(result.warnings, ["Microphone audio was unavailable; saved system audio only."])
        XCTAssertTrue(SpeedwagonAudioFileMixer.isUsableAudioFile(outputPath))
    }

    func testRequiresSystemAudio() throws {
        let root = try makeTemporaryDirectory()
        let microphonePath = root.appendingPathComponent("meeting-3-mic.wav").path
        let outputPath = root.appendingPathComponent("meeting-3.wav").path
        try writeTone(path: microphonePath, frequency: 880, amplitude: 0.2)

        XCTAssertThrowsError(
            try SpeedwagonAudioFileMixer.mixWAV(
                systemPath: root.appendingPathComponent("missing-system.wav").path,
                microphonePath: microphonePath,
                outputPath: outputPath
            )
        ) { error in
            XCTAssertEqual(error as? AudioFileMixerError, .noSystemAudio)
        }
    }

    private func makeTemporaryDirectory() throws -> URL {
        let url = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("SpeedwagonAudioFileMixerTests-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }

    private func writeTone(path: String, frequency: Double, amplitude: Float) throws {
        let format = AVAudioFormat(
            commonFormat: .pcmFormatFloat32,
            sampleRate: 48_000,
            channels: 2,
            interleaved: false
        )!
        let frames = AVAudioFrameCount(9_600)
        let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: frames)!
        buffer.frameLength = frames
        let channels = Int(format.channelCount)
        for channel in 0..<channels {
            let data = buffer.floatChannelData![channel]
            for frame in 0..<Int(frames) {
                let phase = 2.0 * Double.pi * frequency * Double(frame) / format.sampleRate
                data[frame] = Float(sin(phase)) * amplitude
            }
        }
        let settings: [String: Any] = [
            AVFormatIDKey: kAudioFormatLinearPCM,
            AVSampleRateKey: format.sampleRate,
            AVNumberOfChannelsKey: Int(format.channelCount),
            AVLinearPCMBitDepthKey: 32,
            AVLinearPCMIsFloatKey: true,
            AVLinearPCMIsBigEndianKey: false,
            AVLinearPCMIsNonInterleaved: false
        ]
        let file = try AVAudioFile(
            forWriting: URL(fileURLWithPath: path),
            settings: settings,
            commonFormat: .pcmFormatFloat32,
            interleaved: false
        )
        try file.write(from: buffer)
    }
}
