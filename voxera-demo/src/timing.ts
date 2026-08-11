// Single source of truth for the demo timing (seconds; fps = 30).
// Voice durations are MEASURED from the generated piper wavs (voice-first rule).

export const W = 1920;
export const H = 1080;
export const FPS = 30;

// measured voice durations (piper es_ES-davefx-medium)
export const VOICE_S = { s1: 4.09, s2: 5.54, s3: 5.47, s4: 4.78, s5: 4.93, s6: 2.87 };

export const SCENES = {
  s1: { start: 0.0, dur: 5.5 },   // hook + before teaser
  s2: { start: 5.5, dur: 7.0 },   // analyze
  s3: { start: 12.5, dur: 7.0 },  // pipeline
  s4: { start: 19.5, dur: 9.0 },  // A/B player (hero)
  s5: { start: 28.5, dur: 6.0 },  // score
  s6: { start: 34.5, dur: 6.0 },  // CTA
};
export const TOTAL_S = 40.5;
export const TOTAL_FRAMES = Math.round(TOTAL_S * FPS);

// audible samples inside scenes
export const S1_TEASER = { start: 0.15, dur: 3.0, volume: 0.4 };
export const AB = { beforeStart: 20.4, beforeDur: 3.6, afterStart: 24.3, afterDur: 3.8 };

export const f = (s: number) => Math.round(s * FPS);
export const VOICE_OFFSET = 0.35; // voice starts this many seconds into its scene
