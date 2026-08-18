# From Raw MP4 to Metrics-Optimized Short: A Scientific Synthesis of Short-Form Video Editing and Its Automation

> **Resumen ejecutivo (ES):** Síntesis de ~100 fuentes (58 revisadas por pares) sobre cómo convertir un MP4 crudo en un short optimizado por métricas y automatizarlo con agentes. Consenso fuerte [C1]: los subtítulos mejoran atención/comprensión/memoria y son el lever de edición mejor documentado (mute 38–52%); la cámara lenta es el único efecto con apoyo experimental masivo (N=27.227); los cortes captan atención pero cuestan capacidad de memoria; el completado rara vez supera ~60% y la duración es su mejor predictor; las plataformas definen métricas pero nunca publican benchmarks orgánicos. Consenso práctico [C2]: hook con promesa de valor ≤1.5 s (scroll-stop mediano 1.9 s), 30–90 s de duración para engagement (~2×), arousal auditivo moderado + congruencia A/V, estructura de curiosidad (open loop). Gaps declarados: captions cinéticas sin evidencia directa, beat-sync sin test, zoom/punch-in sin base académica, nada en español, nada para talking-head/podcast shorts. La automatización es viable hoy: pipeline OSS completo (whisper→cortes→captions→ffmpeg) probado a coste ~0, y el consenso de investigación es la arquitectura Plan-and-Act (LLM planea, ffmpeg determinista ejecuta) — exactamente donde voxera encaja; su única dependencia nueva es transcripción word-level (faster-whisper/WhisperX).

---

## 1. Structured Abstract

- **Background/Objective**: What does the current evidence say about how to transform a raw MP4 into a short-form video (TikTok/Reels/Shorts) optimized for distribution metrics — and can this be automated with agents and skills?
- **Methods**: 4 parallel research contracts (web search: 36+ query batches, 29 full-text fetches) produced 4 notes (R1–R4) with ~100 unique sources: 58 peer-reviewed (journals: JMR, JM, JAMS, Nature Comms, Communications Psychology, npj ×2, PLOS ONE, NeuroImage, eLife, PNAS, WebSci; conferences: CHI ×2, ICIS), 10 official platform docs, ~20 industry/vendor studies, ~30 practitioner/tool sources, ~26 GitHub OSS repos, plus the project's own measured skills (voxera). Confidence graded C1–C3 per claim; gray literature labeled inline.
- **Results**: Six synthesized themes: (1) the hook window is a platform-metric artifact compressing to ~1.9 s median scroll-stop; curiosity gaps are the only experimentally grounded hook mechanism. (2) Cuts capture attention but consume processing capacity — the "more cuts" dogma contradicts both the one controlled experiment (N=242) and measured corpora (U-shaped). (3) Captions are the best-documented editing lever (100+ studies; +12% watch time, Facebook-internal) yet kinetic word-level styling is unevidenced. (4) Moderate auditory arousal + audiovisual congruence maximize engagement; beat-synced cutting is untested. (5) Slow motion is the only effect with massive experimental support (12 experiments, N=27,227) and is absent from practitioner lists. (6) Completion has a ~60% ceiling; duration is its strongest predictor; 30–90 s ≈ 2× engagement. Automation: the full raw→short loop is proven open-source at ~$0 marginal cost; research consensus is a Plan-and-Act split (LLM plans, deterministic ffmpeg executes); agent-skill files are the emerging standard interface. No public benchmark exists for agentic editing quality.
- **Conclusions**: The evidence supports a rule-based "scientific edit" (silence-compression, captions, moderate-arousal audio, hook-front-loading, slow-motion emphasis) whose defaults must be validated against the project's own platform metrics — no universal optimum exists, and metric definitions differ per platform. Automation should keep the LLM in the planning layer only, executing through verified deterministic primitives (voxera), with word-level transcription as the single new dependency.

---

## 2. Introduction

The short-form video economy now sets the editorial standard for attention: three platforms (TikTok, Instagram Reels, YouTube Shorts) distribute hundreds of billions of plays against a shared constraint — a viewer decides whether to keep watching within roughly two seconds. Editing practice has followed as a body of creator lore ("hooks in 3 seconds", "5–7 cuts per 10 seconds", "kinetic captions"), while an adjacent, largely disconnected academic literature has accumulated on attention, cognitive load, captions, and reward mechanisms. Meanwhile the tooling layer has bifurcated: closed SaaS editors (OpusClip, Descript, CapCut) automate clipping but hide their decision layer, and open-source pipelines now prove the entire loop at near-zero marginal cost. The project context — voxera, a deterministic, numerically-verified ffmpeg effect engine (cutsilence, zoom, magnify, teleport, stabilize, tonal audio) — occupies the execution layer of exactly the architecture the research literature converges on.

