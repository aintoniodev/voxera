// voxera design tokens + demo data (real numbers from this project)
export const C = {
  bg: "#0d0d12",
  card: "#17171c",
  card2: "#1a1a1e",
  border: "#26262e",
  accent: "#7c5cff",
  good: "#35d0a5",
  text: "#e8e8ee",
  muted: "#8a8a96",
  a: "#7ab8ff",
  b: "#ffb35c",
  mono: 'ui-monospace, "Cascadia Code", Consolas, monospace',
  sans: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
};

export const METRICS: Array<[string, string]> = [
  ["SNR", "27.9 dB"],
  ["LUFS-I", "-27.0"],
  ["RT60", "0.79 s"],
  ["Speech", "72%"],
  ["Clicks", "9"],
];

export const STAGES = [
  "DC removal",
  "High-pass 70 Hz",
  "Vocal EQ",
  "De-esser",
  "Compressor 2.5:1",
  "Limiter -1 dBTP",
  "Loudness → -14 LUFS",
];

export const SCORE_DIMS: Array<[string, number]> = [
  ["Noise", 100],
  ["Loudness", 99],
  ["Dynamics", 87],
  ["Room", 58],
  ["Clarity", 12],
];
export const SCORE_BEFORE = 48;
export const SCORE_AFTER = 70;

// deterministic pseudo waveform (same seed as the app icon)
export function waveHeights(n: number, seed = 1.7, spread = 0.9): number[] {
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    out.push(
      0.18 +
        0.6 * Math.abs(Math.sin(i * seed)) * (0.55 + 0.45 * Math.sin(i * 0.9 + spread)),
    );
  }
  return out;
}
