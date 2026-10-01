import { useEffect, useRef, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import { useTween } from '../hooks/useTween';
import { motion, useReducedMotion } from 'motion/react';
import { EASE } from '../lib/presentation';

export function NumberValue({ value, format = Math.round, duration = 900 }: {
  value: number | null | undefined; format?: (v: number) => string | number; duration?: number;
}) {
  const current = useTween(value, duration);
  return <>{current === null ? '–' : format(current)}</>;
}
export const entrance = (i: number) => ({ '--i': i }) as CSSProperties;
export function Card({ children, className = '', index }: { children: ReactNode; className?: string; index: number }) {
  return <section className={`card ${className} enter`} style={entrance(index)}>{children}</section>;
}
export function Bar({ width, color, tick, shine = true }: { width: number; color: string; tick?: number; shine?: boolean }) {
  const previous = useRef(width);
  const [flash, setFlash] = useState(false);
  useEffect(() => {
    if (shine && Math.abs(previous.current - width) > 6) setFlash(true);
    previous.current = width;
  }, [width, shine]);
  return <div className="track"><div className={`fill${flash ? ' shine' : ''}`} style={{ width: `${width}%`, background: color }}
    onAnimationEnd={() => setFlash(false)} />{tick !== undefined && <div className="tick" style={{ left: `${tick}%` }} />}</div>;
}
export function FlagChip({ label, value, hot = false }: { label: string; value: number | undefined; hot?: boolean }) {
  const active = value !== undefined && value > .5;
  const [pop, setPop] = useState(false);
  const prev = useRef(false);
  useEffect(() => { if (active && !prev.current) setPop(true); prev.current = active; }, [active]);
  return <span className={`chip ${active ? hot ? 'hot' : 'on' : ''} ${pop ? 'pop' : ''}`} onAnimationEnd={() => setPop(false)}>
    {label} <span className="mono">{value === undefined ? '–' : `${Math.round(value * 100)}%`}</span></span>;
}
export function FadeText({ text, className, style }: { text: string; className?: string; style?: CSSProperties }) {
  const reduced = useReducedMotion();
  const [shown, setShown] = useState(text), [opacity, setOpacity] = useState(1);
  useEffect(() => {
    if (text === shown) return;
    if (reduced) { setShown(text); setOpacity(1); return; }
    setOpacity(0);
    const timer = setTimeout(() => { setShown(text); setOpacity(1); }, 300);
    return () => clearTimeout(timer);
  }, [text, shown, reduced]);
  return <motion.span className={className} style={style} animate={{ opacity }}
    transition={{ duration: reduced ? 0 : .4, ease: EASE }}>{shown}</motion.span>;
}
export function Icon({ name }: { name: 'calibrate' | 'mic' | 'nudge' | 'pause' | 'resume' | 'camera' | 'calendar' }) {
  if (name === 'pause' || name === 'resume') return <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    {name === 'resume' ? <path d="M7 5l12 7-12 7z" /> : <><rect x="6" y="5" width="4" height="14" rx="1" /><rect x="14" y="5" width="4" height="14" rx="1" /></>}</svg>;
  return <svg width={name === 'camera' ? 22 : name === 'calendar' ? 13 : 15} height={name === 'camera' ? 22 : name === 'calendar' ? 13 : 15}
    viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
    {name === 'calibrate' && <><circle cx="12" cy="12" r="9" /><path d="M9 10h.01M15 10h.01M9 15h6" /></>}
    {name === 'mic' && <><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></>}
    {name === 'nudge' && <><path d="M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15z" /><path d="M10 20.5a2 2 0 0 0 4 0" /></>}
    {name === 'camera' && <><path d="M3 8a2 2 0 0 1 2-2h2l2-2h6l2 2h2a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><circle cx="12" cy="13" r="3.5" /></>}
    {name === 'calendar' && <><rect x="4" y="5" width="16" height="15" rx="2" /><path d="M4 10h16M9 3v4M15 3v4" /></>}
  </svg>;
}
