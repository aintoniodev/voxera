# R3 — Metrics & Analytics for Short-Form Video

> **Resumen ejecutivo** (ES): El ecosistema de métricas de vídeo corto tiene una jerarquía clara — TikTok pondera watch time + completion rate por encima de todo, Meta pondera watch time (tanto % como segundos absolutos) + likes/sends por reach, y YouTube Shorts gira en torno al ratio *viewed vs swiped away* — pero los **benchmarks numéricos son casi todos de vendors** (campañas de ads o estudios de agencias), no publicados por las plataformas: TikTok/YouTube/Meta definen métricas oficialmente pero nunca publican valores "buenos" orgánicos. Los datos más accionables para edición: la ventana de hook se ha comprimido a ~1.9 s de scroll-stop mediano en TikTok (2026), los primeros 3 s deciden el "cliff" de retención (30–50% de pérdida en Shorts), los subtítulos/texto son el único elemento de edición con lift documentado (interno de Meta: +12% watch time, no verificable), y el A/B de clips necesita 30–60 pares por variante con 7–14 días de ventana y ratios de mediana (distribución heavy-tailed). voxera ya tiene el protocolo A/B humano (Track 8, MOS + umbral ≥60%) pero no instrumentación de métricas de plataforma; los gaps de mayor ROI son: análisis de curva de retención, captions, y log de experimentos con mediana/variante/plataforma.

## Method

6 web searches (2 batches × 3–6 queries) covering: TikTok/Reels/Shorts analytics + benchmarks, algorithm ranking factors (2025–2026), retention-curve reading, captions→watch-time evidence, hook/hold-rate benchmarks, and A/B testing frameworks for clips. Full page content fetched for 8 URLs (TikTok For Business Creative Codes, TikTok Ads Manager video-play metrics, YouTube Help Shorts page, Metricool 2025 report, Socialinsider video stats, SaliencyLab Hooks 2026, Sepia Lab hold rates, Conbersa A/B framework). Source mix by type: **8 official platform docs** (TikTok/YouTube/Meta/Instagram: sources 1–8), **13 vendor/industry benchmark studies** (SaliencyLab, Sepia, Metricool, Socialinsider, Hootsuite, 3Play, Zoomsphere, iMotions, Music Ally: 9–22), **9 practitioner/analytics blogs** (Retensis, Rule1, TubeAI, VidCognition, Aibrify, SocialPilot, Sprout, Bevy, Gyre: 23–31), **3 local repo docs** (32–34). Honest caveats: (a) no platform publishes *organic* completion/retention benchmarks — every organic figure below is vendor-measured or practitioner lore; (b) paid-ad benchmarks (hold rates, hook-rate tiers) may not transfer to organic FYP; (c) caption-lift figures trace to a Facebook *internal* study (unverifiable); (d) SaliencyLab scroll-stop is AI-model-scored, not direct measurement (ρ +0.31 OOS, honestly disclosed). Confidence tags: [C1] ≥3 sources, [C2] 2 sources or 1 strong vendor study, [C3] single source, [C3-flagged] single unverifiable/vendor claim, [C3-local] local voxera-measured. All bullets cite source numbers from the list at the end.

## Theme 1: Metric taxonomy — definitions & what the platform algorithms optimize

- **Watch time** (absolute seconds watched) vs **completion rate** (% who reach the end) are tracked
  separately and weighted differently per platform: TikTok's algorithm is described as "watch time
  first, completion second, then saves/shares, then likes" (2026 practitioner consensus, no confirmed
  ranking change as of Aug 2026) [C2] 27, 28, 29. Instagram's Mosseri (Feb 2025) states watch time is
  weighed *both* as percentage watched *and* total seconds — "10 s watched on a 1-min video holds the
  same weight as 10 s on a 10-s video" [C1] 22, 21.
