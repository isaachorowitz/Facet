import type { Caption, FocusSession, GestureEvent, Mark, MirrorView } from '../api/types';

// The crop is an unmirrored 720×600 image, centre-cropped again by object-fit: cover.
export function mirrorPoint(point: [number, number], view: MirrorView, width: number, height: number, imageWidth = 720, imageHeight = 600): [number, number] {
  const scale = Math.max(width / imageWidth, height / imageHeight);
  const w = imageWidth * scale, h = imageHeight * scale;
  return [width - ((point[0] - view.x) / view.w * w + (width - w) / 2),
    (point[1] - view.y) / view.h * h + (height - h) / 2];
}
export const freshCaption = (caption: Caption | null | undefined, now: number) =>
  !!caption?.text.trim() && now >= caption.ts && now - caption.ts < 40;
export const focusRemaining = (session: FocusSession | null | undefined, now: number) =>
  session ? Math.max(0, session.ends - now) : 0;
export function mergeMarks(...lists: Mark[][]): Mark[] {
  const unique = new Map(lists.flat().map(mark => [`${mark.ts}:${mark.kind}`, mark]));
  return [...unique.values()].sort((a, b) => a.ts - b.ts);
}
export const MARK_LABELS = { good: 'Good moment', rough: 'Rough moment', win: 'Win' };
export const MARK_GESTURES = { good: 'Thumb_Up', rough: 'Thumb_Down', win: 'Victory' } as const;
export function gestureLabel(event: GestureEvent, focus: FocusSession | null, transition?: 'started' | 'ended') {
  switch (event.action) {
    case 'mark_good': return 'Good moment marked';
    case 'mark_rough': return 'Rough moment marked';
    case 'mark_win': return 'Win marked';
    case 'toggle_focus': return `Focus ${transition ?? (focus && Math.abs(focus.started - event.ts) < 5 ? 'started' : focus ? 'ended' : 'started')}`;
    case 'hello': return 'Hey!';
    default: return ({ None: 'Hand in view', Closed_Fist: 'A little resolve', Open_Palm: 'Hello there',
      Pointing_Up: 'Looking up', Thumb_Down: 'Thumbs down', Thumb_Up: 'Thumbs up', Victory: 'Victory', ILoveYou: 'Love you', Wave: 'Hey!' })[event.gesture];
  }
}
