import Foundation

public struct BackendPaths {
    public let support: URL
    public let log: URL
    public let resources: URL?
    public let environment: [String: String]
    public let home: URL

    public init(resources: URL? = Bundle.main.resourceURL,
                home: URL = FileManager.default.homeDirectoryForCurrentUser,
                environment: [String: String] = ProcessInfo.processInfo.environment) {
        self.resources = resources
        self.environment = environment
        self.home = home
        support = home.appendingPathComponent("Library/Application Support/Facet", isDirectory: true)
        log = home.appendingPathComponent("Library/Logs/Facet/backend.log")
    }

    public var childEnvironment: [String: String] {
        var value = environment
        value["UV_PROJECT_ENVIRONMENT"] = support.appendingPathComponent("venv").path
        // The native dashboard and app WebSocket use one fixed loopback origin.
        value["FACET_HOST"] = "127.0.0.1"
        value["FACET_PORT"] = "8765"
        value["PYTHONUNBUFFERED"] = "1"
        return value
    }

    public func uvURL() throws -> URL {
        let fm = FileManager.default
        var candidates = [URL]()
        if let resources { candidates.append(resources.appendingPathComponent("bin/uv")) }
        candidates.append(home.appendingPathComponent(".local/bin/uv"))
        candidates.append(URL(fileURLWithPath: "/opt/homebrew/bin/uv"))
        candidates += (environment["PATH"] ?? "/usr/bin:/bin").split(separator: ":").map {
            URL(fileURLWithPath: String($0), isDirectory: true).appendingPathComponent("uv")
        }
        guard let url = candidates.first(where: { fm.isExecutableFile(atPath: $0.path) }) else {
            throw BackendError.configuration("uv was not found. Rebuild Facet with uv installed.")
        }
        return url
    }

    public func backendDirectory() throws -> URL {
        let fm = FileManager.default
        if let override = environment["FACET_BACKEND_DIR"], !override.isEmpty {
            let dir = URL(fileURLWithPath: (override as NSString).expandingTildeInPath, isDirectory: true)
            try validate(dir)
            return dir
        }
        guard let bundled = resources?.appendingPathComponent("backend", isDirectory: true) else {
            throw BackendError.configuration("The bundled backend is missing.")
        }
        try validate(bundled)
        let version = try String(contentsOf: bundled.appendingPathComponent("VERSION"), encoding: .utf8)
        let target = support.appendingPathComponent("backend", isDirectory: true)
        let installed = try? String(contentsOf: target.appendingPathComponent("VERSION"), encoding: .utf8)
        if installed != version || !fm.fileExists(atPath: target.appendingPathComponent("pyproject.toml").path) {
            try fm.createDirectory(at: support, withIntermediateDirectories: true)
            let staging = support.appendingPathComponent("backend-install-\(UUID().uuidString)")
            defer { try? fm.removeItem(at: staging) }
            try fm.copyItem(at: bundled, to: staging)
            // Downloaded tracker models survive source updates; all other source comes from the bundle.
            let models = target.appendingPathComponent("models")
            if fm.fileExists(atPath: models.path) {
                try fm.copyItem(at: models, to: staging.appendingPathComponent("models"))
            }
            if fm.fileExists(atPath: target.path) {
                _ = try fm.replaceItemAt(target, withItemAt: staging)
            } else { try fm.moveItem(at: staging, to: target) }
        }
        return target
    }

    private func validate(_ dir: URL) throws {
        for name in ["pyproject.toml", "uv.lock", "facet"] {
            guard FileManager.default.fileExists(atPath: dir.appendingPathComponent(name).path) else {
                throw BackendError.configuration("Backend source is missing \(name): \(dir.path)")
            }
        }
    }
}

public enum BackendError: LocalizedError {
    case configuration(String)
    public var errorDescription: String? { switch self { case .configuration(let value): return value } }
}