**Organizing question:** *What does current evidence (2024–2026) say about how a raw MP4 should be transformed into a metrics-optimized short-form video, and how can that transformation be automated with agents and skills while keeping the edit decisions verifiable?*

**Boundary conditions:** Sources collected August 2026; temporal scope 1993–2026 with emphasis 2024–2026 (classics admitted where they anchor mechanisms: Geiger & Reeves 1993, Loewenstein 1994, Carmi & Itti 2006). Inclusion: peer-reviewed research on attention/cognition/marketing applied to (or transferable to) short-form video; official platform documentation; measured industry corpora; open-source tooling with verifiable repositories. Exclusion: unverifiable "internal agency studies" (flagged, never counted as corroboration), paid-vendor performance claims, and non-English sources (a documented gap: only English/Chinese evidence was found, plus one Polish caption-style study). All confidence tiers follow the grading schema: C1 = 3+ independent sources incl. ≥1 peer-reviewed; C2 = 2 sources or 1 strong study; C3 = single source; C0 = unresolved conflict.

---

## 3. Methodology

**Search strategy.** Four parallel contracts (R1–R4), each executed by an isolated research subagent with web-search tooling; the orchestrator grounded contracts in local voxera docs and validated outputs against explicit success criteria (structure, source counts, tag coverage, no-repo-mutation). Total: 36+ search batches (multiple providers), 29 full-text page fetches, 4 GitHub repos read directly.

- **R1 — editing techniques**: 12 searches + 6 fetches → 39 sources (9 peer-reviewed / 7 industry / 23 practitioner-vendor).
- **R2 — scientific basis**: 18 searches + 12 fetches → 51 sources (41 peer-reviewed / 10 industry).
- **R3 — metrics & analytics**: 6 searches + 8 fetches → 34 sources (8 official platform / 14 vendor / 9 practitioner / 3 local).
- **R4 — automation & agents**: ~24 searches + 4 fetches → 42 sources (3 arXiv / ~26 GitHub / 4 official docs / 9 blogs & vendor pages).

**Quality/bias assessment.** Four tiers applied: (a) peer-reviewed (weighted highest; N/effect size recorded when reported); (b) official platform documentation (definitions are authoritative, benchmarks are never published — absence is itself a finding); (c) industry/vendor studies (well-documented N but self-published and unaudited — Fanpage Karma N=32,000, Metricool 2.3M posts, SaliencyLab n=700 model-scored with disclosed ρ+0.31); (d) practitioner blogs — treated as ONE correlated SEO-motivated cluster (Kudoflix, Blitzcut, ByteCap, Kapwing, Kompozy, OpusClip blog…), never counted as independent corroboration. Claims from "internal/agency studies" are flagged `[C3-flagged]` and excluded from C1 aggregation. Reproducibility: full per-source audit trails (URLs, dates, types) live in research-notes/R1–R4; the working synthesis matrix is research-notes/synthesis-matrix.md.

---

## 4. Thematic Results

### Theme 1 — The hook window: a metric artifact that is compressing

The "first 3 seconds" rule is best understood as a **consequence of platform measurement definitions** rather than a universal psychological constant: TikTok counts a view at ~1 s of playback and computes hook rate on 6-second views, Meta's thumb-stop is a 3-second stay, and Shorts keys on viewed-vs-swiped decisions estimated at <400 ms [C1 — official definitions, R3#1–8]. The effective decision window has compressed: median scroll-stop fell from 2.4 s (2024) to **1.9 s** (2026) in a model-scored cohort of 700 ads [C2 — single vendor cohort, disclosed AI-scoring, R3#9]. This convergence corroborates the practitioner consensus that value/promise/face must land by ~1.0–1.5 s [C2], and promise-first openings measured +28% completion over brand-first [C2 — model-scored].

