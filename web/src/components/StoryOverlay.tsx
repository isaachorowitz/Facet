import { useMotionPreference } from '../hooks/useMotionPreference';
import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { motion } from 'motion/react';
import { getRecap, regenerateRecap } from '../api/client';
import type { Recap } from '../api/types';
import { EASE, hhmm } from '../lib/presentation';
import { WordReveal } from './WordReveal';
export function StoryOverlay({ date, onClose }: { date: string; onClose: () => void }) {
  const reduced = useMotionPreference(), dialog = useRef<HTMLDivElement>(null);
  const generation = useRef(0);
  const [recap, setRecap] = useState<Recap | null>(null), [busy, setBusy] = useState(true), [error, setError] = useState('');
  const load = useCallback(async (regenerate: boolean) => {
    const id = ++generation.current;
    setBusy(true); setError('');
    try {
      const result = await (regenerate ? regenerateRecap(date) : getRecap(date));
      if (id === generation.current) setRecap(result);
    } catch {
      if (id === generation.current) setError(regenerate ? 'The narrator could not regenerate your story. Try again.' : 'Your story is not available yet. The narrator may still be warming up.');
    } finally { if (id === generation.current) setBusy(false); }
  }, [date]);
  useEffect(() => { void load(false); return () => { generation.current++; }; }, [load]);
  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const app = document.getElementById('app'), wasInert = app?.inert ?? false;
    if (app) app.inert = true;
    dialog.current?.focus({ preventScroll: true });
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); onClose(); }
      if (event.key !== 'Tab') return;
      const buttons = [...(dialog.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? [])];
      const first = buttons[0], last = buttons[buttons.length - 1];
      if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && (document.activeElement === last || document.activeElement === dialog.current)) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener('keydown', key);
    return () => { document.removeEventListener('keydown', key); if (app) app.inert = wasInert; previous?.focus({ preventScroll: true }); };
  }, [onClose]);
  const titleDate = new Date(`${date}T12:00:00`).toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' });
  return createPortal(<motion.div className="story-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
    transition={{ duration: reduced ? 0 : .3 }} onClick={event => { if (event.target === event.currentTarget) onClose(); }}>
    <motion.div className="story-dialog" ref={dialog} role="dialog" aria-modal="true" aria-labelledby="story-title" tabIndex={-1}
      initial={{ y: reduced ? 0 : 24, scale: reduced ? 1 : .97 }} animate={{ y: 0, scale: 1 }} exit={{ y: reduced ? 0 : 12, opacity: 0 }} transition={{ duration: reduced ? 0 : .45, ease: EASE }}>
      <div className="story-top"><span className="lab">A day, reflected</span><button className="story-close" type="button" aria-label="Close story" onClick={onClose}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="m6 6 12 12M18 6 6 18" /></svg></button></div>
      <h1 id="story-title" className="serif">The story of your day.</h1><div className="story-date">{titleDate}</div>
      <div className="story-body" aria-busy={busy}>{recap?.text ? <p key={`${recap.generated_at ?? ''}:${recap.text}`}><WordReveal text={recap.text} pace={65} /></p> :
        <p className="story-empty">{busy ? 'Gathering the small moments…' : error || 'A story is waiting to be told. Ask the narrator to gather your moments.'}</p>}</div>
      {error && recap?.text && <p className="story-error" role="status">{error}</p>}
      <div className="story-footer"><span className="note">{busy ? 'Narrator · reflecting' : recap?.generated_at ? `Narrator · ${hhmm(recap.generated_at)}` : 'Narrator · on device'}</span>
        <button className="btn" type="button" disabled={busy} onClick={() => void load(true)}>{busy ? 'Reflecting…' : 'Regenerate'}</button></div>
    </motion.div>
  </motion.div>, document.body);
}
