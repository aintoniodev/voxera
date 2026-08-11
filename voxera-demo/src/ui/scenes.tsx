import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { AB, FPS, SCENES } from "../timing";
import {
  C,
  METRICS,
  SCORE_AFTER,
  SCORE_BEFORE,
  SCORE_DIMS,
  STAGES,
  waveHeights,
} from "../theme";

// ---------------------------------------------------------------------------
// shared building blocks
// ---------------------------------------------------------------------------

const ease = (p: number) => 1 - Math.pow(1 - p, 3);
const clamp = (v: number, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v));

export const Fade: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const fIn = 10;
  const fOut = 10;
  const opacity = clamp(
    Math.min(frame / fIn, (durationInFrames - frame) / fOut),
  );
  return <div style={{ opacity, width: "100%", height: "100%" }}>{children}</div>;
};

const Card: React.FC<{ children: React.ReactNode; style?: React.CSSProperties; width?: number }> = ({
  children,
  style,
  width = 1500,
}) => (
  <div
    style={{
      width,
      background: C.card,
      border: `1px solid ${C.border}`,
      borderRadius: 28,
      padding: "46px 56px",
      ...style,
    }}
  >
    {children}
  </div>
);

export const Bars: React.FC<{
  heights: number[];
  color: string;
  width?: number;
  height?: number;
  gap?: number;
  radius?: number;
  alpha?: number;
}> = ({ heights, color, width = 560, height = 120, gap = 5, radius = 5, alpha = 1 }) => {
  const bw = (width - gap * (heights.length - 1)) / heights.length;
  return (
    <div style={{ display: "flex", alignItems: "center", gap, height, width }}>
      {heights.map((h, i) => (
        <div
          key={i}
          style={{
            width: bw,
            height: Math.max(3, h * height),
            background: color,
            opacity: alpha,
            borderRadius: radius,
          }}
        />
      ))}
    </div>
  );
};

export const Logo: React.FC<{ size?: number; showTag?: boolean }> = ({ size = 64, showTag = true }) => (
  <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
    <div
      style={{
        width: size,
        height: size,
        borderRadius: size * 0.24,
        background: C.accent,
        display: "flex",
        alignItems: "flex-end",
        justifyContent: "center",
        paddingBottom: size * 0.14,
        gap: size * 0.06,
      }}
    >
      {[0.35, 0.75, 0.5, 1, 0.6, 0.8, 0.4].map((h, i) => (
        <div key={i} style={{ width: size * 0.08, height: h * size * 0.5, background: "#fff", borderRadius: 3 }} />
      ))}
    </div>
    {showTag && (
      <div style={{ color: C.text, fontFamily: C.sans, fontSize: size * 0.62, fontWeight: 800, letterSpacing: 1 }}>
        voxera
      </div>
    )}
  </div>
);

const Title: React.FC<{ children: React.ReactNode; size?: number }> = ({ children, size = 74 }) => (
  <div style={{ color: C.text, fontFamily: C.sans, fontWeight: 800, fontSize: size, lineHeight: 1.12 }}>
    {children}
  </div>
);

const Sub: React.FC<{ children: React.ReactNode; size?: number }> = ({ children, size = 34 }) => (
  <div style={{ color: C.muted, fontFamily: C.sans, fontSize: size, lineHeight: 1.35, fontWeight: 400 }}>
    {children}
  </div>
);

const Stagger: React.FC<{ i: number; step?: number; children: React.ReactNode }> = ({ i, step = 7, children }) => {
  const frame = useCurrentFrame();
  const p = clamp((frame - i * step) / 10);
  return (
    <div style={{ opacity: p, transform: `translateY(${(1 - ease(p)) * 26}px)` }}>{children}</div>
  );
};

// ---------------------------------------------------------------------------
// scene 1 — hook
// ---------------------------------------------------------------------------
export const HookScene: React.FC = () => {
  const frame = useCurrentFrame();
  const before = waveHeights(34, 1.7, 0.9);
  const after = waveHeights(34, 1.7, 0.9).map((h) => h * 1.45);
  const p = clamp((frame - 30) / 60); // morph to the "after" wave at the end of the scene
  const heights = before.map((h, i) => h + (after[i] - h) * ease(p));
  return (
    <Fade>
      <Absolute>
        <div style={{ position: "absolute", top: 70, left: 90 }}>
          <Logo size={54} />
        </div>
        <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 44 }}>
          <div style={{ textAlign: "center", maxWidth: 1500 }}>
            <Title>Suena a llamada de teléfono.</Title>
            <div style={{ height: 18 }} />
            <Sub size={38}>Y en el vídeo, se nota.</Sub>
          </div>
          <Bars heights={heights} color={C.accent} width={1300} height={170} gap={10} radius={8} alpha={0.9} />
        </div>
      </Absolute>
    </Fade>
  );
};

