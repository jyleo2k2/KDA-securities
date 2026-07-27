export const SWIPE_THRESHOLD_PX = 42;

export function normalizeIndex(index: number, length: number): number {
  return ((index % length) + length) % length;
}

export function shortestOffset(index: number, activeIndex: number, length: number): number {
  const direct = index - activeIndex;
  const wrapped = direct > 0 ? direct - length : direct + length;
  return Math.abs(direct) <= Math.abs(wrapped) ? direct : wrapped;
}

export interface FanCardStyle {
  x: string;
  y: string;
  rotation: string;
  scale: string;
  opacity: string;
  z: number;
}

export function cardStyle(offset: number): FanCardStyle {
  const distance = Math.abs(offset);
  const visible = Math.min(distance, 3);
  return {
    x: `${offset * 100}px`,
    y: `${visible * 30}px`,
    rotation: `${offset * 10}deg`,
    scale: String(Math.max(0.6, 1 - visible * 0.3)),
    opacity: distance > 2 ? "0" : String(Math.max(0.55, 1 - distance * 0.12)),
    z: Math.max(0, 20 - distance),
  };
}
