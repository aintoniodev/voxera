# R1 — Short-form Editing Techniques (2024–2026)

> **Resumen ejecutivo** (ES): El corpus muestra un consenso PRÁCTICO (no académico) en 7 bloques: hook en los primeros 3 s, cortes frecuentes tipo jump-cut, subtítulos siempre (estilo cinético), música "beat-synced", zooms/punch-ins de énfasis, formato 1080×1920 respetando safe zones por plataforma, y estructura de retención (open loops + loops). La única evidencia experimental revisada por pares cubre jump-cuts (seamless vs overlapping, N=242) y cámara lenta (Journal of Marketing). El resto son guías de creadores con cifras a menudo no verificables (varias marcadas [C3-flagged]). voxera ya cubre cutsilence, zoom grow/pulse, magnify, teleport, stabilize y audio tonal (transition/riser/melody/lowpass), todos verificados numéricamente contra tutoriales de Premiere; sus gaps principales son subtítulos/captions, slow-motion (único efecto con apoyo académico), safe zones y cualquier análisis de retención/loop. Este note alimenta la síntesis "raw MP4 → short optimizado por métricas". Recomendación inicial para el orquestador: los gaps de mayor ROI son captions/subtítulos (obligatorios en la práctica) y slow-motion (único efecto con evidencia académica); validar cualquier receta de pacing con métricas propias de retención, no con cifras de blogs.

## Method

12 web searches (2 batches × 6 queries) covering: hooks/retention data, vertical-video pacing rules, kinetic captions, beat-sync music editing, retention-curve/thumb-stop metrics, and safe-zone specs. Full page content fetched for 6 URLs (FYPNow data study, Kudoflix practitioner guide, Hootsuite industry blog, JAT academic paper, SmoothyEdit and Blitzcut safe-zone guides); abstract-level evidence used for the remaining academic papers. Source mix by type: **9 peer-reviewed/academic** (conference & journal papers, one NIH-indexed review: sources 1–9), **7 industry** (Hootsuite, Later, SaliencyLab, SociaVault, Vidmob, TechCrunch, Facebook Business Help: sources 10–17), **~20 practitioner/creator-tool** (Kudoflix, Blitzcut, ByteCap, OpusClip, Kapwing, influencers-time, Clipspeed, vidio.ai, Canva, A.V. Mapping, etc.: sources 18–39). Honest caveats: (a) "best practices" here are overwhelmingly practitioner lore — only jump-cut style/frequency and slow motion have experimental evidence; (b) several popular statistics (71% decide in 3 s; 40–60% retention lift) cite unverifiable "internal/agency studies" and are flagged; (c) most data is TikTok-centric; Reels/Shorts differences are less measured. Confidence tags: [C1] ≥3 sources, [C2] 2 sources, [C3] single source, [C3-flagged] single unverifiable source, [C3-local] single local (voxera-measured) source. All bullets cite source numbers from the list at the end.

## Theme 1: Hook & first 3 seconds

- Platforms measure the opening differently: TikTok counts a view at ~1 s of playback and its Creative Center computes "hook rate" on **6-second views**, while Meta's thumb-stop ratio is a **3-second stay** (industry analytics [C2] 13, 14, 15). Editing the open deliberately changes which metric you win.
- Retention curves drop steepest in the opening seconds; the "decision window" is quoted as **0–3 s** (a YouTube-hook data analysis claims 71% of viewers decide to stay/leave in the first 3 s [C3] 28), or even **1–2 s** per a 2026 hook guide [C3] 27. Multiple practitioner sources converge on "first 3 s decide the swipe" [C1] 15, 27, 28, 34, 35.
- Recurring hook structures with examples: **contradiction** ("You've been doing this wrong"), **curiosity gap** ("Here's what nobody tells you about X"), **result-first** (finished outcome in frame one, then explain), **bold claim** — per practitioner roundups [C2] 19, 34, 35.
- **Measured counter-datum**: FYPNow's corpus (median hook resolution 3.0 s; hooks resolving in 4–6 s save at 1.34% vs 0.69% for 2–3 s) contradicts "resolve the hook instantly" advice — the source itself flags it as correlational, confounded by length and creator house style [C2] 18.
- **Open-loop hook**: opening an information gap at the hook and delaying resolution through the video maps onto the Zeigarnik effect; this is the most-cross-referenced cross-platform retention device at script level [C2] 29, 30 (the psychology is classic; the short-form application is practitioner lore).
- Sound-off audit: the hook must read with sound muted — "add a text overlay stating the claim in the first 3 s" if the open isn't visually obvious (pre-publish checklist [C3] 19).
- **Sources:** 13, 14, 15, 18, 19, 27, 28, 29, 30, 34, 35.