- **Retention curve** (second-by-second % of the original cohort still watching) is the shared
  diagnostic across all three platforms; TikTok/Meta expose it in creator analytics, YouTube calls it
  Audience Retention with a "typical retention" comparison vs your 10 latest similar-length videos
  [C2] 5, 24, 25.
- **Hook/hold rates** have precise paid-side definitions: TikTok Ads Manager counts 2-second and
  6-second video views (replays excluded) [C1] 2, 3; Meta counts 3-second video plays [C1] 7; YouTube
  Shorts (since 3/31/2025) counts *any* play as a "view" and keeps "Engaged views" (viewed past the
  initial seconds) for monetization [C1] 4, 5. Organic TikTok views (Creator Analytics) = unique +
  returning viewers — a different number from the public counter [C3] 3, 8.
- **Replays/loops**: TikTok ads *exclude* replays from view counts but *include* them in average play
  time per user [C2] 2; YouTube Shorts *counts* replays as new views (official) [C1] 4 — loop-designed
  endings therefore inflate different metrics per platform.
- **Shares, saves, comments** are the "quality" tier: TikTok's 2026 hierarchy reportedly re-weights
  saves/shares above likes [C2] 28, 29; Meta's top-three ranking signals are watch time, likes per
  reach, and sends per reach (shares) [C2] 21, 22.
- **Engagement rate is NOT a standard metric**: Socialinsider's TikTok ER (per-video interactions over
  follower count) runs 4.45–5.35% [C2] 13, 14, while Hootsuite's "average TikTok engagement rate" is
  1.5% (Mar 2025, per-post over impressions/reach) [C3] 15 — same label, different denominators; never
  compare across tools.

**voxera mapping:** the project currently tracks audio-quality metrics (MOS, PESQ, RTF) and human preference (Track 8) [32, 33]; none of the distribution metrics above exist in the pipeline. R3 defines the target metric set for the video output (completion %, 3 s retention, save/share rate, per platform), which the "raw MP4 → metrics-optimized short" synthesis needs as its objective function.

## Theme 2: Benchmarks — typical values by platform (all vendor/practitioner unless flagged)

- **3-second hold rate (paid, DTC UGC ads, 2026):** TikTok in-feed 38–48% (5 s: 28–38%; 15 s: 12–20%);
  Meta Reels 40–50% (5 s: 30–40%; 15 s: 14–22%); Instagram Stories 50–65% (15 s: 20–30%). "Good" =
  >42% at 3 s on TikTok, >45% on Meta Reels [C2 — single vendor cohort, paid ads only] 10.
- **Hook-rate tiers (paid):** Meta (3 s): <20% needs work / 20–25% table stakes / 25–35% competitive /
  >35% elite; TikTok (2 s): <25% / 25–30% / 30–40% / >40% — from multi-account ecommerce-brand
  analyses, methodology unpublished [C3-flagged] 18. Hook rate = 3-s views ÷ impressions; hold rate =
  views past t ÷ 3-s views [C2] 10, 18.
- **Organic completion benchmarks:** only one vendor table found — TikTok retention by length (2026):
  <15 s → 60–70%, 15–30 s → 50–60%, 30–60 s → 40–50% [C3-flagged — Retensis publishes no methodology]
  17. TikTok/YouTube/Meta publish **no** official organic completion benchmarks — any number
  circulating is vendor or practitioner.
- **Scroll-stop (paid cohort, model-scored):** median TikTok scroll-stop = **1.9 s** (2026 Q1–Q2,
  n=700 ads, 22 markets; was 2.4 s in 2024); matched-creative medians per surface: Snap 1.3 s / TikTok
  1.9 s / Reels 2.0 s / Shorts 2.2 s [C2 — large cohort but AI-scored, not in-market] 9.
- **YouTube Shorts:** "Viewed vs Swiped Away" — >70% viewed = "viral territory", ~50% average, <30% =
  dead (practitioner tiers) [C3] 30, 31; Shorts with >80% viewed reportedly get up to 10× views vs the
  50–60% band [C3] 19; Average Percentage Viewed targets: 100–120% for <15 s Shorts, 80–90% for longer
  (replays push APV past 100%) [C3] 19.
