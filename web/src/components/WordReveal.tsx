import { useMotionPreference } from '../hooks/useMotionPreference';
import { useEffect, useState } from 'react';

export function WordReveal({ text, pace = 90 }: { text: string; pace?: number }) {
  const reduced = useMotionPreference();
  const words = text.match(/\S+\s*/g) ?? [];
  const [progress, setProgress] = useState({ text, count: reduced ? words.length : 0 });
  const count = reduced ? words.length : progress.text === text ? progress.count : 0;
  useEffect(() => {
    const total = (text.match(/\S+\s*/g) ?? []).length;
    if (reduced) { setProgress({ text, count: total }); return; }
    let count = 0;
    setProgress({ text, count });
    const timer = window.setInterval(() => {
      count = Math.min(count + 1, total);
      setProgress({ text, count });
      if (count === total) window.clearInterval(timer);
    }, pace);
    return () => window.clearInterval(timer);
  }, [text, pace, reduced]);
  return <><span className="sr-only">{text}</span><span aria-hidden="true">{words.slice(0, count).join('')}{count < words.length && <span className="caret" />}</span></>;
}
