import type { Message, State, Status, Speech, Summary, Timeline, Mark, Caption, FocusSession, Recap } from './types';

// Validate network JSON before its one boundary cast. Extra backend keys are allowed.
type Check = (value: unknown) => boolean;
const number: Check = v => typeof v === 'number' && Number.isFinite(v);
const string: Check = v => typeof v === 'string';
const boolean: Check = v => typeof v === 'boolean';
const literal = (...values: unknown[]): Check => v => values.includes(v);
const nullable = (check: Check): Check => v => v === null || check(v);
const array = (check: Check): Check => v => Array.isArray(v) && v.every(check);
const record = (check: Check): Check => v => isObject(v) && Object.values(v).every(check);
const object = (required: Record<string, Check>, optional: Record<string, Check> = {}): Check => v =>
  isObject(v) && Object.entries(required).every(([k, c]) => c(v[k])) &&
  Object.entries(optional).every(([k, c]) => v[k] === undefined || c(v[k]));
function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}
const numbers = (...keys: string[]) => Object.fromEntries(keys.map(k => [k, number]));
const choice = object({ choice: string, confidence: number, probabilities: record(number) });
const face = object({
  ts: number, expression: choice, posture: choice, activity: choice,
  ...numbers('stress', 'fatigue', 'focus', 'energy', 'positivity', 'tension', 'smiling', 'frowning',
    'jaw_clenched', 'eyes_heavy', 'eyes_on_screen', 'hand_on_face', 'talking', 'yawning', 'distracted'),
});
const overall = object({ ts: number, mood: choice,
  ...numbers('stress', 'fatigue', 'focus', 'positivity', 'needs_break', 'in_flow', 'overwhelmed') });
const voice = object({ ts: number, tone: choice,
  ...numbers('stress', 'energy', 'positivity', 'confident', 'tired', 'frustrated') });
const latest = object({}, { face, overall, voice });
export const statusCheck = object({
  paused: boolean, camera: literal('on', 'off', 'paused'), camera_error: nullable(string),
  judge: literal('loading', 'warming up', 'ready', 'failed'), judge_error: nullable(string),
  latency_ms: object({}, numbers('face', 'face_detail', 'voice', 'overall')),
  voice: string, voice_error: nullable(string), mic: string,
  calibrating_seconds_left: number, baseline_samples: number,
  baseline: record(object({ mean: number, std: number })),
  settings: object({ notifications: boolean, mic: boolean, store_transcripts: boolean }),
});
const point: Check = v => Array.isArray(v) && v.length === 3 && v.every(number);
const skeleton = object({}, Object.fromEntries(
  ['nose', 'l_eye', 'r_eye', 'l_ear', 'r_ear', 'l_sh', 'r_sh', 'l_el', 'r_el', 'l_wr', 'r_wr', 'l_hip', 'r_hip'].map(k => [k, point])));
const posture = object({ visible: boolean, score: number, state: literal('good', 'fair', 'poor', 'unknown'),
  issues: array(string), reference: literal('calibrated', 'learned', 'learning'), skeleton,
  ...numbers('neck', 'shoulder_tilt', 'lean', 'sink', 'ref_neck') }, { stale: boolean });
const liveShape = {
  type: literal('live'), status: statusCheck, posture, minutes_since_break: number,
  face: object({ present: boolean, metrics: record(number), vs_usual: record(number), blink_rate: number,
    looking_at_screen: boolean, yawning: boolean, fps: number }),
  voice: object({ level_db: number, speaking: boolean }),
};
const gesture = literal('None', 'Closed_Fist', 'Open_Palm', 'Pointing_Up', 'Thumb_Down', 'Thumb_Up', 'Victory', 'ILoveYou', 'Wave');
const markKind = literal('good', 'rough', 'win');
const mark = object({ ts: number, kind: markKind, note: nullable(string) });
const caption = object({ ts: number, text: string });
const focusSession = object(numbers('started', 'ends', 'minutes'));
const handPoint: Check = v => Array.isArray(v) && v.length === 2 && v.every(number);
const hand = object({ handedness: literal('Left', 'Right'), gesture, score: number,
  landmarks: v => Array.isArray(v) && v.length === 21 && v.every(handPoint), near_face: boolean });
