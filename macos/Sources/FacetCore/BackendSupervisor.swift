import Foundation
import Combine
import Darwin

@MainActor
public final class BackendSupervisor: ObservableObject {
    @Published public private(set) var machine = SupervisorMachine()
    public var state: SupervisorState { machine.state }
    public var generation: Int { machine.generation }
    private let api: APIClient
    private let paths: BackendPaths
    private var loop: Task<Void, Never>?
    private var child: Process?
    private var processGroup: pid_t?
    private var logHandle: FileHandle?

    public init(api: APIClient = APIClient(), paths: BackendPaths = BackendPaths()) {
        self.api = api
        self.paths = paths
    }

    public func start() {
        guard loop == nil else { return }
        loop = Task { [weak self] in await self?.supervise() }
    }

    public func stop() async {
        machine.stop()
        let running = loop
        loop?.cancel(); loop = nil
        await running?.value
        await terminateOwnedGroup()
        machine.stopped()
    }

    private func supervise() async {
        // Attachment never acquires ownership, including when an external backend later disappears.
        if await attachIfRunning() { return }
        while !Task.isCancelled {
            do {
                machine.prepare()
                let directory = try paths.backendDirectory()
                let uv = try paths.uvURL()
                try launch(uv, arguments: ["sync", "--frozen", "--project", directory.path], directory: directory)
                let result = try await waitForExit()
                await terminateOwnedGroup()
                guard result == 0 else { throw BackendError.configuration("uv sync exited with status \(result). See backend.log.") }
                try Task.checkCancellation()
                // Recheck before spawning, in case another app started a backend during preparation.
                if await attachIfRunning() { return }
                try Task.checkCancellation()
                try launch(uv, arguments: ["run", "--frozen", "--project", directory.path, "facet", "--no-browser"], directory: directory)
                machine.spawned()
                await monitorOwned()
                try Task.checkCancellation()
                let code = child?.terminationStatus ?? -1
                await terminateOwnedGroup()
                try Task.checkCancellation()
                let delay = machine.unexpectedExit(reason: "Backend exited with status \(code). See backend.log.")
                try await Task.sleep(for: .seconds(delay))
            } catch is CancellationError { return }
            catch {
                if Task.isCancelled { return }
                await terminateOwnedGroup()
                let delay = machine.unexpectedExit(reason: error.localizedDescription)
                do { try await Task.sleep(for: .seconds(delay)) } catch { return }
            }
        }
    }

    private func attachIfRunning() async -> Bool {
        let health = try? await api.health()
        if Task.isCancelled { return true }
        if let health, health.ok == true {
            machine.attach(judge: health.judge)
            await monitorAttached()
            return true
        }
        // Refuse to start a competing camera process if an older backend lacks /api/health.
        let existing = try? await api.state()
        if Task.isCancelled { return true }
        if existing?.status != nil {
            machine.fail("A running backend lacks /api/health. Update it before using the native app.")
            return true
        }
        return false
    }

    private func monitorAttached() async {
        while !Task.isCancelled {
            if let health = try? await api.health(), health.ok == true { machine.health(judge: health.judge) }
            else { machine.fail("Attached backend unavailable. Waiting for it to return.") }
            do { try await Task.sleep(for: .seconds(1)) } catch { return }
        }
    }

    private func monitorOwned() async {
        var readySince: Date?
        machine.waitingForJudge()
        while !Task.isCancelled, child?.isRunning == true {
            if let health = try? await api.health(), health.ok == true {
                machine.health(judge: health.judge)
                if health.judge == "ready" {
                    if readySince == nil { readySince = Date() }
                    if let readySince, Date().timeIntervalSince(readySince) >= 30 { machine.stable() }
                } else { readySince = nil }
            } else {
                if machine.reachable { machine.connectionLost() }
                readySince = nil
            }
            do { try await Task.sleep(for: .seconds(1)) } catch { return }
        }
    }

    private func launch(_ executable: URL, arguments: [String], directory: URL) throws {
        try Task.checkCancellation()
        let fm = FileManager.default
        try fm.createDirectory(at: paths.log.deletingLastPathComponent(), withIntermediateDirectories: true)
        // O_APPEND also makes simultaneous stdout/stderr writes append safely.
        let fd = open(paths.log.path, O_WRONLY | O_CREAT | O_APPEND, S_IRUSR | S_IWUSR)
        guard fd >= 0 else { throw BackendError.configuration("Cannot open backend.log: \(String(cString: strerror(errno)))") }
        let handle = FileHandle(fileDescriptor: fd, closeOnDealloc: true)
        let process = Process()
        process.executableURL = executable
        process.arguments = arguments
        process.currentDirectoryURL = directory
        process.environment = paths.childEnvironment
        process.standardInput = FileHandle.nullDevice
        process.standardOutput = handle
        process.standardError = handle
        try process.run() // Direct child: never Terminal, launchd, a shell, or a helper launcher.
        let pid = process.processIdentifier
        // Foundation normally gives Process its own group. Verify before ever sending a group signal.
        if getpgid(pid) != pid, setpgid(pid, pid) != 0, process.isRunning {
            process.terminate()
            throw BackendError.configuration("Could not isolate the backend process group.")
        }
        child = process
        processGroup = pid
        logHandle = handle
    }

    private func waitForExit() async throws -> Int32 {
        while child?.isRunning == true {
            try await Task.sleep(for: .milliseconds(250))
        }
        try Task.checkCancellation()
        return child?.terminationStatus ?? -1
    }

    private func terminateOwnedGroup() async {
        guard let group = processGroup else { return }
        processGroup = nil
        // Only the group recorded from our direct child is ever signalled. Attached processes have none.
        kill(-group, SIGTERM)
        if kill(-group, 0) == 0 {
            // An uncancelled cleanup task ensures quitting cannot skip the grace period or SIGKILL.
            await Task.detached {
                try? await Task.sleep(for: .seconds(5))
                if kill(-group, 0) == 0 { kill(-group, SIGKILL) }
            }.value
        }
        child = nil
        try? logHandle?.close(); logHandle = nil
    }
}
