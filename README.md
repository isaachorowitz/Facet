# Facet

A local mirror that watches your face and listens to your voice through the day and
tells you how you look and sound: expression, stress, fatigue, focus, energy, mood,
posture, what you are doing, and how all of it changes over the day. Nothing leaves
the Mac. Video frames and audio are never written to disk; only numbers (and
transcripts, if you keep them), gesture marks, captions and recaps go into a local
SQLite file.

## Run

```sh
cd ~/Projects/facet
uv run facet            # opens http://127.0.0.1:8765
uv run facet --no-browser
uv run facet --host 127.0.0.1 --port 8799 --no-browser
```

The first start downloads Clef-flash (about 19 GB) and the narrator into the
Hugging Face cache, and the three MediaPipe trackers into `models/`. Later starts
reuse these cached models.

The terminal you start it from needs camera and microphone permission (System
Settings → Privacy & Security). Pause in the dashboard releases the camera and mic.

## How it works

Six channels, kept separate so they can check each other:

1. **Measured face** (`facet/face.py`). MediaPipe tracks 478 face points and 52
   muscle activations at about 30 fps on the CPU. From these come smile (and whether
   it reaches the eyes), brow furrow, eye squint, lip press, jaw, frown, blinks per
   minute, yawns, head pose, gaze, distance from the screen, and head movement. If
   other people are in frame, it stays on the largest face, which is usually you.
2. **Clef-flash judge** (`facet/judge.py`, `facet/clef_mlx.py`). About once a
   second, a head-and-shoulders crop goes to Cloudflare's Clef-flash decision model.
   It answers typed questions from the image alone: expression (14 options),
   stress, fatigue, focus, energy, positivity and tension every cycle; posture,
   activity and yes/no flags (jaw clenched, heavy eyes, distracted...) every third.
   Clef runs in its own process. Its Qwen3.5 backbone runs on MLX with mlx-vlm's
   Metal kernels; the small schema head stays in PyTorch exactly as released.
3. **Posture** (`facet/posture.py`). MediaPipe Pose on its own thread at 10 Hz:
   head height above the shoulder line, shoulder tilt, sinking, leaning in, scored
   0 to 100 against your calibrated (or best recent) upright posture. A face
   position only gates pose selection when seen within 0.5 seconds. Misses hold the
   last skeleton and smoothed score for up to 3 seconds, marked `stale`, before
   posture becomes invisible.
4. **Voice** (`facet/voice.py`). The mic (Razer Seiren first, then the Brio) is cut
   into speech segments, transcribed with Parakeet (MLX), and measured for pace,
   pitch, pitch variation, loudness, and pauses. A HuBERT speech emotion model adds
   neutral/happy/angry/sad scores. Clef turns all of that into a tone (calm, rushed,
   tense, flat...) plus stress and energy.
5. **Hands and gestures** (`facet/hands.py`). MediaPipe GestureRecognizer runs on
   its own CPU thread at about 15 Hz, tracking up to two hands. Pose, hands and
   narration share one latest 640×360 full RGB frame; hand inference never runs
   on the camera thread. Handedness labels are corrected for unmirrored input.
6. **Vision narrator** (`facet/narrator.py`). A separate process runs
   `mlx-community/Qwen3.5-9B-MLX-4bit` with mlx-vlm. Every 12 seconds while your
   face is present and tracking is unpaused, it describes the current full frame
   in one present-tense sentence, addressed as "you", of at most 22 words. It
   uses greedy decoding, about 48 new tokens, and disables thinking through the
   chat template. Busy cycles are skipped. It never shares Clef's work queue.
   Frames stay in memory; only caption text is stored.

Every 15 s an **overall read** combines the last 90 s of face judgments, your
measured face compared with your usual face, recent voice, and time since your last
break, plus the last three captions. It decides mood, stress, fatigue, focus, needs a break, in flow, and
overwhelmed. Sustained stress, fatigue, or a long stretch without a break sends
a macOS notification, at most one of each kind per 30 minutes.

