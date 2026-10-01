import type { OverallVerdict } from '../api/types';
import { hhmm } from '../lib/presentation';
import { Card, FadeText, FlagChip } from './Primitives';
export function OverallCard({ overall }: { overall: OverallVerdict | null }) {
  const tense = overall && (overall.stress >= 2 ? 'tense' : overall.stress >= 1.3 ? 'a little tense' : 'relaxed');
  const focus = overall && (overall.focus >= 2.5 ? 'focused' : overall.focus >= 1.5 ? 'partly focused' : 'unfocused');
  return <Card className="pad overall" index={3}>
    <div className="section-heading"><span className="lab">Overall read</span><span className="note">face · voice · posture · baseline</span></div>
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginTop: 10, minWidth: 0 }}>
      <FadeText className="word serif" text={overall?.mood.choice ?? '–'} /><span style={{ fontSize: 12, color: 'var(--muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {overall ? `${focus}, ${tense} · ${hhmm(overall.ts)}` : 'first read in about 15 s'}</span></div>
    <div className="chips" style={{ marginTop: 12 }}>{overall && <><FlagChip label="Needs a break" value={overall.needs_break} hot />
      <FlagChip label="In flow" value={overall.in_flow} /><FlagChip label="Overwhelmed" value={overall.overwhelmed} hot /></>}</div>
  </Card>;
}