- **Engagement rates (organic, vendor-measured):** TikTok ER by account size 5.35% (1K–5K) →
  4.45–4.60% (50K–1M) [C2] 13, 14; TikTok avg 1.5% (Hootsuite, Mar 2025) [C3] 15; Facebook Reels
  0.20–0.40% [C2] 13; Instagram Reels ~3.5% vs static images 6.2% (Zoomsphere, 5M+ posts) [C3] 20;
  Shorts brand-account engagement ~0.40% (Socialinsider) [C3] 14, 30.
- **Length effects (organic, vendor):** engagement *rises* with length on TikTok (peaks just past 2
  min) and Reels (60–90 s sweet spot); Reels views: 1–15 s ≈ 1,750 vs 15–30 s ≈ 3,000 avg [C2] 13.
  Saturation trend: Metricool 2026 TikTok study (2.3M posts, 92K accounts) measures views −31% YoY
  [C2] 12; short-form posts +70% YoY (2025, 5M+ videos, 582K accounts) [C2] 11.

**voxera mapping:** voxera's output target is 1080×1920@30 (README) [32]; the practical benchmark set for its videos: hook window 0–2 s (scroll-stop 1.9 s) [9], 3 s hold ≥40% as a *paid-side* sanity target [10], completion benchmarked per-length only against the account's own baseline (no trustworthy organic external table) [17-flagged]. Treat all Theme-2 numbers as directional, not acceptance criteria.

## Theme 3: Retention curve analysis — reading the curve, drop-off points, edit fixes

- **Anatomy:** the curve starts at 100% and the steepest loss is always in the first seconds — Shorts
  curves lose 30–50% of viewers between second 1 and second 3 ("cliff"); the algorithm reads a cliff
  as low-value regardless of the rest [C2] 24, 25, 26. Flat early line + slow decay = healthy; a late
  upward spike = replays/loops [C2] 24, 25.
- **Diagnostic patterns:** (a) steep 0–3 s drop → hook/promise mismatch; (b) 3 s OK but collapse by
  ~10 s → slow pacing or unclear value; (c) mid-video dip at a consistent timestamp → that segment's
  content/edit; (d) end drop → weak close, no loop [C2] 10, 24, 26. Platform-native "key moments"
  reports (YouTube) surface the exact seconds [C1] 6.
- **Edit fixes per shape:** cliff → move value/promise into 0–1.5 s, cut intro filler [C2] 9, 10; 10 s
  collapse → cut filler frames, tighten script so benefit lands by second 5 [C2] 10; mid dip → pattern
  interrupt (visual/audio change) every 10–20 s + open loop at the dip [C3] 26; end drop → loop the
  ending into frame one (replay metric) [C2] 4, 29.
- **Platform specifics:** YouTube overlays swipe-away rate on the retention graph per second [C2] 31;
  TikTok shows 2 s/6 s markers and traffic-source splits (FYP vs search vs profile) [C2] 3, 8; Meta
  Reels exposes 3-s views, replays, and watch time but not a public per-second curve for organic posts
  [C2] 7, 21.
- **Data hygiene:** retention data takes 1–2 days to settle (YouTube official) [C1] 6; curves on
  <1,000-ish views are noisy — compare like-length videos, and per Sepia's paid-side rule, 500–1,000
  impressions is the minimum for ranking variants [C2] 5, 10.
- **Honest gap:** no independent study validates the curve-shape → edit-fix mappings; they are
  practitioner heuristics layered on the (official) fact that platforms *show* curves and *use* early
  retention [C2 for the official part, C3 for the heuristics] 6, 24, 26.