## Performance

Measured on an M5 Max (128 GB), Clef-flash bf16, a 384 px crop:

| | Released PyTorch path (MPS) | Facet (MLX backbone) |
|---|---|---|
| Face judgment, all 18 questions | 5.8 s | 1.9 s |
| Face judgment, core 7 questions | | 0.8 s |
| Voice judgment | 2.1 s | 0.6 s |
| Overall read | 2.6 s | 0.7 s |
| New face reading on screen | every 2.5 s | about every 1.2 s |
| Startup to first reading | about 60 s | about 25 s |
| Face tracking | 20 to 31 fps | 31 fps (camera limit) |

Answers match the released path to within 0.008 probability with no top choice
changed (`uv run python scripts/compare_backends.py <image>` checks this). 8-bit
quantization gave no extra speed, because prefill is compute bound, so weights stay
bf16. `FACET_BACKEND=torch` switches back to the released code path.

## Your baseline

Faces differ, and a relaxed face can look "serious" to any model. Facet learns
your usual face from the last 14 days, and the dashboard shows each measurement
against it (▲/▼ in standard deviations, a tick mark on each bar). Press
**Calibrate** once, sitting upright and relaxed for 30 seconds, to anchor your face and posture sooner.

## Limits

- Cameras see expressions, not feelings. Trends and changes from your own baseline
  are more trustworthy than any single reading.
- The mic cannot tell your voice from someone else's in the room.
- Clef-flash was not trained on faces specifically; its vision is general purpose.

## Data

`~/Library/Application Support/Facet/facet.db`. Delete it to start over. Toggle
"keep transcripts" off to store voice measurements without the words.

Settings via environment: `FACET_CAMERA`, `FACET_MIC` (comma-separated name
fragments), `FACET_JUDGE_INTERVAL` (seconds between face readings, default 1.2),
`FACET_BACKEND` (`mlx` or `torch`), `FACET_CROP`, `FACET_HOST`, `FACET_PORT`,
`FACET_DATA`, `FACET_HEADLESS`, `FACET_NARRATOR` (default
`mlx-community/Qwen3.5-9B-MLX-4bit`; accepts another mlx-vlm model repository).

## Backend and tests

`--host` and `--port` override `FACET_HOST` and `FACET_PORT`. The defaults remain
`127.0.0.1:8765`. `GET /api/health` reports backend availability, judge status,
and the installed Facet version. The backend serves `web/dist` when built,
including `/assets`, or the bundled dashboard otherwise. macOS app WebSockets
use `/ws?client=app`; while any app connection is open, notification events still
go to clients and history, and the app handles the native notification.

Shutdown on SIGTERM or Ctrl-C signals and joins workers, releases hardware,
closes SQLite and stops the Clef child process. The Clef child also watches for
its parent disappearing. Voice analysis finishes any current model call before
its thread exits.

Run the test suite with `uv run pytest -q`. Tests use temporary databases and
block hardware/model startup. To exercise the API manually without hardware or
models, use a separate data directory and port:

```sh
FACET_HEADLESS=1 FACET_DATA="$(mktemp -d)" uv run facet --no-browser --port 8799
```

Headless mode skips model downloads and camera, pose, hands, voice, judge, narrator
and history/wellness worker startup. The judge remains `loading`, with the API and WebSocket shapes
available for client development and CI.


## Gestures, focus and wellness

| Gesture | Action |
|---|---|
| Thumb up (`Thumb_Up`) | Mark a good moment |
| Thumb down (`Thumb_Down`) | Mark a rough moment |
| Victory (`Victory`) | Mark a win |
| Pointing up (`Pointing_Up`), held 1.5 seconds | Toggle a 25-minute focus session |
| Wave | Send a greeting gesture for the client UI |
| Closed fist, open palm, ILoveYou | Show the gesture without an action |