The only **experimentally grounded** hook mechanism is the curiosity gap: Loewenstein's information-gap theory and five experiments on incomplete content show curiosity drives continued interest when attention is focused on a knowledge gap [C1 — peer-reviewed classics, R2#37,38]. Practitioner hook recipes (contradiction, result-first, bold claim) layer lore onto this base [C3]. Two measured counter-data complicate the dogma: hooks resolving at 4–6 s saved at 1.34% vs 0.69% for 2–3 s in a measured corpus (correlational, confounded) [C2], and the first-seconds drop is proportionally small for short videos (Wistia nose-drop 4.9% for 1–2 min) [C2]. The evidence therefore supports front-loading *value* while cautioning against reading "resolve everything by second 3" as law [C0 — dogma vs corpus remains unreconciled].

**→ voxera:** missing primitives are opening-second analysis and curiosity-gap checks; `audio riser --hit` and `zoom --pulse` at t≈0 are the natural orienting triggers, and the first content beat should land ≤1 s (industry-consistent, academically untested).

### Theme 2 — Pacing: cuts buy attention at the price of capacity

A consistent mechanistic picture emerges across four decades of research: scene changes trigger an involuntary orienting response [C1 — Geiger & Reeves 1993; ERP study 2013; JAMS 2025], but processing capacity is limited — unrelated cuts raise moment-to-moment attention while **reducing message memory**, whereas related cuts preserve it [C1]. In advertising, short, visually simple scenes maximize attentional synchrony while visual complexity exerts a *delayed negative* effect [C2 — JAMS, 2,520 viewing experiences], and denser editing compresses subjective duration (a plausible mechanism behind watch-time gains) [C3 — Cognitive Science, N=70].

The one controlled experiment on short-form cut style qualifies the lore: seamless cuts raise *liking*, overlapping cuts raise *sustained engagement* — but **only at low transition frequency**, and high frequency reduces sustained engagement overall [C2 — N=242 + field benchmark of 50 TikToks]. Measured corpora agree there is "no clean more-cuts-is-better line": engagement is U-shaped in scene count (1–2 scenes and 11+ scenes both beat the 3–5 middle) [C2]. The industry prescription of 5–7 visual changes per 10 s and the "3-second rule" (with its unverifiable 40–60% retention-lift claim) rest on practitioner lore alone [C3-flagged]. Integrated: *pace for the KPI — cuts for engagement with message retention as the constraint*, which for educational/talking-head content argues against maximal stimulation [C2].

**→ voxera:** `cutsilence` implements the experimentally-adjacent move (seamless silence-compression, frame-accurate); the actionable additions are a transition-frequency guard and a scenes-per-10-s *measurement*, not prescription.

### Theme 3 — Captions: the best-documented lever, with an unevidenced styling layer

Captions are the strongest consensus point in the entire synthesis: a review of 100+ studies shows captions improve attention, comprehension and memory across populations [C1 — Gernsbacher 2015, corroborated by PLOS ONE 2024 eye-tracking and an ICEDBC 2023 engagement study], and sound-off is a measurably distinct viewing state (muted+subtitled changes comprehension, load, immersion, gaze) [C2]. The practical urgency is documented: feed muting runs 52% (TikTok) to 38% (Shorts) [C2], TikTok officially states creative attributes that get people to read increase view time [C1-qualitative], and a Facebook-internal study reports +12% average view time from captions — unverifiable but directionally consistent [C3-flagged]. Caption *style* measurably matters on TikTok: emojis + non-standard typography (no punctuation/capitalization) beat traditional subtitles in the only controlled style study found (N=171 + engagement metrics, University of Warsaw) [C2].

The dominant creator style — **kinetic word-by-word pop** — inverts this evidence base: ubiquitous in practice, claimed to raise retention by tool vendors, but with **no direct experimental support**; the academic base is indirect (moving text helps only when motion aligns with attention; animation speed changes information-transmission efficiency) [C2 for indirect; explicit gap]. Captions are also a serial reading task: subtitle regions capture a large share of fixations in sound-off viewing, so caption pace must respect reading rate [C2]. Practical style defaults (white + black stroke, 60–80 pt on phone, ≤3 lines, 1 frame after cut / 1 frame before next) are consistent across practitioner guides [C2] but remain unmeasured.

**→ voxera:** the largest gap in the engine — no ASR, no styling, no word-level timing, no safe-zone placement, and no Spanish caption handling (a documented language gap with zero academic precedent).

