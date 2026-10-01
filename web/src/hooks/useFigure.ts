import { useEffect, useMemo, useRef, useState } from 'react';
import { useReducedMotion } from 'motion/react';
import type { Posture } from '../api/types';
import { figurePoints } from '../lib/figure';
import type { FigurePoints, PointName } from '../lib/figure';
export function useFigure(posture: Posture | null) {
  const reduced = useReducedMotion();
  const target = useMemo(() => posture ? figurePoints(posture) : null, [posture]);
  const targetRef = useRef(target), current = useRef<FigurePoints | null>(null);
  const [points, setPoints] = useState<FigurePoints | null>(null);
  useEffect(() => {
    targetRef.current = target;
    if (!target || reduced) { current.current = target; setPoints(target); }
  }, [target, reduced]);
  useEffect(() => {
    if (reduced) return;
    let frame = 0, timer: ReturnType<typeof setTimeout>;
    const draw = () => {
      if (targetRef.current) {
        const next: FigurePoints = { ...current.current };
        for (const name of Object.keys(targetRef.current) as PointName[]) {
          const t = targetRef.current[name];
          if (!t) continue;
          const c = current.current?.[name] ?? t;
          next[name] = [c[0] + (t[0] - c[0]) * .18, c[1] + (t[1] - c[1]) * .18, t[2]];
        }
        current.current = next; setPoints(next);
      }
      timer = setTimeout(() => { frame = requestAnimationFrame(draw); }, 33);
    };
    draw();
    return () => { clearTimeout(timer); cancelAnimationFrame(frame); };
  }, [reduced]);
  return points;
}