Gestures need confidence at least 0.6 and a continuous hold of at least 0.6 seconds,
except pointing up. Each gesture has a 3-second cooldown shared between hands.
One continuous hold fires once; release or change the gesture to repeat it. A wave
requires an open palm with at least three horizontal wrist reversals within 1.5
seconds, each moving at least 4% of the frame width. Keep waving through the hold.

A hand near your face means any landmark intersects the face box expanded by 15%.
A continuous episode lasting at least 0.5 seconds counts once, including when both
hands are near the face. The live count covers the last hour. This measures proximity,
not physical contact.

Focus sessions end automatically or when toggled again. All non-posture nudges are
suppressed during a session; their wellness conditions continue to be measured.
Posture nudges remain available. Session events and duration are included in the day
summary, and an active session survives a backend restart.

Wellness adds these reminders, each at most once per kind per 30 minutes:

- **Eyes:** after 20 minutes on screen, look 20 feet away for 20 seconds. The
  reminder is counted as due once per screen stretch; looking away for at least
  20 seconds afterwards counts as taken and resets the screen timer.
- **Blink:** blink rate below 8 per minute continuously for 5 minutes.
- **Hydrate:** 90 minutes of observed presence without an estimated sip. A sip is
  a transition into Clef's `eating_or_drinking` activity at confidence at least
  0.5, counted at most once per 60 seconds. Eating can also count; this is a proxy.
  `minutes_since_sip` is null until the first sip today.
- **Stand:** 50 minutes at the desk without a break, replacing the old 90-minute
  break wording. An absence of at least 180 seconds resets the desk stretch.

Pause releases the camera and mic, stops caption/gesture activity, and resets active
wellness stretches without inventing a taken eye break. Existing notification
settings and macOS app notification forwarding still apply.

## v2 API

