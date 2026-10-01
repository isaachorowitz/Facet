import Foundation

public enum BackendMessage: Codable, Equatable, Sendable {
    case hello(Hello)
    case live(Live)
    case face(FaceVerdict, latencyMs: Double?)
    case overall(OverallVerdict, latencyMs: Double?)
    case speech(Speech, latencyMs: Double?)
    case notification(Nudge)
    case calibrated(Status)
    case unknown(String)

    private enum Keys: String, CodingKey { case type, kind, data, latencyMs }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Keys.self)
        let type = try c.decode(String.self, forKey: .type)
        switch type {
        case "hello": self = .hello(try Hello(from: decoder))
        case "live": self = .live(try Live(from: decoder))
        case "verdict":
            let latency = try c.decodeIfPresent(Double.self, forKey: .latencyMs)
            switch try c.decodeIfPresent(String.self, forKey: .kind) {
            case "face": self = .face(try c.decodeIfPresent(FaceVerdict.self, forKey: .data) ?? FaceVerdict(), latencyMs: latency)
            case "overall": self = .overall(try c.decodeIfPresent(OverallVerdict.self, forKey: .data) ?? OverallVerdict(), latencyMs: latency)
            default: self = .unknown(type)
            }
        case "speech": self = .speech(try c.decodeIfPresent(Speech.self, forKey: .data) ?? Speech(), latencyMs: try c.decodeIfPresent(Double.self, forKey: .latencyMs))
        case "notification": self = .notification(try c.decodeIfPresent(Nudge.self, forKey: .data) ?? Nudge())
        case "calibrated": self = .calibrated(try c.decodeIfPresent(Status.self, forKey: .data) ?? Status())
        default: self = .unknown(type)
        }
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: Keys.self)
        switch self {
        case .hello(let value):
            try c.encode("hello", forKey: .type); try value.encode(to: encoder)
        case .live(let value):
            try value.encode(to: encoder); try c.encode("live", forKey: .type)
        case .face(let value, let latency):
            try c.encode("verdict", forKey: .type); try c.encode("face", forKey: .kind)
            try c.encode(value, forKey: .data); try c.encodeIfPresent(latency, forKey: .latencyMs)
        case .overall(let value, let latency):
            try c.encode("verdict", forKey: .type); try c.encode("overall", forKey: .kind)
            try c.encode(value, forKey: .data); try c.encodeIfPresent(latency, forKey: .latencyMs)
        case .speech(let value, let latency):
            try c.encode("speech", forKey: .type); try c.encode(value, forKey: .data)
            try c.encodeIfPresent(latency, forKey: .latencyMs)
        case .notification(let value):
            try c.encode("notification", forKey: .type); try c.encode(value, forKey: .data)
        case .calibrated(let value):
            try c.encode("calibrated", forKey: .type); try c.encode(value, forKey: .data)
        case .unknown(let type): try c.encode(type, forKey: .type)
        }
    }
}
