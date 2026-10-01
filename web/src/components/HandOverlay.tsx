import { useMotionPreference } from '../hooks/useMotionPreference';
import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import type { Hand, MirrorView } from '../api/types';
import { mirrorPoint } from '../lib/v2';
const chains = [[0, 1, 2, 3, 4], [0, 5, 6, 7, 8], [5, 9, 10, 11, 12], [9, 13, 14, 15, 16], [13, 17, 18, 19, 20], [0, 17]];
export function HandOverlay({ hands, view, visible }: { hands?: Hand[]; view?: MirrorView; visible: boolean }) {
  const ref = useRef<SVGSVGElement>(null);
  const reduced = useMotionPreference();
  const [size, setSize] = useState({ width: 0, height: 0 });
  useEffect(() => {
    if (!ref.current) return;
    const observer = new ResizeObserver(([entry]) => setSize({ width: entry.contentRect.width, height: entry.contentRect.height }));
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);
  return <svg ref={ref} className="hand-overlay" viewBox={`0 0 ${size.width || 1} ${size.height || 1}`} aria-hidden="true">
    <AnimatePresence>{visible && view && size.width > 0 && hands?.map(hand => {
      const points = hand.landmarks.map(point => mirrorPoint(point, view, size.width, size.height));
      const color = hand.handedness === 'Right' ? 'var(--mint)' : 'var(--ice)';
      return <motion.g key={hand.handedness} initial={{ opacity: 0 }} animate={{ opacity: .9 }} exit={{ opacity: 0 }}
        transition={{ duration: reduced ? 0 : .35 }} style={{ color, filter: 'drop-shadow(0 0 4px currentColor)' }}>
        {chains.map((chain, i) => <polyline key={i} points={chain.map(index => points[index]?.join(',')).join(' ')}
          fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />)}
        {points.map(([x, y], i) => <circle key={i} cx={x} cy={y} r={i === 0 ? 2.8 : 2} fill={color} />)}
      </motion.g>;
    })}</AnimatePresence>
  </svg>;
}
