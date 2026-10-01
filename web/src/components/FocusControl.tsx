import { useState } from 'react';
import type { FocusSession } from '../api/types';
import { toggleFocus } from '../api/client';
import { useInterval } from '../hooks/useInterval';
import { clamp } from '../lib/presentation';
import { focusRemaining } from '../lib/v2';
export function FocusControl({ session, onSession, onError }: {
  session: FocusSession | null; onSession: (session: FocusSession | null) => void; onError: (text: string) => void;
}) {
  const [now, setNow] = useState(() => Date.now() / 1000), [busy, setBusy] = useState(false);
  useInterval(() => setNow(Date.now() / 1000), 1000);
  const seconds = focusRemaining(session, Math.max(now, Date.now() / 1000)), active = seconds > 0;
  const fraction = session ? clamp(seconds / Math.max(1, session.ends - session.started), 0, 1) : 1;
  return <button type="button" className={`btn focus-control${active ? ' active' : ''}`} disabled={busy}
    title={active ? 'End this focus session' : 'Start a 25 minute focus session'} aria-label={active ? `End focus, ${Math.ceil(seconds / 60)} minutes left` : 'Focus 25'}
    onClick={async () => {
      if (busy) return;
      setBusy(true);
      try { onSession(await toggleFocus()); }
      catch { onError('Focus is unavailable. Your session was not changed.'); }
      finally { setBusy(false); }
    }}>
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" opacity=".18" strokeWidth="1.5" />
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeDasharray={Math.PI * 18}
        strokeDashoffset={Math.PI * 18 * (1 - fraction)} transform="rotate(-90 12 12)" />
      {active ? <circle cx="12" cy="12" r="2" fill="currentColor" /> : <path d="M12 7v5l3 2" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />}
    </svg><span>{busy ? 'Connecting…' : active ? <>Focus <b className="mono">{Math.ceil(seconds / 60)}</b><small>min left</small></> : 'Focus 25'}</span>
  </button>;
}