const positive: Check = v => number(v) && typeof v === 'number' && v > 0;
const liveOptional = {
  view: object({ x: number, y: number, w: positive, h: positive }), hands: array(hand),
  focus_session: nullable(focusSession), caption: nullable(caption),
  wellness: object({ eyes_on_screen_minutes: number, low_blink: boolean,
    minutes_since_sip: nullable(number), face_touches_last_hour: number }),
};
export const speechCheck = object({ ts: number, text: string, emotion: record(number), verdict: nullable(voice),
  prosody: object(numbers('duration_s', 'words_per_minute', 'pitch_hz', 'pitch_variation_semitones', 'loudness_db', 'pause_ratio')) });
export const timelineCheck = object({ start: number, bucket_minutes: number, points: array(object({ t: number }, {
  expression: string, marks: array(markKind), ...numbers('stress', 'fatigue', 'focus', 'energy', 'positivity', 'tension', 'present',
    'measured_tension', 'smile', 'blink_rate', 'posture', 'speech_s'),
})) });
export const summaryCheck = object({ date: string, minutes_present: number, first_seen: nullable(number),
  last_seen: nullable(number), verdicts: number, minutes_talking: number,
  notifications: array(object({ ts: number, kind: string, text: string })),
}, {
  ...numbers('avg_posture', 'minutes_poor_posture', 'minutes_good_posture', 'avg_stress', 'avg_fatigue',
    'avg_focus', 'avg_energy', 'avg_positivity', 'avg_tension', 'smiling_share',
    'sips', 'face_touches', 'eyes_breaks_taken', 'eyes_breaks_due'),
  marks: array(mark), focus_sessions: array(object(numbers('started', 'minutes'))),
  expressions: record(number), posture: record(number), activity: record(number), voice_tones: record(number),
  stress_peaks: array(object(numbers('ts', 'stress'))), focus_streaks: array(object(numbers('start', 'minutes'))),
  breaks: array(object(numbers('start', 'minutes'))),
  by_hour: array(object({ top_expression: string, ...numbers('hour', 'stress', 'focus', 'fatigue', 'positivity') })),
});
const messageChecks: Check[] = [
  object(liveShape, liveOptional), object({ type: literal('hello'), latest, status: statusCheck }),
  object({ type: literal('verdict'), kind: literal('face'), data: face }, { latency_ms: number }),
  object({ type: literal('verdict'), kind: literal('overall'), data: overall }, { latency_ms: number }),
  object({ type: literal('speech'), data: speechCheck }, { latency_ms: number }),
  object({ type: literal('notification'), data: object({ kind: literal('stress', 'break', 'fatigue', 'posture', 'eyes', 'blink', 'hydrate', 'stand'), text: string }) }),
  object({ type: literal('calibrated'), data: statusCheck }),
  object({ type: literal('gesture'), data: object({ ts: number, gesture, hand: literal('Left', 'Right'),
    action: nullable(literal('mark_good', 'mark_rough', 'mark_win', 'toggle_focus', 'hello')) }) }),
  object({ type: literal('mark'), data: mark }),
  object({ type: literal('caption'), data: caption }),
  object({ type: literal('focus'), data: object({ state: literal('started', 'ended'), session: focusSession }) }),
  object({ type: literal('face_touch'), data: object(numbers('ts', 'count_last_hour')) }),
];
function decode<T>(value: unknown, check: Check): T {
  if (!check(value)) throw new Error('Facet returned a payload outside docs/contract.md');
  return value as T;
}
export const parseMessage = (value: unknown) => decode<Message>(value, v => messageChecks.some(c => c(v)));
export const parseState = (value: unknown) => decode<State>(value, object({ ...liveShape, latest }, liveOptional));
export const parseStatus = (value: unknown) => decode<Status>(value, statusCheck);
export const parseSpeech = (value: unknown) => decode<Speech[]>(value, array(speechCheck));
export const parseTimeline = (value: unknown) => decode<Timeline>(value, timelineCheck);
export const parseSummary = (value: unknown) => decode<Summary>(value, summaryCheck);

export const parseMarks = (value: unknown) => decode<Mark[]>(value, array(mark));
export const parseCaptions = (value: unknown) => decode<Caption[]>(value, array(caption));
export const parseFocusSession = (value: unknown) => decode<FocusSession | null>(value, nullable(focusSession));
export const parseRecap = (value: unknown) => decode<Recap>(value,
  object({ date: string, text: nullable(string) }, { generated_at: number }));