### Theme 4 — Audio: arousal in an inverted U, congruence as multiplier, beat-sync untested

The strongest direct evidence for audio editing levers comes from a large multimodal analysis of 12,842 Douyin videos: auditory emotional arousal has an **inverted-U effect** on engagement (moderate arousal optimal), visual variation has a positive linear effect, and **audiovisual congruence multiplies** both [C2 — peer-reviewed, MDPI JTAER 2025]. Corroborating experimental work shows music tempo shifts attitudes and recall via affective response [C2 — Oakes 2006; Stewart 2017], and the brain entrains to musical beats (familiarity and salience modulate synchronization) [C2 — eLife; PNAS] — yet **no study directly tests beat-synced vs random cuts** on engagement (explicit gap; tool convergence is not evidence). For spoken content, lower speech rate measurably raises listener engagement (10,000 audio files, ICIS 2020) [C2], supporting ducking music under voice. Trending-audio advice conflates discovery with retention: a measured corpus found original ≈ licensed audio on engagement within rounding error [C2], so trending sounds are a *reach* lever, not a *retention* one.

**→ voxera:** the tonal primitives (riser/transition/melody, 8-mood table) map directly onto the arousal mechanism — target *moderate* arousal, check audio-mood/visual-pace congruence, duck music under speech; beat detection on the user's own track (aubio/librosa) is the missing piece if beat-grid cutting becomes a requirement.

### Theme 5 — Motion & effects: slow motion is the science; zooms are the lore

Motion is a causal attention attractor (motion contrast ranks among the strongest saliency features) [C2 — Carmi & Itti], and cuts can even pass unnoticed when attention is already engaged ("edit blindness") [C2 — Smith & Henderson] — together implying effects should be placed at emphasis points, not on fixed rhythms. The standout result: **slow motion is the only editing effect with massive experimental support** — three peer-reviewed papers (12 experiments, N=27,227, 5 preregistered; 7 studies incl. eye-tracking and a Facebook Ads field experiment) show it increases virality, brand liking, choice and willingness-to-pay via processing fluency [C1]. Strikingly, it is *absent from practitioner best-practice lists* — a conflict discussed in Section 5. Zoom/punch-in emphasis ("zoom = pacing beat") is industry lore with no isolating experiment [C3]; magnify-style teaching zooms and stabilization are established craft conventions validated locally [C3-local].

**→ voxera:** slow motion is the highest-ROI missing primitive (the only academically-supported effect), especially for demo/product content; existing zoom/magnify are best driven by voice-peak auto-emphasis rather than a fixed cadence.

### Theme 6 — Length, completion and the reward system

