# Facet native macOS app

Build and verification report · 1 October 2026

The native app is implemented in macos/, builds in release mode, passes all 14 tests, and produces an ad hoc signed arm64 Facet.app that passes strict bundle verification. The app was never launched. Camera and microphone permission behavior, native UI behavior, and the Python process driver remain unverified at runtime.

## Architecture

FacetCore contains the contract models, REST client, one native WebSocket client, source installation logic, and backend supervisor. Facet is the SwiftUI executable target, exposed as the FacetApp product. The package targets macOS 15, uses Swift tools 6.0 and language mode 5, and adds no third-party Swift dependencies. Package.swift follows AgentReel's separation between the app target name and binary product name.

| Component | Responsibility and evidence |
|---|---|
| Models.swift:1 and Message.swift:1 | Codable shapes for the whole contract. Missing fields decode as nil, missing message payloads use empty shapes, and unknown event/state values are tolerated. Invalid field types are rejected. A message still needs its type discriminator. |
| APIClient.swift:3 | Typed GETs and control POSTs, JSON settings patches that omit untouched keys, HTTP status validation, and a three-second request timeout. |
| WebSocketClient.swift:5 | One URLSessionWebSocketTask to ws://127.0.0.1:8765/ws?client=app, cancelled on quit and reconnected with capped backoff. The embedded dashboard retains its own existing web client. |
| SupervisorState.swift:30 | Pure state transitions, ownership flag, readiness, dashboard generation, and exponential restart backoff. |
| BackendSupervisor.swift:36 | Direct Foundation Process launches, health polling, external attachment, append-only logs, and owned process-group cleanup. |
| BackendPaths.swift:45 | Development override or versioned installation of bundled source into Application Support. |

Paths in the table refer to Sources/FacetCore/ under macos/.

Startup checks /api/health before acquiring process ownership. A compatible existing backend is attached to and is never terminated or replaced by this app. If an older server responds to /api/state but lacks /api/health, the app displays an update message and does not spawn a competing camera process. The check is repeated after environment preparation to cover another backend starting during uv sync.

For an owned backend, the flow is Preparing Python environment → Starting backend → Loading Clef-flash → Ready. The app runs uv sync --frozen --project <directory>, then uv run --frozen --project <directory> facet --no-browser. Both inherit UV_PROJECT_ENVIRONMENT=~/Library/Application Support/Facet/venv. Loopback host and port are pinned to the native dashboard's 127.0.0.1:8765 origin.

FACET_BACKEND_DIR selects development source. Otherwise the app copies Contents/Resources/backend to ~/Library/Application Support/Facet/backend when VERSION differs, using a staging directory and replacement. Downloaded tracker models survive source updates. uv resolution prefers the bundled binary, then ~/.local/bin/uv, /opt/homebrew/bin/uv, and PATH. The build writes a deterministic SHA-256 source version.

An unexpected exit exposes its reason and retries after 1, 2, 4, 8, 16, 32, then 60 seconds. A stable ready period resets the retry counter. Every owned backend launch increments the dashboard generation. Quit cancels networking and supervision, sends SIGTERM only to the recorded child process group, and sends SIGKILL after a five-second grace period if the group remains. Logs append to ~/Library/Logs/Facet/backend.log. An attached backend has no recorded child group.

## Native experience

Sources/Facet/FacetApp.swift:11 defines a hidden-title-bar WindowGroup with a default 1440×900 content size and minimum 1180×720. Closing the last window keeps Facet in the menu bar. DashboardView.swift:1 provides the #09090a loading surface, serif italic wordmark, animated ring, supervisor state, and WKWebView. The web view loads the loopback dashboard only after readiness, reloads for a new backend generation, and enables inspection in debug builds.

MenuPanel.swift:1 shows a state-colored dot, the latest face expression as mood, posture score/state, and face stress. Controls open the dashboard, pause or resume, calibrate for 30 seconds, and patch Mic or Nudges. Launch at Login uses SMAppService.mainApp. Control failures and login approval requirements appear in the panel. POST responses and WebSocket messages update the shared app model.

AppModel.swift:95 requests notification authorization on first launch. Notification messages become native notifications titled Facet, with the supplied text as body and kind as the thread identifier. The app-tagged WebSocket lets a compatible backend suppress its own osascript notification. MenuBarExtra uses window style.