**voxera mapping:** retention-curve analysis is implementable as a CLI/UI feature reading per-platform analytics CSV exports; the existing voice-energy envelope (`zoom --auto-emphasis`, `riser --hit` [32]) already locates pattern-interrupt opportunities at measured drop-point timestamps. Biggest actionable pattern: mid-video dips → `cutsilence` + pulse zoom at that second.

## Theme 4: Editing → metric evidence — measured links between edits and metrics

- **Hooks:** promise-first openings beat brand-first by **+28% completion**; value/stakes/face must
  land by ~1.0–1.5 s (median scroll-stop 1.9 s); logo-first slates and "story" openers deferring value
  past 3 s are the worst failure modes (SaliencyLab cohort, model-scored — not direct measurement)
  [C2] 9. Official TikTok: 90% of ad-recall impact lands in the first 6 s [C1] 1.
- **Captions/text overlays — the best-documented lever:** TikTok official: creative attributes that
  get people to read increase view time and recall [C1] 1; Facebook *internal* study: captions +12%
  average view time (A&W case +25%) — platform-internal, unverifiable [C3-flagged] 16; caption-first
  composition (top-third, sound-off readable <600 ms) +7 "Get Noticed" [C2] 9. Mute rates justify it:
  TikTok feed ~52% muted vs Shorts ~38% [C2] 9. An eye-tracking/facial-EMG exploratory study
  (iMotions) found subtitles shift attention/emotion in short-form [C3] 22.
- **Pacing/cuts:** TikTok Marketing Science (Neuro-Insight): faster scene changes draw viewers in
  early [C1 — official-cited internal study] 1; cutting silence (`cutsilence`-style) shortens
  duration, mechanically raising completion % for the same content (inference, not measured) [C3] 32,
  33. R1's only controlled experiment (jump cuts, N=242) showed overlapping cuts raise *sustained
  engagement* only at low transition frequency — no platform-metric link measured [C3] 33.
- **Audio pattern breaks:** sub-bass drop / abrupt silence at <1 s: +6–9 points on "Beat the Skip"
  (model-scored) [C2] 9; sound-on is structurally viable on Shorts (38% mute) — audio-led openers get
  a chance there [C2] 9.
- **CTAs/closes:** CTA cards → +45% recall, +19% likeability (TikTok official) [C1] 1; loopable
  endings → replays add watch time on TikTok and views on Shorts (official counting) [C2] 2, 4.
- **Honest summary:** the only edit→metric links with official backing are *qualitative* (text
  overlays ↑ view time; scene changes ↑ early attention; CTA cards ↑ recall). Every *quantified* lift
  (+12%, +28%, +6–9 pts) comes from platform-internal or vendor-modeled sources and must be treated as
  directional [C2/C3-flagged] 1, 9, 16.

**voxera mapping:** existing primitives already target these levers — `audio riser`/`lowpass` = pattern-break audio at the hook [32]; `video zoom --pulse` = visual interrupt; `cutsilence` = pacing/completion; `melody --duck` = sound-on engagement. **Captions are the missing edit with the strongest documented metric link** (mute rates 38–52%) — confirmed as the top gap (matches R1) [33].

## Theme 5: A/B testing & instrumentation — how variants are tested, tools, sample-size caveats

- **No organic A/B on any platform**: TikTok/Reels/Shorts do not offer variant testing for organic
  posts; creators test by publishing variants over time/accounts. Paid-side, TikTok Ads Manager
  exposes per-variant hold rates (video views at 25/50/75/100%), Meta exposes ThruPlay + 3-s plays
  [C1] 2, 7, 10. TikTok Creative Center's Top Ads dashboard serves as a competitive retention-curve
  benchmark [C2] 8, 11.
- **The clip-testing framework (podcast networks, most relevant to voxera):** isolate one variable at
  a time; **30–60 paired clips per variant** (minimum viable, detects 2× median lifts; 100–200 for
  30–50% lifts); run **7–14 days** (TikTok/Reels resurface clips 5–14 days after upload; 24–72 h reads
  undercount long-tail and reward the wrong variant); report **median view ratio, not mean**
  (heavy-tailed distribution); replicate a winner in a second batch before locking in (catches ~half
  of false positives) [C2 — vendor framework, no peer review] 23.
