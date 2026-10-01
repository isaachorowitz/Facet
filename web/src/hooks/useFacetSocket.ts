import { useCallback, useEffect, useRef, useState } from 'react';
import { getCaptions, getMarks, getSpeech, getTimeline } from '../api/client';
import type { FaceVerdict, Live, Message, OverallVerdict, Speech, Status, TimelinePoint, Caption, FocusSession, Mark } from '../api/types';
import { parseMessage } from '../api/validate';
import type { GestureEntry } from '../components/GestureOverlay';
import { mergeMarks } from '../lib/v2';
import { clamp } from '../lib/presentation';

export type FacetEvent = Extract<Message, { type: 'notification' | 'calibrated' }>;
export type EventEntry = { id: number; event: FacetEvent };
export type SpeechEntry = { speech: Speech; animate: boolean };
type Snapshot = {
  live: Live | null; status: Status | null; face: FaceVerdict | null; overall: OverallVerdict | null;
  faceZScores: Record<string, number>; speech: SpeechEntry[]; liveSeries: TimelinePoint[]; events: EventEntry[];
  caption: Caption | null; focusSession: FocusSession | null; marks: Mark[];
  gesture: GestureEntry | null; faceTouch: { id: number; ts: number; count_last_hour: number } | null;
  focusEvent: { state: 'started' | 'ended'; session: FocusSession; receivedAt: number } | null;
  videoSession: number | null; connected: boolean; error: string | null;
};
function mergeSpeech(entries: SpeechEntry[], incoming: SpeechEntry[]) {
  const byTime = new Map(entries.map(entry => [entry.speech.ts, entry]));
  for (const entry of incoming) if (!byTime.has(entry.speech.ts)) byTime.set(entry.speech.ts, entry);
  return [...byTime.values()].sort((a, b) => b.speech.ts - a.speech.ts).slice(0, 4);
}
export function useFacetSocket() {
  const [state, setState] = useState<Snapshot>({ live: null, status: null, face: null, overall: null,
    faceZScores: {}, speech: [], liveSeries: [], events: [], caption: null, focusSession: null, marks: [],
    gesture: null, faceTouch: null, focusEvent: null, videoSession: null, connected: false, error: null });
  const timing = useRef({ lastVerdictAt: 0, cadence: 2500 });
  useEffect(() => {
    let disposed = false, socket: WebSocket | null = null, retry: ReturnType<typeof setTimeout> | undefined;
    let eventId = 0;
    const connect = () => {
      if (disposed) return;
      socket = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`);
      socket.onopen = () => {
        if (!disposed) setState(s => ({ ...s, connected: true, videoSession: Date.now(), error: null }));
      };
      socket.onmessage = event => {
        if (disposed) return;
        let message: Message;
        try { const value: unknown = JSON.parse(String(event.data)); message = parseMessage(value); }
        catch { setState(s => ({ ...s, error: 'A Facet message did not match the backend contract.' })); return; }
        const incomingFace = message.type === 'hello' ? message.latest.face :
          message.type === 'verdict' && message.kind === 'face' ? message.data : undefined;
        if (incomingFace) {
          const now = performance.now(), gap = timing.current.lastVerdictAt ? now - timing.current.lastVerdictAt : 2500;
          timing.current = { lastVerdictAt: now, cadence: clamp(timing.current.cadence * .7 + gap * .3, 800, 6000) };
        }
        const id = ++eventId;
        setState(s => {
          if (message.type === 'live') return { ...s, live: message, status: message.status,
            caption: message.caption && (!s.caption || message.caption.ts > s.caption.ts) ? message.caption : s.caption,
            focusSession: message.focus_session === undefined ? s.focusSession : message.focus_session };
          if (message.type === 'caption') return { ...s,
            caption: !s.caption || message.data.ts >= s.caption.ts ? message.data : s.caption };
          if (message.type === 'focus') return { ...s, focusEvent: { ...message.data, receivedAt: Date.now() / 1000 },
            focusSession: message.data.state === 'started' ? message.data.session : null };
          if (message.type === 'gesture') return { ...s, gesture: { id, data: message.data } };
          if (message.type === 'face_touch') return { ...s, faceTouch: { id, ...message.data } };
          if (message.type === 'mark') return { ...s, marks: mergeMarks(s.marks, [message.data]).slice(-500) };
          if (message.type === 'hello' || message.type === 'verdict') {
            const f = incomingFace;
            const overall = message.type === 'hello' ? message.latest.overall : message.kind === 'overall' ? message.data : undefined;
            const point: TimelinePoint | null = f ? { t: f.ts, stress: f.stress, focus: f.focus,
              fatigue: f.fatigue, positivity: f.positivity, expression: f.expression.choice,
              posture: s.live && s.live.posture.state !== 'unknown' ? s.live.posture.score / 25 : undefined } : null;
            const series = point ? [...s.liveSeries.filter(p => p.t !== point.t), point]
              .filter(p => p.t > Date.now() / 1000 - 600).sort((a, b) => a.t - b.t) : s.liveSeries;
            return { ...s, face: f ?? s.face, faceZScores: f ? s.live?.face.vs_usual ?? {} : s.faceZScores, overall: overall ?? s.overall, liveSeries: series,
              status: message.type === 'hello' ? message.status : s.status };
          }
          if (message.type === 'speech') return { ...s, speech: mergeSpeech(s.speech, [{ speech: message.data, animate: true }]) };
          return { ...s, status: message.type === 'calibrated' ? message.data : s.status,
            events: [...s.events, { id, event: message }].slice(-32) };
        });
      };
      socket.onerror = () => { if (!disposed) setState(s => ({ ...s, error: 'Connection interrupted. Reconnecting…' })); };
      socket.onclose = () => {
        if (disposed) return;
        setState(s => ({ ...s, connected: false }));
        retry = setTimeout(connect, 1500);
      };
    };
    connect();
    // v1 servers may not offer captions yet. Incoming socket captions always win older history.
    void getMarks().then(marks => {
      if (!disposed) setState(s => ({ ...s, marks: mergeMarks(marks, s.marks).slice(-500) }));
    }).catch(() => {});
    void getCaptions().then(captions => {
      const latest = captions[captions.length - 1];
      if (!disposed && latest) setState(s => ({ ...s, caption: !s.caption || latest.ts > s.caption.ts ? latest : s.caption }));
    }).catch(() => {});
    void getSpeech(240).then(speech => {
      if (!disposed) setState(s => ({ ...s, speech: mergeSpeech(s.speech, speech.slice(-4).map(item => ({ speech: item, animate: false }))) }));
    }).catch(() => { if (!disposed) setState(s => ({ ...s, error: 'Could not load earlier speech.' })); });
    void getTimeline(undefined, 1).then(timeline => {
      if (!disposed) setState(s => {
        const points = timeline.points.filter(p => p.t > Date.now() / 1000 - 600 && p.stress != null);
        const byTime = new Map([...points, ...s.liveSeries].map(p => [p.t, p]));
        return { ...s, liveSeries: [...byTime.values()].sort((a, b) => a.t - b.t) };
      });
    }).catch(() => { if (!disposed) setState(s => ({ ...s, error: 'Could not load recent readings.' })); });
    return () => {
      disposed = true;
      clearTimeout(retry);
      if (socket) {
        socket.onopen = socket.onmessage = socket.onerror = socket.onclose = null;
        socket.close();
      }
    };
  }, []);
  const setFocusSession = useCallback((focusSession: FocusSession | null) => setState(s => ({ ...s, focusSession })), []);
  return { ...state, timing, setFocusSession };
}
