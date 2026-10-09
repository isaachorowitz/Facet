# Facet

Facet is a private mirror for your workday. It watches your face, posture and hands
through the webcam, listens to your voice, and shows you in real time how you look
and sound: expression, stress, fatigue, focus, energy, mood, posture, what you are
doing, and how all of it changes over the day.

Everything runs on your Mac. Video frames and audio are never written to disk and
never leave the machine. Only numbers, gesture marks, captions, recaps and (if you
keep them) transcripts go into a local SQLite file.

It is built on [Clef-flash](https://huggingface.co/Cloudflare/clef-flash),
Cloudflare's open decision model, running locally on Apple Silicon through MLX.

## What you get

- **Live read of your face.** Clef-flash judges a crop of your head and shoulders
  about once a second: one of 14 expressions, stress, fatigue, focus, energy, mood
  and tension, plus posture, activity and flags like jaw clenched, heavy eyes or
  distracted.
- **Measured face.** MediaPipe tracks 52 facial muscle activations at camera rate:
  smile (and whether it reaches the eyes), brow furrow, squint, lip press, blinks
  per minute, yawns, head angle, gaze and distance from the screen, each compared
  with your own usual face.
- **Posture.** Head height above the shoulders, shoulder tilt, sinking and leaning
  in, scored 0 to 100 against your own upright posture, with a nudge when you have
  slouched for ten minutes.
- **Hands and gestures.** Thumbs up marks a good moment, thumbs down a rough one,
  a victory sign marks a win, a pointed finger held up starts a 25 minute focus
  session, and a wave says hello. Face touches are counted.
- **Voice.** Speech is transcribed locally and measured for pace, pitch, loudness
  and pauses; Clef turns that into a tone (calm, rushed, tense, flat and so on).
- **Narrator.** A local vision model describes what you are doing every 12
  seconds, and can write a short story of your day.
- **Wellness nudges.** 20-20-20 eye breaks, low blink rate, hydration, standing up,
  sustained stress and fatigue, as native macOS notifications.
- **Day view.** Timeline, expression mix, stress peaks, focus streaks, breaks and an
  hour by hour table, for today or any past day.

## Privacy

- Camera frames and audio stay in memory and are discarded after analysis.
- History lives in `~/Library/Application Support/Facet/facet.db`. Delete the file
  to start over. Turn off "keep transcripts" to store voice measurements without
  the words.
- The server listens on `127.0.0.1` only.
- Network use is limited to downloading models on first run (Hugging Face and
  Google's MediaPipe model storage), Python packages when the environment is
  created, and the dashboard's fonts from Google Fonts. No analytics, no telemetry,
  no accounts.

Facet reads expressions and posture, not feelings or health. Treat it as a mirror,
not a diagnosis.

## Requirements

- A Mac with Apple Silicon and macOS 15 or later.
- Memory: Clef-flash alone takes about 20 GB, the narrator about 6 GB more. Facet
  was developed on an M5 Max with 128 GB; plan on 48 GB or more, or use the smaller
  narrator described under Configuration.
- About 30 GB of free disk for models.
- A webcam and, for voice features, a microphone.
- [uv](https://docs.astral.sh/uv/) for Python. To build the dashboard, Node.js 20 or
  later and [pnpm](https://pnpm.io). To build the Mac app, Xcode 16 or later
  (Swift 6).

## Quick start

```sh
git clone https://github.com/isaachorowitz/Facet.git
cd Facet

# Build the dashboard (optional; a simpler built-in page is used without it)
(cd web && pnpm install && pnpm build)

# Start Facet and open http://127.0.0.1:8765
uv run facet
```

The first start downloads Clef-flash (about 19 GB), the narrator, the speech models
and the MediaPipe trackers, so it takes a while. Later starts reuse the cache.

macOS asks for camera and microphone access for the app you start Facet from (your
terminal, when run this way). Pause in the dashboard releases both.

Press **Calibrate** once, sitting upright and relaxed for 30 seconds. Facet then
compares your face and posture with that baseline; until you do, it learns your
usual face from your history over the first days.

## The Mac app

`macos/` holds a native SwiftUI app that runs the backend for you, shows the
dashboard in its own window, sits in the menu bar with your current mood, posture
and stress, posts native notifications, and can launch at login. Camera and
microphone permissions belong to Facet.app itself.

```sh
(cd web && pnpm install && pnpm build)
macos/scripts/build-app.sh
open macos/build/Facet.app
```

The build script bundles the backend source, the built dashboard and `uv` into the
app. On first launch the app creates its Python environment in
`~/Library/Application Support/Facet/venv` and logs to
`~/Library/Logs/Facet/backend.log`.

Signing: the script uses the first "Developer ID Application" identity in your
keychain, then "Apple Development", then ad hoc. Set `FACET_SIGN_IDENTITY` to choose
one (`-` for ad hoc) and `FACET_BUNDLE_ID` to use your own bundle identifier. macOS
ties camera permission to the signature, so an ad hoc build may ask again after
each rebuild. If the app finds a Facet backend already running on port 8765 it
attaches to it instead of starting a second one.

## How it works

Facet keeps its channels separate so they can check each other.

1. **Measured face** (`facet/face.py`). MediaPipe Face Landmarker on the CPU at
   camera rate. If other people are in frame, it stays on the largest face.
2. **Clef-flash judge** (`facet/judge.py`, `facet/clef_mlx.py`). Runs in its own
   process. The Qwen3.5 backbone runs on MLX with mlx-vlm's Metal kernels; the
   small schema head stays in PyTorch exactly as Cloudflare released it.
3. **Posture** (`facet/posture.py`). MediaPipe Pose on its own thread at 10 Hz.
   Brief dropouts hold the last reading for up to 3 seconds instead of blanking.
4. **Hands** (`facet/hands.py`). MediaPipe Gesture Recognizer on its own thread at
   about 15 Hz, up to two hands. Waves are detected from wrist motion.
5. **Voice** (`facet/voice.py`). Speech segments are transcribed with Parakeet on
   MLX and scored by a HuBERT speech emotion model, then judged by Clef.
6. **Narrator** (`facet/narrator.py`). Qwen3.5-9B (4-bit, MLX) in a separate process
   captions the frame every 12 seconds and writes the story of the day on request.

Every 15 seconds an overall read combines recent face judgments, your measured face
against your baseline, posture, recent voice, captions and time since your last
break. Nudges come from that read and from the wellness timers, at most one of each
kind per 30 minutes, and are held back during focus sessions (posture excepted).

The backend is a FastAPI app on `127.0.0.1:8765`. The dashboard (`web/`, Vite, React,
TypeScript and Motion) and the Mac app are both clients of its REST and WebSocket
API, documented in [docs/contract.md](docs/contract.md).

### Performance

Measured on an M5 Max (128 GB), Clef-flash bf16, a 384 px crop:

| | Released PyTorch path (MPS) | Facet (MLX backbone) |
|---|---|---|
| Face judgment, all 18 questions | 5.8 s | 1.9 s |
| Face judgment, core 7 questions | | 0.8 s |
| Voice judgment | 2.1 s | 0.6 s |
| Overall read | 2.6 s | 0.7 s |
| Narrator caption (Qwen3.5-9B 4-bit) | | about 1.5 s |

Answers match the released PyTorch path to within 0.008 probability with no top
choice changed; `uv run python scripts/compare_backends.py <image>` checks this on
your machine. `FACET_BACKEND=torch` switches back to the released code path.

## Gestures

| Gesture | Action |
|---|---|
| Thumb up | Mark a good moment |
| Thumb down | Mark a rough moment |
| Victory | Mark a win |
| Pointing up, held 1.5 seconds | Start or end a 25 minute focus session |
| Wave | Say hello |
| Closed fist, open palm, I love you | Shown, no action |

A gesture fires after a steady 0.6 second hold at confidence 0.6 or higher, at most
once every 3 seconds. Marks appear on the day timeline.

## Wellness reminders

- **Eyes:** after 20 minutes looking at the screen, look 20 feet away for 20
  seconds. Looking away that long counts the break as taken.
- **Blink:** blink rate under 8 per minute for 5 minutes.
- **Hydrate:** 90 minutes at the desk without a sip. Sips are estimated from Clef's
  eating or drinking activity, so this is an approximation.
- **Stand:** 50 minutes at the desk without a break of 3 minutes or more.
- **Posture, stress, fatigue:** sustained for about ten minutes.

## Configuration

Environment variables, all optional:

| Variable | Default | Meaning |
|---|---|---|
| `FACET_CAMERA` | `0` | Camera index |
| `FACET_MIC` | system default | Comma separated name fragments; the first matching input device is used |
| `FACET_HOST`, `FACET_PORT` | `127.0.0.1`, `8765` | Where the server listens (also `--host`, `--port`) |
| `FACET_DATA` | `~/Library/Application Support/Facet` | History database location |
| `FACET_JUDGE_INTERVAL` | `1.2` | Seconds between face judgments |
| `FACET_BACKEND` | `mlx` | `mlx`, or `torch` for the released PyTorch code path |
| `FACET_NARRATOR` | `mlx-community/Qwen3.5-9B-MLX-4bit` | Any mlx-vlm model; `mlx-community/Qwen3.5-4B-MLX-4bit` uses less memory |
| `FACET_CROP` | `384` | Size of the face crop sent to Clef |
| `FACET_HEADLESS` | unset | `1` starts the API without camera, mic or models |

## Development

```sh
uv run pytest -q                      # backend tests, no camera, mic or models needed
(cd web && pnpm typecheck && pnpm test)
(cd macos && swift test)

# API only, no hardware or models, on a spare port
FACET_HEADLESS=1 FACET_DATA="$(mktemp -d)" uv run facet --no-browser --port 8799

# Dashboard with hot reload against a running backend on 8765
(cd web && pnpm dev)
```

`uv run python -m facet.benchmark_narrator IMAGE --model <repo>` times a narrator
model on an image of your choice.

## Limits

- Cameras see expressions, not feelings. Trends and changes from your own baseline
  are more trustworthy than any single reading.
- The microphone cannot tell your voice from someone else's in the room.
- Clef-flash and the narrator were not trained on faces specifically. The narrator
  can misread a scene or add details that are not there.
- Hydration and face touches are estimates from vision, not measurements.

## License

Facet is MIT licensed; see [LICENSE](LICENSE). The models it downloads keep their
own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
