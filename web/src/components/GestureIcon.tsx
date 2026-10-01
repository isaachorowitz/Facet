import type { Hand } from '../api/types';

// Hand-drawn line art shared by the mirror celebrations and day markers.
export function GestureIcon({ gesture, size = 80 }: { gesture: Hand['gesture']; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 80 80" fill="none" stroke="currentColor" strokeWidth="2.4"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {(gesture === 'Thumb_Up' || gesture === 'Thumb_Down') ? <g transform={gesture === 'Thumb_Down' ? 'translate(0 80) scale(1 -1)' : undefined}>
      <path d="M25 37c8-5 14-15 15-24 1-5 7-5 9-1 3 7 0 15-3 22h16c5 0 7 4 6 8l-5 20c-1 5-5 8-10 8H38c-5 0-9-2-13-5M13 36h12v34H13z" />
      <path d="M46 34h-6M63 47h-8M60 57h-7" opacity=".45" />
    </g> : gesture === 'Victory' ? <>
      <path d="M29 45 19 17c-2-6 5-9 8-4l13 25 8-28c2-6 10-4 9 2l-6 31M29 45c-6-6-12-1-9 6l8 16c4 7 22 9 29 0 5-7 6-16 5-23-1-5-8-6-10-1-1-5-8-6-11-1" />
      <path d="m29 45 12 11c4 4 1 9-4 7l-8-6M42 43v8M52 43v9" />
    </> : gesture === 'Pointing_Up' ? <>
      <path d="M30 43V12c0-7 9-7 9 0v25c2-6 10-6 11 0 3-5 10-3 10 3 4-3 10 0 9 6l-3 17c-2 9-9 12-19 12-9 0-14-4-18-11L18 46c-4-7 3-13 8-7l11 14" />
      <path d="M39 37v14M50 37v15M60 41v12M24 17l-5 3M46 17l5 3" opacity=".5" />
    </> : gesture === 'ILoveYou' ? <>
      <path d="M27 44V14c0-6 9-6 9 0v27c1-7 10-7 10 0 1-6 9-6 10 0V20c0-6 9-6 9 0v37c0 12-7 17-20 17-10 0-16-5-20-13L14 43c-4-7 3-12 8-6l10 12" />
      <path d="M36 43v10M46 42v10M56 43v10M30 62c7-6 13-6 18-2" opacity=".5" />
    </> : gesture === 'Closed_Fist' ? <>
      <path d="M20 45V33c0-8 10-8 10 0 0-10 11-10 11 0 0-9 11-9 11 0 1-8 11-6 11 1v23c0 12-8 17-20 17S21 66 19 55c-3-11 7-14 12-7l9 9" />
      <path d="M30 33v12M41 33v14M52 33v14" opacity=".5" />
    </> : <>
      <path d="M23 45V22c0-6 8-6 8 0v19V12c0-6 9-6 9 0v28V9c0-6 9-6 9 0v32V17c0-6 9-6 9 0v34l5-13c3-7 10-4 8 3l-6 20c-3 10-9 14-21 14-10 0-16-6-20-14L14 45c-4-7 3-12 8-6l9 13" />
      <path d="M32 59c6-5 13-5 19-1" opacity=".5" />
      {gesture === 'Wave' && <path d="M9 16c-5 5-6 13-3 19M66 8c6 4 9 10 9 17" opacity=".65" />}
    </>}
  </svg>;
}
