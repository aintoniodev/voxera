import React from "react";
import { AbsoluteFill, Audio, Sequence, staticFile } from "remotion";
import { AB, FPS, f, SCENES, S1_TEASER, TOTAL_FRAMES, VOICE_OFFSET } from "./timing";
import {
  AnalyzeScene,
  ABScene,
  CTAScene,
  EnhanceScene,
  HookScene,
  ScoreScene,
} from "./ui/scenes";

const scenes: Array<{ id: string; start: number; dur: number; Comp: React.FC }> = [
  { id: "s1", start: SCENES.s1.start, dur: SCENES.s1.dur, Comp: HookScene },
  { id: "s2", start: SCENES.s2.start, dur: SCENES.s2.dur, Comp: AnalyzeScene },
  { id: "s3", start: SCENES.s3.start, dur: SCENES.s3.dur, Comp: EnhanceScene },
  { id: "s4", start: SCENES.s4.start, dur: SCENES.s4.dur, Comp: ABScene },
  { id: "s5", start: SCENES.s5.start, dur: SCENES.s5.dur, Comp: ScoreScene },
  { id: "s6", start: SCENES.s6.start, dur: SCENES.s6.dur, Comp: CTAScene },
];

export const Demo: React.FC = () => {
  return (
    <AbsoluteFill style={{ backgroundColor: "#0d0d12" }}>
      {scenes.map(({ id, start, dur, Comp }) => (
        <Sequence key={id} from={f(start)} durationInFrames={f(dur)}>
          <Comp />
        </Sequence>
      ))}

      {/* voice lines, one per scene */}
      {scenes.map(({ id, start }) => (
        <Sequence key={"vo" + id} from={f(start + VOICE_OFFSET)}>
          <Audio src={staticFile(`audio/vo_${id}.wav`)} />
        </Sequence>
      ))}

      {/* real audio: before teaser in scene 1 */}
      <Sequence from={f(S1_TEASER.start)} durationInFrames={f(S1_TEASER.dur)}>
        <Audio src={staticFile("audio/before.wav")} volume={S1_TEASER.volume} />
      </Sequence>

      {/* real audio: A/B scene — before then after */}
      <Sequence from={f(AB.beforeStart)} durationInFrames={f(AB.beforeDur)}>
        <Audio src={staticFile("audio/before.wav")} volume={0.9} />
      </Sequence>
      <Sequence from={f(AB.afterStart)} durationInFrames={f(AB.afterDur)}>
        <Audio src={staticFile("audio/after.wav")} volume={0.9} />
      </Sequence>
    </AbsoluteFill>
  );
};
