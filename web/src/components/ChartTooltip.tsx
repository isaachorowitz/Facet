import { createPortal } from 'react-dom';
import type { Mark, TimelinePoint } from '../api/types';
import { COLORS, EXPRESSIONS, hhmm } from '../lib/presentation';
import { MARK_GESTURES, MARK_LABELS } from '../lib/v2';
import { GestureIcon } from './GestureIcon';
export type ChartHover = { fraction: number; left: number; top: number; point: TimelinePoint | null; mark?: Mark };
export function ChartTooltip({ hover, marks, bucketSeconds }: { hover: ChartHover | null; marks: Mark[]; bucketSeconds: number }) {
  if (!hover?.point && !hover?.mark) return null;
  const point = hover.point, mark = hover.mark;
  const bucket = point ? marks.filter(m => m.ts >= point.t && m.ts < point.t + bucketSeconds) : [];
  const extra = point?.marks?.filter(kind => !bucket.some(m => m.kind === kind)) ?? [];
  return createPortal(<div className="chart-tooltip" role="tooltip" style={{ left: Math.max(12, Math.min(window.innerWidth - 232, hover.left)), top: Math.max(70, Math.min(window.innerHeight - 230, hover.top - 160)) }}>
    {mark ? <><div className="tooltip-mark"><GestureIcon gesture={MARK_GESTURES[mark.kind]} size={20} /><b>{MARK_LABELS[mark.kind]}</b><time className="mono">{hhmm(mark.ts)}</time></div>{mark.note && <p>{mark.note}</p>}</> : point && <>
      <div className="tooltip-heading mono">{hhmm(point.t)}{point.expression && <> · <span style={{ color: EXPRESSIONS[point.expression] }}>{point.expression}</span></>}</div>
      {(['stress', 'focus', 'fatigue', 'positivity', 'posture'] as const).map(key => {
        const value = point[key];
        return value === undefined ? null : <div className="r" key={key}><span><span className="dot" style={{ background: COLORS[key], marginRight: 6 }} />{key === 'positivity' ? 'Mood' : key.charAt(0).toUpperCase() + key.slice(1)}</span>
          <b className="mono">{key === 'posture' ? Math.round(value * 25) : `${value.toFixed(1)} / 4`}</b></div>;
      })}
      {(bucket.length > 0 || extra.length > 0) && <div className="tooltip-marks">{bucket.map(m => <div className="tooltip-mark" key={`${m.ts}:${m.kind}`}><GestureIcon gesture={MARK_GESTURES[m.kind]} size={16} /><span>{MARK_LABELS[m.kind]}{m.note ? ` · ${m.note}` : ''}</span><time className="mono">{hhmm(m.ts)}</time></div>)}
        {extra.map((kind, i) => <div className="tooltip-mark" key={`${kind}:${i}`}><GestureIcon gesture={MARK_GESTURES[kind]} size={16} /><span>{MARK_LABELS[kind]}</span></div>)}</div>}
    </>}
  </div>, document.body);
}
