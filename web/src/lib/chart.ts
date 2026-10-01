import type { Mark, Timeline, TimelinePoint } from '../api/types';
import type { ChartView } from '../hooks/useDayData';
import { EXPRESSIONS, hhmm } from './presentation';
export function chartModel(view: ChartView, timeline: Timeline | null, recent: TimelinePoint[], now: number, dayMarks: Mark[] = []) {
  let t0 = now - 600, t1 = now;
  const points = view === 'live' ? recent.filter(p => p.t > t0) : timeline?.points ?? [];
  let title = view === 'live' ? 'Last 10 minutes' : 'Today';
  if (view === 'day' && timeline) {
    const startDate = new Date(timeline.start * 1000);
    title = startDate.toDateString() === new Date().toDateString() ? 'Today' : startDate.toLocaleDateString([], { weekday: 'short', day: 'numeric', month: 'short' });
    t0 = timeline.start + 8 * 3600; t1 = timeline.start + 22 * 3600;
    if (points.length) { t0 = Math.min(t0, points[0].t - 1800); t1 = Math.max(t1, points[points.length - 1].t + 1800); }
    if (dayMarks.length) { t0 = Math.min(t0, dayMarks[0].ts - 1800); t1 = Math.max(t1, dayMarks[dayMarks.length - 1].ts + 1800); }
    t0 = Math.max(t0, timeline.start); t1 = Math.min(t1, timeline.start + 86400);
  }
  const x = (t: number) => (t - t0) / (t1 - t0) * 1000;
  const strip = Array.from({ length: 64 }, (_, i) => {
    const a = t0 + i * (t1 - t0) / 64, b = a + (t1 - t0) / 64;
    const inside = points.filter(p => p.t >= a - (view === 'day' ? (timeline?.bucket_minutes || 5) * 30 : 0) && p.t < b && p.expression);
    const expression = inside[inside.length - 1]?.expression;
    return expression ? EXPRESSIONS[expression] || '#555' : 'rgba(255,255,255,.04)';
  });
  const marks: string[] = [];
  if (view === 'live') for (let m = 10; m >= 0; m -= 2) marks.push(m ? `−${m}m` : 'now');
  else {
    const step = t1 - t0 > 12 * 3600 ? 7200 : 3600;
    for (let t = Math.ceil(t0 / step) * step; t <= t1; t += step) marks.push(hhmm(t));
  }
  return { t0, t1, points, title, x, strip, marks };
}
export function nearestPoint(points: TimelinePoint[], time: number, tolerance: number) {
  let best: TimelinePoint | null = null, distance = Infinity;
  for (const p of points) { const d = Math.abs(p.t - time); if (d < distance) { distance = d; best = p; } }
  return distance <= tolerance ? best : null;
}