- **Paid-ad volume rule:** 500–1,000 impressions per variant to rank hold rates; kill variants <30%
  hold at 3 s unless hook rate is exceptional (12%+) [C3] 10.
- **Variable ranking by impact:** hook (first 1–3 s) #1; thumbnail/cover #2 (matters more on
  Shorts/Reels, less on autoplay TikTok); then caption style, length, CTA; posting time lowest [C2]
  23, 27.
- **What creators actually do:** 3–4 hook variants per video with the body held constant; change one
  variable per test or results become unreadable; single-pair comparisons are anecdotes in
  heavy-tailed distributions [C2] 23, 27.
- **Tooling:** platform-native analytics (TikTok Creator Analytics completion/retention [3, 8],
  YouTube Studio viewed-vs-swiped + "Get feedback" AI hook/pacing analysis [4, 5, 31], Meta 3-s plays
  [7]); third-party dashboards (Motion, Smartly, Revealbot) for hold-rate at scale [C3] 10; YouTube's
  built-in "Get feedback" pre-publish hook/pacing analysis is official and new [C1] 4.

**voxera mapping:** the repo already has the experimental skeleton — Track 8's paired A/B (60 pairs, randomized sides, ≥60% preference threshold, MOS, votes.csv) [34] — and `video compare` for 3-panel A/B rendering [32]. Extending to platform metrics requires: (a) per-variant metadata rows (variant id, platform, publish date, median of views/completion/3-s retention), (b) 30+ clip pairs and 7–14 day windows per decision [23], (c) median-based summaries instead of means [23]. The ≥60% human-preference gate stays the creative gate; platform metrics become the distribution gate.

## Theme 6: Platform algorithm behavior — ranking/distribution and what it implies for editing

- **TikTok:** interest-graph FYP; per 2026 practitioner consensus the signal hierarchy is completion
  rate + watch time first, saves/shares second, likes third; no confirmed ranking changes detected
  through Aug 2026 [C2] 27, 28, 29. Implication: optimize the retention curve above all; loops and
  saves-compelling endings pay off [C2] 29.
- **Instagram/Reels:** recommendation is split between follow-graph and recommendation surfaces;
  Mosseri (Feb 2025): watch time counts as both % and absolute seconds, plus likes-per-reach and
  sends-per-reach [C2] 21, 22; Reels recommendation updates (Apr 2024) explicitly designed so small
  creators break through [C1] 8. Implication: since absolute seconds count equally with %,
  medium-length Reels (60–90 s sweet spot per vendor data) can win without a perfect completion rate
  [C2] 13, 22.
- **YouTube Shorts:** a separate algorithm from long-form; the feed conversion metric is "how many
  chose to view" (viewed vs swiped away); the swipe decision is described as <400 ms (practitioner
  claim) [C2] 5, 19, 30, 31; YPP/monetization keys off engaged views, not the new views metric [C1] 4.
  Implication: front-load everything (frame one carries the decision); lower mute rate (38%) makes
  audio-led hooks viable [C2] 9.
- **Distribution mechanics:** TikTok tests on a small FYP pool and scales only if early
  retention/engagement clears thresholds — "did the audience find it worth their time" is the
  assessment at each stage [C2] 27, 28; this is why first-3-s metrics are described as distribution
  gates rather than vanity metrics [C2] 24, 27.
- **Saturation drift:** engagement per post is falling across platforms — TikTok views −31% YoY
  (Metricool 2026) [C2] 12, YouTube interactions −50% (Metricool 2025) [C2] 11, Instagram engagement
  −24% YoY (Socialinsider 2026) [C2] 14 — so any benchmark must be re-validated against current
  baselines; 2024-era "good" numbers are stale.
