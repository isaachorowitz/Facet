import SwiftUI

struct MenuPanel: View {
    @ObservedObject var model: AppModel
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text("Facet").font(.custom("Baskerville-Italic", size: 30))
                Spacer()
                Circle().fill(model.supervisor.state.tint).frame(width: 8, height: 8)
            }
            Text(model.supervisor.state.title).font(.caption).foregroundStyle(.secondary)
            if let detail = model.supervisor.state.detail {
                Text(detail).font(.caption).foregroundStyle(.secondary)
            }
            VStack(spacing: 10) {
                reading("Mood", value: model.mood)
                reading("Posture", value: model.postureText)
                reading("Stress", value: model.stressText)
            }
            Divider()
            Button("Open Dashboard") {
                openWindow(id: "dashboard")
                NSApp.activate(ignoringOtherApps: true)
            }
            Button(model.status?.paused == true ? "Resume" : "Pause") { model.pause() }
                .disabled(!model.controlsEnabled)
            Button(calibrateTitle) { model.calibrate() }
                .disabled(!model.controlsEnabled || (model.status?.calibratingSecondsLeft ?? 0) > 0)
            Toggle("Mic", isOn: Binding(get: { model.status?.settings?.mic ?? false }, set: model.setMic))
                .disabled(!model.controlsEnabled)
            Toggle("Nudges", isOn: Binding(get: { model.status?.settings?.notifications ?? false }, set: model.setNudges))
                .disabled(!model.controlsEnabled)
            Toggle("Launch at Login", isOn: Binding(get: { model.loginEnabled }, set: model.setLogin))
            if !model.socket.connected && model.supervisor.machine.reachable {
                Text(model.socket.error ?? "Connecting to live readings…").font(.caption).foregroundStyle(.secondary)
            }
            if let error = model.actionError {
                Text(error).font(.caption).foregroundStyle(.orange).textSelection(.enabled)
            }
            Divider()
            Button("Quit Facet") { NSApp.terminate(nil) }.keyboardShortcut("q")
        }
        .buttonStyle(.plain)
        .toggleStyle(.switch)
        .padding(22)
        .frame(width: 340)
        .preferredColorScheme(.dark)
    }

    private var calibrateTitle: String {
        let seconds = model.status?.calibratingSecondsLeft ?? 0
        return seconds > 0 ? "Calibrating · \(Int(ceil(seconds))) s" : "Calibrate (30 s)"
    }
    private func reading(_ title: String, value: String) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title).foregroundStyle(.secondary)
            Spacer()
            Text(value).multilineTextAlignment(.trailing)
        }.font(.system(size: 13))
    }
}