Completion has a measured ceiling: the fraction watched to the end rarely exceeds ~60% and does not improve with personalization, and **duration is the single strongest predictor of completion** — demographics add almost nothing [C2 — peer-reviewed WebSci'26 + industry corroboration]. Length optima are KPI-dependent: 0–10 s maximizes reach and completion, 30–90 s delivers ~2× engagement (N=32,000 corpus) [C2], and save rate *climbs* with length (0.63% <15 s → 1.29% at 60–120 s) while engagement stays flat [C2] — the classic 20–35 s guidance is a completion-targeting rule, not a universal law [C0]. The reward-system literature reframes why retention is the master signal: engagement follows reinforcement learning with reward prediction errors [C2 — Nature Comms 2021], and TikTok's *personalized recommendations* activate the ventral tegmental area [C3 — fMRI] — the algorithm's novelty is the reward carrier, not the video's cuts. Meanwhile, short-form consumption demonstrably degrades sustained attention and memory encoding [C2 — Communications Psychology 2026; npj ×2; CHI'24], and "dopamine editing" recipes are pop oversimplification: no per-cut dopamine measurement exists anywhere [C2]. Integrated, this argues for **structured novelty** — curiosity gaps, loops, pattern interrupts at measured drop points — over maximal stimulation, and makes message comprehension a first-class goal for educational content rather than an assumption [C2].

**→ voxera:** 30–90 s band for voice-first shorts (largest industry dataset); retention *curves* (not binary completion) as the actionable signal; loop-point detection and drop-point analysis as new features; watch-fraction analytics to replace borrowed lore with own baselines.

### Theme 7 — Metrics & algorithms: definitions are official, benchmarks are not

The platforms define their metrics authoritatively — TikTok (1 s view, 2 s/6 s views, replay exclusion in ads), Meta (3-s plays; watch time as % AND absolute seconds; likes/sends per reach per Mosseri, Feb 2025), Shorts (any play = view since 3/31/2025; engaged views for monetization; replays count as views) [C1 — official docs] — but **none publishes organic benchmarks**; every circulating number is vendor-measured (Sepia 3-s hold 38–48% paid DTC; Retensis completion 60–70% <15 s with no methodology) [C2/C3-flagged]. The signal hierarchies (TikTok: watch time → completion → saves/shares → likes) are practitioner interpretation, not official [C2]. Benchmarks are decaying (−31% TikTok views YoY, Metricool 2026) [C2], so acceptance criteria must come from the account's own baselines. Retention-curve anatomy is the shared diagnostic: Shorts loses 30–50% of viewers between seconds 1–3 ("the cliff"), and the algorithm reads a cliff as low-value regardless of the rest [C2]; curve-shape→edit-fix mappings (cliff → value by 1.5 s; 10 s collapse → tighten script; mid dip → pattern interrupt; end drop → loop) are practitioner heuristics layered on the official fact that platforms show curves and use early retention [C2 official / C3 heuristics]. A/B practice for clips is converging on a sound protocol: one variable at a time, 30–60 paired clips per variant, 7–14-day windows, **median** ratios (heavy-tailed distributions), replicate winners before locking in [C2 — vendor framework, no peer review; consistent with the repo's own Track-8 protocol].

**→ voxera:** the Track-8 human A/B skeleton (60 pairs, ≥60% preference gate) extends naturally into a distribution gate (per-variant medians of views/completion/3-s retention), with per-platform output presets (TikTok: loop-friendly + completion-first; Shorts: frame-one hook + audio-led open; Reels: medium length acceptable, absolute watch time matters) [C2].

### Theme 8 — Automation: the loop is proven, the agents are unbenchmarked

The full raw→short loop is commercially mature but opaque: OpusClip/Descript/CapCut/Munch automate clipping at subscription + per-minute credit cost with watermarked free tiers, and none exposes the *decision layer* (why this moment?) as a programmable API [C2]; the only same-input comparisons are two n=1 blogger tests (OpusClip best auto-framing/captions; Video AI truncates mid-sentence; Munch ~120 min) [C3]. The open-source alternative is complete and near-zero-cost: whisper-family transcription → silence cuts (auto-editor, 20k+★, exports edit lists) → word-level captions (WhisperX forced alignment, the de-facto standard since raw Whisper timestamps are off by seconds) → ASS karaoke burn-in (`\k` tags via libass) → single-pass ffmpeg → optional upload (FreeFaceless, YT_Shorts_Generator prove the end-to-end loop) [C1 — repos]. Agentic editing converges on a **Plan-and-Act split**: research frameworks (UniVA, VideoAgent, Aurora) and the first commercial agentic editor (Descript Underlord) all have the LLM emit a plan that a deterministic executor renders [C1 for the pattern — arXiv/repos; C2 for maturity], and agent-skill files (.claude/skills; OpenAI's skills repo; auto-editor ships 4) are emerging as the standard agent↔tool interface [C1 — repos]. Critically, **no public benchmark measures agentic editing quality** — no leaderboard, no human-eval, no retention A/B; whether an LLM planner beats a rule-based baseline (silence-cut + energy emphasis) is unmeasured [C2 — absence of evidence].

**→ voxera:** the reference architecture (R4 Theme 6) maps stages analyze/transcribe/plan/effects/captions/render/QA onto existing subcommands for 5 of 7 stages; the only new dependency is word-level transcription (faster-whisper fits the existing extras pattern); the LLM emits a declarative edit-spec JSON that the deterministic engine executes, keeping every "agent decision" verifiable against numeric QA (frame counts ±1, sync <20 ms, per-effect SSIM/FFT) [C1 — repo-grounded].

---

## 5. Conflicts, Gaps & Limitations

**Contradictions.** (1) *Hook speed*: practitioner dogma (resolve in 1–3 s) vs measured corpus (4–6 s hooks save more) — correlational and confounded; no RCT exists [C0]. (2) *Cut density*: "5–7 changes/10 s" (lore) vs the N=242 experiment (high frequency reduces sustained engagement) vs U-shaped measured scene counts — the experiment measured perceived outcomes, not on-platform retention [C0]. (3) *Length*: completion tables favor <30 s; engagement and saves favor 60–120 s — the optimum is KPI-dependent, and no evidence links any metric to follower growth [C0]. (4) *Completion benchmarks*: measured ~60% ceiling (peer-reviewed) vs "80%+ is excellent" (industry) — definitional mismatch (plays vs impressions vs unique viewers) unresolved; benchmarks must be matched to exact metric definitions before use [C0]. (5) *Slow motion*: three strong papers vs total absence from practitioner lists — likely niche/context dependence (product/brand vs talking-head) untested [C0]. (6) *Watch-time weighting*: Mosseri's "both % and seconds" (Reels) vs TikTok's watch-time-first lore vs Shorts' viewed-vs-swiped — no public source reconciles them; a single "optimized edit" across platforms likely does not exist [C0].

**Knowledge gaps across all sources.** Kinetic word-by-word captions have no direct engagement evidence [gap]; beat-synced cutting has neuroscience plausibility but zero outcome tests [gap]; punch-in/zoom effects are unisolated [gap]; loop/rewatch design has RL-theoretic plausibility only [gap]; paid→organic transfer of hold-rate benchmarks is untested [gap]; the memory-vs-engagement tension (fragmentation captures bottom-up attention while reducing encoding) is unresolved for educational content — the strongest argument against "max stimulation" defaults [gap]; no public benchmark exists for agentic editing quality — the first experiment to run in-project is LLM-planned vs rule-based edits on the same source [gap].

**Source-material constraints.** Practitioner sources behave as one correlated SEO cluster and are excluded from C1 aggregation; all benchmark corpora are self-published and unaudited; the AI-scored evidence (SaliencyLab ρ+0.31) is directional, not in-market measurement; ACM bot-blocking forced mirror verification for two papers; everything is English/Chinese — nothing Spanish, and nothing on podcast-derived talking-head shorts (the project's exact content class); one "ktool" reference in the original request could not be verified as a real tool. Vendor claims ("world's first", "viral moment detection") are marketing until measured.

---

## 6. Conclusion

**Direct answer to the organizing question.** The evidence supports a *rule-based scientific edit* as the default transformation from raw MP4 to short: (1) front-load value within the first second and open a curiosity gap at the hook [C2]; (2) compress silence with seamless cuts but keep transition frequency moderate and scenes visually simple [C2]; (3) always burn captions (mute 38–52%), defaulting to high-contrast styled text — kinetic word-level motion is optional until own-metric validation [C1 for captions, gap for kinetics]; (4) moderate-arousal music with audiovisual congruence, ducked under voice, with pattern-break audio at hook and drop points [C2]; (5) target 30–90 s for engagement or shorter for completion — decide the KPI first [C2]; (6) consider slow motion for product/demo emphasis — the only academically-supported effect [C1]; (7) treat every benchmark as directional and validate against the account's own retention curves and median-based A/B [C2]. The single most defensible claim of this synthesis is also the least glamorous: **captions** [C1]. The single most actionable new primitive is **slow motion** [C1]. The single most important methodological lesson is that metric definitions differ per platform and per denominator, so "optimized" must be defined per platform before any edit decision is made [C1].

**Temporal evolution.** Understanding has shifted measurably across the window: the hook window compressed from 2.4 s to 1.9 s (2024→2026); benchmarks decayed −31% YoY; YouTube's view definition changed in 2025; AI-scored creative analytics and agentic editors (Underlord, 2025) emerged as a new evidence tier — while the underlying mechanisms (orienting, curiosity gaps, dual-coding, entrainment, reinforcement learning) have been stable for decades. Earlier lore ("decide in 3 s", "cuts per 10 s") is now contradicted by measured corpora; the trend is from prescriptive rules toward measured, metric-anchored practice.

**Practical implications & next steps.** (1) Implement captions + word-level ASR in voxera (single new dependency: faster-whisper/WhisperX) — the highest-consensus, highest-lift feature. (2) Add slow motion as an effect primitive. (3) Add pacing measurement (scenes-per-10-s, transition-frequency guard) rather than prescription. (4) Instrument the pipeline for platform metrics: per-variant medians, 7–14-day windows, retention-curve exports mapped back to edit decisions. (5) Run the first experiment the field lacks: LLM-planned edit vs rule-based baseline on the same source, judged by platform retention — that is the empirical question this synthesis cannot answer from public data. (6) Keep the agent in the planning layer: LLM emits a declarative edit-spec JSON; deterministic, numerically-verified primitives execute; every claim about the output is checked by QA stages, not by the model's self-report. The user's target workflow — raw MP4 in, metrics-optimized short out — is achievable today with the architecture in Section 7; what remains genuinely unknown is whether the LLM planning layer beats the deterministic rule layer, and that is a measurement, not a research project.

---

## 7. Implementation Blueprint — voxera autopilot (raw MP4 → metrics-optimized short)

Reference architecture synthesized from R4, grounded in voxera's measured capabilities (docs/skills/*.md, cli.py):

```
 raw.mp4 (podcast/single-cam, any aspect)
   │
   ▼ [1 ANALYZE]   voxera video info (ffprobe JSON) + analyze (energy envelope 30 ms,
   │               VAD thr=max(-50, p75-12) dBFS, breath margin 200 ms → emphasis windows)
   ▼
   │ [2 TRANSCRIBE] faster-whisper (word-level JSON)  ← NEW dependency (only gap)
   │               optional: WhisperX forced alignment; pyannote diarization (HF gating check)
   ▼
   │ [3 EDIT PLAN]  LLM planner (any model via opencode/ollama) reads transcript + envelope
   │               → emits declarative edit-spec JSON (contract below)
   │               └─ deterministic guards: no mid-sentence cuts; silence trigger levels
   │                  (light/medium/aggressive); max clip length; frame-quantized timestamps
   ▼
   │ [4 EFFECTS]    voxera video zoom|magnify|teleport|stabilize · audio lowpass|transition
   │               |riser|melody (8-mood table) — all numerically verified
   ▼
   │ [5 CAPTIONS]   word JSON → cues → ASS karaoke (\k) → ffmpeg subtitles= (libass burn-in)
   │               style: white + black stroke, 60–80 pt, ≤3 lines, safe zone 900×1160 px
   ▼
   │ [6 RENDER]     ONE ffmpeg pass: select with gte*lt (upper-bound exclusive), setpts/asetpts
   │               on same frame grid, libx264 CRF 18 + AAC 192k + -shortest; 9:16 crop/reframe
   ▼
   │ [7 QA]         container dur == Σ quantized parts (±1 frame); A/V sync <20 ms;
   │               per-effect numeric checks (SSIM zoom, FFT lowpass/tonal, frame counts)
   ▼
 short.mp4 (9:16, captioned, scored) → metrics log (per-variant medians, retention curve)
```

**Edit-spec contract (LLM ↔ engine):**
```json
{ "version": 1, "source": "raw.mp4",
  "keep_spans": [[0.0, 8.4], [9.1, 31.2]],
  "hook": {"type": "zoom-grow", "at": 0.0, "pct": 35, "curve": 62},
  "effects": [
    {"cmd": "video zoom", "args": {"anchor": [0.58, 0.24], "dir": "grow", "at": [12.0, 16.0]}},
    {"cmd": "audio riser", "args": {"mood": "tension", "hit": 31.2}} ],
  "captions": {"style": "karaoke-word", "highlight": ["hook", "CTA"]},
  "target": {"aspect": "9:16", "max_dur": 45, "crf": 18} }
```

**Design rules (from voxera's own measured lessons + this synthesis):** LLM plans, never executes; one ffmpeg pass; frame-grid quantization (AAC delay ~44 ms → `-shortest`); reuse the silence map for captions (don't re-detect — Whisper hallucination on silence is real); captions default ON (mute 38–52%); slow-motion primitive for demo/product emphasis; per-platform presets (TikTok completion-first + loop close; Shorts frame-one hook, audio-led open; Reels medium length OK); A/B gate: Track-8 human preference (≥60%) + platform metrics (medians, 7–14 days, replicate winners).

**Agent/skill layer:** a `voxera-autopilot` skill (mirroring the repo's 7 documented skills: trigger, procedure, numeric verification) exposes the pipeline as an agent-callable skill; the agent's role is choosing the plan within the JSON contract's vocabulary — every decision it makes is executable by verified subcommands and checkable by QA. This is the emerging industry pattern (auto-editor's 4 skills, OpenAI skills repo) applied to voxera's stricter numeric-QA philosophy.
