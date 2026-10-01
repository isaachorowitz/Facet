# Facet React dashboard report

The dashboard implements all ten requested v2 additions from `docs/contract.md`. The contract, previous report, and every original file in `web/src` were read before implementation. Source, fixtures, tests, and build output for this change are under `web/`. No dependencies were added, and no staging, commits, or other git mutations were performed.

React 19, strict TypeScript, Vite, pnpm, and the existing `motion/react` remain the stack. Inline SVG and the existing Motion primitives preserve the dashboard's visual language without another icon or animation dependency. Original `styles.css` remains intact; `v2.css` adds the responsive layout and v2 presentation rules.

## Implemented features

| Feature | Result |
| --- | --- |
| Hands on the mirror | Both 21-point skeletons map unmirrored frame coordinates through `live.view`, apply the centred 720×600 image's `object-fit: cover` geometry, then reflect horizontally. Right is mint, left is ice; dots and bones glow softly and fade on entry and exit. Overlays hide when the camera is unavailable or crop metadata is absent. |
| Gestures | Hand-drawn SVG for thumbs up/down, victory, pointing up, open palm, wave, I-love-you, and closed fist. A spring entrance, expanding ring, action label, and floating exit celebrate socket events. Focus transition events resolve the started/ended label. No emoji were added. |
| Face touches | A brief amber edge glow accompanies `face_touch`; the mirror shows the hourly count. Daily totals appear in Stats. |
| Narrator | Fresh captions replace the generated Now sentence, reveal by word, and show a narrator label and timestamp. At 40 seconds the generated sentence returns. Older history cannot replace newer socket captions. Long captions occupy up to three lines, with full text available on hover and to assistive technology. |
| Focus | Idle “Focus 25” control; active countdown ring and minutes remaining; clicking toggles through `POST /api/focus`. Pending requests disable the control; unavailable endpoints show a toast. Focus cools the aura and mirror scan. |
| Day marks | GET history, summary marks, and socket marks merge without duplicates. Small gesture icons sit at their time along the chart's top edge, with hover and keyboard-focus tooltips. Bucket tooltips include their marks. Timeline-only kinds fall back to bucket-start markers. Mark times can extend the day domain. |
| Wellness | A three-column, nine-cell stats grid retains desk time, posture, talking, breaks, and predominant expression alongside sips, face touches, eye breaks taken/due, and longest focus across streaks and sessions. Missing v2 counts show a dash. |
| Story | The selected day's Story button opens a portal overlay with blurred backdrop, serif headline, date, and word reveal. Opening performs GET; Regenerate alone performs POST. Esc, outside click, and Close dismiss it. Background controls become inert; keyboard focus stays in the dialog and returns to Story. Loading and unavailable states fit in the overlay. Long stories scroll inside the dialog. |
| Posture | Brief stale readings hold the last visible figure and score, dim the figure, and show “holding”. Missing shoulders show a quiet silhouette and empty state. |
| macOS shell | `html[data-shell="mac"]` reserves 76px of header padding for traffic lights. Production code never removes or overwrites the app-injected attribute. |

## Contract and compatibility

`src/api/types.ts` adds the v2 types and makes new members of existing Live, Posture, TimelinePoint, and Summary shapes optional. Boundary validation accepts v1 payloads while validating supplied v2 fields, new events, and notification kinds. Invalid landmark tuples and non-positive crop dimensions are rejected.

`client.ts` adds timeout-protected, validated requests for marks, captions, focus, and recap. Optional marks/caption history failures are quiet; recap and focus failures stay contained in their UI. New POSTs occur only after deliberate clicks. Socket state retains fresh captions, focus transitions, the latest gesture/touch event, and merged marks. Day loading retains its existing stale-response guard.

The new motion preference hook subscribes to changes in `prefers-reduced-motion`, including changes while the page is open. Reduced motion displays complete caption/story text, removes visible ring bursts and gesture movement, and disables hand fades. Existing global reduced-motion CSS remains in effect.

## Verification, 2026-10-02 local time

| Check | Outcome |
| --- | --- |
| `cd web && pnpm typecheck && pnpm build` | Passed, exit 0. Strict TypeScript and production build are green. |
| `FACET_CONTRACT_SMOKE=1 node --test web/tests/behaviour.test.mjs` | 12 passed, 0 failed. Includes crop/cover/reflection geometry, caption age boundaries, focus expiry math, mark deduplication/domain expansion, v1/v2 validation, all new socket event kinds, and existing behavior checks. |
| GET-only live contract smoke | `/api/state`, `/api/timeline`, `/api/summary`, and `/api/speech` from `127.0.0.1:8765` passed validation. No live backend POSTs were sent. |
| Managed isolated browser, `tests/browser-v2.mjs` | Passed layout and interaction assertions at 1280×720, 1440×900, 1920×1080, and 2560×1440. Document scroll dimensions matched each viewport; all wellness cells stayed inside the padded card; 42 hand joints rendered. Zero page errors in the successful fixture run. |
| Managed isolated browser, `tests/browser-v2-states.mjs` | Passed face-touch feedback, hand removal, focus-ended label, bucket mark details, caption expiry, outside-click dismissal, runtime reduced-motion change, and v1/missing-endpoint fallbacks. |
| Mocked actions | Focus start/end and recap regeneration were exercised with intercepted responses. All fixture API methods, video, and WebSockets were intercepted; these actions never reached the user's backend. |
| Visual inspection | Inspected the compact dashboard and populated story overlay from synthetic video/data. Original mood/ring/chart animation components remain in place. |
| Source scan | No `any`, debug console calls, or TODOs in `src`. No new dependencies. |

The browser fixtures are replayable through the managed Playwright MCP: start the existing Vite dev command on port 5178, run `tests/browser-v2.mjs` via `browser_run_code`, then `tests/browser-v2-states.mjs` in that same fixture page. The primary fixture remaps its recorded day to the browser's current local day. `behaviour.test.mjs` runs directly with Node and uses the installed TypeScript compiler.

The host npm configuration warns about an unset `NPM_TOKEN`; both required commands completed successfully. The temporary Vite server and task browser were closed after verification. The user's existing backend was not restarted or stopped.

## States and behavior not observed rendered

Actual camera-to-hand pixel alignment, rapidly moving hands against a real MJPEG stream, real detector-driven gestures, live narrator generation, and real focus/recap POST responses remain unverified. Browser interactions used synthetic data. The app-injected macOS attribute was simulated in Chromium; the native WKWebView and traffic-light placement were not opened.

The rendered checks did not cover a cached recap with `text: null`, a focus countdown naturally reaching zero, densely overlapping marks, or arbitrarily long captions/stories. Their boundary/fallback logic is implemented; focus expiry and caption freshness were tested as pure functions. Safari/Firefox, actual camera reconnect behavior, and original Calibrate/Mic/Nudges/Pause actions were not exercised. Frame-for-frame animation parity was not measured.

## Production bundle

| Output | Size | Gzip |
| --- | ---: | ---: |
| `dist/index.html` | 0.63 kB | 0.38 kB |
| `dist/assets/index-CMZtMgLs.css` | 25.40 kB | 6.93 kB |
| `dist/assets/index-BEJcf7Ph.js` | 422.55 kB | 134.32 kB |
