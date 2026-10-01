import { useRef, useState } from 'react';
import type { RefObject } from 'react';
import { useAnimationFrame } from 'motion/react';
import type { Live, Status, FocusSession } from '../api/types';
import { calibrate, pause, resume, updateSettings } from '../api/client';
import { useInterval } from '../hooks/useInterval';
import { clamp } from '../lib/presentation';
import { FocusControl } from './FocusControl';
import { entrance, Icon } from './Primitives';

export function Header({ status, live, timing, onError, focus, onFocus }: {
  status: Status | null; live: Live | null; timing: RefObject<{ lastVerdictAt: number; cadence: number }>;
  onError: (text: string) => void; focus: FocusSession | null; onFocus: (session: FocusSession | null) => void;
}) {
  const [clock, setClock] = useState(() => new Date());
  const beat = useRef<SVGCircleElement>(null);
  useInterval(() => setClock(new Date()), 1000);
  useAnimationFrame(() => {
    if (!beat.current || !timing.current.lastVerdictAt || status?.judge !== 'ready' || status.paused) return;
    const k = clamp((performance.now() - timing.current.lastVerdictAt) / timing.current.cadence, 0, 1);
    beat.current.setAttribute('stroke-dashoffset', (37.7 * (1 - k)).toFixed(2));
  });
  const action = (fn: () => Promise<Status>) => { void fn().catch(() => onError('The action could not reach Facet. Please try again.')); };
  const paused = status?.paused ?? false;
  const cam = !status ? '–' : status.camera === 'on' ? `${Math.round(live?.face.fps ?? 0)} fps` : status.camera;
  const clef = !status ? 'loading' : status.judge === 'ready' ? status.latency_ms.face ? `${(status.latency_ms.face / 1000).toFixed(1)} s` : 'ready' : status.judge;
  const baseline = !status ? '–' : status.calibrating_seconds_left ? `calibrating · ${status.calibrating_seconds_left}s` :
    status.baseline_samples >= 60 ? 'personal' : `learning · ${Math.min(99, Math.round(status.baseline_samples / 60 * 100))}%`;
  return <header className="enter" style={entrance(0)}>
    <div className="brand"><span className="serif">Facet</span><span className={`live${paused ? ' paused' : ''}`}><span className="dot" />
      <span>{paused ? 'Paused · camera and mic off' : 'Live · on device'}</span></span></div>
    <div className="sys">
      <span>Camera <b className={`mono ${status?.camera_error ? 'bad' : status && status.camera !== 'on' ? 'warn' : ''}`}>{cam}</b></span>
      <span><svg className="beat" viewBox="0 0 16 16"><circle cx="8" cy="8" r="6" fill="none" stroke="rgba(255,255,255,.12)" strokeWidth="2" />
        <circle ref={beat} cx="8" cy="8" r="6" fill="none" stroke="#8fb8ff" strokeWidth="2" strokeDasharray="37.7" strokeDashoffset="37.7" transform="rotate(-90 8 8)" strokeLinecap="round" /></svg>
        Clef-flash <b title={status?.judge_error ?? ''} className={`mono ${status?.judge === 'failed' ? 'bad' : status?.judge !== 'ready' ? 'warn' : ''}`}>{clef}</b></span>
      <span>Mic <b title={status?.voice_error ?? ''} className={status?.voice_error && !status.voice_error.startsWith('voice emotion') ? 'warn' : ''}>
        {status?.voice === 'paused' ? 'off' : (status?.mic || '–').replace(/^Razer /, '')}</b></span>
      <span>Baseline <b className={status && status.baseline_samples >= 60 && !status.calibrating_seconds_left ? '' : 'warn'}>{baseline}</b></span>
    </div><div className="grow" />
    <FocusControl session={focus} onSession={onFocus} onError={onError} />
    <span className="mono clock">{clock.toLocaleDateString([], { weekday: 'short', day: 'numeric', month: 'short' })} · {clock.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })}<span className="sec">:{String(clock.getSeconds()).padStart(2, '0')}</span></span>
    <button className="btn" type="button" title="Sit upright and relaxed, face the screen, for 30 seconds" onClick={() => action(() => calibrate(30))}><Icon name="calibrate" />Calibrate</button>
    <button className={`btn ${status?.settings.mic === false ? 'off' : ''} ${status?.settings.mic && live?.voice.speaking ? 'live-mic' : ''}`} type="button"
      aria-pressed={status?.settings.mic ?? true} onClick={() => action(() => updateSettings({ mic: !status?.settings.mic }))}><Icon name="mic" />Mic</button>
    <button className={`btn ${status?.settings.notifications === false ? 'off' : ''}`} type="button" aria-pressed={status?.settings.notifications ?? true}
      onClick={() => action(() => updateSettings({ notifications: !status?.settings.notifications }))}><Icon name="nudge" />Nudges</button>
    <button className="btn solid" type="button" onClick={() => action(paused ? resume : pause)}><Icon name={paused ? 'resume' : 'pause'} /><span>{paused ? 'Resume' : 'Pause'}</span></button>
  </header>;
}
