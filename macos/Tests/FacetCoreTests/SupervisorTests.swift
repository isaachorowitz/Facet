import XCTest
@testable import FacetCore

final class SupervisorTests: XCTestCase {
    func testOwnedLifecycleAndDashboardGeneration() {
        var machine = SupervisorMachine()
        XCTAssertEqual(machine.state, .idle)
        machine.prepare()
        XCTAssertEqual(machine.state.title, "Preparing Python environment")
        XCTAssertTrue(machine.ownsBackend)
        machine.spawned()
        XCTAssertEqual(machine.state, .starting)
        XCTAssertEqual(machine.generation, 1)
        machine.waitingForJudge()
        XCTAssertEqual(machine.state, .loading)
        XCTAssertFalse(machine.reachable)
        machine.health(judge: "warming up")
        XCTAssertEqual(machine.state, .loading)
        XCTAssertTrue(machine.reachable)
        XCTAssertFalse(machine.state.isReady)
        machine.health(judge: "ready")
        XCTAssertEqual(machine.state, .ready)
        XCTAssertTrue(machine.state.isReady)
        machine.health(judge: "ready")
        XCTAssertEqual(machine.generation, 1)
        XCTAssertEqual(machine.unexpectedExit(reason: "crash"), 1)
        XCTAssertFalse(machine.reachable)
        XCTAssertEqual(machine.state, .restarting(delay: 1, reason: "crash"))
        machine.prepare(); machine.spawned()
        XCTAssertEqual(machine.generation, 2)
        machine.stop(); machine.stopped()
        XCTAssertEqual(machine.state, .stopped)
        XCTAssertFalse(machine.ownsBackend)
    }
    func testExponentialBackoffCapsAndStableRunResetsIt() {
        var machine = SupervisorMachine()
        for delay in [1, 2, 4, 8, 16, 32, 60, 60, 60] {
            XCTAssertEqual(machine.unexpectedExit(reason: "test"), delay)
            machine.prepare(); machine.spawned(); machine.health(judge: "ready")
            // Merely reaching ready does not reset a crashing backend's backoff.
        }
        machine.stable()
        XCTAssertEqual(machine.retryCount, 0)
        XCTAssertEqual(machine.unexpectedExit(reason: "later"), 1)
        XCTAssertEqual(SupervisorMachine.backoff(attempt: Int.max), 60)
        XCTAssertEqual(SupervisorMachine.backoff(attempt: Int.min), 1)
    }
    func testAttachmentDoesNotAcquireOwnership() {
        var machine = SupervisorMachine()
        machine.attach(judge: "loading")
        XCTAssertEqual(machine.state, .loading)
        XCTAssertFalse(machine.ownsBackend)
        machine.health(judge: "ready")
        XCTAssertEqual(machine.state, .attached)
        XCTAssertEqual(machine.state.title, "Attached to running backend")
        machine.fail("Unavailable")
        XCTAssertFalse(machine.ownsBackend)
        machine.health(judge: "ready")
        XCTAssertEqual(machine.state, .attached)
        machine.stop(); machine.stopped()
        XCTAssertFalse(machine.ownsBackend)
    }
    func testJudgeFailureConnectionLossAndQuitIgnoreLateEvents() {
        var machine = SupervisorMachine()
        machine.prepare(); machine.spawned()
        machine.health(judge: "failed")
        XCTAssertEqual(machine.state, .failed("Clef-flash failed to load. See backend.log."))
        machine.health(judge: "ready")
        machine.connectionLost()
        XCTAssertEqual(machine.state, .starting)
        XCTAssertFalse(machine.reachable)
        machine.stop()
        machine.health(judge: "ready"); machine.connectionLost()
        XCTAssertEqual(machine.unexpectedExit(reason: "late exit"), 0)
        XCTAssertEqual(machine.state, .stopping)
        machine.stopped(); machine.health(judge: "ready")
        XCTAssertEqual(machine.state, .stopped)
    }
}
