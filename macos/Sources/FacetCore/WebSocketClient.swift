import Foundation
import Combine

@MainActor
public final class WebSocketClient: ObservableObject {
    @Published public private(set) var connected = false
    @Published public private(set) var error: String?
    public var onMessage: ((BackendMessage) -> Void)?
    private let url: URL
    private let session: URLSession
    private var socket: URLSessionWebSocketTask?
    private var loop: Task<Void, Never>?

    public init(url: URL = URL(string: "ws://127.0.0.1:8765/ws?client=app")!, session: URLSession = .shared) {
        self.url = url
        self.session = session
    }

    public func start() {
        guard loop == nil else { return }
        loop = Task { [weak self] in await self?.receiveLoop() }
    }

    public func stop() {
        loop?.cancel(); loop = nil
        socket?.cancel(with: .goingAway, reason: nil); socket = nil
        connected = false
    }

    private func receiveLoop() async {
        var failures = 0
        while !Task.isCancelled {
            let task = session.webSocketTask(with: url)
            socket = task
            task.resume()
            do {
                while !Task.isCancelled {
                    let frame = try await task.receive()
                    connected = true; error = nil; failures = 0
                    let data: Data
                    switch frame {
                    case .data(let value): data = value
                    case .string(let value): data = Data(value.utf8)
                    @unknown default: continue
                    }
                    do { onMessage?(try ContractJSON.decoder().decode(BackendMessage.self, from: data)) }
                    catch { self.error = "Unreadable backend message: \(error.localizedDescription)" }
                }
            } catch {
                if !Task.isCancelled { self.error = "Dashboard connection interrupted" }
            }
            task.cancel(with: .goingAway, reason: nil)
            connected = false
            if Task.isCancelled { break }
            let delay = min(pow(2.0, Double(min(failures, 6))), 60)
            failures += 1
            do { try await Task.sleep(for: .seconds(delay)) } catch { break }
        }
    }
}