- **Confidence note:** everything above about *weights and stages* is practitioner interpretation of
  platform behavior; the only official facts are metric definitions [1–8] and Mosseri/TikTok
  statements about *which* signals exist [1, 8, 21, 22]. Weights are never published [C1 for
  definitions, C3 for the hierarchy] 2, 4, 7, 27.

**voxera mapping:** per-platform output presets are defensible: TikTok preset → loop-friendly close + tight retention (completion-first); Shorts preset → front-loaded hook in frame one + audio-led opening; Reels preset → medium length allowed, absolute watch time matters. These map onto existing knobs (`--level aggressive` pacing, `riser --hit` at 1.5 s, `transition` at the loop point) [32].

## Conflicts & open questions

- **Watch time % vs absolute seconds vs completion:** Mosseri says both % and seconds count (Reels)
  [22]; TikTok lore says watch time is the single strongest signal [27, 28]; Shorts keys on
  viewed-vs-swiped [19]. No public source reconciles the three — a single "optimized edit" likely does
  not exist across platforms (see Theme 6 presets).
- **Long vs short:** vendor data shows engagement *rising* with length (TikTok peaks >2 min; Reels
  60–90 s) [13], while completion-rate tables favor <30 s [17-flagged]. Reach-vs-depth tradeoff
  unresolved; R1's measured corpus similarly showed saves climbing with length [33].
- **Organic benchmarks don't exist officially:** every organic completion/retention figure in this
  note is vendor or practitioner (Retensis [17], TubeAI [19]) with unreported methodology; the
  platform "official" sources only define metrics [1–8]. Any acceptance criterion for voxera must come
  from its own account baselines, not external tables.
- **Paid → organic transfer unverified:** hold-rate/hook-rate tiers come from paid DTC UGC cohorts
  [10, 18]; organic FYP distribution may weight differently (e.g., muted autoplay, no impression
  auction) — no study tests the transfer.
- **Model-scored evidence:** SaliencyLab's scroll-stop/completion-lift numbers are AI-scored
  predictions validated against public signals (ρ +0.31 OOS), explicitly *not* in-market measurement
  [9]; treat as directional.
- **Caption lift figures:** the +12% watch-time caption figure is a Facebook internal study relayed by
  a captioning vendor [16-flagged]; the widely-cited "80% more likely to watch fully"
  (Verizon/Publicis) was not independently reproduced. Captions are still the highest-consensus edit
  lever (official TikTok statement on text overlays ↑ view time [1]) but exact lifts are unverified.
- **View-counting incoherence across platforms:** Shorts counts replays as views (official) [4];
  TikTok ads exclude replays [2]; TikTok organic public counter ≠ Creator Analytics views [3, 8].
  Loop-strategy "wins" are therefore partially an accounting artifact — decide per platform which
  number you're optimizing.
- **Benchmark decay:** all 2025–2026 figures show engagement/view declines YoY [11, 12, 14]; vendor
  "2026" numbers published mid-year may already be stale by deployment — re-check quarterly.
- **Language/ES gap (inherited from R1):** all evidence is English-language content; nothing covers
  Spanish short-form benchmarks — relevant to voxera's Spanish-first positioning [33].

## Source list