**voxera coverage:** Missing. No hook analysis, no opening-second metric. Closest primitives: `video cutsilence` trims lead-in silence (default `--keep 0.15 s`) so the open starts on speech; `audio riser --hit` can land a musical hit at the hook. Gap: opening-3-s analysis, retention-curve feedback, text-overlay hook automation.

## Theme 2: Pacing & cut density (jump cuts, cut-on-action, b-roll inserts)

- Jump cuts = silence-compression of talking heads; automated "remove silence" is a first-class tool feature (CapCut/Descript ecosystem) and the baseline short-form pacing move (practitioner guides [C2] 19, 33; voxera's `cutsilence` is a local re-implementation).
- **Only controlled editing experiment found**: N=242, 20 s talking-head clip, 2×3 design + unedited control. *Seamless* cuts raise **liking**; *overlapping* cuts (slight audio overlap at the cut) raise **sustained engagement** (completion/rewatch) but only at low transition frequency; higher transition frequency reduces sustained engagement overall → "match cut to KPI; don't chase speed" (conference paper with field benchmark of 50 TikToks [C2 — single experiment + measured-corpus corroboration] 1, 18).
- Industry pacing prescription: **5–7 visual changes per 10 s** (a beat ≈ every 1.5–2 s; <4 reads slow, >8 chaotic), where a "change" = cut, zoom, text in/out, or B-roll swap [C3] 19 (attributes its threshold to another tool blog; not independently verified).
- **Measured reality is looser**: median TikTok runs 29 s with 5 scenes and ~6.5 s average shot; engagement is U-shaped in scene count (1–2 scenes at 9.6% and 11+ scenes at 11.4% both beat the 3–5-scene middle at 8.4%) — "no clean more-cuts-is-better line" (measured corpus [C2] 18).
- B-roll over voiceover is the standard remedy for jump-cut/static-shot fatigue; B-roll sourcing eats 60–70% of editing time per practitioner workflow estimates; a tagged library of 150–300 clips is the suggested fix [C3] 19.
- "3-second rule": a visual or audio change every 3–4 s ("engagement dips every 3–4 s during static content") circulates widely — the 40–60% retention lift attached to it comes from unverifiable "agency internal studies" [C3-flagged] 22.
- **Sources:** 1, 18, 19, 22, 33.

**voxera coverage:** Partial. `video cutsilence` = seamless-style jump cuts, frame-accurate A/V sync (`--level light|medium|aggressive` maps to cut density; `--keep` avoids hard-zero cuts). Missing: overlapping-cut style, B-roll insertion, cut-on-action detection, a beats-per-10-s pacing metric, retention-driven rate limiting.

## Theme 3: Captions & subtitles (styled, kinetic, placement)

- Captions are near-mandatory: vertical video is consumed muted more than any other format, and caption presence is treated as a ranking factor by creator-platform guides [C2] 20, 24.
- Academic base is strong on captions generally: 100+ studies show captions improve attention, comprehension and memory (peer-reviewed review [C1] 3); a 2024 eye-tracking study shows sound-off/subtitled viewing changes comprehension, cognitive load, immersion and gaze — L1 vs L2 and sound-on/off dependent, not short-form-specific [C2] 4; captions correlate with social-video engagement in one conference study [C3] 8.
- Default style: white text + black stroke (TikTok auto-caption default), ~2–3 px outline for contrast on busy backgrounds, **60–80 pt-equivalent** on a phone, max 2–3 lines per block, never light-on-light [C2] 20, 24.
- **Styling changes engagement**: emojis + non-standard typography (no punctuation/capitalization) beat traditional subtitles on TikTok in the only caption-*style* study found — survey (N=171) + engagement metrics, University of Warsaw AVT lab, 2025 [C2] 2; consistent with style-guide practice re: platform-native playful typography [C3] 25.
- Kinetic word-by-word pop synced to speech is the dominant creator style for talking-head shorts and is *claimed* to raise retention/watch-time — practitioner claims only; no independent measurement found [C2] 25, 26.
- Timing discipline: captions should appear 1 frame after a cut and drop 1 frame before the next; drifting auto-captions read as amateur (practitioner checklist [C3] 19).
- **Sources:** 2, 3, 4, 8, 19, 20, 24, 25, 26.

**voxera coverage:** **None — the largest gap.** No subtitle/caption generation (no ASR/STT in the pipeline), no styling, no word-level timings, no safe-zone placement, and no ES-caption handling for the product's Spanish voice-first use case (the only non-English study found is Polish).

## Theme 4: Sound & music sync (beat-synced cuts, audio trends)

- Beat-synced cuts to a (trending) track are a core technique: CapCut auto-detects beats and snaps cuts, and Canva ships "Beat Sync" as a packaged one-click feature — tool-level adoption signals industry convergence on audio-led editing [C2] 31, 32.
- **Trending-audio assumption is shaky**: in FYPNow's measured corpus, original audio ≈ licensed tracks on engagement/save/share ("within rounding error") — trending sounds may drive *discovery/reach*, not *retention*, but practitioner advice rarely separates the two [C2] 18, 36, and still pushes trending audio as a reach lever [C3] 33.
- Start-of-trend detection is now a product category: A.V. Mapping's TikTok integration claims momentum-detection of rising sounds before peak (vendor claim, unverified [C3-flagged] 39).
- Music usage was one of five content characteristics (length, pacing, text overlay, format, music) studied against teen engagement/focused attention in a 100-video content analysis — descriptive, no effect sizes quoted (student journal [C3] 9).
- The editing tool landscape is baking sync-first workflows into products: Meta's "Edits" (CapCut rival) leads with sync/effects/freestyle tooling per its TechCrunch review [C3] 16.
- Audio quality bar: clean voice is one of the 10 listed "professional look" elements, and multi-track audio (music/voice/SFX independent → ducking) is a deciding tool feature in practitioner comparisons [C2] 19, 37.
- **Sources:** 9, 16, 18, 19, 31, 32, 33, 36, 37, 39.

**voxera coverage:** Strong partial. `audio transition|riser|melody` (8-mood table) provide emotional musical hits that land exactly at cut times (`riser --hit`); `melody --duck` = ducking music under voice; `lowpass` (800 Hz, S-ramps) = diegetic-space narrative shifts. Missing: beat/BPM detection from an existing track to schedule cuts, trending-sound selection, music library integration.

## Theme 5: Effects & motion (zooms, punch-ins, magnify, transitions, stabilization)

- Zoom/punch-in on emphasis counts as a pacing "beat" and is the default emphasis move in talking-head shorts — not just a cut [C2] 19, 22.
- **Slow motion measurably increases virality** (likes/views) and brand liking/choice via processing fluency — Journal of Marketing experiment; notably absent from most practitioner "what works" lists (niche/context dependence untested) [C2 — single strong study + practitioner silence] 5.
- Magnify/loupe "teaching zoom" is an established tutorial-era effect — replicated and numerically verified in voxera against a Premiere 26.x tutorial (@billycreative_) [C3-local] voxera-magnify.md.
- Stability is a "professional" marker: handheld shake is an amateur tell and Warp-Stabilizer-style smoothing is table stakes (practitioner production-elements list [C3] 37; voxera replicates Smooth Motion with guards — local).
- Reframing horizontal footage: static center crops read amateur — track the subject instead; face/eyes in the upper-middle third [C2] 20, 33.
- Transition restraint: heavy "template" transitions are discouraged; hard cuts + zoom pushes + text entrances dominate observed best-practice edits; a "visual change" can be a zoom or text event, not necessarily a cut [C2] 18, 19.
- **Sources:** 5, 18, 19, 20, 22, 33, 37 + local voxera-magnify.md.

**voxera coverage:** Substantial — `video zoom` (grow/shrink/pulse, anchor, S-curve 60–65, voice-peak auto-emphasis), `video magnify` (voice-driven circular lens, YUV-clean pipeline), `video teleport` (2-2-2 glint + LaMa plate), `video stabilize` (guarded smooth-motion, shake verified −50 to −90%). Missing: **slow motion** (only academically supported effect), glitch/pop-in text, cut-on-action/scene-change detection.

## Theme 6: Format & layout (safe zones, aspect ratio, text safe margins)

- Format standard: **1080×1920, 9:16, MP4** across TikTok in-feed, Reels and Shorts [C2] 10, 11 (voxera's own output target per docs/README). Shooting/editing vertical from the first frame beats cropping horizontal [C2] 20, 33.
- UI safe zones differ per platform but share geometry: right ~15–20% width = engagement column; bottom ~25–30% = caption/username/description strip (Shorts bottom ~25% + right column; Reels/TikTok bottom ~25–30%); top strips = nav [C1] 20, 21, 23 (three practitioner safe-zone guides, mutually consistent).
- A universal center-safe box of ≈ **900×1160 px** on a 1080×1920 canvas is proposed so captions survive all three platforms [C2] 23 (corroborated by 20).
- Only platform-primary source found: Facebook/Meta Business Help defines a safe zone for text and logo overlays in Stories/Reels ads (official guidance [C2] 17, 21).
- Text margins: top ~15% and bottom ~15% are dead zones; keep must-read content ≥~250 px from frame edges; right ~150 px (TikTok/Reels) is reserved for engagement icons [C2] 20, 21.
- Length sweet spot is contested: classic guidance 20–35 s (Hootsuite [C2] 10, 19); measured corpus shows save rate *climbing* with length (0.63% <15 s → 1.29% at 60–120 s, engagement flat ~9–10%) [C2] 18.
- **Sources:** 10, 11, 17, 18, 20, 21, 23, 33.

**voxera coverage:** `video enhance` upscales to 1080×1920@30 (spec target; CUDA; ~1 compute-min per media-min measured on RTX 2060). Missing: safe-zone overlays/grids in the UI, 16:9→9:16 reframing with subject tracking, text-margin validation, per-platform layout presets.

## Theme 7: Retention-driven structure (loops, open loops, pattern interrupts)

- **Open loops**: unresolved question/tension opened at the hook and resolved at the end — the top script-level retention device across platforms, classically grounded in the Zeigarnik effect [C2] 29, 30.
- **Loop/rewatch design**: making the ending feed seamlessly back into the first frame invites replays; "check the loop point before publishing" is standard Shorts/Reels advice [C2] 19, 29.
- **Pattern interrupts**: engagement dips ~every 3–4 s during static content; changing the visual or audio rhythm on that cadence is the standard palliative — the quantified 40–60% retention claim is unverifiable "internal study" lore [C3-flagged] 22, 27.
- Scheduling values: median first value lands at ~5.5 s and median CTA at ~25.7 s (measured corpus [C3] 18); practitioner rule = reveal/payoff before the 60% mark (e.g., before 18 s of a 30 s video) [C3] 19; payoff "holds" of 3–4 s are exempt from pacing pressure [C3] 19.
- Retention (avg % watched / completion + rewatch) is described as the primary amplification signal across platforms, but the *measured* definitions differ (TikTok hook rate on 6 s views vs Meta thumb-stop at 3 s) so which structure "counts" is platform-dependent [C2] 13, 18, 36.
- Honest gap: no peer-reviewed study directly tests loops, open loops, or pattern interrupts on short-form retention — all practitioner lore layered on classic psychology [C2 for lore breadth; evidence absent — stated].
- **Sources:** 13, 18, 19, 22, 27, 29, 30, 36.

**voxera coverage:** None structural. Closest primitives: `zoom --pulse --auto-emphasis` inserts visual pattern interrupts at voice-energy peaks; `audio riser --hit` lands a musical interrupt at an arbitrary cut; `cutsilence` tightens overall structure (completion benefit plausible but untested). Missing: loop-point detection, open-loop scripting, per-frame retention analytics.

## Conflicts & open questions

- **Instant hook (0–3 s) vs measured 4–6 s hooks**: FYPNow shows slower-resolving hooks save *more*; practitioner dogma says resolve in 1–3 s. Correlational confounds (length, house style) make this unresolvable from public data. Open: what exactly counts as "hook resolution" technically?
- **Cut density**: "5–7 visual changes/10 s" (practitioner) vs the N=242 experiment showing high transition frequency *reduces* sustained engagement, plus U-shaped measured scene counts. Both cannot be simultaneously optimal; the experiment measured perceived outcomes in a viewer survey, not on-platform retention.
- **Trending audio**: practitioner consensus says required; measured corpus shows no engagement difference original-vs-licensed. The discovery vs retention confound was never separated.
- **Kinetic captions**: ubiquitous in practice; the only academic style finding (2025, Polish participants) covers emojis/no-punctuation, not word-by-word motion. Over-engineering risk unmeasured.
- **Slow motion**: strong academic effect, absent from practitioner lists — likely niche/context dependence (dance/ASMR vs talking-head) untested.
- **Data quality**: many practitioner "statistics" (71% decide in 3 s, 50% lost in first 10 s, 40–60% retention lift) have no verifiable primary source. "Internal/agency studies" tier = flagged, never C1.
- **Safe zones drift**: third-party figures differ somewhat from Meta's official help; platform UI changes over time, so safe-zone constants need periodic re-validation (e.g., Shorts right column, TikTok bottom nav).
- **2026 platform shift**: commentary reports watch time up ~20% YoY while completion falls, and AI-curated feeds (TikTok ads hook rate) may re-weight which edits matter — no primary data captured in this note.
- **Language bias**: nearly all evidence is English-language content; the only non-EN caption study is Polish. Nothing found for Spanish-language caption styling or ES kinetic typography — relevant to voxera's Spanish-first positioning.
- **ES-niche gap**: no evidence found that these techniques generalize to the project's actual content class (voice/podcast talking-head verticals) as opposed to dance/trend-driven content.

- **Vendor-blog clustering**: most practitioner sources are AI-tool/creator-tool blogs (Kudoflix, Blitzcut, ByteCap, Clipspeed, vidio.ai, TokCount, influencers-time, Lomero…) with a commercial interest in selling editing tools; content is SEO-motivated and overlaps heavily — they behave as one correlated cluster, not independent evidence, so [C1] from practitioner guides alone is weak.
- **No head-to-head platform comparison found**: nothing public tests the same edit across TikTok/Reels/Shorts; all cross-platform advice (safe zones aside) is inference from metric definitions (hook rate vs thumb-stop) and UI geometry.

- **Which metric to optimize?**: classic length advice (20–35 s) targets completion; measured corpus favors longer saves (60–120 s). The two coexist only if goals differ (reach vs saves). Open: no evidence on which metric best predicts follower growth — decide for voxera before tuning.

## Source list

Peer-reviewed / academic (1–9):
1. Dost, S. & Huang, S. (2026). "Jump Cut Editing Style and Transition Frequency Differentially Affect Interactive and Sustained Engagement in Short-Form Video." Marketing Trends Congress 2026 proceedings — [peer-reviewed conference; field benchmark of 50 TikToks + 2×3 experiment N=242].
     https://archives.marketing-trends-congress.com/2026/pages/PDF/paper_professor_DOST_HUANG.pdf
2. Duraj, K. & Szarkowska, A. (2025-04-11). "Beyond Traditional Subtitles: How Emojis and Non-Standard Typography in Subtitles Boost Engagement on TikTok." *Journal of Audiovisual Translation* 8(1) — [peer-reviewed journal]. DOI 10.47476/jat.v8i1.2025.339.
     https://www.jatjournal.org/index.php/jat/article/view/339
3. Gernsbacher, M.A. (2015). "Video Captions Benefit Everyone." *Policy Insights from the Behavioral and Brain Sciences* 2(1) — [peer-reviewed review].
     https://pmc.ncbi.nlm.nih.gov/articles/PMC5214590/
4. PLOS ONE (2024). "Watching subtitled videos with the sound off affects viewers' comprehension, cognitive load, immersion, enjoyment, and gaze patterns" — [peer-reviewed journal, eye-tracking]. DOI 10.1371/journal.pone.0306251.
     https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0306251
5. *Journal of Marketing* (online 2023). "The Art of Slowness: Slow Motion Enhances Consumer Evaluations by Increasing Processing Fluency" — [peer-reviewed journal, experiments]. DOI 10.1177/00222437231179187.
     https://journals.sagepub.com/doi/full/10.1177/00222437231179187
6. "Slapping Cats, Bopping Heads, and Oreo Shakes: Understanding Indicators of Virality in TikTok Short Videos." (2022). ACM WebSci '22 — [peer-reviewed conference, mixed-method virality codebook]. DOI 10.1145/3501247.3531551.
     https://dl.acm.org/doi/fullHtml/10.1145/3501247.3531551
7. "Like, Comment, and Share on TikTok: The Effect of Sentiment and Second-Person View on User Engagement with TikTok News Videos." (2023). *Social Science Computer Review* — [peer-reviewed; 101,292 videos]. DOI 10.1177/08944393231178603.
     https://journals.sagepub.com/doi/full/10.1177/08944393231178603
8. Atlantis Press (2023). "Social Media Engagement: Can Video Captions Increase User Engagement?" ICEDBC 2023 — [peer-reviewed proceedings]. DOI 10.2991/978-94-6463-246-0_12.
     https://www.atlantis-press.com/proceedings/icedbc-23/125991294
9. Sheynin, R. (n.d., accessed 2026). "Quick, Stop Scrolling: Impact of Short-Form TikTok Video Characteristics on Video Engagement and Teenagers' Focused Attention." *The Young Researcher* — [student journal, content analysis N=100; date undated].
     http://www.theyoungresearcher.com/papers/sheynin.pdf

Industry (10–17):
10. Hootsuite (2023). "How to Make Short-Form Videos That Stand Out" — [industry social-media blog].
     https://blog.hootsuite.com/short-form-video/
11. Hootsuite (2024). "The Complete Guide to Social Media Video Specs" — [industry; platform specs].
     https://blog.hootsuite.com/social-media-video-specs/
12. Later (2025-03-29). "12 Instagram Reels Hacks to Boost Reach and Engagement" — [industry social-media blog].
     https://later.com/blog/instagram-reels-hacks/
13. SaliencyLab (n.d., accessed 2026). "Hook rate vs thumbstop: what each platform measures" — [industry analytics research].
     https://www.saliencylab.com/hubs/creative-analysis/hook-rate-vs-thumbstop
14. SociaVault (n.d., accessed 2026). "How to Use TikTok Ad Retention Curves to Optimize Your Hooks" — [industry analytics blog, TikTok Creative Center data].
     https://sociavault.com/blog/tiktok-ad-retention-curves-hook-optimization
15. Vidmob (n.d., accessed 2026). "The Science of the Hook: How Brands Can Cultivate Curiosity on TikTok" — [industry; TikTok Creative Center 6 s hook window].
     https://vidmob.com/resource/tiktok-hook-analysis
16. TechCrunch (2025-08-12). "A guide to using Edits, Meta's CapCut rival for short-form video editing" — [tech press].
     https://techcrunch.com/2025/08/12/a-guide-to-using-edits-metas-new-capcut-rival-for-short-form-video-editing/
17. Facebook Business Help (n.d., accessed 2026). "About text overlays and the safe zone for ads in Stories and Reels" — [official platform docs].
     https://www.facebook.com/business/help/980593475366490

Practitioner / creator-tool (18–39):
18. FYPNow Research (2026-08-04). "The Anatomy of a TikTok Video: Length, Hooks, Pacing and Audio" — [practitioner data study, measured corpus].
     https://fypnow.com/research/tiktok-video-anatomy
19. Kudoflix (2026-06-26). "Short-Form Video Editing Best Practices for 2026" — [practitioner/creator guide].
     https://kudoflix.com/blog/2026/06/26/short-form-video-editing-best-practices-for-2026/
20. SmoothyEdit (n.d., accessed 2026). "The Editor's Field Guide to Vertical Video" — [practitioner/creator guide].
     https://smoothyedit.com/blog/editors-field-guide-vertical-video
21. Blitzcut (2026). "Safe Zone Guide for YouTube Shorts, Reels & TikTok" — [practitioner/tool blog].
     https://blitzcutai.com/blog/safe-zones-youtube-shorts-reels-tiktok
22. Blitzcut (2026). "TikTok 3-Second Rule: Jump Cut Timing That Hooks" — [practitioner; cites unverifiable "internal studies"].
     https://blitzcutai.com/blog/3-second-rule-tiktok-jump-cuts
23. ByteCap (2026). "Short Form Video Safe Zones: UI Overlay Guide" — [practitioner/tool blog; 900×1160 px center-safe box].
     https://www.bytecap.io/blog/short-form-video-safe-zones-ui-overlays
24. OpusClip (2026). "TikTok Caption & Subtitle Best Practices" — [practitioner/AI-tool blog].
     https://www.opus.pro/blog/tiktok-caption-subtitle-best-practices
25. Kapwing (n.d., accessed 2026). "A Complete Guide to TikTok Subtitles" — [practitioner/editor-tool guide].
     https://www.kapwing.com/resources/a-complete-guide-to-tiktok-subtitles/
26. influencers-time (2026). "Kinetic Typography for TikTok: Boost Retention & Engagement" — [practitioner/marketing blog].
     https://www.influencers-time.com/kinetic-typography-boost-video-retention-on-tiktok-and-reels/
27. Clipspeed (2026). "Short-Form Video Hooks: Win the First 1-2 Seconds" — [practitioner/tool blog].
     https://www.clipspeed.ai/blog/hook-first-second-video-retention.html
28. Tukey (2026). "YouTube Hook Formula: Stop the Scroll in 3 Seconds" — [practitioner/tool blog].
     https://tukey.ai/blog/the-youtube-hook-formula-that-stops-the-scroll-in-3-seconds-here-is-the-data
29. Monitor YT (2026). "YouTube Shorts Hooks and Loops" — [practitioner/analytics blog].
     https://monitoryt.com/blog/shorts-hooks-and-loops
30. TokCount (2026). "Scripting for Retentive Attention Using the Narrative Open Loop Strategy" — [practitioner/analytics blog; Zeigarnik].
     https://tokcount.com/blog/scripting-for-retentive-attention-using-the-narrative-open-loop-strategy
31. vidio.ai (2026). "How do I auto-sync my edit cuts to a trending TikTok sound in CapCut?" — [practitioner/tool blog].
     https://www.vidio.ai/blog/article/how-do-i-auto-sync-my-edit-cuts-to-a-trending-tiktok-sound-in-capcut
32. Canva (n.d., accessed 2026). "Beat Sync — Auto Sync Audio and Video" — [industry tool feature page].
     https://www.canva.com/features/beat-sync/
33. Kompozy (2026). "How to edit vertical video for Reels, TikTok, and Shorts" — [practitioner/tool guide].
     https://kompozy.io/how-to/edit-vertical-video
34. ClickyApps (2025). "The 3–7 Seconds Rule: Editing Shorts for Retention" — [practitioner/tool guide].
     https://clickyapps.com/creator/video/guides/three-seven-seconds-rule-editing-retention
35. Lomero (n.d., accessed 2026). "Hook patterns that work on Reels, TikTok, and Shorts" — [practitioner/tool blog].
     https://www.lomero.app/blog/hook-patterns-that-work
36. Sydium (2026). "Short-Form Video Strategy Across Every Platform" — [practitioner/tool blog].
     https://sydium.com/blog/short-form-video-strategy
37. Ascynd (2026). "How to Make Vertical Videos Look Professional Without Hiring an Editor" — [practitioner/tool blog; 10 production elements].
     https://ascynd.io/en/blog/professional-vertical-video-editing
38. Kreatli (2026). "Safe Zone Hub — Instagram Reels, TikTok, YouTube Shorts Dimensions & Overlays" — [practitioner/tool blog].
     https://kreatli.com/guides/safe-zone-guide
39. A.V. Mapping (n.d., accessed 2026). "TikTok — Trend-aware audio and visual-audio sync" — [vendor tool; claims unverified].
     https://avmapping.co/en/platform/tiktok-a-v-mapping/

Local (project-measured, not web): voxera skills `voxera-cutsilence.md`, `voxera-grow-zoom.md`, `voxera-magnify.md`, `voxera-teleport.md`, `voxera-video-stabilize.md`, `voxera-audio-lowpass.md`, `voxera-audio-tonal.md` (docs/skills/) and research/README.md — effects verified frame/audio-exact against @serri.mp4 and @billycreative_ Premiere tutorials; used as [C3-local] evidence for the "voxera coverage" lines.Local (project-measured, not web): voxera skills `voxera-cutsilence.md`, `voxera-grow-zoom.md`, `voxera-magnify.md`, `voxera-teleport.md`, `voxera-video-stabilize.md`, `voxera-audio-lowpass.md`, `voxera-audio-tonal.md` (docs/skills/) and research/README.md — effects verified frame/audio-exact against @serri.mp4 and @billycreative_ Premiere tutorials; used as [C3-local] evidence for the "voxera coverage" lines.

— R1 · built from 12 web searches + 6 full-text fetches (2026); safe-zone figures require re-validation on each platform UI update —
Verificación R1: 7 temas · 39 fuentes (9 peer-reviewed / 7 industry / 23 practitioner-vendor) · tags 5×C1, 28×C2, 16×C3, 5×C3-flagged, 4×C3-local. Sin ficheros del repo modificados.
