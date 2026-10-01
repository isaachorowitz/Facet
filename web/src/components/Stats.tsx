import type { Summary } from '../api/types';
import { capitalise, hhmm, pct } from '../lib/presentation';
const formatMinutes = (m: number) => m >= 60 ? `${Math.floor(m / 60)}h ${String(Math.round(m % 60)).padStart(2, '0')}` : `${Math.round(m)}`;
export function Stats({ summary }: { summary: Summary | null }) {
  const s = summary;
  const top = Object.entries(s?.expressions ?? {})[0];
  const sessions = [...(s?.focus_streaks ?? []), ...(s?.focus_sessions ?? [])];
  const longest = sessions.length ? Math.max(...sessions.map(session => session.minutes)) : null;
  const breaks = s?.breaks ?? [];
  const items: [string, string | number, string][] = [
    ['At desk', s ? formatMinutes(s.minutes_present) : '–', s && s.minutes_present < 60 ? 'min' : ''],
    ['Longest focus', longest === null ? '–' : formatMinutes(longest), longest !== null && longest < 60 ? 'min' : ''],
    ['Posture', s?.avg_posture == null ? '–' : Math.round(s.avg_posture), s?.minutes_poor_posture ? `${Math.round(s.minutes_poor_posture)}m slouched` : ''],
    ['Sips today', s?.sips ?? '–', ''],
    ['Face touches', s?.face_touches ?? '–', 'today'],
    ['20-20-20', s?.eyes_breaks_taken ?? '–', `taken · ${s?.eyes_breaks_due ?? '–'} due`],
    ['Talking', s ? formatMinutes(s.minutes_talking) : '–', s && s.minutes_talking < 60 ? 'min' : ''],
    ['Desk breaks', s ? breaks.length : '–', breaks.length ? `last ${hhmm(breaks[breaks.length - 1].start)}` : ''],
    ['Mostly', top ? capitalise(top[0]) : '–', top ? pct(top[1]) : ''],
  ];
  return <div className="stats">{items.map(([label, value, sub]) => <div key={label} title={`${label}: ${value} ${sub}`}><div className="lab sm">{label}</div><div className="v">
    <span className={typeof value === 'number' || /^\d/.test(value) ? 'mono' : ''}>{value}</span>{sub && <span className="s">{sub}</span>}</div></div>)}</div>;
}
