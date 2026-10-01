import type { Posture } from '../api/types';
export type FigurePoints = Posture['skeleton'];
export type PointName = keyof FigurePoints;
export function figurePoints(posture: Posture): FigurePoints | null {
  const k = posture.skeleton;
  if ((!posture.visible && !posture.stale) || !k.l_sh || !k.r_sh) return null;
  const mx = (k.l_sh[0] + k.r_sh[0]) / 2, my = (k.l_sh[1] + k.r_sh[1]) / 2;
  const shoulderWidth = Math.hypot(k.l_sh[0] - k.r_sh[0], k.l_sh[1] - k.r_sh[1]) || .3;
  const scale = 96 / shoulderWidth, out: FigurePoints = {};
  for (const name of Object.keys(k) as PointName[]) {
    const point = k[name];
    if (point) out[name] = [-(point[0] - mx) * scale, (point[1] - my) * scale, point[2]];
  }
  return out;
}