// ---------------------------------------------------------------------------
// scene 2 — analyze
// ---------------------------------------------------------------------------
export const AnalyzeScene: React.FC = () => {
  return (
    <Fade>
      <Absolute>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 50, height: "100%" }}>
          <div style={{ textAlign: "center" }}>
            <Title size={64}>Primero, lo analiza.</Title>
            <div style={{ height: 14 }} />
            <Sub size={32}>Sin tocar nada. Métricas reales, con confianza.</Sub>
          </div>
          <Card width={1460} style={{ padding: "40px 50px" }}>
            <div style={{ fontFamily: C.mono, color: C.muted, fontSize: 26, marginBottom: 34 }}>
              <span style={{ color: C.good }}>❯</span> voxera analyze test1.wav
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "22px 70px" }}>
              {METRICS.map(([k, v], i) => (
                <Stagger key={k} i={i} step={9}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontFamily: C.mono, fontSize: 34, borderBottom: `1px solid ${C.border}`, paddingBottom: 14 }}>
                    <span style={{ color: C.muted }}>{k}</span>
                    <span style={{ color: C.text, fontWeight: 700 }}>{v}</span>
                  </div>
                </Stagger>
              ))}
            </div>
          </Card>
        </div>
      </Absolute>
    </Fade>
  );
};

// ---------------------------------------------------------------------------
// scene 3 — enhance pipeline
// ---------------------------------------------------------------------------
export const EnhanceScene: React.FC = () => {
  const frame = useCurrentFrame();
  const before = waveHeights(30, 1.7, 0.9);
  const after = waveHeights(30, 1.7, 0.9).map((h) => h * 1.5);
  const p = clamp((frame - 40) / 90);
  const heights = before.map((h, i) => h + (after[i] - h) * ease(p));
  return (
    <Fade>
      <Absolute>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 44, height: "100%" }}>
          <div style={{ textAlign: "center" }}>
            <Title size={64}>Después, la trabaja.</Title>
            <div style={{ height: 14 }} />
            <Sub size={32}>Siete etapas, orden congelado, byte a byte.</Sub>
          </div>
          <div style={{ display: "flex", gap: 70, alignItems: "center" }}>
            <Card width={980} style={{ padding: "34px 44px" }}>
              {STAGES.map((s, i) => (
                <Stagger key={s} i={i} step={5}>
                  <div style={{ display: "flex", alignItems: "center", gap: 18, fontFamily: C.mono, fontSize: 27, padding: "7px 0", color: C.text }}>
                    <span style={{ color: C.good, fontWeight: 800 }}>✓</span>
                    <span style={{ color: i >= 3 ? C.text : C.text }}>{s}</span>
                  </div>
                </Stagger>
              ))}
            </Card>
            <div style={{ display: "flex", flexDirection: "column", gap: 16, alignItems: "center" }}>
              <Bars heights={heights} color={C.accent} width={420} height={150} gap={7} alpha={0.95} />
              <div style={{ fontFamily: C.mono, color: C.muted, fontSize: 22 }}>48 kHz · PCM 24-bit</div>
            </div>
          </div>
        </div>
      </Absolute>
    </Fade>
  );
};

// ---------------------------------------------------------------------------
// scene 4 — A/B player (hero)
// ---------------------------------------------------------------------------
export const ABScene: React.FC = () => {
  const frame = useCurrentFrame();
  // relative offsets inside this scene (scene starts at 19.5s)
  const beforeStartF = Math.round((AB.beforeStart - SCENES.s4.start) * FPS); // 27
  const afterStartF = Math.round((AB.afterStart - SCENES.s4.start) * FPS); // 144
  const beforeDurF = Math.round(AB.beforeDur * FPS);
  const afterDurF = Math.round(AB.afterDur * FPS);
  const onAfter = frame >= afterStartF;
  const onBefore = frame >= beforeStartF && !onAfter;
  const prog = onAfter
    ? clamp((frame - afterStartF) / afterDurF)
    : onBefore
      ? clamp((frame - beforeStartF) / beforeDurF)
      : 0;
  const hA = waveHeights(40, 1.7, 0.9);
  const hB = waveHeights(40, 1.7, 0.9).map((x) => x * 1.5);
  const playheadX = 60 + prog * 1340;
  return (
    <Fade>
      <Absolute>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 40, height: "100%" }}>
          <Title size={60}>Escucha la diferencia.</Title>
          <Card width={1560} style={{ padding: "34px 44px" }}>
            <div style={{ display: "flex", justifyContent: "center", gap: 26, marginBottom: 26 }}>
              {(["A", "B"] as const).map((k) => {
                const active = k === "A" ? !onAfter : onAfter;
                return (
                  <div
                    key={k}
                    style={{
                      minWidth: 210,
                      textAlign: "center",
                      padding: "16px 0",
                      borderRadius: 16,
                      fontSize: 40,
                      fontWeight: 800,
                      fontFamily: C.sans,
                      color: k === "A" ? C.a : C.b,
                      background: active ? (k === "A" ? "#1d3a5f" : "#4a2f12") : C.card2,
                      border: `2px solid ${active ? (k === "A" ? C.a : C.b) : C.border}`,
                    }}
                  >
                    {k}
                  </div>
                );
              })}
            </div>
            <div style={{ position: "relative", height: 250, background: "#0c0c10", borderRadius: 16, overflow: "hidden" }}>
              <div style={{ position: "absolute", top: 16, left: 24, display: "flex", gap: 4, alignItems: "center", height: 100, opacity: onAfter ? 0.25 : 1 }}>
                <Bars heights={hA} color={C.a} width={1240} height={90} gap={6} radius={4} />
              </div>
              <div style={{ position: "absolute", top: 138, left: 24, display: "flex", gap: 4, alignItems: "center", height: 100, opacity: onAfter ? 1 : 0.25 }}>
                <Bars heights={hB} color={C.b} width={1240} height={130} gap={6} radius={4} />
              </div>
              {onBefore && (
                <div style={{ position: "absolute", top: 0, bottom: 0, left: playheadX, width: 4, background: "#fff" }} />
              )}
              {onAfter && (
                <div style={{ position: "absolute", top: 0, bottom: 0, left: playheadX, width: 4, background: "#fff" }} />
              )}
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontFamily: C.mono, color: C.muted, fontSize: 22, marginTop: 16 }}>
              <span>original</span>
              <span>voxera</span>
            </div>
          </Card>
          <Sub size={30}>El mismo tú, solo que mejor.</Sub>
        </div>
      </Absolute>
    </Fade>
  );
};

