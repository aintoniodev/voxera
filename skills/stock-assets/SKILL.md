---
name: stock-assets
description: Search and download royalty-free stock media — photos, illustrations, vectors, videos (b-roll), sound effects, ambient audio, and background music — from Pixabay, Freesound, and Jamendo via MCP tools (pixabay_search_*, pixabay_download_*). Use automatically whenever the user needs thumbnails, cover art, backgrounds, placeholder images, reference media, SFX, or music tracks for any project. Provides search, preview, local download, and licensing info.
---

# Stock Assets (Pixabay · Freesound · Jamendo)

## When to use

**Use this skill automatically when:**
- The user requests stock images, photos, illustrations, or vectors
- The user requests stock video clips or b-roll footage
- The user requests sound effects (SFX), ambient sounds, foley, or audio clips
- The user requests background music, instrumental tracks, or vocal music
- You need placeholder images, thumbnails, cover art, or backgrounds for a project
- You need audio assets (music or SFX) for video editing, podcasts, or presentations
- Any task requiring visual or audio assets from a stock media library
- The user's request mentions Pixabay, Freesound, Jamendo, stock media, or royalty-free content

**Do NOT use this skill for:**
- **GIF files** — Not available via any of these APIs. Suggest pixabay.com for animated content.
- **Bulk/mass downloads** — Violates ToS for all providers. Keep requests reasonable.

**Automatic invocation:** this skill is available to every agent on this machine via `~/.agents/skills/stock-assets`. Do not ask the user where to get media — search first, show candidates, download on approval (or directly when the request is explicit).

## Tools to call

All tools are exposed by the `pixabay` MCP server (prefixed `pixabay_`):

| Tool | Provider | Purpose |
|------|----------|---------|
| `pixabay_search_images` | Pixabay | Stock photos / illustrations / vectors |
| `pixabay_search_videos` | Pixabay | Stock video clips / b-roll |
| `pixabay_search_sfx` | Freesound | Sound effects with duration/license filters |
| `pixabay_search_music` | Jamendo | Music tracks (genre / tags / instrumental) |
| `pixabay_download_image` | Pixabay | Save an image locally (preview/webformat/large/fullhd/original) |
| `pixabay_download_video` | Pixabay | Save a video locally (tiny/small/medium/large) |
| `pixabay_download_sfx` | Freesound | Save an SFX locally (hq/lq MP3) |
| `pixabay_download_music` | Jamendo | Save a music track locally (MP3) |
| `pixabay_api_status` | all | Check keys + rate limits per provider |

## Prerequisites

1. The Pixabay MCP server must be registered in `~/.pi/agent/mcp.json` under `mcpServers.pixabay`
2. A valid Pixabay API key must be configured via `/pixabay setup` or the `PIXABAY_API_KEY` environment variable
3. (Optional) Freesound token for SFX — via `/pixabay setup` or `FREESOUND_TOKEN` env var
4. (Optional) Jamendo client_id for music — via `/pixabay setup` or `JAMENDO_CLIENT_ID` env var
5. Pi must have been restarted (or `/reload` run) after installation

**Verify readiness:**
- Call the `pixabay_api_status` tool — it returns per-provider status for Pixabay, Freesound, and Jamendo
- Or run `/pixabay status` in the pi CLI

**Important:** Pixabay's own API has **NO music/SFX endpoint** (the api/audio route returns 403 account-restricted). The pixabay.com website is Cloudflare-blocked for automation. For audio, use the Freesound and Jamendo tools instead.

## Procedimiento

### 1. Verify API status
Call `pixabay_api_status` first. It returns a combined report for all 3 providers. If a provider is `ok: false`, instruct the user to run `/pixabay setup`.

### 2. Search for visual assets

**Images:** Use `pixabay_search_images` with:
- `q`: Short English keywords (e.g., "sunset ocean", "coffee shop interior"). Max 100 chars.
- `image_type`: `photo`, `illustration`, `vector`, or `all` (default)
- `orientation`: `horizontal`, `vertical`, or `all` (default)
- `category`: One of the predefined categories (nature, food, technology, etc.)
- `colors`: Comma-separated color filter (e.g., "blue,white")
- `min_width` / `min_height`: Pixel dimensions (e.g., 1920 for HD)
- `safesearch`: `true` by default
- `per_page`: 3–200, default 20

**Videos:** Use `pixabay_search_videos` with:
- Same params as images except: no `image_type`/`orientation`/`colors`
- Add `video_type`: `all` (default), `film`, or `animation`

### 3. Search for sound effects (Freesound)

Use `pixabay_search_sfx` to find SFX:
- `q`: Search keywords (max 100 chars). E.g., "rain on window", "footsteps concrete", "thunder rumble".
- `filter_duration_min` / `filter_duration_max`: Duration bounds in seconds. E.g., `filter_duration_min=0.5, filter_duration_max=10` for short clips.
- `license`: Filter by license. For commercial use, prefer `"Creative Commons 0"` or `"Attribution"`.
- `sort`: `score` (relevance, default), `duration_desc`, `duration_asc`, `downloads_desc`, `created_desc`
- `per_page`: 1–50 (default 15)

### 4. Search for music (Jamendo)

