# Notes (working)

## Teaching preferences
- None recorded yet. Skill guidance applies: short lessons, retrieval practice, tight feedback loops, spacing.
- **Locale:** the environment serves a Spanish UI — ask whether lessons should be in Spanish, or English with Spanish glosses.

## Working notes
- **"Autoresearch" interpretation:** the user said "autoresearch from Karpathy" — this maps to the GitHub repo `karpathy/autoresearch` ("AI agents running research on single-GPU nanochat training automatically"). **Not yet confirmed with the user — confirm in next session.**
- Key framing adopted in lesson 1: **autoresearch is a (1+1)-evolutionary strategy with an LLM as the mutation operator.** This gives GP the bridge into the mission.
- The teaching workspace lives at the repo root per the teach skill (MISSION.md, RESOURCES.md, NOTES.md, lessons/, assets/, reference/, learning-records/). Offered to move to a subfolder — user hasn't decided.
- **Tooling:** during setup the web_search tool was down (Serper returning no results); used direct fetches instead (GitHub, arXiv abs pages, Semantic Scholar API, gp-field-guide.org.uk, karpathy.ai). S2 + arXiv API rate-limited intermittently.
- **Component convention:** lessons and reference docs are **self-contained HTML** — they inline the canonical components from `assets/` (lesson.css, quiz.js, ga-demo.js) so they render standalone when double-clicked and in the app's single-file preview server (which serves only the registered HTML file; sibling assets 404). Each inlined file carries a header comment naming its canonical source. **Edit the component in `assets/`, then re-inline it in every lesson.**
- Current date context: 2026-08-19. Karpathy's autoresearch repo updated 2026-03; repo description and program.md captured in full — see RESOURCES.md.
- GECCO = the main GP/evolutionary-computation conference (via SIGEVO), worth mentioning when the user wants the community step.

## Resources status
- Deep Neuroevolution (Such et al. 2017) link unverified at setup (rate limits) — see Gaps in RESOURCES.md.
