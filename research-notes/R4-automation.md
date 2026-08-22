# R4 — Automation & Agentic Pipelines for Short-Form Video

> **Resumen ejecutivo (ES):** La automatización de edición de vídeo corto está
> madura en dos frentes: SaaS cerrados (OpusClip/Descript/CapCut) y pipelines
> open-source ffmpeg+python (whisper → cortes → captions → render). Los agentes
> LLM ya se usan como *planificadores* que emiten specs de edición declarativas
> ejecutadas por ffmpeg determinista — exactamente el hueco donde voxera encaja
> (sus 8 efectos verificados numéricamente cubren la capa de ejecución). Ningún
> benchmark público mide calidad de edición agéntica; las comparaciones reales
> son tests anecdóticos de un solo vídeo. Recomendación: arquitectura
> analyze → transcribe → plan (LLM) → effects → captions → render → QA, con
> WhisperX añadido como única dependencia nueva.

## Method (1 para)
6 web_search batches (~24 queries, provider default, workflow none) covering: commercial tool comparisons,
measured same-input tests, open-source silence/caption/beat tools (GitHub primary sources), agentic/LLM
editing (arXiv + GitHub), and faceless-shorts pipelines; plus fetch_content on 3 primary pages (auto-editor
repo, WhisperX repo, opus.pro homepage) and 1 measured third-party comparison. Source tally: 38 numbered
sources = 3 vendor homepages/pricing pages, ~24 GitHub repos (most read via search/fetch), 3 arXiv papers, 4
official docs/changelogs, 8 blog comparisons/roundups (2 with measured same-input or timed tests). Confidence
tags: [C1] primary/verified (repo content read, arXiv, official docs, multi-source), [C2] single-source or
measured-but-not-peer-reviewed, [C3] vendor marketing claims.

## Theme 1: Commercial AI editing tools

