import { useEffect, useState } from 'react';
import { useReducedMotion } from 'motion/react';
import type { Live, Speech, Status } from '../api/types';
import type { SpeechEntry } from '../hooks/useFacetSocket';
import { clamp, hhmm, WORDS } from '../lib/presentation';
import { Card } from './Primitives';
function Utterance({ speech, animate }: { speech: Speech; animate: boolean }) {
  const reduced = useReducedMotion(), full = `“${speech.text}”`;
  const [length, setLength] = useState(animate && !reduced ? 2 : full.length);
  useEffect(() => {
    if (!animate || reduced || !speech.text) { setLength(full.length); return; }
    let i = 2;
    setLength(i);
    const timer = setInterval(() => {
      i = Math.min(full.length, i + 2); setLength(i);
      if (i === full.length) clearInterval(timer);
    }, 16);
    return () => clearInterval(timer);
  }, [animate, reduced, full, speech.text]);
  const verdict = speech.verdict;
  return <div className="utter"><div className="t">{speech.text ? <>{full.slice(0, length)}{length < full.length && <span className="caret" />}</> : <span style={{ color: 'var(--faint)' }}>Transcript not kept</span>}</div>
    <div className="meta"><span className="mono">{hhmm(speech.ts)}</span>{verdict && <span className="chip on">{verdict.tone.choice}</span>}
      <span className="mono">{Math.round(speech.prosody.words_per_minute)} wpm</span><span className="mono">{Math.round(speech.prosody.pitch_hz)} Hz</span>
      {verdict && <span>stress {WORDS[Math.round(verdict.stress)]}</span>}</div></div>;
}
export function VoiceCard({ live, status, speech }: { live: Live | null; status: Status | null; speech: SpeechEntry[] }) {
  const [wave, setWave] = useState(() => Array.from({ length: 64 }, () => ({ height: 3, background: 'rgba(233,230,223,.2)' })));
  const speaking = live?.voice.speaking ?? false;
  useEffect(() => {
    if (!live) return;
    const level = clamp((live.voice.level_db + 62) / 42, 0, 1);
    setWave(bars => [...bars.slice(1), { height: 3 + level * 19,
      background: live.voice.speaking ? 'rgba(243,181,98,.9)' : `rgba(233,230,223,${(.16 + level * .3).toFixed(2)})` }]);
  }, [live]);
  const off = status?.voice === 'paused';
  return <Card className={`pad voice${speaking ? ' speaking' : ''}`} index={6}>
    <div className="section-heading" style={{ alignItems: 'center' }}><span className="lab">Voice</span><span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--muted)' }}>
      <span className="dot" style={{ background: off ? 'var(--faint)' : speaking ? 'var(--amber)' : live ? 'var(--mint)' : 'var(--faint)', boxShadow: speaking && !off ? '0 0 8px var(--amber)' : undefined }} />
      <span style={{ color: speaking && !off ? 'var(--amber)' : undefined }}>{off ? 'Mic off' : speaking ? 'Hearing speech' : 'Listening'}</span></span></div>
    <div className="wave">{wave.map((bar, i) => <span key={i} style={{ height: `${bar.height.toFixed(1)}px`, background: bar.background }} />)}</div>
    <div className="utters">{speech.length ? speech.map(entry => <Utterance key={entry.speech.ts} speech={entry.speech} animate={entry.animate} />) : <div className="empty">Nothing heard yet.</div>}</div>
  </Card>;
}
