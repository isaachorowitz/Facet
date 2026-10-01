import AppKit
import Combine
import FacetCore
import ServiceManagement
import UserNotifications

@MainActor
final class AppModel: ObservableObject {
    static let shared = AppModel()
    let supervisor = BackendSupervisor()
    let socket = WebSocketClient()
    let api = APIClient()
    private let notifications = NotificationBridge()
    @Published private(set) var status: Status?
    @Published private(set) var face: FaceVerdict?
    @Published private(set) var posture: Posture?
    @Published private(set) var busy = false
    @Published var actionError: String?
    @Published private(set) var loginEnabled = SMAppService.mainApp.status == .enabled
    private var observers = Set<AnyCancellable>()

    private init() {
        supervisor.$machine.sink { [weak self] machine in
            guard let self else { return }
            self.objectWillChange.send()
            if machine.reachable { self.socket.start() }
            else { self.status = nil; self.face = nil; self.posture = nil }
        }.store(in: &observers)
        socket.objectWillChange.sink { [weak self] in self?.objectWillChange.send() }.store(in: &observers)
        socket.onMessage = { [weak self] in self?.receive($0) }
    }

    var controlsEnabled: Bool { supervisor.machine.reachable && socket.connected && status != nil && !busy }
    var mood: String { face?.expression?.choice?.replacingOccurrences(of: "_", with: " ").capitalized ?? "Waiting for a reading" }
    var postureText: String {
        guard let posture, let state = posture.state, state != "unknown", let score = posture.score else { return "Unknown" }
        return "\(Int(score.rounded())) / 100 · \(state.capitalized)"
    }
    var stressText: String {
        guard let stress = face?.stress else { return "Unknown" }
        let words = ["Low", "Mild", "Moderate", "High", "Very high"]
        return "\(words[min(4, max(0, Int(stress.rounded())))]) · \(String(format: "%.1f", stress)) / 4"
    }

    func start() { notifications.requestAtFirstLaunch(); supervisor.start() }
    func stop() async { socket.stop(); await supervisor.stop() }

    func pause() { perform { try await self.api.pause(!(self.status?.paused ?? false)) } }
    func calibrate() { perform { try await self.api.calibrate() } }
    func setMic(_ enabled: Bool) {
        var patch = Settings(); patch.mic = enabled
        perform { try await self.api.settings(patch) }
    }
    func setNudges(_ enabled: Bool) {
        var patch = Settings(); patch.notifications = enabled
        perform { try await self.api.settings(patch) }
    }
    func setLogin(_ enabled: Bool) {
        do {
            if enabled { try SMAppService.mainApp.register() }
            else { try SMAppService.mainApp.unregister() }
            loginEnabled = SMAppService.mainApp.status == .enabled
            if SMAppService.mainApp.status == .requiresApproval {
                actionError = "Approve Facet in System Settings → General → Login Items."
            }
        } catch { actionError = error.localizedDescription }
    }

    private func perform(_ action: @escaping () async throws -> Status) {
        guard controlsEnabled else { return }
        busy = true; actionError = nil
        Task {
            defer { busy = false }
            do { status = try await action() }
            catch { actionError = "Could not update Facet: \(error.localizedDescription)" }
        }
    }

    private func receive(_ message: BackendMessage) {
        switch message {
        case .hello(let hello): status = hello.status; face = hello.latest?.face
        case .live(let live): status = live.status; posture = live.posture
        case .face(let value, _): face = value
        case .calibrated(let value): status = value
        case .notification(let nudge): notifications.post(nudge)
        case .overall, .speech, .unknown: break
        }
    }
}

final class NotificationBridge: NSObject, UNUserNotificationCenterDelegate {
    private let center = UNUserNotificationCenter.current()
    override init() { super.init(); center.delegate = self }

    func requestAtFirstLaunch() {
        let key = "Facet.requestedNotificationAuthorization"
        guard !UserDefaults.standard.bool(forKey: key) else { return }
        center.requestAuthorization(options: [.alert, .sound]) { _, error in
            if error == nil { UserDefaults.standard.set(true, forKey: key) }
        }
    }
    func post(_ nudge: Nudge) {
        guard let text = nudge.text, !text.isEmpty else { return }
        let content = UNMutableNotificationContent()
        content.title = "Facet"
        content.body = text
        content.threadIdentifier = nudge.kind ?? "facet"
        content.sound = .default
        center.add(UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil))
    }
    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .sound])
    }
}
