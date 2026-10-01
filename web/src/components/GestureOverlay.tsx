import { useMotionPreference } from '../hooks/useMotionPreference';
import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import type { FocusSession, GestureEvent } from '../api/types';
import { gestureLabel } from '../lib/v2';
import { GestureIcon } from './GestureIcon';
export type GestureEntry = { id: number; data: GestureEvent };
export function GestureOverlay({ event, focus, transition }: {
  event: GestureEntry | null; focus: FocusSession | null; transition?: 'started' | 'ended';
}) {
  const reduced = useMotionPreference();
  const [shown, setShown] = useState<GestureEntry | null>(null);
  useEffect(() => {
    if (!event) return;
    setShown(event);
    const timer = window.setTimeout(() => setShown(null), 2600);
    return () => window.clearTimeout(timer);
  }, [event]);
  return <div className="gesture-layer" role="status" aria-live="polite"><AnimatePresence>
    {shown && <motion.div key={shown.id} className={`gesture-celebration${shown.data.action === 'mark_rough' ? ' rough' : ''}`}
      initial={{ opacity: 0, y: reduced ? 0 : 35, scale: reduced ? 1 : .65 }} animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: reduced ? 0 : -65, scale: reduced ? 1 : 1.06 }}
      transition={reduced ? { duration: 0 } : { type: 'spring', stiffness: 200, damping: 18, opacity: { duration: .35 } }}>
      <div className="gesture-medallion">
        {!reduced && <motion.span className="gesture-burst" initial={{ scale: .45, opacity: .8 }} animate={{ scale: 1.75, opacity: 0 }} transition={{ duration: 1.1, ease: 'easeOut' }} />}
        <GestureIcon gesture={shown.data.gesture} />
      </div><span className="gesture-label">{gestureLabel(shown.data, focus, transition)}</span>
    </motion.div>}
  </AnimatePresence></div>;
}
