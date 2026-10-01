import { useEffect, useRef, useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import type { FaceVerdict } from '../api/types';
import { clamp, COLORS, EASE, RINGS } from '../lib/presentation';
import { NumberValue } from './Primitives';
export function Ring({ face }: { face: FaceVerdict | null }) {
  const reduced = useReducedMotion();
  const last = useRef({ expression: '', rippleAt: 0 });
  const [ripple, setRipple] = useState(0);
  useEffect(() => {
    if (!face) return;
    const now = performance.now();
    if (face.expression.choice !== last.current.expression || now - last.current.rippleAt > 6000) {
      setRipple(n => n + 1); last.current.rippleAt = now;
    }
    last.current.expression = face.expression.choice;
  }, [face]);
  return <div className="ring"><svg viewBox="0 0 300 300">
    <defs><linearGradient id="sheen" x1="0" x2="1"><stop offset="0" stopColor="rgba(255,255,255,0)" /><stop offset=".5" stopColor="rgba(255,255,255,.10)" /><stop offset="1" stopColor="rgba(255,255,255,0)" /></linearGradient></defs>
    <circle className="sheen" cx="150" cy="150" r="146" fill="none" stroke="url(#sheen)" strokeWidth="1" />
    <motion.circle key={ripple} className="ripple" cx="150" cy="150" r="140" fill="none" stroke="rgba(143,184,255,.6)" strokeWidth="1.5"
      initial={ripple && !reduced ? { opacity: .55, scale: .55 } : { opacity: 0 }} animate={{ opacity: 0, scale: 1.12 }}
      transition={{ duration: reduced ? 0 : 1.4, ease: EASE }} />
    {RINGS.map(([key], i) => {
      const radius = 136 - i * 17, circumference = 2 * Math.PI * radius, arc = circumference * .75;
      const value = clamp(face?.[key] ?? 0, 0, 4);
      return <g key={key}><circle cx="150" cy="150" r={radius} fill="none" stroke="rgba(255,255,255,.055)" strokeWidth="9" strokeLinecap="round"
        strokeDasharray={`${arc} ${circumference}`} transform="rotate(135 150 150)" />
        <motion.circle cx="150" cy="150" r={radius} fill="none" stroke={COLORS[key]} strokeWidth="9" strokeLinecap="round"
          initial={{ strokeDasharray: `0 ${circumference.toFixed(1)}` }} animate={{ strokeDasharray: `${(arc * value / 4).toFixed(1)} ${circumference.toFixed(1)}` }}
          transition={{ duration: reduced ? 0 : 1.2, ease: EASE }} transform="rotate(135 150 150)" />
        {/* Plain CSS rotation pivoted on the ring centre: Motion pivots SVG groups on their own bounding box. */}
        <g className="tip" style={{ color: COLORS[key], transformBox: 'view-box', transformOrigin: '150px 150px',
          transform: `rotate(${135 + 270 * value / 4}deg)`, transition: reduced ? 'none' : undefined }}>
          <circle cx={150 + radius} cy="150" r="2.6" fill="#fff" /></g></g>;
    })}
  </svg><div className="center"><div className="mono"><NumberValue value={face?.stress} format={v => v.toFixed(1)} /></div><div className="lab sm">stress / 4</div></div></div>;
}
