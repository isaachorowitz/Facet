# Facet backend contract

The Python backend (`facet/`) is the single source of truth. The React dashboard
(`web/`) and the macOS app (`macos/`) are clients of it. Everything is served on
`http://127.0.0.1:8765` (override with `FACET_PORT`). Nothing listens on any other
interface.

Timestamps are Unix seconds (float). Scores named `stress`, `fatigue`, `focus`,
`energy`, `positivity`, `tension` are expected values on a 0..4 scale. `noul`
answers are a probability (0..1) that the statement is true.

## Shared shapes

```ts
type Choice = { choice: string; confidence: number; probabilities: Record<string, number> };

// One Clef judgment of the face crop. Core keys refresh every ~1.2 s, the rest every third cycle.
type FaceVerdict = {
  ts: number;
  expression: Choice;            // happy content neutral focused serious tired bored sad frustrated angry anxious confused surprised amused
  stress: number; fatigue: number; focus: number; energy: number; positivity: number; tension: number;
  smiling: number; frowning: number; jaw_clenched: number; eyes_heavy: number; eyes_on_screen: number;
  hand_on_face: number; talking: number; yawning: number; distracted: number;
  posture: Choice;               // upright leaning_forward slumped reclined head_on_hand
  activity: Choice;              // working reading talking listening on_phone eating_or_drinking thinking idle
};

type OverallVerdict = {
  ts: number;
  mood: Choice;                  // same options as expression
  stress: number; fatigue: number; focus: number; positivity: number;
  needs_break: number; in_flow: number; overwhelmed: number;
};

type VoiceVerdict = {
  ts: number;
  tone: Choice;                  // calm cheerful energetic rushed tense irritated flat sad uncertain
  stress: number; energy: number; positivity: number;
  confident: number; tired: number; frustrated: number;
};

type Speech = {
  ts: number;
  text: string;                  // "" when transcripts are not kept
  prosody: { duration_s: number; words_per_minute: number; pitch_hz: number;
             pitch_variation_semitones: number; loudness_db: number; pause_ratio: number };
  emotion: Record<string, number>;   // voice model: neutral happy angry sad
  verdict: VoiceVerdict | null;
};

type Posture = {
  visible: boolean;
  score: number;                 // 0..100, meaningful only when state != "unknown"
  state: "good" | "fair" | "poor" | "unknown";
  issues: string[];              // e.g. "Head dropping forward", "Left shoulder low"
  neck: number; shoulder_tilt: number; lean: number; sink: number;
  reference: "calibrated" | "learned" | "learning";
  ref_neck: number;              // 0 when no reference yet
  // Keypoints in aspect-corrected image coords: [x (0..16/9), y (0..1), visibility]. NOT mirrored.
  skeleton: Partial<Record<"nose"|"l_eye"|"r_eye"|"l_ear"|"r_ear"|"l_sh"|"r_sh"|"l_el"|"r_el"|"l_wr"|"r_wr"|"l_hip"|"r_hip", [number, number, number]>>;
};

type Status = {
  paused: boolean;
  camera: "on" | "off" | "paused";
  camera_error: string | null;
  judge: "loading" | "warming up" | "ready" | "failed";
  judge_error: string | null;
  latency_ms: Partial<Record<"face" | "face_detail" | "voice" | "overall", number>>;
  voice: string;                 // "listening", "paused", "loading", "listening (loading transcriber)", "transcriber failed"
  voice_error: string | null;
  mic: string;                   // input device name
  calibrating_seconds_left: number;
  baseline_samples: number;      // >= 60 means a personal baseline exists
  baseline: Record<string, { mean: number; std: number }>;
  settings: { notifications: boolean; mic: boolean; store_transcripts: boolean };
};

type Live = {
  type: "live";
  face: {
    present: boolean;
    metrics: Record<string, number>;   // smile genuine_smile smile_asymmetry brow_furrow brow_raise eye_squint eye_openness
                                       // eye_wide lip_press jaw_forward jaw_open frown sneer gaze_down gaze_side tension
                                       // yaw pitch roll (degrees) face_size movement
    vs_usual: Record<string, number>;  // z-scores against the personal baseline
    blink_rate: number; looking_at_screen: boolean; yawning: boolean; fps: number;
  };
  voice: { level_db: number; speaking: boolean };
  status: Status;
  minutes_since_break: number;
  posture: Posture;
};
```

## WebSocket `GET /ws`

Server pushes JSON messages. On connect: one `hello`, then a `live` every 200 ms,
plus events as they happen.

```ts
type Message =
  | { type: "hello"; latest: { face?: FaceVerdict; overall?: OverallVerdict; voice?: VoiceVerdict }; status: Status }
  | Live
  | { type: "verdict"; kind: "face"; data: FaceVerdict; latency_ms?: number }
  | { type: "verdict"; kind: "overall"; data: OverallVerdict; latency_ms?: number }
  | { type: "speech"; data: Speech; latency_ms?: number }
  | { type: "notification"; data: { kind: "stress" | "break" | "fatigue" | "posture"; text: string } }
  | { type: "calibrated"; data: Status };
```

Query parameter `?client=app` marks the macOS app's connection: while one is
connected the backend does not show its own `osascript` notification, so the app
shows a native one instead.

## REST

