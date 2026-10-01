import AppKit
import SwiftUI
import FacetCore

@main
struct FacetApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @StateObject private var model = AppModel.shared

    var body: some Scene {
        WindowGroup("Facet", id: "dashboard") {
            DashboardView(model: model)
                .frame(minWidth: 1180, minHeight: 720)
        }
        .windowStyle(.hiddenTitleBar)
        .windowResizability(.contentMinSize)
        .defaultSize(width: 1440, height: 900)
        MenuBarExtra {
            MenuPanel(model: model)
        } label: {
            Image(systemName: "circle.dotted.circle")
                .symbolRenderingMode(.palette)
                .foregroundStyle(model.supervisor.state.tint, .secondary)
        }
        .menuBarExtraStyle(.window)
    }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    private var quitting = false
    func applicationDidFinishLaunching(_ notification: Notification) { AppModel.shared.start() }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard !quitting else { return .terminateLater }
        quitting = true
        Task {
            await AppModel.shared.stop()
            sender.reply(toApplicationShouldTerminate: true)
        }
        return .terminateLater
    }
}

extension SupervisorState {
    var tint: Color {
        switch self {
        case .ready, .attached: return Color(red: 0.50, green: 0.84, blue: 0.64)
        case .failed: return Color(red: 0.94, green: 0.56, blue: 0.45)
        case .stopped, .stopping: return .gray
        default: return Color(red: 0.95, green: 0.71, blue: 0.38)
        }
    }
}
