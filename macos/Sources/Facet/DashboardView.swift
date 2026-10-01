import SwiftUI
import WebKit

struct DashboardView: View {
    @ObservedObject var model: AppModel
    private let graphite = Color(red: 9 / 255, green: 9 / 255, blue: 10 / 255)

    var body: some View {
        ZStack {
            graphite
            if model.supervisor.state.isReady {
                DashboardWebView(generation: model.supervisor.generation)
                    .overlay(alignment: .top) {
                        // The web view takes every click, so a thin strip along the top edge moves the window.
                        Color.clear.frame(height: 14).contentShape(Rectangle()).gesture(WindowDragGesture())
                    }
            } else {
                VStack(spacing: 26) {
                    Text("Facet")
                        .font(.custom("Baskerville-Italic", size: 68))
                        .foregroundStyle(Color(red: 0.95, green: 0.91, blue: 0.85))
                    LoadingRing()
                    Text(model.supervisor.state.title)
                        .font(.system(size: 15, weight: .medium))
                        .foregroundStyle(.white.opacity(0.75))
                    if let detail = model.supervisor.state.detail {
                        Text(detail).font(.caption).foregroundStyle(.white.opacity(0.45))
                    }
                }
                .padding(40)
            }
        }
        .ignoresSafeArea()
        .preferredColorScheme(.dark)
    }
}

private struct LoadingRing: View {
    @State private var rotating = false
    var body: some View {
        ZStack {
            Circle().stroke(.white.opacity(0.06), lineWidth: 2)
            Circle().trim(from: 0, to: 0.75)
                .stroke(AngularGradient(colors: [.clear, Color(red: 0.95, green: 0.71, blue: 0.38)], center: .center),
                        style: StrokeStyle(lineWidth: 2, lineCap: .round))
                .rotationEffect(.degrees(rotating ? 360 : 0))
                .animation(.linear(duration: 3).repeatForever(autoreverses: false), value: rotating)
        }
        .frame(width: 52, height: 52)
        .onAppear { rotating = true }
    }
}

struct DashboardWebView: NSViewRepresentable {
    let generation: Int
    func makeCoordinator() -> Coordinator { Coordinator() }
    func makeNSView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        // Hidden title bar: leave room for the traffic lights beside the wordmark.
        let css = "header{padding-left:72px}"
        let script = "var s=document.createElement('style');s.textContent='\(css)';document.documentElement.appendChild(s);document.documentElement.dataset.shell='mac';"
        configuration.userContentController.addUserScript(
            WKUserScript(source: script, injectionTime: .atDocumentEnd, forMainFrameOnly: true))
        let view = WKWebView(frame: .zero, configuration: configuration)
        view.navigationDelegate = context.coordinator
        view.setValue(false, forKey: "drawsBackground")
        #if DEBUG
        view.isInspectable = true
        #endif
        load(view, context: context)
        return view
    }
    func updateNSView(_ view: WKWebView, context: Context) {
        if context.coordinator.generation != generation { load(view, context: context) }
    }
    private func load(_ view: WKWebView, context: Context) {
        context.coordinator.generation = generation
        view.load(URLRequest(url: URL(string: "http://127.0.0.1:8765/")!))
    }
    final class Coordinator: NSObject, WKNavigationDelegate {
        var generation = -1
        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            let url = navigationAction.request.url
            let local = url?.scheme == "http" && url?.host == "127.0.0.1" && url?.port == 8765
            decisionHandler(local ? .allow : .cancel)
        }
    }
}