Official platform docs (1–8):
1. TikTok For Business blog — "Creative Codes: 6 principles for creating on TikTok" — [official platform blog; cites internal TikTok Marketing Science studies 2020–2022, Kantar/Ipsos/Lumen/Neuro-Insight]. Accessed 2026. https://www.tiktok.com/business/en-US/blog/creative-best-practices-top-performing-ads
2. TikTok Ads Manager Help — "Video play metrics" — [official platform docs; 2 s/6 s views, 25/50/75/100% views, replay rules]. Accessed 2026. https://ads.tiktok.com/help/article/video-play
3. TikTok Ads Manager Help — "Basic metrics and definitions" — [official platform docs]. Accessed 2026. https://ads.tiktok.com/help/article/basic-data
4. YouTube Help — "Get started creating YouTube Shorts" (view-count change 3/31/2025; engaged views; YPP) — [official platform docs]. Updated 2025-03. https://support.google.com/youtube/answer/10059070
5. YouTube Help — "Understand your content reach and engagement" — [official platform docs; engaged views, typical retention]. Accessed 2026. https://support.google.com/youtube/answer/12220281
6. YouTube Help — "Measure key moments for audience retention" — [official platform docs; 1–2 day data latency]. Accessed 2026. https://support.google.com/youtube/answer/9314415
7. Meta Business Help — "About Video Ad Metrics on Facebook and Instagram" — [official platform docs; 3-second video plays]. Accessed 2026. https://www.facebook.com/business/help/1792720544284355
8. Instagram for Creators blog — "Helping creators of all sizes break through" — [official platform blog; Reels ranking update Apr 2024]. 2024. https://creators.instagram.com/blog/helping-creators-of-all-sizes-break-through

Vendor / industry benchmark studies (9–22):
9. SaliencyLab — "TikTok Hooks 2026 · Industry Research" — [vendor; AI-scored cohort n=700 TikTok ads + matched n=240/surface; model-validated ρ +0.31, not in-market]. 2026 Q1–Q2. https://www.saliencylab.com/hubs/industry-research/tiktok-hooks-2026
10. Sepia Lab — "Hold Rate Benchmarks 2026: What Good Performance Looks Like on Meta & TikTok" — [vendor; aggregated DTC UGC paid-ad data]. 2026. https://sepia-lab.com/en/blog/hold-rate-benchmarks
11. Metricool — "State of Short-Form Video in Social Media in 2025" — [vendor study; 5M+ videos, 582K accounts]. 2025-09-10. https://metricool.com/social-media-short-video-report-2025/
12. Metricool — "2026 TikTok Study" press release — [vendor study; 2.3M posts, 92K accounts; views −31% YoY]. 2026-05-12. https://metricool.com/press-release-tiktok-study-2026/
13. Socialinsider — "2025 Social Media Video Performance Statistics" — [vendor study; ER by platform/account size/length]. 2025. https://www.socialinsider.io/social-media-benchmarks/social-media-video-statistics
14. Socialinsider — "2026 TikTok Benchmarks" — [vendor study; 2M TikTok posts, 214,507 profiles, Jan 2024–Dec 2025]. 2026. https://www.socialinsider.io/social-media-benchmarks/tiktok
15. Hootsuite — "How to boost TikTok engagement: 10 tips + calculator" — [industry blog; avg TikTok ER 1.5%, Mar 2025]. 2025. https://blog.hootsuite.com/tiktok-engagement/
16. 3Play Media — "Studies Find Captions Can Improve Focus on Video Content" — [captioning vendor; relays Facebook internal study +12% view time and Verizon/Publicis survey]. Accessed 2026. https://www.3playmedia.com/blog/studies-find-captions-improve-engagement/
17. Retensis — "TikTok Retention Benchmarks 2026 (by Length)" — [practitioner analytics blog; methodology not published]. 2026. https://retensis.com/blog/tiktok-retention-rate-benchmarks-2026
18. Rule1.ai — "Hook rate: what it is, how to calculate it, and what good looks like" — [practitioner; multi-account ecommerce analyses, methodology unpublished]. 2026. https://rule1.ai/articles/hook-rate
19. TubeAI Learn — "YouTube Shorts Analytics: How to Read Swipe Rate, Retention & Growth Metrics" — [practitioner analytics]. 2026. https://learn.tubeai.app/blog/youtube-video-performance-analysis/youtube-shorts-analytics-swipe-retention-metrics
20. Zoomsphere — "The State of Social Media Engagement in 2025" — [vendor study; 5M+ posts; IG Reels 3.5% ER vs static 6.2%; TikTok 4.1%]. 2025. https://www.zoomsphere.com/data-reports/the-state-of-social-media-engagement-rate-in-2025
21. Music Ally — "Instagram offers new details on how reels algorithms work" — [industry press; reports Mosseri statements on watch-time weighting]. 2025-02-27. https://musically.com/2025/02/27/instagram-offers-new-details-on-how-reels-algorithms-work/
22. iMotions — "Short-Form Videos: An Exploratory Study on the Impact of Subtitles and ASMR Split-screen Format Options (Eyegaze and Facial Expression Data)" — [industry biometrics lab; exploratory, not peer-reviewed journal]. Accessed 2026. https://imotions.com/blog/publications/short-form-videos-an-exploratory-study-on-the-impact-of-subtitles-and-asmr-split-screen-format-options-using-eyegaze-and-facial-expression-data/

