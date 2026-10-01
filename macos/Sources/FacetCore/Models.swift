import Foundation

// Optional fields accept sparse startup payloads and future additive contract changes.
// String state values preserve unknown values instead of rejecting a whole message.

public struct Choice: Codable, Equatable, Sendable {
    public var choice: String?
    public var confidence: Double?
    public var probabilities: [String:Double]?
    public init() {}
}

public struct FaceVerdict: Codable, Equatable, Sendable {
    public var ts: Double?
    public var expression: Choice?
    public var stress: Double?
    public var fatigue: Double?
    public var focus: Double?
    public var energy: Double?
    public var positivity: Double?
    public var tension: Double?
    public var smiling: Double?
    public var frowning: Double?
    public var jawClenched: Double?
    public var eyesHeavy: Double?
    public var eyesOnScreen: Double?
    public var handOnFace: Double?
    public var talking: Double?
    public var yawning: Double?
    public var distracted: Double?
    public var posture: Choice?
    public var activity: Choice?
    public init() {}
}

public struct OverallVerdict: Codable, Equatable, Sendable {
    public var ts: Double?
    public var mood: Choice?
    public var stress: Double?
    public var fatigue: Double?
    public var focus: Double?
    public var positivity: Double?
    public var needsBreak: Double?
    public var inFlow: Double?
    public var overwhelmed: Double?
    public init() {}
}

public struct VoiceVerdict: Codable, Equatable, Sendable {
    public var ts: Double?
    public var tone: Choice?
    public var stress: Double?
    public var energy: Double?
    public var positivity: Double?
    public var confident: Double?
    public var tired: Double?
    public var frustrated: Double?
    public init() {}
}

public struct Prosody: Codable, Equatable, Sendable {
    public var durationS: Double?
    public var wordsPerMinute: Double?
    public var pitchHz: Double?
    public var pitchVariationSemitones: Double?
    public var loudnessDb: Double?
    public var pauseRatio: Double?
    public init() {}
}

public struct Speech: Codable, Equatable, Sendable {
    public var ts: Double?
    public var text: String?
    public var prosody: Prosody?
    public var emotion: [String:Double]?
    public var verdict: VoiceVerdict?
    public init() {}
}

public struct Posture: Codable, Equatable, Sendable {
    public var visible: Bool?
    public var score: Double?
    public var state: String?
    public var issues: [String]?
    public var neck: Double?
    public var shoulderTilt: Double?
    public var lean: Double?
    public var sink: Double?
    public var reference: String?
    public var refNeck: Double?
    public var skeleton: [String:[Double]]?
    public init() {}
}

public struct Baseline: Codable, Equatable, Sendable {
    public var mean: Double?
    public var std: Double?
    public init() {}
}

public struct Settings: Codable, Equatable, Sendable {
    public var notifications: Bool?
    public var mic: Bool?
    public var storeTranscripts: Bool?
    public init() {}
}

public struct Status: Codable, Equatable, Sendable {
    public var paused: Bool?
    public var camera: String?
    public var cameraError: String?
    public var judge: String?
    public var judgeError: String?
    public var latencyMs: [String:Double]?
    public var voice: String?
    public var voiceError: String?
    public var mic: String?
    public var calibratingSecondsLeft: Double?
    public var baselineSamples: Int?
    public var baseline: [String:Baseline]?
    public var settings: Settings?
    public init() {}
}

public struct LiveFace: Codable, Equatable, Sendable {
    public var present: Bool?
    public var metrics: [String:Double]?
    public var vsUsual: [String:Double]?
    public var blinkRate: Double?
    public var lookingAtScreen: Bool?
    public var yawning: Bool?
    public var fps: Double?
    public init() {}
}

public struct LiveVoice: Codable, Equatable, Sendable {
    public var levelDb: Double?
    public var speaking: Bool?
    public init() {}
}

public struct Latest: Codable, Equatable, Sendable {
    public var face: FaceVerdict?
    public var overall: OverallVerdict?
    public var voice: VoiceVerdict?
    public init() {}
}

public struct Live: Codable, Equatable, Sendable {
    public var type: String?
    public var face: LiveFace?
    public var voice: LiveVoice?
    public var status: Status?
    public var minutesSinceBreak: Double?
    public var posture: Posture?
    public var latest: Latest?
    public init() {}
}

public struct Hello: Codable, Equatable, Sendable {
    public var latest: Latest?
    public var status: Status?
    public init() {}
}

public struct Nudge: Codable, Equatable, Sendable {
    public var kind: String?
    public var text: String?
    public init() {}
}

public struct Health: Codable, Equatable, Sendable {
    public var ok: Bool?
    public var judge: String?
    public var version: String?
    public init() {}
}

public struct TimelinePoint: Codable, Equatable, Sendable {
    public var t: Double?
    public var stress: Double?
    public var fatigue: Double?
    public var focus: Double?
    public var energy: Double?
    public var positivity: Double?
    public var tension: Double?
    public var expression: String?
    public var present: Double?
    public var measuredTension: Double?
    public var smile: Double?
    public var blinkRate: Double?
    public var posture: Double?
    public var speechS: Double?
    public init() {}
}

public struct Timeline: Codable, Equatable, Sendable {
    public var start: Double?
    public var bucketMinutes: Double?
    public var points: [TimelinePoint]?
    public init() {}
}

public struct NotificationRecord: Codable, Equatable, Sendable {
    public var ts: Double?
    public var kind: String?
    public var text: String?
    public init() {}
}

public struct StressPeak: Codable, Equatable, Sendable {
    public var ts: Double?
    public var stress: Double?
    public init() {}
}

public struct TimeSpan: Codable, Equatable, Sendable {
    public var start: Double?
    public var minutes: Double?
    public init() {}
}

public struct HourSummary: Codable, Equatable, Sendable {
    public var hour: Int?
    public var stress: Double?
    public var focus: Double?
    public var fatigue: Double?
    public var positivity: Double?
    public var topExpression: String?
    public init() {}
}

public struct Summary: Codable, Equatable, Sendable {
    public var date: String?
    public var minutesPresent: Double?
    public var firstSeen: Double?
    public var lastSeen: Double?
    public var verdicts: Int?
    public var minutesTalking: Double?
    public var notifications: [NotificationRecord]?
    public var avgPosture: Double?
    public var minutesPoorPosture: Double?
    public var minutesGoodPosture: Double?
    public var expressions: [String:Double]?
    public var avgStress: Double?
    public var avgFatigue: Double?
    public var avgFocus: Double?
    public var avgEnergy: Double?
    public var avgPositivity: Double?
    public var avgTension: Double?
    public var smilingShare: Double?
    public var posture: [String:Double]?
    public var activity: [String:Double]?
    public var stressPeaks: [StressPeak]?
    public var focusStreaks: [TimeSpan]?
    public var breaks: [TimeSpan]?
    public var byHour: [HourSummary]?
    public var voiceTones: [String:Double]?
    public init() {}
}

public enum ContractJSON {
    public static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }
    public static func encoder() -> JSONEncoder {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return encoder
    }
}
