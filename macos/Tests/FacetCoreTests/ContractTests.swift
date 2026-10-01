import XCTest
@testable import FacetCore

final class ContractTests: XCTestCase {
    private func fixture(_ name: String) throws -> Data {
        let url = try XCTUnwrap(Bundle.module.url(forResource: name, withExtension: "json", subdirectory: "Fixtures"))
        return try Data(contentsOf: url)
    }

    // Comparing every non-null JSON key catches accidental snake_case mapping omissions.
    private func assertRoundTrip<T: Codable>(_ type: T.Type, fixture name: String) throws -> T {
        let data = try fixture(name)
        let decoded = try ContractJSON.decoder().decode(type, from: data)
        let encoded = try ContractJSON.encoder().encode(decoded)
        let expected = normalize(try JSONSerialization.jsonObject(with: data)) as AnyObject
        let actual = normalize(try JSONSerialization.jsonObject(with: encoded)) as AnyObject
        XCTAssertTrue(expected.isEqual(actual), "Fields changed in \(name)")
        return decoded
    }
    private func normalize(_ value: Any) -> Any {
        if let dictionary = value as? [String: Any] {
            return dictionary.filter { !($0.value is NSNull) }.mapValues(normalize) as NSDictionary
        }
        if let array = value as? [Any] { return array.map(normalize) as NSArray }
        return value
    }

    func testEveryWebSocketMessageAndAllNotificationKinds() throws {
        for name in ["hello", "live", "face", "overall", "speech", "speech-null", "calibrated",
                     "notification-stress", "notification-break", "notification-fatigue", "notification-posture"] {
            let message = try assertRoundTrip(BackendMessage.self, fixture: name)
            switch (name, message) {
            case ("hello", .hello(let value)): XCTAssertEqual(value.latest?.voice?.tone?.choice, "calm")
            case ("live", .live(let value)): XCTAssertEqual(value.posture?.skeleton?["l_sh"], [0.6, 0.5, 0.97])
            case ("face", .face(let value, let latency)):
                XCTAssertEqual(value.jawClenched, 0.2); XCTAssertEqual(latency, 825.3)
            case ("overall", .overall(let value, _)): XCTAssertEqual(value.inFlow, 0.8)
            case ("speech", .speech(let value, _)): XCTAssertEqual(value.prosody?.pitchHz, 160.7)
            case ("speech-null", .speech(let value, let latency)): XCTAssertNil(value.verdict); XCTAssertNil(latency)
            case ("calibrated", .calibrated(let value)): XCTAssertEqual(value.baselineSamples, 120)
            case (let name, .notification(let value)):
                XCTAssertEqual(name, "notification-\(value.kind ?? "")"); XCTAssertFalse(value.text?.isEmpty ?? true)
            default: XCTFail("Incorrect message case: \(name)")
            }
        }
    }

    func testAllRESTShapes() throws {
        let health = try assertRoundTrip(Health.self, fixture: "health")
        XCTAssertEqual(health.ok, true)
        let state = try assertRoundTrip(Live.self, fixture: "state")
        XCTAssertEqual(state.latest?.face?.expression?.choice, "focused")
        let timeline = try assertRoundTrip(Timeline.self, fixture: "timeline")
        XCTAssertEqual(timeline.points?.first?.speechS, 22.1)
        let summary = try assertRoundTrip(Summary.self, fixture: "summary")
        XCTAssertEqual(summary.byHour?.first?.topExpression, "focused")
        let speech = try assertRoundTrip([Speech].self, fixture: "speech-list")
        XCTAssertNil(speech.last?.verdict)
        let status = try assertRoundTrip(Status.self, fixture: "status")
        XCTAssertEqual(status.settings?.storeTranscripts, false)
    }

    func testMissingKeysAndFutureStates() throws {
        let sparse = [
            #"{"type":"hello"}"#, #"{"type":"live","status":{"judge":"future-state"}}"#,
            #"{"type":"verdict","kind":"face","data":{}}"#,
            #"{"type":"verdict","kind":"overall","data":{}}"#,
            #"{"type":"speech","data":{}}"#, #"{"type":"notification","data":{}}"#,
            #"{"type":"calibrated","data":{}}"#,
            #"{"type":"verdict"}"#, #"{"type":"verdict","kind":"face"}"#,
            #"{"type":"verdict","kind":"overall"}"#, #"{"type":"speech"}"#,
            #"{"type":"notification"}"#, #"{"type":"calibrated"}"#,
        ]
        for json in sparse { XCTAssertNoThrow(try ContractJSON.decoder().decode(BackendMessage.self, from: Data(json.utf8))) }
        for decode in [
            { _ = try ContractJSON.decoder().decode(Health.self, from: Data("{}".utf8)) },
            { _ = try ContractJSON.decoder().decode(Summary.self, from: Data("{}".utf8)) },
            { _ = try ContractJSON.decoder().decode(Timeline.self, from: Data("{}".utf8)) },
            { _ = try ContractJSON.decoder().decode(Posture.self, from: Data("{}".utf8)) },
        ] { XCTAssertNoThrow(try decode()) }
        let unknown = try ContractJSON.decoder().decode(BackendMessage.self, from: Data(#"{"type":"new-event","extra":true}"#.utf8))
        XCTAssertEqual(unknown, .unknown("new-event"))
        let verdict = try ContractJSON.decoder().decode(BackendMessage.self, from: Data(#"{"type":"verdict","kind":"future","data":{}}"#.utf8))
        XCTAssertEqual(verdict, .unknown("verdict"))
    }

    func testMalformedTypesAreRejected() {
        XCTAssertThrowsError(try ContractJSON.decoder().decode(BackendMessage.self, from: Data(#"{"type":"live","face":{"fps":"wrong"}}"#.utf8)))
        XCTAssertThrowsError(try ContractJSON.decoder().decode(BackendMessage.self, from: Data("{}".utf8)))
    }
    func testSettingsPatchOmitsUntouchedSettings() throws {
        var settings = Settings(); settings.mic = false
        let data = try ContractJSON.encoder().encode(settings)
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Bool])
        XCTAssertEqual(object, ["mic": false])
    }
}
