import type { FaceVerdict, TimelinePoint } from '../api/types';
export const COLORS = { stress: '#f3b562', tension: '#ef8f72', fatigue: '#b9a6ff', focus: '#8fb8ff', positivity: '#7fd6a4', posture: '#c9b48f' };
export const EXPRESSIONS: Record<string, string> = { happy: '#7fd6a4', content: '#9fdcbc', neutral: '#6f6c66', focused: '#8fb8ff', serious: '#c9b48f', tired: '#b9a6ff', bored: '#8f8a9e', sad: '#7f9fd6', frustrated: '#ef8f72', angry: '#ff8a80', anxious: '#f3b562', confused: '#d6c27f', surprised: '#e3a6d8', amused: '#b8e07f' };
export const POSTURE_COLORS = { good: '#7fd6a4', fair: '#f3b562', poor: '#ef8f72', unknown: '#8a877f' };
export const WORDS = ['none', 'slight', 'moderate', 'high', 'extreme'];
export const MOOD_WORDS = ['very low', 'low', 'neutral', 'good', 'great'];
export const RINGS = [['stress', 'Stress'], ['tension', 'Tension'], ['fatigue', 'Fatigue'], ['focus', 'Focus'], ['positivity', 'Mood']] as const;
export const MEASURED = [['brow_furrow', 'Brow furrow'], ['eye_squint', 'Eye squint'], ['lip_press', 'Lip press'], ['jaw_forward', 'Jaw forward'], ['tension', 'Facial tension'], ['eye_openness', 'Eye openness'], ['smile', 'Smile'], ['genuine_smile', 'Genuine smile'], ['movement', 'Head movement'], ['frown', 'Mouth frown']] as const;
export const FLAGS = [['frowning', 'Frowning', true], ['jaw_clenched', 'Jaw clenched', true], ['eyes_on_screen', 'Eyes on screen', false], ['eyes_heavy', 'Heavy eyes', true], ['distracted', 'Distracted', true], ['smiling', 'Smiling', false], ['hand_on_face', 'Hand on face', true], ['talking', 'Talking', false], ['yawning', 'Yawning', true]] as const;
export const EASE = [0.2, 0.8, 0.2, 1] as const;
export const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));
export const pct = (v: number) => `${Math.round(v * 100)}%`;
export const hhmm = (ts: number) => new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
export const capitalise = (word: string) => word.charAt(0).toUpperCase() + word.slice(1);
export const todayString = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
export function sentence(f: FaceVerdict, z: Record<string, number> = {}) {
  const parts: string[] = [], sentences: string[] = [];
  if (f.frowning > .5 || (z.brow_furrow ?? 0) > 1.2) parts.push('brow furrowed');
  if (f.jaw_clenched > .5 || (z.lip_press ?? 0) > 1.2) parts.push('lips pressed');
  if (f.eyes_heavy > .5) parts.push('eyes heavy');
  if (f.smiling > .5) parts.push(f.smiling > .8 ? 'smiling broadly' : 'smiling');
  if (parts.length) sentences.push(capitalise(parts.join(', ')) + '.');
  const doing = f.activity.choice.replaceAll('_', ' ');
  if (doing) sentences.push(`Looks like you're ${doing === 'idle' ? 'taking a pause' : doing}.`);
  sentences.push(f.stress < 1.5 ? 'Stress is low.' : f.stress < 2.5 ? 'Some stress showing.' : 'Stress is high.');
  if (f.fatigue >= 2) sentences.push('Looking tired.');
  return sentences.join(' ');
}
export function auraFor(f: FaceVerdict) {
  const warm = clamp((f.stress + f.tension) / 5, 0, 1), cool = clamp(f.focus / 4, 0, 1), calm = clamp(f.positivity / 4, 0, 1);
  return `radial-gradient(closest-side, rgba(243,181,98,${(.04 + warm * .17).toFixed(3)}), rgba(143,184,255,${(.03 + cool * .10).toFixed(3)}) 52%, rgba(127,214,164,${(calm * .04).toFixed(3)}) 68%, transparent 76%)`;
}
export type PlotKey = 'posture' | 'focus' | 'fatigue' | 'positivity' | 'stress';
export function linePath(points: TimelinePoint[], key: PlotKey, x: (t: number) => number) {
  let d = '', last: number | null = null;
  for (const p of points) {
    const value = p[key];
    if (value == null) { last = null; continue; }
    d += (last === null || p.t - last > 1200 ? 'M' : 'L') + x(p.t).toFixed(1) + ',' + (120 - clamp(value, 0, 4) / 4 * 114 - 3).toFixed(1);
    last = p.t;
  }
  return d;
}
