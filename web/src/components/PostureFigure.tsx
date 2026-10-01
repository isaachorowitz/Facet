import type { Posture } from '../api/types';
import type { PointName } from '../lib/figure';
import { clamp, POSTURE_COLORS } from '../lib/presentation';
import { useFigure } from '../hooks/useFigure';
export function PostureFigure({ posture }: { posture: Posture | null }) {
  const cur = useFigure(posture);
  if (!cur?.l_sh || !cur.r_sh) return <svg viewBox="-95 -125 190 175" preserveAspectRatio="xMidYMid meet">
    <g opacity=".28" fill="none" stroke="var(--sand)" strokeWidth="1.5" strokeLinecap="round"><circle cx="0" cy="-78" r="18" /><path d="M-8-59v15M8-59v15M-43-15c0-37 86-37 86 0" /></g>
    <text x="0" y="12" textAnchor="middle" fill="#8a877f" fontSize="10" fontFamily="Geist">Your posture will return</text></svg>;
  const visible = (name: PointName) => (cur[name]?.[2] ?? 0) > .45;
  const color = POSTURE_COLORS[posture?.state ?? 'unknown'];
  const head = (['nose', 'l_ear', 'r_ear'] as const).flatMap(name => visible(name) && cur[name] ? [cur[name]] : []);
  const hx = head.reduce((a, b) => a + b[0], 0) / (head.length || 1), hy = head.reduce((a, b) => a + b[1], 0) / (head.length || 1);
  const earWidth = visible('l_ear') && visible('r_ear') && cur.l_ear && cur.r_ear ? Math.abs(cur.l_ear[0] - cur.r_ear[0]) : 40;
  const radius = clamp(earWidth * .62, 18, 34), ls = cur.l_sh, rs = cur.r_sh;
  const gy = posture?.ref_neck ? -posture.ref_neck * 96 : null;
  const bw = Math.abs(ls[0] - rs[0]), neckBottom = hy + radius * .92;
  const limb = (a: PointName, b: PointName, width: number, opacity: number) => {
    const start = cur[a], end = cur[b];
    return visible(a) && visible(b) && start && end ? <line key={`${a}-${b}`} className="bone" x1={start[0]} y1={start[1]} x2={end[0]} y2={end[1]} stroke={color} strokeWidth={width} opacity={opacity} /> : null;
  };
  return <svg viewBox="-95 -125 190 175" preserveAspectRatio="xMidYMid meet">
    <defs><linearGradient id="torsoG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={color} stopOpacity=".30" /><stop offset="1" stopColor={color} stopOpacity="0" /></linearGradient>
      <radialGradient id="headG" cx=".4" cy=".35" r=".75"><stop offset="0" stopColor={color} stopOpacity=".35" /><stop offset="1" stopColor={color} stopOpacity=".04" /></radialGradient>
      <filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="4" /></filter></defs>
    {gy !== null && <><path className="ghost" d={`M ${ls[0]} ${ls[1]} Q 0 ${gy + radius * 1.9} ${rs[0]} ${rs[1]}`} /><circle className="ghost" cx="0" cy={gy} r={radius} />
      <text x="0" y={gy - radius - 7} textAnchor="middle" fill="rgba(233,230,223,.35)" fontSize="9" fontFamily="Geist" letterSpacing="1.5">UPRIGHT</text></>}
    <path d={`M ${ls[0]} ${ls[1]} C ${ls[0]} ${ls[1] + 30}, ${ls[0] * .82} ${ls[1] + 60}, ${ls[0] * .78} 60 L ${rs[0] * .78} 60 C ${rs[0] * .82} ${rs[1] + 60}, ${rs[0]} ${rs[1] + 30}, ${rs[0]} ${rs[1]} Q 0 ${Math.min(ls[1], rs[1]) - bw * .06} ${ls[0]} ${ls[1]} Z`} fill="url(#torsoG)" stroke="none" />
    {limb('l_sh', 'l_el', 2.5, .55)}{limb('r_sh', 'r_el', 2.5, .55)}{limb('l_el', 'l_wr', 2, .35)}{limb('r_el', 'r_wr', 2, .35)}
    <path className="bone" d={`M ${ls[0]} ${ls[1]} Q 0 ${Math.min(ls[1], rs[1]) - bw * .06} ${rs[0]} ${rs[1]}`} fill="none" stroke={color} strokeWidth="3.5" />
    {head.length > 0 && <><path className="bone" d={`M ${-radius * .32} 2 L ${hx - radius * .3} ${neckBottom} M ${radius * .32} 2 L ${hx + radius * .3} ${neckBottom}`} stroke={color} strokeWidth="2" opacity=".7" fill="none" />
      <circle cx={hx} cy={hy} r={radius + 4} fill={color} opacity=".18" filter="url(#glow)" />
      <circle cx={hx} cy={hy} r={radius} fill="url(#headG)" stroke={color} strokeWidth="2.2" className="bone" />
      {visible('nose') && cur.nose && <><circle cx={cur.nose[0]} cy={cur.nose[1]} r="2" fill={color} />
        <line x1={hx} y1={hy} x2={cur.nose[0]} y2={cur.nose[1]} stroke={color} strokeWidth="1" opacity=".5" /></>}</>}
    {(['l_sh', 'r_sh', 'l_el', 'r_el'] as const).map(name => {
      const point = cur[name];
      return visible(name) && point ? <circle key={name} cx={point[0]} cy={point[1]} r={name.endsWith('sh') ? 4.5 : 3} fill="#0f0f11" stroke={color} strokeWidth="2" className="bone" /> : null;
    })}
  </svg>;
}