Use `pixabay_search_music` to find music tracks. **Important: Jamendo's `q` matches TRACK TITLES only** — a style query like `q="ambient"` returns 0 results. Use the right param:
- `genre`: style/genre search — ambient, rock, pop, electronic, classical, jazz, lounge, etc. (e.g. `genre="ambient"`)
- `tags`: keyword search — cinematic, epic, sad, lo-fi, horror, etc. (e.g. `tags="cinematic"`)
- `q`: specific track titles/words only
- `vocalinstrumental`: `"instrumental"` for BGM/background, `"vocal"` for songs.
- `order`: `popularity_total` (default), `popularity_week`, `popularity_month`, `rating`, `random`
- `limit`: 1–200 (default 10)

**Search strategy:** style → `genre`; mood/keyword → `tags`; known title → `q`. Combine with `vocalinstrumental="instrumental"` for background music.

### 5. Review results

**Pixabay hits** include:
- `previewURL` (150px thumbnail) — quick review
- `webformatURL` (640px) — **expires in 24 hours**
- `largeImageURL` (1280px) — preferred for local use
- For videos: `videos.large/medium/small/tiny` — prefer `medium`

**Freesound hits** include:
- `previews.hq_mp3` / `previews.lq_mp3` — preview URLs (**expire**, always download before use)
- `duration`, `username`, `license`, `pageURL`

**Jamendo hits** include:
- `audio_download` — direct MP3 download URL (may be null; `audio` streaming URL always works)
- `artist_name`, `license_ccurl`, `pageURL` (shareurl)

### 6. Download assets locally

```
pixabay_download_image(id, size="large", dest_dir="C:/path/to/project/media/pixabay/")
pixabay_download_video(id, quality="medium", dest_dir="C:/path/to/project/media/pixabay/")
pixabay_download_sfx(id, dest_dir="C:/path/to/project/media/sfx/")  # hq by default
pixabay_download_music(id, dest_dir="C:/path/to/project/media/music/")
```

Create destination directories by type (the tools create directories automatically). Use the active project's media convention when one exists (e.g. `media/assets/pixabay/<category>/`).

**Note on Freesound preview URLs:** They expire (signed URLs). `pixabay_download_sfx` resolves the sound fresh before downloading, so it always works.

### 7. Attribution

- **Pixabay:** Free under Pixabay license (no attribution required but appreciated). Include `pageURL` and `user` in project notes.
- **Freesound:** License varies per sound. The `attribution` field in the download response provides the correct attribution text. CC-BY variants require attribution.
- **Jamendo:** License varies per track (check `license_ccurl`). CC-BY-NC-ND is common. The `attribution` field provides the correct attribution text.

## Licencias

| License | Attribution | Commercial use | Notes |
|---------|-------------|----------------|-------|
| CC0 (Creative Commons 0) | Not required | ✅ Yes | Public domain dedication |
| CC-BY (Attribution) | Required | ✅ Yes | Use the attribution text from the tool response |
| CC-BY-SA (Attribution Share Alike) | Required | ✅ Yes | Derivative works must use same license |
| CC-BY-NC (Attribution Noncommercial) | Required | ❌ No | Non-commercial projects only |
| CC-BY-NC-SA | Required | ❌ No | Non-commercial + same license |
| CC-BY-NC-ND | Required | ❌ No | Non-commercial + no derivatives |
| Pixabay License | Not required | ✅ Yes | Pixabay content — free for commercial use |

**Tip:** For commercial projects, filter SFX with `license="Creative Commons 0"` and check Jamendo's `license_ccurl` before downloading.

## Etiqueta / Límites

| Rule | Detail |
|------|--------|
| Pixabay rate limit | 100 requests per 60 seconds |
| Freesound rate limit | ~2000 requests per day |
| Jamendo | No strict rate limit documented; be reasonable |
| Response caching | Pixabay responses cached 24h (server handles this). Freesound/Jamendo NOT cached. |
| No bulk scraping | Do not iterate through hundreds of pages |
| Images: download required | Hotlinking Pixabay URLs is not allowed |
| `webformatURL` expiry | URLs expire after 24h — download if needed long-term |
| Freesound previews | Preview URLs expire — `pixabay_download_sfx` resolves fresh each time |

## Troubleshooting

| Error | Solution |
|-------|----------|
| Pixabay 429 | Wait until the `X-RateLimit-Reset` timestamp (shown in `rateLimit` response) |
| "Pixabay API key not configured" | Run `/pixabay setup` or set `PIXABAY_API_KEY` env var |
| "Freesound token not configured" | Run `/pixabay setup` or set `FREESOUND_TOKEN` env var (get token at https://freesound.org/apiv2/apply/) |
| Freesound 401/403 | Invalid or revoked token — re-apply at freesound.org |
| Freesound 429 | Rate limited (~2000/day) — wait and retry later |
| "Jamendo client_id not configured" | Run `/pixabay setup` or set `JAMENDO_CLIENT_ID` env var (get at https://developer.jamendo.com) |
| Jamendo `headers.status: "failed"` | Invalid client_id — check your Jamendo account |
| Jamendo empty results | Try broader search terms or remove genre filter (the server retries empty searches automatically) |
| Freesound empty results | Try different keywords; check filter syntax |
| `fullHDURL`/`imageURL` empty | Account not approved — use `largeImageURL` |
| Video `large` quality empty | Some videos lack large — use `medium` or `small` |
| Download URL returns 403 | Pixabay URL expired (24h TTL) — re-search |
| `q` too long | Query must be ≤100 characters |

## Reference

See [api.md](references/api.md) for complete API references covering Pixabay, Freesound, and Jamendo with all parameters, response fields, and examples.