- **OpusClip** (opus.pro): long→short clipping factory — "ClipAnything" (claims any genre, not just podcasts),
"ReframeAnything" (object-tracking reframe), keyword-triggered clips, brand templates, API, autoposting.
Pricing: free 60 min/mo (watermarked), $15/mo, $29/mo, Business custom
[C2 pricing verified on pricing page; C3 for "only AI clipping model for any genre" claim] [1, 5, 6]
- **Measured same-input test #1 (tech-distilled, one 54-min YouTube video through 5 tools)**: TwoShorts <1 min
(31 clips), Vizard ~3 min, Video AI ~18 min (25 clips), OpusClip ~20 min (26 clips), Munch ~120 min. Quality:
OpusClip best auto-framing + caption control; Video AI produced mid-sentence truncations and missed speaker
framing; Munch slow + paid ($49+/mo); Vizard adds viral scoring, auto-schedule, calendar
[C2 — single blogger's test, n=1 video, no engagement metrics] [2]
- **Measured same-input test #2 (AI Hustle Guy, timed workflows)**: Descript full edit workflow 28 min; CapCut
5 shorts in 18 min; OpusClip 17 clips in ~4 min (auto-discovery only). Free tiers: Descript ~60 media-min/mo
watermarked, CapCut generous 1080p no watermark, OpusClip 60 processing-min/mo watermarked
[C2 — single author timed test] [9]
- **CapCut**: the short-form polish/template workhorse — auto-captions, trending effects, beat-synced
templates; Pro $19.99/mo or $179.99/yr (team ~$24.99/mo); region-dependent pricing [C2] [8, 26]
- **Descript**: text-based (document) editing with silence removal; "Underlord" agentic AI co-editor launched
2025 ("world's first agentic video editor", "Cursor for video" per CEO) — chat prompt → edits; model picker
incl. Claude Sonnet 4.5; trained to watch video (multimodal clip finding). Hobbyist $16-24, Creator $24-35,
Business $50-65 per person/mo [C2 — vendor changelog/blog; C3 for "world's first" claim] [7, 13, 26]
- **Munch AI / Vizard / TwoShorts / CutFast / Submagic**: Munch = keyword/trend context + suggested titles but
~2 h turnaround; TwoShorts = fastest but generic styling; CutFast = "highlighter" subtitle-cutter, $0.5/min
pay-as-you-go; Submagic = caption-styling focus; Vizard = viral scoring + scheduling
[C2 — vendor blogs + the two measured tests] [2, 9, 26]
- **Quality gaps reported across tools**: mid-sentence truncation, auto-framing missing the active speaker,
off-context auto-B-roll/keywords, generic caption styling, server-dependent latency. Vendors market "viral
moment detection" but no vendor publishes precision/recall on moment selection [C2; C3 for viral-score claims]
[2, 26]
- **Pricing model pattern**: all SaaS = subscription + per-minute/credit processing + watermark on free tiers;
per-clip marginal cost makes bulk repurposing expensive; none expose the *decision* layer (why this moment?)
as a programmable API [C2] [2, 6, 7, 8, 26]
- **Map to voxera**: commercial tools are the benchmark targets for quality (auto-framing, captions) and the
value argument for a local pipeline (zero marginal cost, no watermark, programmable decisions). voxera already
covers two of their flagship automations (silence removal ≈ Descript/CapCut "remove silence"; caption-free but
has the QA rigor they lack)
[C1 — repo: cutsilence skill replicates "remove silence" of TikTok/CapCut/Descript; C2 on parity claims]
[1, 2]

## Theme 2: Open-source pipelines (ffmpeg + python)

- **auto-editor** (WyattBlue, ~Nim/C++ single binary, 20k+★): CLI that edits video/audio by analyzing loudness
(or motion/subtitles/audio levels); cuts "dead space" (first pass), `--margin` keeps a slice of silence for
rhythm; renders via ffmpeg and exports edit lists to FCP/kdenlive/OTIO/JSON; ships 4 agent skills
(`auto-editor`, `-effects`, `-export`, `-transcribe`). Canonical OSS reference for voxera's `video cutsilence`
[C1 — repo read] [3]
- **WhisperX** (m-bain, 23k★): batched inference 70× realtime (large-v2), word-level timestamps via wav2vec2
forced phoneme alignment (raw Whisper utterance timestamps "can be inaccurate by several seconds"), VAD
preprocessing reduces hallucination without WER loss, speaker diarization via pyannote-audio. Paper: arXiv
2303.00747. De-facto standard for word-accurate captions [C1 — repo + arXiv] [4]
- **Silence-cut ecosystem**: sysulq/jumpcutter (opencv + silence threshold, carykh-inspired: different speeds
for silent/sounded), maxmakesmagic/autoeditor (ffmpeg complex filter, crossfades, max silence 3 s),
beenotung/silencecut-ffmpeg (pure ffmpeg filter). All simpler than auto-editor; none publish sync verification
— voxera's design (frame-grid quantization, A/V sync <20 ms measured, breathing margin 200 ms) is the rigorous
end of this family
[C1 GitHub; C2 on comparative capability — design intent from repo skill, not head-to-head test] [10, 11, 12]
- **ASR backends**: faster-whisper (SYSTRAN, CTranslate2) — up to 4× faster than OpenAI Whisper at same
accuracy, int8 quantization for CPU/low-memory; whisper.cpp (ggml) — C/C++ with karaoke-ASS workflows; both
power the caption CLIs below. OpenAI Whisper itself does not batch and has unreliable per-word timestamps
[C1 — WhisperX README; C2 for faster-whisper speed factor — vendor README] [4, 28]
- **End-to-end faceless-shorts pipelines (proof the full loop is OSS)**: FreeFaceless — script (Groq) →
voiceover (edge-tts) → captions (faster-whisper local) → b-roll (Pexels) → assemble (ffmpeg) → upload (YouTube
API), $0; YT_Shorts_Generator — Ollama script + Piper TTS + WhisperX word timing + Pillow scenes + ffmpeg,
fully local; ai-video-factory — GitHub Actions serverless ($0/mo)
[C1 — repos; C2 on output quality — self-reported] [14, 15, 36]
- **ktool caveat**: the "ktool" auto-caption tool referenced in the task could not be verified — no
widely-known OSS video-caption tool by that name exists (searches return Kindle/sailing tools). Closest
verified equivalents: m1guelpf/auto-subtitle, jurczykpawel/captions-cli, VideoCaptioner, subtool
[C3 — unresolved identification] [23, 19, 22, 34]

## Theme 3: Agentic / LLM-orchestrated editing

- **Descript Underlord** (2025-2026): first mainstream agentic editor — chat with an "AI co-editor that knows
what a good video looks like and knows how to make it"; multimodal (watches video, not just transcript — finds
"the moment someone holds something up"); model picker (Claude Sonnet 4.5 among options); free during beta.
All claims vendor-side; no published eval of edit quality or edit-decision accuracy
[C2 vendor; C3 for superiority claims] [13]
- **Open research frameworks**: UniVA (arXiv 2511.08521) — open-source "video generalist" unifying
understanding/segmentation/editing/generation; **Plan-and-Act dual-agent architecture** with iterative
multi-round co-creation. VideoAgent (arXiv 2606.23327v1) — all-in-one agentic framework; automated shot
segmentation + LLM-driven narrative coherence for long video. Both validate the **planner→executor split** as
the research consensus [C1 — arXiv abstracts; C2 on measured performance — preprint-stage] [16, 27]
- **Aurora** (yeates/Aurora, MIT): tool-using vision-language agent — rewrites a natural-language request into
an editor-facing instruction, decides edit type, optionally retrieves a reference image and grounds a target
object with a mask, executes via a unified "video diff" tool (edits expressed as a diff against source).
Academic/demo scale, not a production renderer [C1 repo; C2 on maturity] [17]
- **LLM→ffmpeg bridges**: HariharanElancheliyan/ai-video-editor — natural language → LLM selects/executes
ffmpeg operations; supports local Ollama or Gemini (no API-key lock-in). Pattern: LLM emits a **plan**,
deterministic ffmpeg executes it — the same separation voxera's CLI already provides (effects are fixed,
well-tested subcommands) [C1 repo] [12]
- **Agent-skill pattern (opencode-style loops)**: multiple OSS projects ship `.claude/skills` as the
orchestration layer — auto-editor ships 4 skills, beat-synced-edit ships a `beat-sync-edit` skill,
VideoCaptioner ships a Claude Code skill, OpenAI publishes a curated `skills` repo incl. a Sora API skill.
Conclusion: skill files (like voxera's 7 mirror docs in `docs/skills/`) are becoming the standard agent↔tool
interface — each skill = trigger + procedure + numeric verification [C1 — repos + repo skills README]
[3, 18, 22, 24]
- **Consumer-agent integrations**: ChatGPT can drive partner video tools (e.g. CapCut GPT-style integrations
assemble clips from prompts); Sora editor (web/iOS) does frame-level trim, stitch/reorder, extend/reprompt —
generation-focused, not a general editing agent [C2 — official docs + secondary blog] [25, 37]
- **Honest gap**: zero public benchmarks for agentic editing (no leaderboard, no human-eval protocol, no
retention A/B); every claim is demo or anecdote. An LLM planner's edit decisions are unvalidated against
rule-based baselines (pure silence-cut + energy emphasis) — this is exactly what voxera could measure first
[C2 — absence of evidence is itself the finding] [2, 16, 27]

## Theme 4: Caption & subtitle generation pipelines

- **Canonical chain**: (1) transcribe with word-level timestamps — WhisperX forced alignment beats raw Whisper
(utterance-level, seconds-off); (2) segment words into cues; (3) style as ASS (ScriptType v4.00+, `\k`/`\kf`
karaoke tags, PlayResX 1080, `\fad` fades); (4) burn with ffmpeg `subtitles=` filter (libass). whisper.cpp
supports this natively (karaoke-ASS workflow per issues #338/#884) [C1] [4, 20, 28]
- **OSS burn-in tools**: nikhil-reddy05/auto-captions (per-word ASS, font/outline/pop/shadow controls);
bighippoman/subcap (WhisperX alignment + styling + encode in one command); m1guelpf/auto-subtitle
(whisper→srt→overlay, minimal); jurczykpawel/captions-cli ("what Submagic/CapCut Pro/Veed/Descript do — local,
zero SaaS", karaoke word highlight, pluggable render engine); prafiles/subsai (GUI+CLI over Whisper variants);
tsmdt/whisply (batch CLI, Zenodo DOI) [C1 — repos] [19, 20, 21, 23, 29, 30]
- **Kinetic typography**: CaptionsPlease (Node/TS: Whisper word timing + GPT-4o emphasis-word detection +
Remotion animated word pop-in, green highlights — TikTok style); Araon/Steno (local kinetic-typography
captions, React/Remotion); rendobar `captions.animate` API — $0.10/min, presets named after viral styles
(hormozi/mrbeast/tiktok/pill), whisper.cpp→ASS→ffmpeg server-side. Remotion (React→MP4) is the main
alternative to libass for complex animation [C1 repos; C2 for "viral style" naming — marketing] [31, 32, 33]
- **Translation-augmented**: VideoCaptioner (transcribe → LLM subtitle optimization → translate → burn; CLI +
GUI + Claude Code skill); fcjr/subtool (Whisper + NLLB-200 translation + embed) — relevant for multi-language
shorts [C1 repos] [22, 34]
- **Map to voxera**: word timing is the missing dependency (faster-whisper + optional WhisperX alignment); no
caption subcommand exists in voxera's CLI today (verified: `video
info|enhance|compare|zoom|teleport|magnify|cutsilence|stabilize`, `audio lowpass|transition|riser|melody` — no
transcribe/caption). Caption rendering should stay ffmpeg/libass (ASS burn-in) to preserve the single-pass
philosophy; Remotion only if per-word in/out animation becomes a requirement [C1 — cli.py grep + repo mapping]
[4, 19, 20]

## Theme 5: Voiceover & music automation

- **TTS layers seen in OSS pipelines**: edge-tts (free, MS cloud voices — FreeFaceless), Piper (fully local —
YT_Shorts_Generator), Kokoro-82M (local — Cstrp/vml), OpenAI/ElevenLabs (paid — youtube-shorts-pipeline).
Trend: local TTS is now viable for faceless shorts; no published blind comparison vs ElevenLabs quality
[C1 repos; C2 on quality equivalence — unmeasured] [14, 15, 35]
- **Beat detection**: aubio (C library: onset/beat/tempo — the standard low-level engine, GPL-3); librosa
(Python: tempo/onset/RMS — used by beatsync-engine and aeon-music-video); ffmpeg has no built-in beat tracker.
BPM + onset lists are the inputs for cut placement [C1] [38, 39, 40]
- **Auto beat-sync editing**: Antiarin/beatsync-engine — BPM detection + bass-snap cuts, N-source alternation,
5 preset modes, any aspect ratio, ffmpeg render; ZiadAbdelkarim/beat-synced-edit — beat + energy + scene
tagging, then cuts a ready-to-post edit, ships a Claude Code skill. Pattern: **cuts quantized to a beat grid**
— the same idea as voxera's frame-grid quantization, one abstraction level up [C1 repos; C2 on output quality]
[18, 39]
- **Map to voxera (music)**: voxera `audio tonal` already implements the score layer commercial tools
approximate with licensed libraries — riser landing exactly on the cut (`--hit`), mood→mode/root/timbre table
(8 moods: hope/tension/melancholy/triumph/wonder/calm/mystery/urgency), melody under voice, minimum-movement
harmonic transitions [C1 — repo skill] [41]
- **Map to voxera (sync)**: missing pieces are (a) a music source (generated or licensed), (b) BPM/onset
detection (aubio/librosa — new dep), (c) beat-grid quantization of cuts (extends `quantize_frames`). Ducking
voice-under-music is available via ffmpeg `sidechaincompress` or volume automation driven by voxera's existing
envelope VAD output [C1 — repo skill for existing; C2 — ffmpeg capability standard, not measured here]
[38, 39]

## Theme 6: Reference architecture — raw MP4 → finished short
Suggested pipeline for voxera (stage → tool → notes). Design rules from voxera's own lessons: **one ffmpeg
pass with frame-grid-quantized cuts** (AAC encoder delay ~44 ms → `-shortest`; `gte*lt` not `between()` —
upper bound exclusive), **numeric QA per stage** (frame counts ±1, sync <20 ms, SSIM/FFT), **LLM plans, never
executes** (deterministic renderer).

```
 raw.mp4 (landscape, podcast/single-cam)
   │
   ▼ [1 ANALYZE]   voxera video info (ffprobe JSON: fps/dims/streams)
   │               voxera silence (envelope VAD 30 ms, thr=max(-50, p75-12) dBFS,
   │               breath margin 200 ms → keep/drop parts) + voxera analyze
   │               (energy envelope → emphasis windows for --auto-emphasis)
   ▼
   │ [2 TRANSCRIBE] faster-whisper (word-level JSON) + optional WhisperX
   │               forced alignment + pyannote diarization   ← NEW dep (only gap)
   ▼
   │ [3 EDIT PLAN]  LLM planner (Claude/Gemini/Ollama) reads transcript + envelope:
   │               picks hook, keep/drop spans, zoom anchors, mood per segment,
   │               riser/cut points → emits JSON edit spec (below)
   │               └─ deterministic guards: no mid-sentence cuts, gaps>trigger
   │                  (cutsilence TRIGGERS light/medium/aggressive), max clip len
   ▼
   │ [4 EFFECTS]    voxera video zoom (grow, curve 62, anchor, --auto-emphasis)
   │               voxera video magnify · teleport (DeepLabV3 plate) · stabilize
   │               voxera audio lowpass (cutoff 800 Hz, S ramps) · audio tonal
   │               (riser hits cut, mood table hope/tension/...)
   ▼
   │ [5 CAPTIONS]   word JSON → cues → ASS karaoke (\k) → ffmpeg subtitles=
   │               (libass burn-in; kinetic pop-in optional via \kf + \fad)
   ▼
   │ [6 RENDER]     ONE ffmpeg pass: select/aselect with gte*lt terms,
   │               setpts=N/fps/TB + asetpts=N/SR/TB (A/V quantized to same
   │               frame grid), libx264 CRF 18 + AAC 192k + -shortest;
   │               9:16 via crop/pad (or zoompan reframe for subject track)
   ▼
   │ [7 QA]         ffprobe: container dur == Σ quantized parts (±1 frame);
   │               A/V sync < 20 ms; per-effect numeric checks (SSIM for zoom,
   │               FFT for lowpass/tonal, frame counts for cutsilence)
   ▼
 short.mp4 (9:16, captioned, scored, metrics-ready)
```
Edit-spec contract between LLM planner and executor (keeps the agent honest — everything the LLM says must be
executable by existing voxera subcommands):

```json {
  "version": 1,
  "source": "raw.mp4",
  "keep_spans": [[0.0, 8.4], [9.1, 31.2]],      // frame-quantized by executor
  "hook": {"type": "zoom-grow", "at": 0.0, "pct": 35, "curve": 62},
  "effects": [
    {"cmd": "video zoom", "args": {"anchor": [0.58, 0.24], "dir": "grow", "at": [12.0, 16.0]}},
    {"cmd": "audio riser", "args": {"mood": "tension", "hit": 31.2}},
    {"cmd": "audio melody", "args": {"mood": "hope", "from": 4.0, "to": 8.4}}
  ],
  "captions": {"style": "karaoke-word", "highlight": ["hook", "CTA"]},
  "target": {"aspect": "9:16", "max_dur": 45, "crf": 18} }
```
Mapping to voxera components (grounded in repo): stages 1/4/6/7 map onto existing subcommands (`video info`,
`video cutsilence|zoom|magnify|teleport|stabilize`, `audio lowpass|transition|riser|melody`, `analyze`) with
verified numeric QA conventions from the skill docs; stage 2 is the only new dependency (faster-whisper fits
the existing `[video]` extra pattern in pyproject.toml); stage 3 is a thin LLM layer that emits the same
declarative plan `--dry-run` already prints (VOXERA PLAN). Each OSS pipeline surveyed (FreeFaceless,
YT_Shorts_Generator, ai-video-editor, beatsync-engine) instantiates this same skeleton with weaker QA — none
publish frame/sync verification [C1 — mapping derived from repo files; C2 — cross-tool comparison]
[14, 15, 12, 18]

- **Dependency delta (small)**: faster-whisper or whisper.cpp + (optional) WhisperX alignment + pyannote;
aubio or librosa only if beat-sync stage is added. Everything else already in repo
[C1 — pyproject.toml + cli.py] [4]
- **Evaluation loop (metrics-optimized short)**: the pipeline's output must be judged on platform metrics
(hook retention, completion rate) — A/B the LLM-planned edit vs the pure rule-based edit (cutsilence +
auto-emphasis) on the same source; no public data exists to predict which wins, so this is the first
experiment to run [C2 — no external evidence; design recommendation] [2]
- **Cost profile**: local pipeline ≈ electricity + storage (GPU optional; CPU viable for <10-min sources with
int8 faster-whisper); commercial equivalent ≈ $15-30/mo per seat + per-minute credits, watermarked free tiers
[C2 — pricing pages + repo deps] [6, 7, 8]

## Conflicts & open questions

- **"ktool" identity unresolved**: no verifiable OSS video-caption tool named ktool found; task's reference
likely conflates auto-subtitle/captions-cli/VideoCaptioner. Verify before citing further [C3]
- **Vendor claims vs measured**: only two same-input/timed tests found (tech-distilled n=1 video across 5
tools; AI Hustle Guy timed workflows) — single bloggers, no engagement metrics; all "viral moment" accuracy
claims unverifiable [C2]
- **No benchmark for agentic editing quality**: no leaderboard, no human-eval, no retention A/B for
LLM-planned edits; unknown whether LLM planning beats rule-based (cutsilence + energy emphasis) for watch-time
— must be measured in-project [C2 — absence of evidence]
- **Commercial pricing model**: all SaaS is subscription/credit-per-minute with watermarked free tiers; API
costs scale linearly (e.g. captions.animate $0.10/min) — OSS local pipeline has ~zero marginal cost but needs
GPU or slower CPU inference [C1 pricing pages; C2 inference] [6, 7, 8, 33]
- **Whisper hallucination on silence** is real (C1, WhisperX README); VAD gating (WhisperX, and voxera's
envelope VAD) mitigates — caption stage must reuse the silence map, not re-detect independently [C1] [4]
- **Sync risk in multi-effect chains**: stacking effects (zoom + cutsilence + captions) without frame-grid
quantization drifts A/V (voxera measured AAC delay ~44 ms; sync verified 4-16 ms in practice); single-pass
ffmpeg is mandatory, per stage 6 [C1 — repo skill data] [41]
- **Diarization licensing**: pyannote speaker-diarization models require accepting HuggingFace gating terms
(user agreement) — a legal/ops check for the pipeline; diarization is optional for single-speaker content
[C1 — known constraint; verify current terms] [4]
- **Date/venue caveats**: arXiv 2606.23327v1 (VideoAgent) and several 2026-dated sources are very recent
preprints/blog posts — treat as emerging, verify claims before building on them [C2]

## Source list

1. Nesyona — "Best AI Video Editing Tools 2026" (comparison roundup) — article — n.d. (accessed 2026) —
https://nesyona.com/articles/best-ai-video-editing-tools-2026
2. tech-distilled-blog — "5 AI Clip Tools, 1 Video: Speed, Quality, and Workflow Compared" (same-input
measured test, 54-min video, 5 tools) — blog/measured — n.d. —
https://www.tech-distilled-blog.com/5-ai-clip-tools-1-video-speed-quality-and-workflow-compared/
3. WyattBlue/auto-editor — GitHub repo (read: README + structure, 4 agent skills, exports FCP/OTIO) — open
source — accessed 2026 — https://github.com/WyattBlue/auto-editor
4. m-bain/whisperX — GitHub repo + paper — open source + arXiv 2303.00747 — accessed 2026 —
https://github.com/m-bain/whisperX (paper: https://arxiv.org/abs/2303.00747)
5. OpusClip homepage ("ClipAnything", "ReframeAnything", API, brand templates) — vendor page — n.d. —
https://www.opus.pro/
6. OpusClip pricing ($15/$29/mo, Business custom) — vendor pricing — n.d. — https://www.opus.pro/pricing
7. Descript pricing (Hobbyist $16-24, Creator $24-35, Business $50-65) — vendor pricing — n.d. —
https://www.descript.com/pricing
8. CapCut — "Standard vs Pro" comparison ($19.99/mo, $179.99/yr) — vendor page — n.d. —
https://www.capcut.com/resource/capcut-standard-vs-pro
9. AI Hustle Guy — "Best AI Video Editor 2026: Descript vs CapCut vs Opus Clip" (timed workflow test: 28 min /
18 min / ~4 min) — blog/measured — n.d. —
https://www.aihustleguy.com/blog/descript-vs-capcut-vs-opus-clip-ai-video-editor
10. sysulq/jumpcutter — GitHub (opencv silence jump cutter, carykh-inspired) — open source — n.d. —
https://github.com/sysulq/jumpcutter
11. maxmakesmagic/autoeditor — GitHub (ffmpeg dead-air cutter, crossfades) — open source — n.d. —
https://github.com/maxmakesmagic/autoeditor
12. beenotung/silencecut-ffmpeg — GitHub (pure ffmpeg silence removal) — open source — n.d. —
https://github.com/beenotung/silencecut-ffmpeg
13. Descript changelog + blog — "The New Underlord (beta)", "How We Trained AI to See What's in Videos",
"Underlord Got a Model Picker (Claude Sonnet 4.5)" — vendor changelog/blog — 2025-07 —
https://descript.canny.io/changelog/the-new-underlord-now-on-for-everyone-beta ·
https://descript.com/blog/article/underlord-ai-can-watch-videos ·
https://descript.com/blog/article/underlord-got-a-model-picker-and-claude-sonnet-45
14. nils44344/FreeFaceless — GitHub (free self-hosted faceless shorts:
Groq→edge-tts→faster-whisper→Pexels→ffmpeg→YT upload) — open source — n.d. —
https://github.com/nils44344/FreeFaceless
15. HernadiB/YT_Shorts_Generator — GitHub (local: Ollama, Piper, WhisperX, Pillow, ffmpeg) — open source —
n.d. — https://github.com/HernadiB/YT_Shorts_Generator
16. UniVA — "Universal Video Agent" — arXiv 2511.08521 — preprint — n.d. — https://arxiv.org/html/2511.08521
17. yeates/Aurora — GitHub (agentic video-editing framework, tool-using VLM, MIT) — open source — n.d. —
https://github.com/yeates/Aurora
18. ZiadAbdelkarim/beat-synced-edit — GitHub (beat/energy/scene analysis + Claude Code skill) — open source —
n.d. — https://github.com/ZiadAbdelkarim/beat-synced-edit
19. jurczykpawel/captions-cli — GitHub (local Whisper + libass kinetic karaoke captions, zero SaaS) — open
source — n.d. — https://github.com/jurczykpawel/captions-cli
20. nikhil-reddy05/auto-captions — GitHub (per-word ASS burn-in, styling controls) — open source — n.d. —
https://github.com/nikhil-reddy05/auto-captions
21. bighippoman/subcap — GitHub (WhisperX forced-alignment caption pipeline) — open source — n.d. —
https://github.com/bighippoman/subcap
22. WEIFENG2333/VideoCaptioner — GitHub (transcribe→optimize→translate→burn; CLI+GUI+Claude Code skill) — open
source — n.d. — https://github.com/WEIFENG2333/VideoCaptioner
23. m1guelpf/auto-subtitle — GitHub (whisper + ffmpeg subtitle overlay) — open source — n.d. —
https://github.com/m1guelpf/auto-subtitle
24. openai/skills — GitHub (curated agent skills incl. Sora API skill) — open source — n.d. —
https://github.com/openai/skills
25. OpenAI Help Center — Sora Release Notes (Sora editor: trim, stitch, reorder, extend) — official docs —
2025 — https://help.openai.com/en/articles/12593142-sora-release-notes
26. CutFast blog — "AI Video Editor Comparison 2026" (free-tier/pricing table) — vendor blog — n.d. —
https://cutfa.st/en/blog/ai-video-editor-comparison-cutfast-capcut-descript-opus-clip-2026
27. VideoAgent — "All-in-One Framework for Video Understanding and Editing" — arXiv 2606.23327v1 — preprint —
n.d. — https://arxiv.org/html/2606.23327v1
28. ggml-org/whisper.cpp — GitHub repo + issue #884 (karaoke-ASS output workflow: word timestamps → `\k` tags)
— open source — n.d. — https://github.com/ggml-org/whisper.cpp/issues/884
29. prafiles/subsai — GitHub (subtitle generation Web-UI + CLI, Whisper variants) — open source — n.d. —
https://github.com/prafiles/subsai
30. tsmdt/whisply — GitHub/PyPI (batch transcription CLI, Zenodo DOI) — open source — n.d. —
https://github.com/tsmdt/whisply
31. ozten/CaptionsPlease — GitHub (Whisper + GPT-4o emphasis + Remotion kinetic captions) — open source — n.d.
— https://github.com/ozten/CaptionsPlease
32. Araon/Steno — GitHub (local kinetic-typography captioning, Remotion) — open source — 2026-01 —
https://github.com/Araon/Steno
33. rendobar docs — "captions.animate" job type ($0.10/min, hormozi/mrbeast/tiktok/pill presets,
whisper.cpp→ASS→ffmpeg) — API docs — n.d. — https://rendobar.com/docs/job-types/captions-animate
34. fcjr/subtool — GitHub (Whisper + NLLB-200 translate + embed) — open source — n.d. —
https://github.com/fcjr/subtool
35. Cstrp/vml — GitHub (ffmpeg + Whisper.cpp + Kokoro TTS + Pexels, REST API) — open source — n.d. —
https://github.com/Cstrp/vml
36. akularya6-del/ai-video-factory-public — GitHub (serverless GitHub Actions shorts pipeline, $0/mo) — open
source — n.d. — https://github.com/akularya6-del/ai-video-factory-public
37. MyAiCave — "ChatGPT Video Creation: Free Step-by-Step Guide" (CapCut GPT-style integrations) — blog — 2025
— https://myaicave.com/chatgpt-video-creation-free-guide/
38. aubio/aubio — GitHub (onset/beat/tempo C library) — open source — n.d. — https://github.com/aubio/aubio
39. Antiarin/beatsync-engine — GitHub (librosa BPM, bass-snap cuts, ffmpeg render) — open source — n.d. —
https://github.com/Antiarin/beatsync-engine
40. aeon-music-video (AEON-7) — GitHub (librosa-driven audio-reactive ffmpeg editing) — open source — n.d. —
https://github.com/AEON-7/aeon-music-video
41. voxera repo skills — `research/docs/skills/*.md` (7 skills: cutsilence, grow-zoom, magnify, teleport,
video-stabilize, audio-lowpass, audio-tonal) — local repo docs — accessed 2026 — file paths in
`research/docs/skills/`
Local grounding (not web sources): `research/README.md`, `research/pyproject.toml`,
`research/src/voxera/cli.py` (subcommand inventory), `research/docs/skills/*.md` (7 skills with measured
defaults, ffmpeg expressions, numeric verification).
