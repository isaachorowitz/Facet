import { useEffect, useRef } from 'react';
import type { Posture, Summary } from '../api/types';
import { clamp, POSTURE_COLORS } from '../lib/presentation';
import { Card, NumberValue } from './Primitives';
import { PostureFigure } from './PostureFigure';
export function PostureCard({ posture: incoming, summary }: { posture: Posture | null; summary: Summary | null }) {
  const last = useRef<Posture | null>(null);
  useEffect(() => { if (incoming?.visible && !incoming.stale && incoming.skeleton.l_sh && incoming.skeleton.r_sh) last.current = incoming; }, [incoming]);
  const posture = incoming?.stale && last.current ? { ...last.current, stale: true } : incoming;
  const scored = (posture?.visible || posture?.stale) && posture.state !== 'unknown';
  const issues = scored ? posture.issues.length ? posture.issues : ['Sitting well'] : [];
  const reference = { calibrated: 'vs your calibrated posture', learned: 'vs your best posture this hour', learning: 'learning your upright posture' };
  return <Card className={`pad posture${scored && !posture.stale && posture.state === 'poor' ? ' alert' : ''}`} index={5}>
    <div className="section-heading"><span className="lab">Posture</span><span className="note">{reference[posture?.reference ?? 'learning']}</span></div>
    <div className="pbody"><div className={`figure${posture?.stale ? ' holding' : ''}`}><PostureFigure posture={posture} /></div><div className="pscore">
      <div className="n mono"><NumberValue value={scored ? posture.score : null} duration={700} /></div>
      <div className="st" style={{ color: POSTURE_COLORS[posture?.state ?? 'unknown'] }}>{posture?.stale ? 'holding' : !posture ? 'measuring' : !posture.visible ? 'not in view' : scored ? posture.state : 'learning'}</div>
      <div className="issues" key={issues.join('|')}>{issues.map(issue => <div key={issue}>{issue}</div>)}</div>
    </div></div>
    <div className="pmetrics">
      <div><div className="lab sm">Neck</div><div className="v mono"><NumberValue value={scored && posture.ref_neck ? clamp(posture.neck / posture.ref_neck * 100, 0, 150) : null} /><span className="u">%</span></div></div>
      <div><div className="lab sm">Shoulders</div><div className="v mono"><NumberValue value={posture?.visible ? Math.abs(posture.shoulder_tilt) : null} format={v => v.toFixed(1)} /><span className="u">°</span></div></div>
      <div><div className="lab sm">Lean in</div><div className="v mono"><NumberValue value={scored ? (posture.lean - 1) * 100 : null} format={v => (v > 0 ? '+' : '') + Math.round(v)} /><span className="u">%</span></div></div>
      <div><div className="lab sm">Good today</div><div className="v mono"><NumberValue value={summary?.avg_posture != null && summary.minutes_present ? (summary.minutes_good_posture || 0) / Math.max(1, summary.minutes_present) * 100 : null} /><span className="u">%</span></div></div>
    </div>
  </Card>;
}
