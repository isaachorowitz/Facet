import XCTest
@testable import FacetCore

final class BackendPathsTests: XCTestCase {
    private var root: URL!
    override func setUpWithError() throws {
        root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent(".build/path-test-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }
    override func tearDownWithError() throws { try FileManager.default.removeItem(at: root) }
    private func source(_ directory: URL, version: String) throws {
        try FileManager.default.createDirectory(at: directory.appendingPathComponent("facet"), withIntermediateDirectories: true)
        for (name, text) in [("pyproject.toml", "project"), ("uv.lock", "lock"), ("VERSION", version)] {
            try Data(text.utf8).write(to: directory.appendingPathComponent(name))
        }
    }
    func testVersionInstallReuseAndUpgradePreservesModels() throws {
        let resources = root.appendingPathComponent("Resources")
        let bundle = resources.appendingPathComponent("backend")
        try source(bundle, version: "one")
        let paths = BackendPaths(resources: resources, home: root, environment: [:])
        let installed = try paths.backendDirectory()
        XCTAssertEqual(installed, paths.support.appendingPathComponent("backend", isDirectory: true))
        let model = installed.appendingPathComponent("models/tracker.task")
        try FileManager.default.createDirectory(at: model.deletingLastPathComponent(), withIntermediateDirectories: true)
        try Data("cached model".utf8).write(to: model)
        try Data("local marker".utf8).write(to: installed.appendingPathComponent("marker"))
        _ = try paths.backendDirectory()
        XCTAssertTrue(FileManager.default.fileExists(atPath: installed.appendingPathComponent("marker").path))
        try Data("two".utf8).write(to: bundle.appendingPathComponent("VERSION"))
        _ = try paths.backendDirectory()
        XCTAssertEqual(try String(contentsOf: installed.appendingPathComponent("VERSION"), encoding: .utf8), "two")
        XCTAssertEqual(try String(contentsOf: model, encoding: .utf8), "cached model")
        XCTAssertFalse(FileManager.default.fileExists(atPath: installed.appendingPathComponent("marker").path))
    }
    func testDevelopmentOverrideDoesNotInstallBundle() throws {
        let dev = root.appendingPathComponent("dev")
        try source(dev, version: "dev")
        let paths = BackendPaths(resources: nil, home: root, environment: ["FACET_BACKEND_DIR": dev.path])
        XCTAssertEqual(try paths.backendDirectory().path, dev.path)
        XCTAssertFalse(FileManager.default.fileExists(atPath: paths.support.path))
        XCTAssertEqual(paths.childEnvironment["UV_PROJECT_ENVIRONMENT"], paths.support.appendingPathComponent("venv").path)
        XCTAssertEqual(paths.childEnvironment["FACET_PORT"], "8765")
    }
    func testBundledUVWinsAndMissingSourceFails() throws {
        let resources = root.appendingPathComponent("Resources")
        let uv = resources.appendingPathComponent("bin/uv")
        try FileManager.default.createDirectory(at: uv.deletingLastPathComponent(), withIntermediateDirectories: true)
        try Data("not executed".utf8).write(to: uv)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: uv.path)
        let paths = BackendPaths(resources: resources, home: root, environment: [:])
        XCTAssertEqual(try paths.uvURL(), uv)
        XCTAssertThrowsError(try paths.backendDirectory())
    }
}
