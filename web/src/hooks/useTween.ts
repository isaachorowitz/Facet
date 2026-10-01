import { useEffect, useRef, useState } from 'react';
import { animate, useReducedMotion } from 'motion/react';
export function useTween(target: number | null | undefined, duration = 900) {
  const reduced = useReducedMotion();
  const normalized = target == null || !Number.isFinite(target) ? null : target;
  const previous = useRef(normalized);
  const [value, setValue] = useState(normalized);
  useEffect(() => {
    const from = previous.current ?? normalized;
    previous.current = normalized;
    if (normalized === null || from === null || reduced || from === normalized) {
      setValue(normalized);
      return;
    }
    const animation = animate(from, normalized, { duration: duration / 1000,
      ease: t => 1 - Math.pow(1 - t, 4), onUpdate: setValue });
    return () => animation.stop();
  }, [normalized, duration, reduced]);
  return value;
}
