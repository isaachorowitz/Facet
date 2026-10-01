import { useLayoutEffect, useRef } from 'react';
import { animate, useReducedMotion } from 'motion/react';
import { EASE } from '../lib/presentation';
export function ChartLine({ d, color, width, opacity, delay }: {
  d: string; color: string; width: number; opacity: number; delay: number;
}) {
  const path = useRef<SVGPathElement>(null);
  const reduced = useReducedMotion();
  useLayoutEffect(() => {
    if (!path.current || reduced) return;
    // Preserve the original measured dash geometry, including its initial blank phase.
    const length = path.current.getTotalLength() * 2 + 50;
    path.current.style.strokeDasharray = String(length);
    const animation = animate(path.current, { strokeDashoffset: [length, 0] }, { duration: 1.8, delay, ease: EASE });
    return () => animation.stop();
  }, [reduced, delay]);
  return <path ref={path} d={d} fill="none" stroke={color} strokeWidth={width} strokeLinejoin="round" strokeLinecap="round"
    vectorEffect="non-scaling-stroke" opacity={opacity} />;
}