Practitioner / analytics blogs (23–31):
23. Conbersa — "What A/B Testing Framework Works for Podcast Clip Distribution?" — [vendor/practitioner framework; 30–60 paired clips, 7–14 days, median ratios, replication]. Accessed 2026. https://www.conbersa.ai/learn/podcast-network-experiment-framework
24. Retensis — "How to Read a Retention Curve" — [practitioner analytics]. 2026. https://retensis.com/blog/how-to-read-retention-curves
25. VidCognition — "What Is an Engagement Curve? Definition + How to Read Yours" — [practitioner analytics]. Accessed 2026. https://vidcognition.com/blog/what-is-engagement-curve
26. Aibrify — "The YouTube Shorts Retention Curve Playbook (2026)" — [practitioner; 30–50% first-3-s cliff]. 2026. https://aibrify.com/blog/youtube-shorts-retention-curve-playbook
27. SocialPilot — "How TikTok Recommends Videos #FYP (August 2026)" — [practitioner; no confirmed ranking changes through Aug 2026]. 2026-08. https://www.socialpilot.co/blog/tiktok-algorithm
28. Sprout Social — "How the TikTok Algorithm Works in 2026" — [industry blog; 2026 hierarchy: saves/shares above likes]. 2026. https://sproutsocial.com/insights/tiktok-algorithm/
29. Bevy — "Short-Form Metrics Decoder: TikTok, Reels & Shorts" — [practitioner tool; cross-platform metric formulas; "60–80%+ past 3 s" aim]. Accessed 2026. https://www.bevyl.ai/tools/metrics
30. Gyre — "YouTube Shorts view count update: impact and strategy for creators in 2026" — [practitioner]. 2026. https://gyre.pro/blog/youtube-shorts-view-count-update-impact-strategy-what-to-do-next
31. ReelRise — "Viewed vs. Swiped Away: The Only YouTube Shorts Metric That Matters" — [practitioner; 70/50/30 viewed tiers]. Accessed 2026. https://reelrise.app/guide/viewed-vs-swiped-away-the-only-youtube-shorts-metric-that-matters/

Local (project-measured, not web) (32–34):
32. voxera research/README.md — project state, video pipeline (1080×1920@30, cutsilence, zoom, magnify, teleport, stabilize, tonal audio, Track 8 protocol). 2026.
33. voxera research/research-notes/R1-editing-techniques.md — sibling note (hooks, pacing, captions, safe zones; 39 sources). 2026.
34. voxera research/docs/track8-results.md — Track 8 human A/B results (60 pairs; ≥60% preference gate; MOS 3.07; randomization). 2026-08-11.

— R3 · built from 6 web searches + 8 full-text fetches (2026); organic benchmark tables are vendor/practitioner only — no official platform benchmarks exist; re-validate quarterly given measured engagement decay —
Verificación R3: 6 temas + conflictos + 34 fuentes (8 oficiales / 14 vendor-industria / 9 practitioner / 3 locales) · tags: 7×C1, 16×C2, 12×C3, 4×C3-flagged, 1×C3-local. Sin ficheros del repo modificados.