The exact additive shapes are in [the backend contract](docs/contract.md#v2-additions-hands-gestures-narration-wellness).
`live` gains `hands`, normalized `view`, `wellness`, `focus_session`, and `caption`;
posture gains `stale`. Landmarks and the view box refer to the original, unmirrored
camera frame. `view` is available even without an MJPEG subscriber.

WebSocket events add `gesture`, `mark`, `caption`, `focus`, and `face_touch`. Marks,
caption text, focus events, wellness counters and reminders use the existing events
table; no schema migration is needed. Summaries add `marks`, `sips`, `face_touches`,
`eyes_breaks_taken`, `eyes_breaks_due`, and `focus_sessions`. Timeline buckets add
`marks` when they contain marked moments. Sessions appear on the date they started,
including a session that ends after midnight.

| Method | Path | Result |
|---|---|---|
| GET | `/api/marks?date=YYYY-MM-DD` | Marks for that local date, oldest first |
| GET | `/api/captions?minutes=60` | Caption objects `{ts, text}`, oldest first |
| POST | `/api/focus` with `{minutes?: number}` | Toggle focus; return active `{started, ends, minutes}` or null |
| GET | `/api/recap?date=YYYY-MM-DD` | Cached `{date, text, generated_at}`, or `{date, text: null}` |
| POST | `/api/recap?date=YYYY-MM-DD` | Generate or regenerate and cache the day story |

Omitted dates use today. Dates must be valid ISO calendar dates. Focus defaults to
25 minutes; custom duration must be a finite positive number no greater than 1440.
Recap GET never loads or calls a model. POST uses the dedicated narrator in text
mode with the day's summary, marks, sampled distinct captions and nudges. It returns
a 120 to 180 word story and preserves an existing cache if generation fails. A busy,
loading, unavailable or headless narrator returns HTTP 503 for generation.

Captions and recaps are model observations and can misread visual details or draw
unsupported conclusions. They are stored locally and should be read alongside the
measured evidence.

## v2 verification report

Verified on 1–2 October 2026 on this Mac's Apple M5 Max with 128 GB RAM. This report
covers local backend source, tests, standalone model inference and isolated HTTP.
The camera-owning Facet.app backend on 127.0.0.1:8765 was left running. No requests
were sent to it, its data directory was untouched, and no git writes were performed.

The final narrator comparison used the same public-domain desk photograph,
[Woman working behind computer, PxHere, CC0](https://commons.wikimedia.org/wiki/File:Woman_working_behind_computer.jpg),
resized to 540×360 while retaining the full frame. Model download time is excluded
from load time. Each row measures one process loading the cached model, followed by
three captions. Models and Metal kernels were already cached for these final runs;
other applications remained running, so these are measurements of this run.

| Model | Load time | Caption 1 | Caption 2 | Caption 3 | Mean per caption |
|---|---:|---:|---:|---:|---:|
| [Qwen3.5-9B-MLX-4bit](https://huggingface.co/mlx-community/Qwen3.5-9B-MLX-4bit) | 10.12 s | 2.43 s | 0.64 s | 1.35 s | 1.47 s |
| [Qwen3.5-4B-MLX-4bit](https://huggingface.co/mlx-community/Qwen3.5-4B-MLX-4bit) | 28.62 s | 1.16 s | 0.69 s | 0.85 s | 0.90 s |

**9B remains the default:** every caption in the final run was below the specified
3-second cutoff. First-ever 9B setup was slower: download 82.18 s, load 48.41 s,
then captions 12.75, 1.87 and 1.77 s. The first 4B run downloaded in 43.28 s, loaded
in 5.30 s, then captioned in 0.81, 0.28 and 0.28 s. The worker warms its vision path
before readiness. First-run compilation and load variation are distinct from normal
caption latency.

Sample 9B caption: "You sit at a desk, wearing glasses and a sleeveless top, using a
laptop while holding a pen." The pen and sleeveless top are visible; glasses are
not clearly visible in the test image. That extra detail demonstrates the model's
remaining visual uncertainty even with an instruction to omit uncertain details.

A real production narrator child also completed image captioning and a **147-word
text-mode recap** from synthetic day evidence, then shut down with exit code 0.
Synthetic evidence was used for this check; it is not a story of the user's day.
The real MediaPipe gesture task loaded with the CPU delegate in VIDEO mode and
recognized two hands in the same test photo. No camera or mic was opened.

| Check | Result |
|---|---|
| `uv run pytest -q` | 132 passed |
| `uv run python -c "import facet.app"` | Passed |
| Headless health on 127.0.0.1:8897 | HTTP 200, `{ok:true, judge:"loading", version:"0.1.0"}` |
| Headless `/api/marks` | HTTP 200, `[]` |
| Headless `/api/captions` | HTTP 200, `[]` |
| Headless `/api/recap` | HTTP 200, today's date with `text:null` |
| Headless resources | Temporary FACET_DATA; no hardware or model workers; graceful shutdown; spare port released |

Tests cover stale face-centre rejection, the 0.5-second freshness boundary,
3-second posture holds, EMA scores, multi-person selection, synthetic waves,
gesture holds/confidence/cooldowns/actions, face-touch episodes, wellness timers,
focus expiry and suppression, restart recovery, marks/day boundaries, timeline and
summary additions, recap caching/regeneration/failure, narrator busy-cycle skips,
separate child IPC/shutdown, and headless startup guards. Synthetic camera cadences
of 29, 30, 31 and 60 fps all deliver about 15 shared small frames per second.

Camera-rate performance, real gesture ergonomics and the current Facet.app UI were
not tested because the existing backend owns the camera. Backend tests and static
photo inference do not establish those behaviors.

Reproduce a model comparison using a test image you own:

```sh
uv run python -m facet.benchmark_narrator IMAGE --model mlx-community/Qwen3.5-9B-MLX-4bit
uv run python -m facet.benchmark_narrator IMAGE --model mlx-community/Qwen3.5-4B-MLX-4bit
uv run python -m facet.benchmark_narrator IMAGE --model mlx-community/Qwen3.5-9B-MLX-4bit --worker-smoke
```

Benchmark logs and the test photograph are reference artifacts under
`~/Assets/facet/docs/` and `~/Assets/facet/images/`. Runtime code depends on neither.
