# Facet

A local mirror that watches your face and listens to your voice through the day and
tells you how you look and sound: expression, stress, fatigue, focus, energy, mood,
posture, what you are doing, and how all of it changes over the day. Nothing leaves
the Mac. Video frames and audio are never written to disk; only numbers (and
transcripts, if you keep them) go into a local SQLite file.

## Run

```sh
cd ~/Projects/facet
uv run facet            # opens http://127.0.0.1:8765
uv run facet --no-browser
```

The first start downloads the models it needs (Clef-flash is about 19 GB) into the
Hugging Face cache, and the two MediaPipe trackers into `models/`. After that the
dashboard is reading your face within about 25 seconds.

The terminal you start it from needs camera and microphone permission (System
Settings → Privacy & Security). Pause in the dashboard releases the camera and mic.

## How it works

Four channels, kept separate so they can check each other:

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
   0 to 100 against your calibrated (or best recent) upright posture.
4. **Voice** (`facet/voice.py`). The mic (Razer Seiren first, then the Brio) is cut
   into speech segments, transcribed with Parakeet (MLX), and measured for pace,
   pitch, pitch variation, loudness, and pauses. A HuBERT speech emotion model adds
   neutral/happy/angry/sad scores. Clef turns all of that into a tone (calm, rushed,
   tense, flat...) plus stress and energy.

Every 15 s an **overall read** combines the last 90 s of face judgments, your
measured face compared with your usual face, recent voice, and time since your last
break. It decides mood, stress, fatigue, focus, needs a break, in flow, and
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
`FACET_BACKEND` (`mlx` or `torch`), `FACET_CROP`, `FACET_PORT`, `FACET_DATA`.