| Method | Path | Returns |
|---|---|---|
| GET | `/api/health` | `{ ok: true, judge: Status["judge"], version: string }` |
| GET | `/api/state` | `Live & { latest: {face?, overall?, voice?} }` |
| GET | `/api/timeline?date=YYYY-MM-DD&bucket=5` | `{ start: number; bucket_minutes: number; points: TimelinePoint[] }` |
| GET | `/api/summary?date=YYYY-MM-DD` | `Summary` |
| GET | `/api/speech?minutes=60` | `Speech[]` (oldest first) |
| POST | `/api/calibrate?seconds=30` | `Status` |
| POST | `/api/pause` | `Status` (releases camera and mic) |
| POST | `/api/resume` | `Status` |
| POST | `/api/settings` body `Partial<Status["settings"]>` | `Status` |
| GET | `/video.mjpg` | MJPEG stream, 720x600 mirror crop that follows the face, ~12 fps |

```ts
type TimelinePoint = {
  t: number;                     // bucket start
  stress?: number; fatigue?: number; focus?: number; energy?: number; positivity?: number; tension?: number;
  expression?: string;           // dominant in the bucket
  present?: number;              // 0..1 share of the bucket at the desk
  measured_tension?: number; smile?: number; blink_rate?: number;
  posture?: number;              // posture score / 25, so it shares the 0..4 axis
  speech_s?: number;             // seconds talking
};

type Summary = {
  date: string;
  minutes_present: number; first_seen: number | null; last_seen: number | null;
  verdicts: number; minutes_talking: number;
  notifications: { ts: number; kind: string; text: string }[];
  avg_posture?: number; minutes_poor_posture?: number; minutes_good_posture?: number;
  expressions?: Record<string, number>;          // share of the day, sorted desc
  avg_stress?: number; avg_fatigue?: number; avg_focus?: number; avg_energy?: number; avg_positivity?: number; avg_tension?: number;
  smiling_share?: number;
  posture?: Record<string, number>; activity?: Record<string, number>;
  stress_peaks?: { ts: number; stress: number }[];
  focus_streaks?: { start: number; minutes: number }[];
  breaks?: { start: number; minutes: number }[];
  by_hour?: { hour: number; stress: number; focus: number; fatigue: number; positivity: number; top_expression: string }[];
  voice_tones?: Record<string, number>;
};
```

## Static files

The backend serves the built dashboard from `web/dist` at `/` when it exists
(`index.html` plus `/assets/*`), and falls back to `facet/static/index.html`.

## v2 additions (hands, gestures, narration, wellness)

Everything above stays valid. These fields and messages are added.

```ts
// Live gains:
type Live = Live & {
  view: { x: number; y: number; w: number; h: number };   // the mirror crop as a fraction of the camera frame,
                                                           // so overlays can map frame coords onto /video.mjpg
  hands: Hand[];                                           // 0..2, updated ~15 Hz
  focus_session: null | { started: number; ends: number; minutes: number };
  wellness: {
    eyes_on_screen_minutes: number;    // continuous, resets after >= 20 s looking away
    low_blink: boolean;                // blink rate under 8/min for 5 min
    minutes_since_sip: number | null;  // null until the first sip today
    face_touches_last_hour: number;
  };
  caption: { ts: number; text: string } | null;           // latest narrator caption
};

type Hand = {
  handedness: "Left" | "Right";        // as the person sees it (mirrored)
  gesture: "None" | "Closed_Fist" | "Open_Palm" | "Pointing_Up" | "Thumb_Down" | "Thumb_Up" | "Victory" | "ILoveYou" | "Wave";
  score: number;
  landmarks: [number, number][];       // 21 points, fractions of the camera frame (x right, y down), NOT mirrored
  near_face: boolean;
};

// Posture gains:
type Posture = Posture & {
  stale: boolean;                      // true while holding the last good reading through a brief dropout (<= 3 s)
};

// New WebSocket messages:
type MessageV2 =
  | { type: "gesture"; data: { ts: number; gesture: Hand["gesture"]; hand: Hand["handedness"]; action: GestureAction | null } }
  | { type: "mark"; data: Mark }                      // a moment the person marked with a gesture
  | { type: "caption"; data: { ts: number; text: string } }
  | { type: "focus"; data: { state: "started" | "ended"; session: { started: number; ends: number; minutes: number } } }
  | { type: "face_touch"; data: { ts: number; count_last_hour: number } };

type GestureAction = "mark_good" | "mark_rough" | "mark_win" | "toggle_focus" | "hello";
type Mark = { ts: number; kind: "good" | "rough" | "win"; note: string | null };
```

Gesture meanings (held >= 0.6 s at score >= 0.6, each gesture at most once per 3 s):
Thumb_Up -> mark_good, Thumb_Down -> mark_rough, Victory -> mark_win,
Pointing_Up held 1.5 s -> toggle_focus (25 minute focus session, nudges held back during it),
Wave (open palm swept side to side) -> hello. Other gestures are shown but do nothing.

Notifications gain kinds `eyes` (20-20-20), `blink`, `hydrate`, `stand`.

REST additions:

| Method | Path | Returns |
|---|---|---|
| GET | `/api/marks?date=` | `Mark[]` |
| GET | `/api/captions?minutes=60` | `{ ts, text }[]` (oldest first) |
| POST | `/api/focus` body `{ minutes?: number }` | starts or ends a focus session, returns `Live["focus_session"]` |
| GET | `/api/recap?date=` | `{ date, text, generated_at } \| { date, text: null }` (cached story of the day) |
| POST | `/api/recap?date=` | generates (or regenerates) the story with the local narrator model, returns the same shape |

Summary gains: `marks: Mark[]`, `sips: number`, `face_touches: number`,
`eyes_breaks_taken: number`, `eyes_breaks_due: number`, `focus_sessions: { started: number; minutes: number }[]`.
TimelinePoint gains `marks?: Mark["kind"][]`.
