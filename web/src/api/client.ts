import type { Status } from './types';
import { parseSpeech, parseState, parseStatus, parseSummary, parseTimeline, parseMarks, parseCaptions, parseFocusSession, parseRecap } from './validate';

async function request<T>(path: string, parse: (value: unknown) => T, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, signal: AbortSignal.timeout(15_000) });
  if (!response.ok) throw new Error(`Facet request failed (${response.status})`);
  const payload: unknown = await response.json();
  return parse(payload);
}
const query = (values: Record<string, string | number | undefined>) => {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(values)) if (v !== undefined) params.set(k, String(v));
  return params.toString();
};
const post = (path: string, body?: Partial<Status['settings']>) => request(path, parseStatus, {
  method: 'POST', headers: { 'content-type': 'application/json' },
  body: body === undefined ? undefined : JSON.stringify(body),
});
export const getState = () => request('/api/state', parseState);
export const getTimeline = (date?: string, bucket?: number) => request(`/api/timeline?${query({ date, bucket })}`, parseTimeline);
export const getSummary = (date?: string) => request(`/api/summary?${query({ date })}`, parseSummary);
export const getSpeech = (minutes = 60) => request(`/api/speech?${query({ minutes })}`, parseSpeech);
// Called exclusively by deliberate UI clicks. No startup or verification writes.
export const pause = () => post('/api/pause');
export const resume = () => post('/api/resume');
export const calibrate = (seconds = 30) => post(`/api/calibrate?${query({ seconds })}`);
export const updateSettings = (settings: Partial<Status['settings']>) => post('/api/settings', settings);

export const getMarks = (date?: string) => request(`/api/marks?${query({ date })}`, parseMarks);
export const getCaptions = (minutes = 60) => request(`/api/captions?${query({ minutes })}`, parseCaptions);
export const getRecap = (date: string) => request(`/api/recap?${query({ date })}`, parseRecap);
export const regenerateRecap = (date: string) => request(`/api/recap?${query({ date })}`, parseRecap, { method: 'POST' });
export const toggleFocus = (minutes = 25) => request('/api/focus', parseFocusSession, {
  method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ minutes }),
});