## Camera and microphone permission attribution

BackendSupervisor.swift:115 launches bundled uv directly with Foundation Process from the Facet app process. It uses no Terminal, shell, launchd service, or external launcher. uv starts the Python backend within that app-owned responsibility chain, allowing macOS to identify Facet.app as the responsible application for camera and microphone prompts. Attaching to an existing backend keeps that backend's existing permission attribution.

Resources/Info.plist identifies com.ziplyne.facet and gives honest camera and microphone usage descriptions stating that frames and audio stay on this Mac and are never saved. Resources/Facet.entitlements grants hardened-runtime camera and audio-input access. The app is unsandboxed so it can launch Python and maintain its environment. The driver verifies process-group isolation before using group signals.

The final signature inspection proves that the bundle has both device entitlements and the hardened-runtime flag. Permission attribution itself is an implementation intent that still needs an actual app launch and an observed macOS privacy prompt. It is not proven by compilation or signature verification. uv dependency installation and model downloads still need network access on first launch; the local-only statement concerns captured camera and microphone data.

## Bundle and verification

scripts/make-icon.swift draws a graphite rounded tile and five concentric 270° arcs in the requested amber, coral, lilac, ice, and mint colors. The generated 1024px icon was visually inspected. scripts/build-app.sh builds release, assembles build/Facet.app, bundles uv and the specified backend files, writes VERSION, signs uv before the app, and verifies the bundle. Identity selection follows AgentReel: FACET_SIGN_IDENTITY override, Developer ID Application, Apple Development, then ad hoc. Hardened runtime remains enabled for this app's ad hoc build because it has no embedded Swift frameworks needing AgentReel's exception.

| Executed command from macos/ | Result |
|---|---|
| swift build -c release | PASS. Release build completed. |
| swift test | PASS. 14 XCTest tests, 0 failures. |
| FACET_SIGN_IDENTITY=- scripts/build-app.sh | PASS. Built build/Facet.app. |
| codesign --verify --deep --strict build/Facet.app | PASS. Exit status 0. |
| plutil -lint build/Facet.app/Contents/Info.plist | PASS. Info.plist: OK. |
| codesign -d --verbose=4 build/Facet.app | arm64; com.ziplyne.facet; flags=0x10002(adhoc,runtime). |
| codesign -d --entitlements - build/Facet.app | camera=true; audio-input=true; no sandbox entitlement. |

Raw evidence is retained in macos/build-release.log, build-tests.log, build-bundle.log, and build-verification.log. Tests cover all seven documented WebSocket variants, all four notification kinds, nullable speech verdicts, every REST JSON shape, sparse keys, future events, malformed types, settings patches, mocked request methods and routes, source installation/version updates, and supervisor ownership/backoff/state transitions. Round-trip fixture assertions compare every non-null key. No test spawns a backend process. Every tested POST uses an in-memory URLProtocol interceptor with the facet.test host and never reaches the live service.

Bundled backend VERSION: a6c61838b1f4635e98e46197342b2e31404ff29c0954a0f6e688f10dea50084b

## Runtime limits and scope

Read-only live checks returned /api/health HTTP 404 and /api/state HTTP 200 with judge=ready. The final health check still returned 404. Therefore attachment to the currently running process was not demonstrated and this app would display the compatibility message for it. After that backend is updated independently, reopen the app to run the compatibility check again.

Other work outside macos/ appeared during the task and was preserved. The final bundled source snapshot includes facet/api.py with /api/health and app-client notification suppression. These are source observations, not evidence that the running backend has those routes. No web/dist directory was present when this bundle was assembled, so the bundled backend has its existing static dashboard fallback. The native shell can display the React dashboard when its built web/dist is supplied, but that path was not rendered or exercised here.

Unverified without launching the app: first-run uv sync and model preparation; camera/microphone prompts and attribution; actual group termination and restart timing; native loading/window/menu behavior; dashboard rendering and reload; WebSocket reconnection; native notification delivery; pause, resume, calibration and settings effects; and Launch at Login registration. Developer ID signing and notarization were outside the requested ad hoc verification.

All task-created source, resources, tests, build outputs, and this report are under macos/. The live backend received no POSTs and was never stopped or restarted by this task. There were no app launches or git writes. Verification commands finished; no task-owned background service was left running.
