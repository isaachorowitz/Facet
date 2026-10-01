import type { Live, Status } from '../api/types';
import { MEASURED } from '../lib/presentation';
import { Bar, Card } from './Primitives';
export function MeasuredFace({ live, status }: { live: Live | null; status: Status | null }) {
  const face = live?.face;
  return <Card className="measured" index={4}>
    <div className="section-heading" style={{ marginBottom: 10 }}><span className="lab">Measured face</span><span className="note">{status && !status.baseline_samples ? 'learning your usual face' : 'tick = your usual'}</span></div>
    <div className="mgrid">{MEASURED.map(([key, label]) => {
      const value = face?.present ? face.metrics[key] ?? 0 : 0, z = face?.vs_usual[key];
      const strong = z !== undefined && Math.abs(z) >= 1;
      const color = strong ? z > 0 ? 'var(--amber)' : 'var(--ice)' : '#a39f97';
      const usual = status?.baseline[key];
      return <div className="mrow" key={key}><div className="top"><span>{label}</span><span className="z mono" style={{ color: strong ? color : 'var(--faint)' }}>
        {strong ? `${z > 0 ? '▲' : '▼'} ${Math.abs(z).toFixed(1)}σ` : face?.present ? value.toFixed(2) : ''}</span></div>
        <Bar width={Math.min(100, value * 100)} color={color} tick={usual ? Math.min(100, usual.mean * 100) : undefined} shine={false} /></div>;
    })}</div>
  </Card>;
}
