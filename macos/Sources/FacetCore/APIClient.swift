import Foundation

public struct APIClient: Sendable {
    public let baseURL: URL
    private let session: URLSession

    public init(baseURL: URL = URL(string: "http://127.0.0.1:8765")!, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.session = session
    }

    public func get<T: Decodable>(_ path: String, as: T.Type) async throws -> T {
        try await request(path, method: "GET", body: nil)
    }
    public func health() async throws -> Health { try await get("/api/health", as: Health.self) }
    public func state() async throws -> Live { try await get("/api/state", as: Live.self) }
    public func pause(_ paused: Bool) async throws -> Status {
        try await request(paused ? "/api/pause" : "/api/resume", method: "POST", body: nil)
    }
    public func calibrate() async throws -> Status {
        try await request("/api/calibrate?seconds=30", method: "POST", body: nil)
    }
    public func settings(_ patch: Settings) async throws -> Status {
        try await request("/api/settings", method: "POST", body: ContractJSON.encoder().encode(patch))
    }

    private func request<T: Decodable>(_ path: String, method: String, body: Data?) async throws -> T {
        guard let url = URL(string: path, relativeTo: baseURL) else { throw URLError(.badURL) }
        var request = URLRequest(url: url, timeoutInterval: 3)
        request.httpMethod = method
        request.httpBody = body
        if body != nil { request.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        let (data, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse, (200..<300).contains(response.statusCode) else {
            throw URLError(.badServerResponse)
        }
        return try ContractJSON.decoder().decode(T.self, from: data)
    }
}
