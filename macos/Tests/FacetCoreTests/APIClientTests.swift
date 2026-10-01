import XCTest
@testable import FacetCore

private final class MockProtocol: URLProtocol {
    static var handler: ((URLRequest) throws -> (Int, Data))?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        do {
            let (code, data) = try Self.handler!(request)
            let response = HTTPURLResponse(url: request.url!, statusCode: code, httpVersion: "HTTP/1.1", headerFields: nil)!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() {}
}

final class APIClientTests: XCTestCase {
    private func client() -> (APIClient, URLSession) {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockProtocol.self]
        let session = URLSession(configuration: config)
        return (APIClient(baseURL: URL(string: "http://facet.test:8765")!, session: session), session)
    }
    func testHealthUsesGETAndValidatesResponse() async throws {
        let (api, session) = client(); defer { session.invalidateAndCancel(); MockProtocol.handler = nil }
        MockProtocol.handler = { request in
            XCTAssertEqual(request.httpMethod, "GET")
            XCTAssertEqual(request.url?.path, "/api/health")
            XCTAssertEqual(request.timeoutInterval, 3)
            return (200, Data(#"{"ok":true,"judge":"ready"}"#.utf8))
        }
        let health = try await api.health()
        XCTAssertEqual(health.ok, true)
        MockProtocol.handler = { _ in (503, Data("{}".utf8)) }
        do { _ = try await api.health(); XCTFail("Expected HTTP failure") } catch {}
    }
    func testControlRoutesOnlyUseMockTransport() async throws {
        let (api, session) = client(); defer { session.invalidateAndCancel(); MockProtocol.handler = nil }
        var paths = [String]()
        MockProtocol.handler = { request in
            XCTAssertEqual(request.url?.host, "facet.test")
            XCTAssertEqual(request.httpMethod, "POST")
            paths.append(request.url!.path)
            if request.url?.path == "/api/calibrate" { XCTAssertEqual(request.url?.query, "seconds=30") }
            if request.url?.path == "/api/settings" {
                XCTAssertEqual(request.value(forHTTPHeaderField: "Content-Type"), "application/json")
                let body: Data
                if let data = request.httpBody { body = data }
                else {
                    let stream = try XCTUnwrap(request.httpBodyStream); stream.open(); defer { stream.close() }
                    var bytes = [UInt8](repeating: 0, count: 1024)
                    let count = stream.read(&bytes, maxLength: bytes.count)
                    body = Data(bytes.prefix(max(0, count)))
                }
                XCTAssertEqual(try JSONSerialization.jsonObject(with: body) as? [String: Bool], ["mic": false])
            }
            return (200, Data(#"{"paused":true,"settings":{"mic":false}}"#.utf8))
        }
        _ = try await api.pause(true); _ = try await api.pause(false); _ = try await api.calibrate()
        var patch = Settings(); patch.mic = false
        let response = try await api.settings(patch)
        XCTAssertEqual(response.settings?.mic, false)
        XCTAssertEqual(paths, ["/api/pause", "/api/resume", "/api/calibrate", "/api/settings"])
    }
}
