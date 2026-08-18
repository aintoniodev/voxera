# R2 — Scientific Basis: Attention & Retention in Short-Form Video

> **Resumen ejecutivo** (ES): Base científica de por qué el vídeo corto engancha y qué parámetros de edición lo miden: (1) el corte/cambio
> visual dispara una respuesta de orientación involuntaria (Geiger & Reeves 1993; ERP), pero consume capacidad de procesamiento — los cortes
> captan atención a costa de la memoria del mensaje; (2) en anuncios, escenas cortas y visualmente simples maximizan la sincronía atencional
> y los cortes suben la atención momento a momento (JAMS 2025, 2.520 visionados/42 PSA); (3) el formato fragmentado captura atención
> bottom-up pero reduce memoria, sincronía neural y atención sostenida (Communications Psychology 2026; npj Science of Learning ×2; CHI
> 2024); (4) el arousal auditivo tiene efecto en U invertida sobre engagement y la variación visual efecto lineal positivo, con congruencia
> audio-visual como multiplicador (12.842 vídeos Douyin, MDPI 2025); (5) la cámara lenta es el único efecto de edición con apoyo
> experimental fuerte (3 papers en JMR/JM, incluido N=27.227); (6) los subtítulos mejoran atención/comprensión/memoria (revisión Gernsbacher
> 2015; eye-tracking PLOS ONE 2024), el estilo (emojis/tipografía no estándar) tiene un estudio controlado (JAT 2025), pero el estilo
> cinético palabra-a-palabra NO tiene evidencia directa de engagement; (7) el completado rara vez supera ~60% y predice mejor por duración
> (WebSci'26); 0-10 s maximiza alcance/completado, 30-90 s ~2× engagement (Fanpage Karma, N=32.000); (8) el engagement en feeds sigue
> aprendizaje por refuerzo con errores de predicción de recompensa (Nature Comms 2021) y los clips recomendados activan el área tegmental
> ventral (NeuroImage 2021). Separación estricta: evidencia peer-reviewed vs industria (etiquetada por tema). Gaps honestos: beat-sync sin
> test directo, kinetic captions sin RCT, punch-in/zoom sin base académica, sin datos en español, y tensión memoria-vs-engagement sin
> resolver para contenido educativo. Alimenta la síntesis "raw MP4 → short optimizado por métricas" junto a R1.

## Method

18 web searches across 5 batches (short-video attention/retention; TikTok engagement datasets; captions &
dual-coding; cuts & cognitive load; slow motion & virality; video length/completion; variable rewards & infinite
scroll; music tempo & neural entrainment; voice prosody; visual saliency). Full-text fetched for 12 primary
pages (Nature Communications Psychology, npj Science of Learning ×2, Springer/JAMS, MDPI JTAER, Frontiers in
Psychology ×2, Fanpage Karma, MPIDR/WebSci, CBS/ICIS, alphaXiv mirror); ACM DL full-text was bot-blocked, so the
CHI '24 data-donation paper was verified via its alphaXiv mirror + SIGCHI program page. Search-level
(abstract/snippet) evidence used for the remaining classics (Geiger & Reeves 1993, Loewenstein 1994, Carmi &
Itti 2006, eLife, PNAS).

Source mix: **41 peer-reviewed/academic** (journals: JMR ×3, JAMS, Journal of Marketing, Communication Research,
Nature Communications, NeuroImage, Communications Psychology, npj Science of Learning ×2, PNAS, eLife, Vision
Research, Cognitive Science, Media Psychology, PLOS ONE, JAT, MDPI ×2, Scientific Reports, Healthcare;
conferences: CHI ×3, WebSci '26, ICIS, ICEDBC, Atlantis, Springer LNCS; classic theory) and **10 industry**
(Wistia ×2, Fanpage Karma, TikTok Calculator, FYPNow, SaliencyLab, Vidmob, Kapwing, influencers-time, Canva).
Cross-refs to R1: R1#1 (jump-cut experiment N=242), R1#18 (FYPNow corpus = source 45 here), R1#19 (Kudoflix),
R1#22 (Blitzcut), R1#31/32 (beat-sync tools), R1#34/35 (hook roundups).

Confidence tags: [C1] ≥3 sources incl. ≥1 peer-reviewed; [C2] 2 sources or 1 strong (large-N peer-reviewed);
[C3] single source (peer-reviewed or industry, labeled). Peer-reviewed and industry claims are labeled inline in
every bullet, and each theme ends with an explicit academic-vs-industry accounting line. N or effect sizes are
reported whenever the source reports them. Gaps are stated as gaps, never filled with inference.

## Theme 1: The first seconds — attention capture & the hook window

- **Change triggers involuntary orienting** — the neurocognitive base of "hook by change": cuts/sudden transitions elicit an orienting
  response; EEG/ERP work shows the brain discriminates *related* vs *unrelated* cuts (peer-reviewed [C2] 4, 5). Unrelated cuts raise visual
  attention but deplete processing capacity → worse message memory; related cuts preserve memory (peer-reviewed classic experiment [C2] 4).
- **Hook windows are platform-metric definitions, not universal truths**: TikTok hook rate is measured on 6-second views; Meta's thumb-stop
  ratio is a 3-second stay (industry analytics [C2] 46, 47). The "decide in 1–3 s" framing is industry lore built on these definitions; no
  peer-reviewed study tests hook-resolution timing on a live feed.
- **Curiosity gaps are the best-supported hook mechanism in the literature**: Loewenstein's information-gap theory — curiosity arises when
  attention focuses on a gap in knowledge (peer-reviewed classic [C2] 37); 5 experiments on incomplete game ads show information gaps drive
  interest via a curiosity drive (peer-reviewed [C2] 38). Practitioner hook recipes (contradiction, result-first, bold claim) are lore
  layered on this base (industry [C3] 45; R1#34,35).
- **Feed viewing is fast and fragmented**: gaze in news feeds shows fragmented attention with Weibull-distributed item visit times
  (peer-reviewed [C3] 40); 20 s of Facebook-feed browsing carries stable, individual gaze signals (N=180, peer-reviewed [C3] 39). Field
  data: TikTok users' attention stays ≈45% stable across their lifetime while daily usage grows (peer-reviewed, 347 users / 9.2M
  recommendations [C2] 26).
- **First-seconds loss is measurable but proportionally small for short videos**: Wistia's retention anatomy puts the average "nose" drop at
  4.9% for 1–2 min videos vs 17.3% for 5–10 min (industry, 564,710 videos / 1.3B plays [C2] 41, 42). Measured counter-datum: hooks resolving
  at 4–6 s save at 1.34% vs 0.69% for 2–3 s — correlational, confounded by length and house style (industry corpus [C2] 45).
- **Sound-off first second**: the hook must read visually because feed autoplay is often muted — practitioner pre-publish rule (industry
  [C3] R1#19), consistent with peer-reviewed evidence that sound-off subtitled viewing is a distinct comprehension state (peer-reviewed [C2]
  32).
- *Academic vs industry*: orienting-to-change and curiosity-gap mechanisms = peer-reviewed; every specific hook-window number (1–3 s, 6 s, 3
  s) and hook-recipe taxonomy = industry.
- **→ voxera:** opening-second analysis and curiosity-gap (open-loop) checks are missing primitives; `audio riser --hit` and `zoom --pulse`
  at t≈0 are the natural orienting triggers; the first content beat should land ≤1 s after frame 1 (industry-consistent; academically
  untested). Retention-curve feedback would let the hook window be validated on own metrics instead of borrowed lore.
- **Sources:** 4, 5, 26, 32, 37, 38, 39, 40, 41, 42, 45, 46, 47 + R1#19.

## Theme 2: Pacing, cut frequency & cognitive load

- **Cuts buy attention but cost capacity**: limited-capacity model — camera changes and information introduced are resource indicators
  (peer-reviewed [C2] 8); cuts trigger orienting (peer-reviewed [C2] 5); more cuts → more orienting but worse encoding (peer-reviewed [C2]
  4). "More cuts = better" has zero support for message memory.
- **In ads, cuts boost moment-to-moment attention while complexity hurts**: short and visually simple scenes maximize attentional synchrony;
  visual complexity exerts a *delayed negative* effect on attention; scene cuts boost attention; synchrony in turn drives immersion, ad
  liking, and recognition (peer-reviewed, 2,520 viewing experiences / 42 PSAs, time-series + eye-tracking [C2] 7).
- **Editing density distorts perceived time**: more cuts compress subjective duration, mediated by eye-movement dynamics (N=70, 9 clips, cut
  count manipulated, peer-reviewed [C3] 9) — denser pacing can make a short video *feel* shorter, a plausible mechanism behind watch-time
  gains.
- **Editing reduces cognitive load but fragments attention and emotion**: in an immersive-film experiment, the unedited version had the
  highest visual attention (TDF M=18,953.83 vs edited, p<.001) and 75% of viewers rated it "highly immersive"; dissolve transitions lowered
  enjoyment (APD M=0.397 vs unedited, p<.001) (N=42, peer-reviewed [C2] 6). VR context — direction of effects may differ in 2D feeds.
- **Industry pacing recipes lack an experimental base**: "5–7 visual changes per 10 s" and the "3-second rule" are practitioner lore
  (industry [C3] R1#19, R1#22); measured corpora show engagement U-shaped in scene count (1–2 scenes and 11+ scenes both beat the 3–5
  middle) and no clean more-cuts-is-better line (industry corpus [C2] 45; R1#18).
- **The one short-form editing experiment reconciles the trade-off by KPI**: N=242 talking-head clips — seamless cuts raise *liking*;
  overlapping cuts raise *sustained engagement* (completion/rewatch) but only at low transition frequency; high transition frequency reduces
  sustained engagement (peer-reviewed [C2] R1#1).
- *Academic vs industry*: cut-orienting, capacity limits, synchrony, time perception = peer-reviewed; "changes per 10 s" thresholds, the
  3-second rule, and the 40–60% retention-lift claim = industry-only (latter unverifiable).
- **→ voxera:** `cutsilence` implements the one experimentally-adjacent pacing move (seamless silence-compression cuts, frame-accurate); add
  a transition-frequency guard to stay out of the high-frequency regime that reduces sustained engagement, and a scenes-per-10-s metric for
  measurement rather than prescription. B-roll insert points are where capacity limits bite — keep scenes simple (JAMS).
- **Sources:** 4, 5, 6, 7, 8, 9, 45 + R1#1, R1#19, R1#22.

## Theme 3: Captions & dual-coding

- **Captions benefit everyone**: 100+ studies show captions improve attention, comprehension, and memory — dual-coding (visual + verbal
  channels) is the theoretical base (peer-reviewed review [C1] 31).
- **Sound-off is a real, measurably different viewing state**: subtitled + muted viewing changes comprehension, cognitive load, immersion,
  enjoyment and gaze patterns, with L1/L2 and sound-on/off interactions (peer-reviewed eye-tracking [C2] 32); captions correlate with
  social-video engagement in one conference study (peer-reviewed [C3] 36).
- **Caption *style* measurably matters on TikTok**: emojis + non-standard typography (no punctuation/capitalization) beat traditional
  subtitles on engagement — survey N=171 + engagement metrics, University of Warsaw AVT lab (peer-reviewed [C2] 33). This is the only
  style-level experimental evidence found.
- **Kinetic word-level captions: ubiquitous in practice, unevidenced in the literature**: retention/watch-time claims come from tool vendors
  (industry [C3] 48, 49); the academic base is indirect — moving text benefits learning only when motion aligns with attention, and
  animation speed + words-per-minute change information-transmission efficiency (peer-reviewed [C2] 34, 35).
- **Captions are a serial reading task competing for gaze**: eye-tracking shows subtitle regions capture a large share of fixations during
  sound-off viewing (peer-reviewed [C3] 32); caption pace must respect reading rate or comprehension drops — temporal-typography experiments
  quantify speed/interpolation limits (peer-reviewed [C3] 34).
- *Academic vs industry*: comprehension/memory/attention benefits (31), sound-off states (32), style effects (33) = peer-reviewed;
  word-by-word kinetic retention lift = industry-only claim, no RCT found.
- **→ voxera:** captions remain the largest gap (R1 confirmed). Science supports captions as a default and style experimentation
  (emoji/no-punctuation, non-standard typography), but word-level kinetic motion should be validated on own retention metrics before
  becoming a default; ES caption handling is a product differentiator with zero academic precedent (language gap).
- **Sources:** 31, 32, 33, 34, 35, 36, 48, 49.

## Theme 4: Audio, music & emotion

- **Auditory emotional arousal is inverted-U in real short-video marketing**: moderate arousal maximizes engagement; visual variation has a
  *positive linear* effect; audiovisual congruence significantly boosts engagement — multimodal ML on 12,842 Douyin videos from 170
  influencers (peer-reviewed [C2] 10). The strongest direct evidence for audio editing levers.
- **Music tempo shifts attitudes and recall via affect**: tempo effects on ad attitudes and content recall, mediated by affective response
  (peer-reviewed [C2] 11, 12); fast-tempo music beats slow for food-ad evaluations and purchase intentions in a three-study paper
  (peer-reviewed [C3] 51).
- **The brain entrains to musical beats**: neural synchronization is strongest at beat frequency and modulated by familiarity and beat
  salience (peer-reviewed [C2] 14, 15). This is the mechanistic base for "beat-synced" edits — but **no study directly tests beat-synced vs
  random cuts on engagement or retention** (gap, stated).
- **Voice prosody drives spoken-content engagement**: lower speech rate → higher listener engagement across 10,000 audio files / 221 podcast
  albums (deep-learning feature extraction); pitch showed no moderating effect (peer-reviewed, ICIS [C2] 13) — directly relevant to voxera's
  voice-first pipeline.
- **Industry convergence is tool-level, not evidence**: beat-sync is a shipped one-click feature (Canva "Beat Sync", CapCut beat detection)
  (industry [C3] 50; R1#31,32); trending-audio advice conflates discovery with retention (industry [C2] 45; R1#36).
- *Academic vs industry*: arousal U-curve, tempo effects, entrainment, prosody = peer-reviewed; beat-sync necessity, trending-sound advice =
  industry.
- **→ voxera:** tonal primitives (riser/transition/melody, 8-mood table) map onto the arousal mechanism — target *moderate* arousal (U-curve
  peak) and check congruence between audio mood and visual pace; `melody --duck` supports the prosody finding (speech clarity over music);
  lowpass ("orejas tapadas") is an arousal/immersion shift, use sparingly. Beat detection on the user's own track remains missing (R1 gap).
- **Sources:** 10, 11, 12, 13, 14, 15, 45, 50, 51 + R1#31,32,36.

## Theme 5: Motion, zoom & visual salience

- **Motion is a causal attention attractor**: motion contrast ranks among the strongest causal saliency features in dynamic scenes
  (peer-reviewed [C2] 16); conversely, cuts can pass unnoticed ("edit blindness") when attention is already engaged (peer-reviewed [C2] 17)
  — motion/change captures attention, but only when the viewer isn't already gripped.
- **Slow motion is the best-supported editing effect in the entire literature**: increases virality (likes, views), brand liking, choice,
  and willingness-to-pay via processing fluency (JMR [C1] 18); a second JMR paper (7 studies incl. eye-tracking + Facebook Ads field
  experiment) shows slow motion shapes consumer inference (peer-reviewed [C2] 19); a third (12 experiments, N=27,227, 5 preregistered) shows
  slow motion signals luxuriousness (peer-reviewed [C2] 20).
- **Visual variation drives engagement linearly in short-video marketing** (peer-reviewed [C2] 10 — cross-ref Theme 4), while scene cuts
  boost moment-to-moment attention in ads (peer-reviewed [C2] 7 — cross-ref Theme 2). Together: dynamic visuals help, but content complexity
  within scenes hurts.
- **Zooms/punch-ins as "pacing beats" are industry lore**: no academic study isolates punch-in/emphasis-zoom effects on attention or
  retention; treat as motion-salience devices with plausible but untested orienting value (industry [C3] R1#19; gap, stated).
- **Slow motion's absence from practitioner lists is notable**: while the science is strong, creator guides rarely include it — likely
  niche/context dependence (product/dance vs talking-head) untested (conflict from R1).
- *Academic vs industry*: motion saliency, edit blindness, slow motion (×3), variation/cuts = peer-reviewed; punch-in frequency rules and
  "zoom = beat" = industry.
- **→ voxera:** slow motion is the missing academically-supported effect (R1 gap confirmed — highest-ROI new primitive, especially for
  demo/product content); zoom grow/pulse and magnify are motion-salience devices best placed at emphasis points (voice-peak auto-emphasis
  already implements this) rather than on a fixed rhythm.
- **Sources:** 7, 10, 16, 17, 18, 19, 20 + R1#19.

## Theme 6: Novelty, reward loops & addiction mechanisms

- **Social-media engagement follows reinforcement learning**: posting and engagement are predicted by reward prediction errors — likes
  function as rewards and drive subsequent behavior (peer-reviewed, Nature Communications [C2] 21); variable reward schedules and infinite
  scroll are reviewed as habit-forming design features (peer-reviewed review [C2] 23).
- **TikTok recommendations activate the dopamine system**: fMRI shows personalized recommended clips activate the ventral tegmental area
  (VTA) and default-mode network (peer-reviewed, NeuroImage [C3] 22) — the *algorithm's* personalized novelty, not the video's cuts, is the
  reward carrier.
- **Infinite scroll creates measurable "loops"**: field study N=46 documents looping behavior and categorized breakout reasons
  (peer-reviewed [C2] 24); interface design frictions reduce mindless scrolling but also satisfaction (N=30, peer-reviewed [C3] 25).
- **Short-form consumption degrades sustained attention**: survey + long-term field experiment (CHI [C2] 28); mobile short-video use
  negatively impacts attention functions (peer-reviewed [C2] 29); attention partially mediates short-form addiction → memory in youth
  (peer-reviewed [C3] 30).
- **Fragmentation captures bottom-up at the expense of top-down processing**: 3 experiments — short-video learning lowers immediate memory
  accuracy, raises forgetting, reduces neural synchrony in visuospatial-attention/episodic-memory regions while raising synchrony in
  bottom-up regions (peer-reviewed [C2] 1); N=57: fragmented viewing → poorer recall + altered retrieval connectivity (peer-reviewed [C2]
  2); acute exposure → worse event segmentation and memory for continuous movies (peer-reviewed [C3] 3).
- **Editing implications (synthesis, not measured)**: each cut is a mini-orienting event that habituates with repetition (4, 5, 7);
  variable-reward logic argues for *structured* novelty — curiosity gaps and loops — rather than maximal stimulation; over-fragmentation
  trades message retention for capture-of-the-moment (synthesis of 1, 2, 4, 7, 21).
- *Academic vs industry*: RL modeling, VTA fMRI, scroll loops, attention-deficit evidence = peer-reviewed; "dopamine hook editing" recipes
  and "3-second dopamine hit" claims = industry oversimplification — no per-cut dopamine measurement exists anywhere.
- **→ voxera:** resist "max stimulation" defaults; use orienting sparingly (emphasis points); loop-point detection for rewatch is industry
  lore with RL-theoretic plausibility only; for educational/voice content, message comprehension should be a first-class measured goal, not
  assumed.
- **Sources:** 1, 2, 3, 4, 5, 7, 21, 22, 23, 24, 25, 26, 28, 29, 30.

## Theme 7: Video length & completion

- **Completion is capped and stable**: the fraction of videos watched to the end rarely exceeds ~60% and does not improve with
  personalization; **video duration is the single strongest predictor of completion**; demographics add almost nothing (peer-reviewed,
  controlled playlist experiment + real-world TikTok data, WebSci'26 [C2] 27).
- **Platform-measured length trade-off**: 0–10 s videos get the highest reach and completion; 30–90 s get ~2× engagement vs very short or
  very long videos; 72% of TikToks are <60 s; completion declines linearly with length (industry study, N=32,000 [C2] 43). Completion
  collapses with length: ~89% at 7 s → <10% at 10 min (industry [C3] 44).
- **Hosted-video (non-feed) curves differ**: engagement ≈70% at 2 min, just above 50% by 6–7 min, then slow decline (industry, 564,710
  videos / 1.3B plays [C2] 41) — the Wistia curve is the origin of "shorter is better" lore but applies to outbound business video, not
  recommendation feeds.
- **Save/share inverts the length story**: save rate climbs with length (0.63% <15 s → 1.29% at 60–120 s) while engagement stays flat ~9–10%
  (industry corpus [C2] 45) — the length optimum is KPI-dependent; there is no universal ideal length (industry [C2] 43).
- **Platform differences are definitional before they are behavioral**: TikTok counts a view at ~1 s and hook rate at 6 s; Meta thumb-stop
  at 3 s; TikTok allows ≤10 min, Shorts ≤3 min, Reels ≤90 s — "optimal length" benchmarks are metric-relative and platform-relative
  (industry [C2] 46, 47; R1#10,11,13–15).
- *Academic vs industry*: the ~60% completion ceiling and duration-as-strongest-predictor = peer-reviewed (27); all per-length benchmark
  numbers (89%→10%, 2× engagement, 72% <60 s) = industry studies — well-documented N but self-published and unaudited.
- **→ voxera:** for voice-first talking-head shorts the 30–90 s band maximizes engagement per the largest industry dataset; the ~60%
  completion ceiling means retention *curves* (not binary completion) are the actionable optimization signal; surface watch-fraction
  analytics and make length a tunable parameter per platform target.
- **Sources:** 27, 41, 42, 43, 44, 45, 46, 47 + R1#10,11.

## Conflicts & open questions

- **Cuts: attention up vs memory down.** JAMS shows scene cuts boost attention in ads (7); Geiger & Reeves and the VR study show cuts
  fragment attention and cost capacity (4, 6). Likely reconciliation: cuts orient but impair encoding — acceptable for entertainment, costly
  for message retention. Never tested head-to-head on a TikTok feed.
- **Visual variation: linear-positive for engagement (10) vs complexity-negative for attention (7).** Different constructs (variation vs
  complexity) and outcomes (engagement vs attentional synchrony); no study pits them on-platform, so voxera should track both.
- **"Dopamine editing" is pop oversimplification.** Real evidence: RL modeling (21), VTA fMRI (22), design reviews (23). No measurement of
  per-cut dopamine exists; addiction discourse should not become editing dogma.
- **Hook speed conflict** (carried from R1): industry 1–3 s vs measured 4–6 s hook resolutions (45) — correlational and confounded; no RCT
  on hook-resolution timing exists.
- **Slow motion** is strongly evidenced for product/brand videos (18, 19, 20) yet absent from practitioner lists and untested for
  talking-head educational shorts — a context-generalization risk.
- **Kinetic captions**: caption comprehension/memory benefits are solid (31); the engagement lift of word-by-word kinetic captions is
  unmeasured; the only style experiment is emoji/no-punctuation with Polish participants (33). Over-engineering risk unquantified.
- **Beat-sync**: neural entrainment to beats is real neuroscience (14, 15); beat-synced *cutting* effectiveness is untested; tool adoption
  (50) is convergence, not evidence.
- **Completion benchmarks conflict**: measured ceiling ~60% (27) vs industry "80%+ is excellent" (44) — definitional differences (plays vs
  impressions vs unique viewers) unresolved; benchmarks must be matched to the exact metric definition before use.
- **Memory-vs-engagement tension**: formats optimized for attention (fragmentation, fast cuts) demonstrably reduce encoding (1, 2, 3) — an
  open product/ethics decision for educational content, and the strongest argument against "maximize stimulation" defaults.
- **Language and content-class bias**: all evidence is EN/CN (Douyin); nothing Spanish; nothing on podcast-derived talking-head shorts
  specifically — voxera's exact content class is unstudied, so all defaults need own-metric validation (same gap as R1).

## Source list

Peer-reviewed / academic (1–41):
1. Wei, M. et al. (2026). "Learning via short videos impairs memory accuracy and reduces brain synchrony." *Communications Psychology* —
  [peer-reviewed; 3 experiments + inter-subject correlation].
https://www.nature.com/articles/s44271-026-00476-x
2. (2025). "Fragmented learning from short videos modulates neural activity and connectivity during memory retrieval." *npj Science of
  Learning* — [peer-reviewed; N=57].
https://www.nature.com/articles/s41539-025-00399-y
3. (2025). "Behavioral and eye-tracking investigation of event segmentation following short video watching." *npj Science of Learning* —
  [peer-reviewed]. https://link.springer.com/article/10.1038/s41539-025-00378-3
4. Geiger, S. & Reeves, B. (1993). "The Effects of Related and Unrelated Cuts on Television Viewers' Attention, Processing Capacity, and
  Memory." *Communication Research* 20(1) — [peer-reviewed classic].
https://journals.sagepub.com/doi/10.1177/009365093020001001
5. Francuz, P. & Zabielska-Mendyk, E. (2013). "Does the Brain Differentiate Between Related and Unrelated Cuts When Processing Audiovisual
  Messages? An ERP Study." — [peer-reviewed ERP].
https://www.kul.pl/files/105/Publikacje/Strony_od_Francuz_Zabielska-Mendyk_2013_Does_the_Brain_Differentiate_Between_Related_and_Unrelated_Cuts_When_Processing_Audiovisual_Messages_-_An_ERP_Study.pdf
6. (2025). "The neural impact of editing on viewer narrative cognition in virtual reality films: eye-tracking insights." *Frontiers in
  Psychology* — [peer-reviewed; N=42].
https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2025.1584250/full
7. (2025). "The dynamic effects of visual complexity and scene cuts on viewer attention." *Journal of the Academy of Marketing Science* —
  [peer-reviewed; 2,520 viewing experiences / 42 PSAs].
https://link.springer.com/article/10.1007/s11747-025-01137-x
8. Lang, A. et al. (2013). "Measuring Television Message Complexity as Available Processing Resources." *Media Psychology* 16(2) —
  [peer-reviewed]. https://www.tandfonline.com/doi/abs/10.1080/15213269.2013.764707
9. (2021). "The Editing Density of Moving Images Influences Viewers' Time Perception: The Mediating Role of Eye Movements." *Cognitive
  Science* — [peer-reviewed; N=70].
https://onlinelibrary.wiley.com/doi/10.1111/cogs.12969
10. Yang, Q., Wang, Y., Wang, Q., Jiang, Y. & Li, J. (2025). "Harmonizing Sight and Sound: Auditory Emotional Arousal, Visual Variation, and
  Congruence in Short Video Marketing." *JTAER* 20(2):69 — [peer-reviewed; 12,842 Douyin videos, 170 influencers].
https://www.mdpi.com/0718-1876/20/2/69
11. Oakes, S. (2006). "The impact of background musical tempo and timbre congruity upon ad content recall and affective response." *Applied
  Cognitive Psychology* — [peer-reviewed].
https://onlinelibrary.wiley.com/doi/10.1002/acp.1199
12. Stewart, K. et al. (2017). "Hooked on a feeling: The effect of music tempo on attitudes and the mediating role of affective responses."
  *Journal of Consumer Behaviour* — [peer-reviewed].
https://onlinelibrary.wiley.com/doi/10.1002/cb.1665
13. (2020). "Disentangling the Effects of Paralinguistic Cues in Bolstering Listeners' Engagement with Podcasters." *ICIS 2020 proceedings*
  — [peer-reviewed; 10,000 audio files / 221 albums].
https://hdl.handle.net/10398/b0a4e775-210e-4d83-8265-59a0f71387e5
14. (2023). "Neural synchronization is strongest to the spectral flux of slow music and depends on familiarity and beat salience." *eLife* —
  [peer-reviewed]. https://elifesciences.org/articles/75515
15. (2015). "Cortical entrainment to music and its modulation by expertise." *PNAS* — [peer-reviewed].
https://www.pnas.org/doi/abs/10.1073/pnas.1508431112
16. Carmi, R. & Itti, L. (2006). "Visual causes versus correlates of attentional selection in dynamic scenes." *Vision Research* —
  [peer-reviewed]. https://www.sciencedirect.com/science/article/pii/S0042698906003816
17. Smith, T.J. & Henderson, J.M. (2008). "Edit Blindness: The Relationship Between Attention and Global Change Blindness in Dynamic
  Scenes." *Journal of Vision* 2(2) — [peer-reviewed].
https://www.mdpi.com/1995-8692/2/2/11
18. Stuppy, A., Landwehr, J.R. & McGraw, A.P. (2024). "The Art of Slowness: Slow Motion Enhances Consumer Evaluations by Increasing
  Processing Fluency." *Journal of Marketing Research* 61(2):185–203 — [peer-reviewed].
https://journals.sagepub.com/doi/full/10.1177/00222437231179187
19. (2021). "The Effect of Slow Motion Video on Consumer Inference." *Journal of Marketing* — [peer-reviewed; 7 studies incl. eye-tracking +
  Facebook Ads field experiment].
https://journals.sagepub.com/doi/10.1177/00222437211025054
20. (2023). "When and How Slow Motion Makes Products More Luxurious." *Journal of Marketing Research* — [peer-reviewed; 12 experiments,
  N=27,227, 5 preregistered].
https://journals.sagepub.com/doi/10.1177/00222437221146728
21. Lindström, B. et al. (2021). "A computational reward learning account of social media engagement." *Nature Communications* —
  [peer-reviewed; RL model]. https://www.nature.com/articles/s41467-020-19607-x
22. Su, C. et al. (2021). "Viewing personalized video clips recommended by TikTok activates default mode network and ventral tegmental
  area." *NeuroImage* 237:118136 — [peer-reviewed fMRI].
https://www.sciencedirect.com/science/article/pii/S1053811921004134
23. (2025). "Old Strategies, New Environments: Reinforcement Learning on Social Media." *Biological Psychiatry* — [peer-reviewed review].
https://www.sciencedirect.com/science/article/pii/S0006322324018201
24. (2023). "The Loop and Reasons to Break It: Investigating Infinite Scrolling Behaviour in Social Media Applications and Reasons to Stop."
  — [peer-reviewed field study; N=46].
https://www.uni-ulm.de/fileadmin/website_uni_ulm/iui.inst.100/1-hci/hci-paper/2023/4-TheLoopAndHowToBreakIT.pdf
25. (2024). "Design Frictions on Social Media: Balancing Reduced Mindless Scrolling and User Satisfaction." *CHI '24* — [peer-reviewed;
  N=30]. https://dl.acm.org/doi/fullHtml/10.1145/3670653.3677495
26. (2024). "Analyzing User Engagement with TikTok's Short Format Video Recommendations using Data Donations." *CHI '24* — [peer-reviewed;
  347 users / 9.2M recommendations].
https://dl.acm.org/doi/fullHtml/10.1145/3613904.3642433 (mirror: https://www.alphaxiv.org/abs/2301.04945)
27. (2026). "Exploring the limits of predicting user watching behavior with short-form videos on TikTok." *WebSci Companion '26* (MPIDR) —
  [peer-reviewed].
https://www.demogr.mpg.de/en/publications_databases_6118/publications_1904/book_chapters/exploring_the_limits_of_predicting_user_watching_behavior_with_short_form_videos_on_tiktok_8988
28. (2024). "Understanding the Effects of Short-Form Videos on Sustained Attention." *CHI '24* — [peer-reviewed; survey + long-term field
  experiment]. https://dl.acm.org/doi/10.1145/3613905.3651018
29. (2024). "Mobile phone short video use negatively impacts attention functions." — [peer-reviewed].
https://pmc.ncbi.nlm.nih.gov/articles/PMC11236742/
30. (2025). "Reels to Remembrance: Attention Partially Mediates the Relationship Between Short-Form Video Addiction and Memory Function
  Among Youth." *Healthcare* 13(3):252 — [peer-reviewed].
https://www.mdpi.com/2227-9032/13/3/252
31. Gernsbacher, M.A. (2015). "Video Captions Benefit Everyone." *Policy Insights from the Behavioral and Brain Sciences* 2(1) —
  [peer-reviewed review; 100+ studies]. https://pmc.ncbi.nlm.nih.gov/articles/PMC5214590/
32. (2024). "Watching subtitled videos with the sound off affects viewers' comprehension, cognitive load, immersion, enjoyment, and gaze
  patterns." *PLOS ONE* — [peer-reviewed eye-tracking].
https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0306251
33. Duraj, K. & Szarkowska, A. (2025). "Beyond Traditional Subtitles: How Emojis and Non-Standard Typography in Subtitles Boost Engagement
  on TikTok." *Journal of Audiovisual Translation* 8(1) — [peer-reviewed; survey N=171 + engagement metrics].
https://www.jatjournal.org/index.php/jat/article/view/339
34. Dolić, J. et al. (2024). "Temporal Typography: The Impact of Animation Speed and Interpolation on Information Transmission Efficiency."
  — [peer-reviewed conference].
https://www.rit.edu/croatia/sites/rit.edu.croatia/files/docs/Temporal%20typography%20-%20The%20impact%20of%20animation%20speed%20and%20interpolation%20on%20information%20transmission%20efficiency%2C%20Dolic%20et%20al.%2C%202024.pdf
35. (2023). "What drives the learning benefits of moving text? A theoretical review." *Humanities & Social Sciences Communications* —
  [peer-reviewed review]. https://www.nature.com/articles/s41599-023-01646-6
36. (2023). "Social Media Engagement: Can Video Captions Increase User Engagement?" *ICEDBC 2023* — [peer-reviewed proceedings].
https://www.atlantis-press.com/proceedings/icedbc-23/125991294
37. Loewenstein, G. (1994). "The Psychology of Curiosity." *Psychological Bulletin* 116(1):75–98 — [peer-reviewed classic].
https://www.cmu.edu/dietrich/sds/docs/golman/golman_loewenstein_curiosity.pdf
38. (2024). "Unlocking play willingness: the dual pathways of curiosity drive and downward social comparison in game advertising."
  *Frontiers in Psychology* — [peer-reviewed; 5 experiments].
https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2024.1374649/full
39. (2022). "Twenty seconds of visual behaviour on social media gives insight into personality." *Scientific Reports* — [peer-reviewed;
  N=180]. https://pmc.ncbi.nlm.nih.gov/articles/PMC8782844/
40. (2023). "Fragmented Visual Attention in Web Browsing: Weibull Analysis of Item Visit Times." *Springer LNCS* — [peer-reviewed].
https://link.springer.com/chapter/10.1007/978-3-031-28238-6_5
41. Guido, G. et al. (2021). "Background music tempo effects on food evaluations and purchase intentions." *Journal of Retailing and
  Consumer Services* 63 — [peer-reviewed; 3 studies].
https://ideas.repec.org/a/eee/joreco/v63y2021ics0969698921002964.html

Industry (42–51):
42. Wistia (2016). "Does Video Length Matter?" — [industry; 564,710 videos / 1.3B plays].
https://wistia.com/blog/does-length-matter-it-does-for-video-2k12-edition
43. Wistia (n.d., accessed 2026). "Understanding Audience Retention" (nose/body/tail anatomy; nose-drop 4.9% @1–2 min vs 17.3% @5–10 min) —
  [industry]. https://wistia.com/learn/marketing/understanding-audience-retention
44. Fanpage Karma (2026-02). "How Long Should TikTok Videos Be?" — [industry study; N=32,000 TikToks; 0–10 s best reach/completion; 30–90 s
  ≈2× engagement].
https://www.fanpagekarma.com/insights/optimal-tiktok-video-length/
45. TikTok Calculator (n.d., accessed 2026). "TikTok Video Completion Rate by Video Length" (~89% @7 s → <10% @10 min) — [industry].
https://tiktokcalculator.net/data/engagement/completion-rate-by-video-length/
46. FYPNow Research (2026-08-04). "The Anatomy of a TikTok Video: Length, Hooks, Pacing and Audio" — [industry corpus; hook resolution,
  saves by length]. https://fypnow.com/research/tiktok-video-anatomy
47. SaliencyLab (n.d., accessed 2026). "Hook rate vs thumbstop: what each platform measures" — [industry analytics].
https://www.saliencylab.com/hubs/creative-analysis/hook-rate-vs-thumbstop
48. Vidmob (n.d., accessed 2026). "The Science of the Hook: How Brands Can Cultivate Curiosity on TikTok" — [industry; TikTok Creative
  Center 6 s hook window]. https://vidmob.com/resource/tiktok-hook-analysis
49. Kapwing (n.d., accessed 2026). "A Complete Guide to TikTok Subtitles" — [industry/editor-tool].
https://www.kapwing.com/resources/a-complete-guide-to-tiktok-subtitles/
50. influencers-time (2026). "Kinetic Typography for TikTok: Boost Retention & Engagement" — [industry blog].
https://www.influencers-time.com/kinetic-typography-boost-video-retention-on-tiktok-and-reels/
51. Canva (n.d., accessed 2026). "Beat Sync — Auto Sync Audio and Video" — [industry tool feature].
https://www.canva.com/features/beat-sync/

Cross-referenced from R1 (not re-numbered): R1#1 (Dost & Huang 2026, jump-cut experiment N=242), R1#10/11
(Hootsuite specs), R1#18 (FYPNow = source 45 here), R1#19 (Kudoflix pacing guide), R1#22 (Blitzcut 3-second
rule), R1#31/32 (vidio.ai/CapCut beat-sync), R1#34/35 (hook pattern roundups), R1#36 (Sydium trending-audio).

— R2 · built from 18 web searches + 12 full-text fetches (2026); ACM full-text bot-blocked → CHI '24 verified
via alphaXiv mirror + SIGCHI program page. Peer-reviewed vs industry evidence separated per theme; industry
benchmarks (completion %, reach multipliers) are self-published and unaudited. —
Verificación R2: 7 temas · 51 fuentes (41 peer-reviewed / 10 industry) · tags C1×3, C2×28, C3×17 (aprox.;
bullets multi-source). Sin ficheros del repo modificados.



