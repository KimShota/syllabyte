import type { PlaybackInterval, PlaybackSnapshot } from "../learning";

export function mergeIntervals(intervals: PlaybackInterval[]): PlaybackInterval[] {
  const merged: PlaybackInterval[] = [];
  for (const [start, end] of [...intervals].sort((a, b) => a[0] - b[0])) {
    const last = merged[merged.length - 1];
    if (last && start <= last[1]) last[1] = Math.max(last[1], end);
    else merged.push([start, end]);
  }
  return merged;
}
export const coveredSeconds = (intervals: PlaybackInterval[]) => mergeIntervals(intervals).reduce((n, [a, b]) => n + b - a, 0);

/** Samples use a monotonic clock. Discontinuities and unknown gaps never become exposure. */
export class PlaybackMeter {
  private previous: { position: number; at: number; rate: number } | null = null;
  private intervals: PlaybackInterval[] = [];
  private elapsed = 0;
  private exposure = 0;
  private position = 0;
  private sequence = 0;
  constructor(private duration: number, private source: PlaybackSnapshot["source"]) {}

  boundary() { this.previous = null; }

  sample(position: number, at: number, running: boolean, rate: number) {
    if (!Number.isFinite(position) || !Number.isFinite(at) || !Number.isFinite(rate) || rate <= 0) {
      this.boundary();
      return;
    }
    position = Math.max(0, Math.min(this.duration, position));
    this.position = position;
    const previous = this.previous;
    this.previous = running ? { position, at, rate } : null;
    if (!running || !previous || previous.rate !== rate) return;
    const wall = (at - previous.at) / 1000;
    const content = position - previous.position;
    // Up to 1.5s between callbacks; tolerate native timestamp jitter, never a seek or suspension.
    if (wall <= 0 || wall > 1.5 || content <= 0 || content > wall * rate + 0.2) return;
    this.intervals = mergeIntervals([...this.intervals, [previous.position, position]]);
    this.elapsed += Math.min(wall, content / rate);
    this.exposure += content;
    this.sequence += 1;
  }

  snapshot(): PlaybackSnapshot {
    return {
      sequence: this.sequence, intervals: this.intervals.map(([a, b]) => [a, b]),
      elapsed_s: this.elapsed, exposure_s: this.exposure, position_s: this.position,
      duration_s: this.duration, source: this.source,
    };
  }
}
