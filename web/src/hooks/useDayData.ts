import { useCallback, useEffect, useRef, useState } from 'react';
import { getMarks, getSummary, getTimeline } from '../api/client';
import type { Summary, Timeline, Mark } from '../api/types';
import { mergeMarks } from '../lib/v2';
import { todayString } from '../lib/presentation';
import { useInterval } from './useInterval';
export type ChartView = 'day' | 'live';
export function useDayData() {
  const [date, setDate] = useState(todayString);
  const [view, setView] = useState<ChartView>('day');
  const [data, setData] = useState<{ timeline: Timeline | null; summary: Summary | null; marks: Mark[]; drawVersion: number; error: string | null }>({
    timeline: null, summary: null, marks: [], drawVersion: 0, error: null,
  });
  const generation = useRef(0), firstLoad = useRef(true);
  const load = useCallback(async (animate: boolean) => {
    const requestId = ++generation.current;
    try {
      const [timeline, summary, marks] = await Promise.all([getTimeline(date), getSummary(date), getMarks(date).catch(() => [])]);
      if (requestId === generation.current) setData(d => ({ timeline, summary, marks: mergeMarks(summary.marks ?? [], marks),
        drawVersion: d.drawVersion + (animate ? 1 : 0), error: null }));
    } catch {
      if (requestId === generation.current) setData(d => ({ ...d, error: 'Could not load the selected day.' }));
    }
  }, [date]);
  useEffect(() => {
    const delay = firstLoad.current ? 700 : 0;
    firstLoad.current = false;
    const timer = setTimeout(() => { void load(true); }, delay);
    return () => { clearTimeout(timer); generation.current++; };
  }, [load]);
  useInterval(() => { if (date === todayString() && view === 'day') void load(false); }, 60000);
  const today = () => { setView('day'); if (date === todayString()) void load(true); else setDate(todayString()); };
  const showLive = () => { setView('live'); setData(d => ({ ...d, drawVersion: d.drawVersion + 1 })); };
  const pick = (next: string) => { if (next) { setView('day'); setDate(next); } };
  return { ...data, date, view, showLive, today, pick };
}
