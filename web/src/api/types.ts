// Shapes from docs/contract.md. Timestamps are Unix seconds; scores are 0..4.
export type Choice = { choice: string; confidence: number; probabilities: Record<string, number> };

// One Clef judgment of the face crop. Core keys refresh every ~1.2 s, the rest every third cycle.
export type FaceVerdict = {
  ts: number;
  expression: Choice;            // happy content neutral focused serious tired bored sad frustrated angry anxious confused surprised amused
  stress: number; fatigue: number; focus: number; energy: number; positivity: number; tension: number;
  smiling: number; frowning: number; jaw_clenched: number; eyes_heavy: number; eyes_on_screen: number;
  hand_on_face: number; talking: number; yawning: number; distracted: number;
  posture: Choice;               // upright leaning_forward slumped reclined head_on_hand
  activity: Choice;              // working reading talking listening on_phone eating_or_drinking thinking idle
};

export type OverallVerdict = {
  ts: number;
  mood: Choice;                  // same options as expression
  stress: number; fatigue: number; focus: number; positivity: number;
  needs_break: number; in_flow: number; overwhelmed: number;
};

export type VoiceVerdict = {
  ts: number;
  tone: Choice;                  // calm cheerful energetic rushed tense irritated flat sad uncertain
  stress: number; energy: number; positivity: number;
  confident: number; tired: number; frustrated: number;
};

export type Speech = {
  ts: number;
  text: string;                  // "" when transcripts are not kept
  prosody: { duration_s: number; words_per_minute: number; pitch_hz: number;
             pitch_variation_semitones: number; loudness_db: number; pause_ratio: number };
  emotion: Record<string, number>;   // voice model: neutral happy angry sad
  verdict: VoiceVerdict | null;
};

export type Posture = {
  visible: boolean;
  stale?: boolean;               // hold the last reading through a brief dropout
  score: number;                 // 0..100, meaningful only when state != "unknown"
  state: "good" | "fair" | "poor" | "unknown";
  issues: string[];              // e.g. "Head dropping forward", "Left shoulder low"
  neck: number; shoulder_tilt: number; lean: number; sink: number;
  reference: "calibrated" | "learned" | "learning";
  ref_neck: number;              // 0 when no reference yet
  // Keypoints in aspect-corrected image coords: [x (0..16/9), y (0..1), visibility]. NOT mirrored.
  skeleton: Partial<Record<"nose"|"l_eye"|"r_eye"|"l_ear"|"r_ear"|"l_sh"|"r_sh"|"l_el"|"r_el"|"l_wr"|"r_wr"|"l_hip"|"r_hip", [number, number, number]>>;
};

export type Status = {
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

export type Live = {
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
  view?: MirrorView;
  hands?: Hand[];
  focus_session?: FocusSession | null;
  wellness?: {
    eyes_on_screen_minutes: number; low_blink: boolean; minutes_since_sip: number | null;
    face_touches_last_hour: number;
  };
  caption?: Caption | null;
};


export type Message =
  | { type: "hello"; latest: { face?: FaceVerdict; overall?: OverallVerdict; voice?: VoiceVerdict }; status: Status }
  | Live
  | { type: "verdict"; kind: "face"; data: FaceVerdict; latency_ms?: number }
  | { type: "verdict"; kind: "overall"; data: OverallVerdict; latency_ms?: number }
  | { type: "speech"; data: Speech; latency_ms?: number }
  | { type: "notification"; data: { kind: "stress" | "break" | "fatigue" | "posture" | "eyes" | "blink" | "hydrate" | "stand"; text: string } }
  | { type: "calibrated"; data: Status }
  | { type: "gesture"; data: GestureEvent }
  | { type: "mark"; data: Mark }
  | { type: "caption"; data: Caption }
  | { type: "focus"; data: { state: "started" | "ended"; session: FocusSession } }
  | { type: "face_touch"; data: { ts: number; count_last_hour: number } };


export type TimelinePoint = {
  t: number;                     // bucket start
  stress?: number; fatigue?: number; focus?: number; energy?: number; positivity?: number; tension?: number;
  expression?: string;           // dominant in the bucket
  present?: number;              // 0..1 share of the bucket at the desk
  measured_tension?: number; smile?: number; blink_rate?: number;
  posture?: number;              // posture score / 25, so it shares the 0..4 axis
  marks?: Mark["kind"][];
  speech_s?: number;             // seconds talking
};

export type Summary = {
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
  marks?: Mark[];
  sips?: number; face_touches?: number; eyes_breaks_taken?: number; eyes_breaks_due?: number;
  focus_sessions?: { started: number; minutes: number }[];
};


export type Latest = { face?: FaceVerdict; overall?: OverallVerdict; voice?: VoiceVerdict };
export type State = Live & { latest: Latest };
export type Timeline = { start: number; bucket_minutes: number; points: TimelinePoint[] };

// v2 fields stay optional on existing shapes for compatibility with v1 servers.
export type MirrorView = { x: number; y: number; w: number; h: number };
export type FocusSession = { started: number; ends: number; minutes: number };
export type Caption = { ts: number; text: string };
export type Hand = {
  handedness: "Left" | "Right";
  gesture: "None" | "Closed_Fist" | "Open_Palm" | "Pointing_Up" | "Thumb_Down" | "Thumb_Up" | "Victory" | "ILoveYou" | "Wave";
  score: number; landmarks: [number, number][]; near_face: boolean;
};
export type GestureAction = "mark_good" | "mark_rough" | "mark_win" | "toggle_focus" | "hello";
export type GestureEvent = { ts: number; gesture: Hand["gesture"]; hand: Hand["handedness"]; action: GestureAction | null };
export type Mark = { ts: number; kind: "good" | "rough" | "win"; note: string | null };
export type Recap = { date: string; text: string | null; generated_at?: number };
