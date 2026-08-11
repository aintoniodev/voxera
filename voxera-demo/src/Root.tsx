import React from "react";
import { Composition } from "remotion";
import { Demo } from "./Demo";
import { FPS, H, TOTAL_FRAMES, W } from "./timing";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="voxera-demo"
      component={Demo}
      durationInFrames={TOTAL_FRAMES}
      fps={FPS}
      width={W}
      height={H}
    />
  );
};
