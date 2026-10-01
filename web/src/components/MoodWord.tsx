import { useEffect, useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { capitalise, EASE } from '../lib/presentation';
export function MoodWord({ word }: { word: string }) {
  const reduced = useReducedMotion();
  const [shown, setShown] = useState(word), [exiting, setExiting] = useState(false);
  useEffect(() => {
    if (word === shown) return;
    if (reduced) { setShown(word); setExiting(false); return; }
    setExiting(true);
    // The original replaces the old letters after 300 ms, even while they exit.
    const timer = setTimeout(() => { setShown(word); setExiting(false); }, 300);
    return () => clearTimeout(timer);
  }, [word, shown, reduced]);
  return <div className="mood serif">{[...capitalise(shown)].map((character, i) => <motion.span key={`${shown}-${i}`} style={{ animation: 'none' }}
    initial={reduced ? false : { opacity: 0, y: '.25em', rotate: 4, filter: 'blur(10px)' }}
    animate={exiting ? { opacity: 0, y: '-.2em', rotate: 0, filter: 'blur(8px)' } : { opacity: 1, y: 0, rotate: 0, filter: 'blur(0px)' }}
    transition={{ duration: reduced ? 0 : exiting ? .35 : .7, delay: reduced ? 0 : i * (exiting ? .018 : .038), ease: exiting ? 'easeIn' : EASE }}>
    {character === ' ' ? '\u00a0' : character}</motion.span>)}</div>;
}
