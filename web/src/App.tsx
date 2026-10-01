import { useCallback, useEffect, useState } from 'react';
import { useMotionPreference } from './hooks/useMotionPreference';
import { MotionConfig } from 'motion/react';
import { useFacetSocket } from './hooks/useFacetSocket';
import { useDayData } from './hooks/useDayData';
import { useInterval } from './hooks/useInterval';
import { focusRemaining } from './lib/v2';
import { useSpotlight } from './hooks/useSpotlight';
import { Background } from './components/Background';
import { Header } from './components/Header';
import { Mirror } from './components/Mirror';
import { MeasuredFace } from './components/MeasuredFace';
import { NowCard } from './components/NowCard';
import { OverallCard } from './components/OverallCard';
import { PostureCard } from './components/PostureCard';
import { VoiceCard } from './components/VoiceCard';
import { DayChart } from './components/DayChart';
import { Toast } from './components/Toast';
import type { ToastMessage } from './components/Toast';
export function App() {
  const reduced = useMotionPreference();
  const facet = useFacetSocket(), day = useDayData();
  const [now, setNow] = useState(() => Date.now() / 1000);
  useInterval(() => setNow(Date.now() / 1000), 1000);
  const focusing = focusRemaining(facet.focusSession, now) > 0;
  const [message, setMessage] = useState<ToastMessage | null>(null);
  const toast = useCallback((text: string) => setMessage(m => ({ id: (m?.id ?? 0) + 1, text })), []);
  const latestEvent = facet.events[facet.events.length - 1];
  useEffect(() => {
    if (latestEvent) toast(latestEvent.event.type === 'calibrated' ? 'Calibrated. Your face and posture now compare against this.' : latestEvent.event.data.text);
  }, [latestEvent, toast]);
  useEffect(() => { if (facet.error) toast(facet.error); }, [facet.error, toast]);
  useEffect(() => { if (day.error) toast(day.error); }, [day.error, toast]);
  useSpotlight();
  return <MotionConfig reducedMotion={reduced ? 'always' : 'user'}><Background /><div id="app" className={`${facet.status?.paused ? 'paused' : ''}${focusing ? ' focusing' : ''}`}>
    <Header status={facet.status} live={facet.live} timing={facet.timing} onError={toast} focus={facet.focusSession} onFocus={facet.setFocusSession} />
    <div className="cols"><div className="col" style={{ gridTemplateRows: 'minmax(0, 1fr) auto' }}>
      <Mirror status={facet.status} live={facet.live} videoSession={facet.videoSession} gesture={facet.gesture} faceTouch={facet.faceTouch} focus={facet.focusSession} focusEvent={facet.focusEvent} /><MeasuredFace status={facet.status} live={facet.live} />
    </div><NowCard face={facet.face} zScores={facet.faceZScores} caption={facet.caption} focusing={focusing} /><div className="col right">
      <OverallCard overall={facet.overall} /><PostureCard posture={facet.live?.posture ?? null} summary={day.summary} />
      <VoiceCard status={facet.status} live={facet.live} speech={facet.speech} />
    </div></div><DayChart day={day} recent={facet.liveSeries} marks={facet.marks} />
  </div><Toast message={message} /></MotionConfig>;
}
