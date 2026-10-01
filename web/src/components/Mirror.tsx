import { useEffect, useRef, useState } from 'react';
import type { Live, Status, FocusSession } from '../api/types';
import { motion } from 'motion/react';
import { HandOverlay } from './HandOverlay';
import { GestureOverlay } from './GestureOverlay';
import type { GestureEntry } from './GestureOverlay';
import { Card, Icon, NumberValue } from './Primitives';

export function Mirror({ live, status, videoSession, gesture, faceTouch, focus, focusEvent }: {
  live: Live | null; status: Status | null; videoSession: number | null; gesture: GestureEntry | null;
  faceTouch: { id: number; ts: number; count_last_hour: number } | null; focus: FocusSession | null;
  focusEvent: { state: 'started' | 'ended'; session: FocusSession; receivedAt: number } | null;
}) {
  const [ready, setReady] = useState(false);
  const [source, setSource] = useState<string>();
  const retry = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => {
    if (videoSession !== null) { clearTimeout(retry.current); setSource(`/video.mjpg?${videoSession}`); }
    return () => clearTimeout(retry.current);
  }, [videoSession]);
  const camOk = !status?.paused && status?.camera === 'on';
  const f = live?.face, metrics = f?.metrics ?? {};
  const left = status?.calibrating_seconds_left ?? 0;
  const touchAge = faceTouch ? Date.now() / 1000 - faceTouch.ts : Infinity;
  const measuredTouches = live?.wellness?.face_touches_last_hour;
  const hourlyTouches = measuredTouches === undefined ? touchAge < 3600 ? faceTouch?.count_last_hour : undefined :
    touchAge < 2 ? Math.max(measuredTouches, faceTouch?.count_last_hour ?? 0) : measuredTouches;
  return <Card index={1} className={`mirror${f?.present && camOk ? ' tracking' : ''}`}>
    <img src={source} className={ready ? 'ready' : ''} alt="Live camera, mirrored" onLoad={() => setReady(true)} onError={() => {
      setReady(false); clearTimeout(retry.current); retry.current = setTimeout(() => setSource(`/video.mjpg?${Date.now()}`), 2000);
    }} />
    <HandOverlay hands={live?.hands} view={live?.view} visible={camOk && ready} />
    <GestureOverlay event={gesture} focus={focus} transition={focusEvent && gesture && Math.abs(focusEvent.receivedAt - gesture.data.ts) < 5 ? focusEvent.state : undefined} />
    {faceTouch && <motion.div key={faceTouch.id} className="touch-flash" aria-hidden="true" initial={{ opacity: 0 }} animate={{ opacity: [0, .7, 0] }} transition={{ duration: .95 }} />}
    <div className="scan" /><div className="brackets"><i /><i /><i /><i /></div>
    <div className="veil" hidden={camOk && ready}><div><div className="orb"><Icon name="camera" /></div>
      <div>{status?.paused ? 'Paused' : status?.camera_error || 'Starting camera'}</div></div></div>
    <div className="tags"><span key={String(f?.present)} className="chip pop"><span className="dot" style={{ background: f?.present ? 'var(--mint)' : 'var(--faint)', boxShadow: f?.present ? '0 0 8px var(--mint)' : undefined }} />{f?.present ? 'Tracking' : 'No face'}</span>
      <span className="chip" hidden={!f?.present}>{f?.yawning ? 'Yawning' : f?.looking_at_screen ? 'Eyes on screen' : 'Looking away'}</span></div>
    {hourlyTouches !== undefined && <div className="touch-count mono" title="Face touches in the last hour">{hourlyTouches} <span>touches / hr</span></div>}
    <div className="vitals">
      <div><div className="lab sm">Blinks</div><div className="v mono"><NumberValue value={f?.present ? f.blink_rate : null} /><span className="u">/min</span></div></div>
      <div><div className="lab sm">Head</div><div className="v mono">{f?.present ? <>{Math.round(metrics.yaw)}°<span className="u">{Math.round(metrics.pitch)}°</span></> : '–'}</div></div>
      <div><div className="lab sm">Sitting</div><div className="v mono"><NumberValue value={live?.minutes_since_break || null} /><span className="u">min</span></div></div>
      <div><div className="lab sm">Distance</div><div className="v mono"><NumberValue value={f?.present && metrics.face_size ? 15 / (1.74 * metrics.face_size) : null} /><span className="u">cm</span></div></div>
    </div>
    <div className={`calib${left > 0 ? ' on' : ''}`}><div>
      <svg viewBox="0 0 120 120"><circle cx="60" cy="60" r="52" fill="none" stroke="rgba(255,255,255,.1)" strokeWidth="3" />
        <circle cx="60" cy="60" r="52" fill="none" stroke="#7fd6a4" strokeWidth="3" strokeLinecap="round" strokeDasharray="326.7"
          strokeDashoffset={(326.7 * (1 - left / 30)).toFixed(1)} transform="rotate(-90 60 60)" style={{ transition: 'stroke-dashoffset 1s linear' }} /></svg>
      <div className="n mono">{left || 30}</div><div className="lab">Calibrating</div><p>Sit upright and relaxed.<br />Neutral face, eyes on the screen.</p>
    </div></div>
  </Card>;
}
