import { useMotionPreference } from '../hooks/useMotionPreference';
import { useState } from 'react';
import { useInterval } from '../hooks/useInterval';
import { freshCaption } from '../lib/v2';
import { WordReveal } from './WordReveal';
import { motion } from 'motion/react';
import type { Caption, FaceVerdict } from '../api/types';
import { auraFor, clamp, COLORS, EASE, EXPRESSIONS, FLAGS, hhmm, MOOD_WORDS, pct, RINGS, sentence, WORDS } from '../lib/presentation';
import { Bar, Card, FadeText, FlagChip, NumberValue } from './Primitives';
import { MoodWord } from './MoodWord';
import { Ring } from './Ring';
export function NowCard({ face, zScores, caption, focusing }: { face: FaceVerdict | null; zScores: Record<string, number>; caption: Caption | null; focusing: boolean }) {
  const reduced = useMotionPreference();
  const [now, setNow] = useState(() => Date.now() / 1000);
  useInterval(() => setNow(Date.now() / 1000), 1000);
  const narrator = freshCaption(caption, Math.max(now, Date.now() / 1000));
  const probabilities = face ? Object.entries(face.expression.probabilities).sort((a, b) => b[1] - a[1]) : [];
  const second = probabilities[1];
  return <Card className={`now${focusing ? ' focus-now' : ''}`} index={2}>
    <div className="aura" style={{ background: focusing ? 'radial-gradient(closest-side, rgba(143,184,255,.18), rgba(127,214,164,.055) 55%, transparent 76%)' : face ? auraFor(face) : undefined }} />
    <div className="hero"><div style={{ minWidth: 0 }}><div className="lab">Right now · your face</div><MoodWord word={face?.expression.choice ?? 'waking'} />
      <div className="conf">{face ? <><span className="mono" style={{ color: 'var(--text)' }}><NumberValue value={face.expression.confidence * 100} duration={700} format={v => `${Math.round(v)}%`} /></span><span>confident</span>
        {second && <><span className="sep" /><span>then {second[0]}</span><span className="mono">{pct(second[1])}</span></>}</> : 'Clef-flash is loading onto the GPU'}</div>
      <div className={`sentence${narrator ? ' narrator-caption' : ''}`} title={narrator ? caption?.text : undefined}>
        {narrator && caption ? <><div className="caption-meta"><span className="lab sm">Narrator</span><time className="mono" dateTime={new Date(caption.ts * 1000).toISOString()}>{hhmm(caption.ts)}</time></div>
          <p key={`${caption.ts}:${caption.text}`}><WordReveal text={caption.text} /></p></> : <p><FadeText text={face ? sentence(face, zScores) : ''} /></p>}
      </div>
    </div><Ring face={face} /><div className="flags">{FLAGS.map(([key, label, hot]) => <FlagChip key={key} label={label} value={face?.[key]} hot={hot} />)}</div></div>
    <div className="lower"><div className="stack">{RINGS.map(([key, label]) => {
      const value = clamp(face?.[key] ?? 0, 0, 4);
      return <div className="srow" key={key}><span className="name"><span className="dot" style={{ background: COLORS[key] }} />{label}</span>
        <Bar width={value / 4 * 100} color={COLORS[key]} /><span className="word">{face ? (key === 'positivity' ? MOOD_WORDS : WORDS)[Math.round(value)] : '–'}</span></div>;
    })}</div><div><div className="lab" style={{ marginBottom: 9 }}>Expression</div>
      <div className="stack" style={{ gap: 6, position: 'relative' }}>{probabilities.slice(0, 5).map(([expression, probability]) =>
        <motion.div key={expression} className="erow" layout={!reduced} initial={{ opacity: reduced ? 1 : 0, y: reduced ? 0 : 8, filter: reduced ? 'none' : 'blur(4px)' }}
          animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }} transition={{ duration: reduced ? 0 : .6, ease: EASE }} style={{ transition: 'none' }}>
          <span>{expression}</span><Bar width={probability * 100} color={EXPRESSIONS[expression] || '#888'} /><span className="mono"><NumberValue value={probability * 100} duration={700} format={v => `${Math.round(v)}%`} /></span>
        </motion.div>)}</div>
    </div></div>
  </Card>;
}
