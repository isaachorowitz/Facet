import { useCallback, useRef, useState } from 'react';
import { AnimatePresence } from 'motion/react';
import { StoryOverlay } from './StoryOverlay';
import { ChartTooltip } from './ChartTooltip';
import type { ChartHover } from './ChartTooltip';
import { GestureIcon } from './GestureIcon';
import { MARK_GESTURES, MARK_LABELS, mergeMarks } from '../lib/v2';
import type { Mark, TimelinePoint } from '../api/types';
import type { useDayData } from '../hooks/useDayData';
import { useInterval } from '../hooks/useInterval';
import { chartModel, nearestPoint } from '../lib/chart';
import { COLORS, hhmm, linePath } from '../lib/presentation';
import type { PlotKey } from '../lib/presentation';
import { Card, Icon } from './Primitives';
import { Stats } from './Stats';
import { ChartLine } from './ChartLine';
const lines: [PlotKey, string, number][] = [['posture', 'Posture', 1.5], ['focus', 'Focus', 2], ['fatigue', 'Fatigue', 2], ['positivity', 'Mood', 2], ['stress', 'Stress', 2.2]];
export function DayChart({ day, recent, marks }: { day: ReturnType<typeof useDayData>; recent: TimelinePoint[]; marks: Mark[] }) {
  const input = useRef<HTMLInputElement>(null);
  const [now, setNow] = useState(() => Date.now() / 1000);
  const [hover, setHover] = useState<ChartHover | null>(null);
  const [story, setStory] = useState(false);
  const closeStory = useCallback(() => setStory(false), []);
  const allMarks = mergeMarks(day.marks, marks).filter(mark => {
    if (day.view === 'live') return true;
    const date = new Date(mark.ts * 1000);
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}` === day.date;
  });
  useInterval(() => setNow(Date.now() / 1000), day.view === 'live' ? 5000 : null);
  const model = chartModel(day.view, day.timeline, recent, Math.max(now, Date.now() / 1000), allMarks);
  const hasDomain = day.view === 'live' || day.timeline !== null;
  const nowT = Date.now() / 1000;
  const bucketSeconds = day.view === 'live' ? 60 : (day.timeline?.bucket_minutes ?? 5) * 60;
  // Timeline-only marks are shown at bucket start when exact timestamp history is unavailable.
  const chartMarks = mergeMarks(allMarks, model.points.flatMap(point => (point.marks ?? []).filter(kind =>
    !allMarks.some(mark => mark.kind === kind && mark.ts >= point.t && mark.ts < point.t + bucketSeconds))
    .map(kind => ({ ts: point.t, kind, note: null })))).filter(mark => mark.ts >= model.t0 && mark.ts <= model.t1);
  return <Card className="day" index={7}><div className="chart"><div className="head">
    <span className="lab">{model.title}</span><span className="legend">{(['stress', 'focus', 'fatigue', 'positivity', 'posture'] as const).map(key => <span key={key}>
      <span className="dot" style={{ background: COLORS[key] }} />{key === 'positivity' ? 'mood' : key}</span>)}</span><div className="grow" />
    <button className="btn small story-button" type="button" onClick={() => setStory(true)}>Story</button>
    <span style={{ display: 'flex', gap: 4, position: 'relative' }}>
      <button className={`btn small${day.view === 'day' ? ' sel' : ''}`} type="button" onClick={day.today}>Today</button>
      <button className={`btn small${day.view === 'live' ? ' sel' : ''}`} type="button" onClick={() => { setNow(Date.now() / 1000); day.showLive(); }}>Last 10 min</button>
      <button className="btn small" type="button" aria-label="Pick a day" onClick={() => {
        try { input.current?.showPicker(); } catch { input.current?.focus(); }
      }}><Icon name="calendar" /></button>
      <input ref={input} type="date" id="day" aria-label="Day" value={day.date} onChange={e => day.pick(e.target.value)} />
    </span></div>
    <div className="plot" onMouseLeave={() => setHover(null)} onMouseMove={event => {
      if (!hasDomain || (event.target instanceof Element && event.target.closest('.chart-mark'))) return;
      const rect = event.currentTarget.getBoundingClientRect(), fraction = (event.clientX - rect.left) / rect.width;
      setHover({ fraction, left: event.clientX + 14, top: rect.top,
        point: nearestPoint(model.points, model.t0 + fraction * (model.t1 - model.t0), day.view === 'live' ? 60 : 900) });
    }}>
      <svg preserveAspectRatio="none" viewBox="0 0 1000 120">
        {hasDomain && <>{[31, 60, 89].map(y => <line key={y} x1="0" x2="1000" y1={y} y2={y} stroke="rgba(255,255,255,.05)" vectorEffect="non-scaling-stroke" />)}
          {day.view === 'day' && (day.summary?.breaks ?? []).map(b => <rect key={b.start} x={model.x(b.start)} y="0" width={Math.max(2, model.x(b.start + b.minutes * 60) - model.x(b.start))} height="120" fill="rgba(255,255,255,.03)" />)}
          {lines.map(([key, , width], i) => {
            const d = linePath(model.points, key, model.x);
            if (!d) return null;
            const props = { d, fill: 'none', stroke: COLORS[key], strokeWidth: width, strokeLinejoin: 'round' as const, strokeLinecap: 'round' as const,
              vectorEffect: 'non-scaling-stroke', opacity: key === 'stress' ? 1 : .85 };
            return key === 'posture' ? <path key={key} {...props} strokeDasharray="2 4" /> :
              <ChartLine key={`${key}-${day.view}-${day.drawVersion}`} d={d} color={COLORS[key]} width={width} opacity={key === 'stress' ? 1 : .85} delay={(i - 1) * .12} />;
          })}</>}
      </svg>
      {hasDomain && nowT > model.t0 && nowT < model.t1 && <div className="nowline" style={{ left: `${model.x(nowT) / 10}%` }} />}
      {hasDomain && !model.points.length && <div className="label empty" style={{ left: '50%', top: '42%', transform: 'translateX(-50%)' }}>{day.view === 'live' ? 'Building the last ten minutes…' : 'No readings for this day.'}</div>}
      {day.view === 'day' && (day.summary?.stress_peaks ?? []).slice(0, 3).map((peak, i) => <div key={peak.ts} className="label mono" style={{ left: `${model.x(peak.ts) / 10}%`, top: `${Math.max(0, 100 - peak.stress / 4 * 100 - 16)}%`, color: 'var(--amber)', transform: 'translateX(-50%)', animationDelay: `${1.2 + i * .15}s` }}>● peak {hhmm(peak.ts)}</div>)}
      <div className="cross" style={{ left: `${(hover?.fraction ?? 0) * 100}%` }} />
      {chartMarks.map((mark, i) => <button key={`${mark.ts}:${mark.kind}`} className={`chart-mark ${mark.kind}`} type="button"
        style={{ left: `${model.x(mark.ts) / 10}%`, top: chartMarks.slice(0, i).some(m => Math.abs(model.x(m.ts) - model.x(mark.ts)) < 22) ? 18 : 0 }}
        aria-label={`${MARK_LABELS[mark.kind]}, ${hhmm(mark.ts)}${mark.note ? `, ${mark.note}` : ''}`}
        onMouseEnter={event => { const rect = event.currentTarget.getBoundingClientRect(); setHover({ fraction: model.x(mark.ts) / 1000, left: rect.left, top: rect.top, point: null, mark }); }}
        onFocus={event => { const rect = event.currentTarget.getBoundingClientRect(); setHover({ fraction: model.x(mark.ts) / 1000, left: rect.left, top: rect.top, point: null, mark }); }}
        onBlur={() => setHover(null)}><GestureIcon gesture={MARK_GESTURES[mark.kind]} size={18} /></button>)}
      <ChartTooltip hover={hover} marks={allMarks} bucketSeconds={bucketSeconds} />
    </div><div style={{ display: 'grid', gap: 4 }}><div className="strip">{hasDomain && model.strip.map((background, i) => <span key={i} style={{ background }} />)}</div>
      <div className="hours mono">{hasDomain && model.marks.map((mark, i) => <span key={i}>{mark}</span>)}</div></div>
  </div><Stats summary={day.summary} /><AnimatePresence>{story && <StoryOverlay key={day.date} date={day.date} onClose={closeStory} />}</AnimatePresence></Card>;
}
