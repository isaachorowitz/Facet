import Foundation

public enum SupervisorState: Equatable, Sendable {
    case idle, preparing, starting, loading, ready, attached, stopping, stopped
    case restarting(delay: Int, reason: String)
    case failed(String)

    public var title: String {
        switch self {
        case .idle: return "Checking for a running backend"
        case .preparing: return "Preparing Python environment"
        case .starting: return "Starting backend"
        case .loading: return "Loading Clef-flash"
        case .ready: return "Ready"
        case .attached: return "Attached to running backend"
        case .restarting(let delay, _): return "Restarting backend in \(delay) s"
        case .failed(let reason): return reason
        case .stopping: return "Stopping backend"
        case .stopped: return "Stopped"
        }
    }
    public var detail: String? {
        if case .restarting(_, let reason) = self { return reason }
        return nil
    }
    public var isReady: Bool { self == .ready || self == .attached }
}

/// Pure transition logic. The driver alone performs networking, file IO and process operations.
public struct SupervisorMachine: Equatable, Sendable {
    public private(set) var state: SupervisorState = .idle
    public private(set) var ownsBackend = false
    public private(set) var retryCount = 0
    public private(set) var generation = 0
    public private(set) var reachable = false

    public init() {}
    public mutating func prepare() { ownsBackend = true; reachable = false; state = .preparing }
    public mutating func spawned() { generation += 1; state = .starting }
    public mutating func waitingForJudge() { state = .loading }
    public mutating func attach(judge: String?) {
        ownsBackend = false
        generation += 1
        health(judge: judge)
    }
    public mutating func health(judge: String?) {
        guard state != .stopping && state != .stopped else { return }
        reachable = true
        if judge == "ready" { state = ownsBackend ? .ready : .attached }
        else if judge == "failed" { state = .failed("Clef-flash failed to load. See backend.log.") }
        else { state = .loading }
    }
    public mutating func connectionLost() {
        reachable = false
        if state != .stopping && state != .stopped { state = .starting }
    }
    public mutating func stable() { retryCount = 0 }
    @discardableResult
    public mutating func unexpectedExit(reason: String) -> Int {
        guard state != .stopping && state != .stopped else { return 0 }
        reachable = false
        let delay = Self.backoff(attempt: retryCount)
        retryCount = min(retryCount + 1, 7)
        state = .restarting(delay: delay, reason: reason)
        return delay
    }
    public mutating func fail(_ reason: String) { reachable = false; state = .failed(reason) }
    public mutating func stop() { reachable = false; state = .stopping }
    public mutating func stopped() { ownsBackend = false; state = .stopped }
    public static func backoff(attempt: Int) -> Int { attempt >= 6 ? 60 : 1 << max(attempt, 0) }
}