// ---------------------------------------------------------------------------
// scene 5 — score
// ---------------------------------------------------------------------------
export const ScoreScene: React.FC = () => {
  const frame = useCurrentFrame();
  const startF = 20;
  const p = ease(clamp((frame - startF) / 70));
  const value = Math.round(SCORE_BEFORE + (SCORE_AFTER - SCORE_BEFORE) * p);
  return (
    <Fade>
      <Absolute>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 40, height: "100%" }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 40 }}>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontFamily: C.mono, color: C.muted, fontSize: 24 }}>antes</div>
              <div style={{ fontFamily: C.sans, fontSize: 120, fontWeight: 800, color: C.muted }}>{SCORE_BEFORE}</div>
            </div>
            <div style={{ fontFamily: C.sans, fontSize: 90, color: C.accent, fontWeight: 800 }}>→</div>
            <div style={{ textAlign: "left" }}>
              <div style={{ fontFamily: C.mono, color: C.muted, fontSize: 24 }}>después</div>
              <div style={{ fontFamily: C.sans, fontSize: 150, fontWeight: 800, color: C.good }}>{value}</div>
            </div>
          </div>
          <div style={{ fontFamily: C.sans, fontSize: 34, color: C.text, fontWeight: 700 }}>
            Voice Score <span style={{ color: C.muted, fontWeight: 400 }}>/ 100</span>
          </div>
          <Card width={1240} style={{ padding: "28px 44px" }}>
            {SCORE_DIMS.map(([k, v], i) => (
              <Stagger key={k} i={i} step={6}>
                <div style={{ display: "flex", alignItems: "center", gap: 22, padding: "6px 0" }}>
                  <div style={{ width: 190, fontFamily: C.sans, color: C.muted, fontSize: 24 }}>{k}</div>
                  <div style={{ flex: 1, height: 16, background: C.card2, borderRadius: 8, overflow: "hidden" }}>
                    <div style={{ width: `${v}%`, height: "100%", background: v >= 80 ? C.good : C.accent, borderRadius: 8 }} />
                  </div>
                  <div style={{ width: 70, textAlign: "right", fontFamily: C.mono, color: C.text, fontSize: 24 }}>{v}</div>
                </div>
              </Stagger>
            ))}
          </Card>
        </div>
      </Absolute>
    </Fade>
  );
};

// ---------------------------------------------------------------------------
// scene 6 — CTA
// ---------------------------------------------------------------------------
export const CTAScene: React.FC = () => {
  const frame = useCurrentFrame();
  const p = ease(clamp((frame - 12) / 30));
  return (
    <Fade>
      <Absolute>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 50, height: "100%" }}>
          <div style={{ opacity: p, transform: `scale(${0.92 + 0.08 * p})` }}>
            <Logo size={130} />
          </div>
          <Title size={88}>Sound like you, only better.</Title>
          <div
            style={{
              marginTop: 8,
              background: C.accent,
              color: "#fff",
              fontFamily: C.sans,
              fontSize: 40,
              fontWeight: 800,
              padding: "22px 64px",
              borderRadius: 60,
              opacity: p,
            }}
          >
            Descargar voxera
          </div>
          <Sub size={28}>terminal-first · voxera.dev · aintonio.dev</Sub>
        </div>
      </Absolute>
    </Fade>
  );
};

// helper: full-screen absolute wrapper
const Absolute: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div style={{ position: "absolute", inset: 0, padding: 70 }}>{children}</div>
);
