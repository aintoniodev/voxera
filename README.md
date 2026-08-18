# Stock Assets Plugin for pi (Pixabay · Freesound · Jamendo)

A pi agent plugin that exposes the [Pixabay](https://pixabay.com/) stock image/video API, [Freesound](https://freesound.org/) sound effects API, and [Jamendo](https://www.jamendo.com/) music API as an **MCP server** plus a shared **agent skill**, so any agent on this machine can fetch royalty-free media on demand.

## How agents get motivated to use it

- **Skill (auto-invoked):** `stock-assets` lives in `~/.agents/skills/stock-assets/` — the shared skills directory read by ALL agent harnesses (pi, Claude Code, Codex, Orca, SwarmForge agents, …). Its description is written with trigger words (thumbnails, b-roll, cover art, backgrounds, SFX, ambient audio, music tracks…) so agents load it automatically whenever media is needed. Renamed from `pixabay-assets` because it covers three providers.
- **System-prompt nudge (pi):** the extension appends a stock-media guideline to every turn's system prompt (`before_agent_start`), telling the agent to use the `pixabay_*` tools instead of asking the user where to get media.
- **MCP tools (pi):** registered via `mcp.json` → `pixabay` server (lazy, directTools).

## Architecture

```
┌───────────────────────────────────────────────────────────────────────────┐
│  ANY agent (pi, Claude Code, Codex, ...)                                  │
│    ~/.agents/skills/stock-assets/SKILL.md   ← auto-loaded when media      │
│    is requested (trigger-word description)                                │
│                                                                            │
│  pi agent additionally:                                                    │
│    before_agent_start ──► system prompt nudge ("use pixabay_* tools")      │
│    /pixabay setup/status ──► index.ts (extension)                          │
│                                │                                           │
│                                ▼                                           │
│                         mcp.json entry                                     │
│                         "pixabay" server                                   │
│                                │                                           │
│                                ▼                                           │
│                  mcp-server/pixabay_server.py                              │
│                  (FastMCP stdio, 11 tools)                                 │
│                                │                                           │
│                  ┌─────────────┼─────────────┐                             │
│                  ▼             ▼             ▼                             │
│            pixabay.com    freesound.org   api.jamendo.com                  │
│               /api/         /apiv2/         /v3.0/                         │
│            (images/video)   (SFX)          (music)                         │
└───────────────────────────────────────────────────────────────────────────┘
```

## Install

### From Git Bash:
```bash
bash install.sh
```

### From PowerShell:
```powershell
.\install.ps1
```

Both install (idempotent, junction preferred so repo edits propagate):
1. `extension/` → `~/.pi/agent/extensions/pixabay/`
2. `skills/stock-assets/` → `~/.agents/skills/stock-assets/`

### Then:
Restart pi or run `/reload` to activate the extension. Other harnesses pick up the skill on their next start.

## Usage

1. **Set up API keys** (required: Pixabay; optional: Freesound, Jamendo):
   ```
   /pixabay setup
   ```
   Or set environment variables: `PIXABAY_API_KEY`, `FREESOUND_TOKEN`, `JAMENDO_CLIENT_ID`.

2. **Check status:**
   ```
   /pixabay status
   ```

3. **Ask for assets** — agents auto-invoke the skill and tools. Just ask:
   - "Find me some sunset photos for a thumbnail"
   - "Download a 1080p ocean video clip"
   - "Search for rain sound effects under 5 seconds"
   - "Find instrumental ambient music for a background track"

## Tools (11)

Exposed by the `pixabay` MCP server; agents see them as `pixabay_*`:

| Tool | Provider | Description |
|------|----------|-------------|
| `pixabay_search_images` | Pixabay | Search images with filters (type, orientation, colors, category) |
| `pixabay_search_videos` | Pixabay | Search videos with filters (video_type, category) |
| `pixabay_get_image` | Pixabay | Get a single image by Pixabay ID |
| `pixabay_get_video` | Pixabay | Get a single video by Pixabay ID |
| `pixabay_download_image` | Pixabay | Download an image (preview/webformat/large/fullhd/original) locally |
| `pixabay_download_video` | Pixabay | Download a video (tiny/small/medium/large) locally |
| `pixabay_api_status` | All | Validate API keys and check rate limits for all providers |
| `pixabay_search_sfx` | Freesound | Search sound effects with duration/license/sort filters |
| `pixabay_download_sfx` | Freesound | Download a sound effect (hq/lq MP3 preview) locally |
| `pixabay_search_music` | Jamendo | Search music (genre/tags/instrumental; `q` is title-only) |
| `pixabay_download_music` | Jamendo | Download a music track (MP3) locally |

## API Keys

| Provider | Key | Where to get | Env var | Required |
|----------|-----|--------------|---------|----------|
| Pixabay | API key | https://pixabay.com/api/docs/ | `PIXABAY_API_KEY` | ✅ Yes |
| Freesound | Token | https://freesound.org/apiv2/apply/ | `FREESOUND_TOKEN` | Optional |
| Jamendo | Client ID | https://developer.jamendo.com | `JAMENDO_CLIENT_ID` | Optional |

Keys are stored in `~/.pi/agent/pixabay-config.json`:
```json
{
  "apiKey": "pixabay-key",
  "freesoundToken": "freesound-token",
  "jamendoClientId": "jamendo-client-id"
}
```

## Notes

- **Pixabay images/videos** are cached 24h per ToS; Freesound/Jamendo results are NOT cached
- **Freesound** only provides preview MP3s (not original files) via API — preview URLs expire, resolved fresh by `pixabay_download_sfx`
- **Jamendo** `q` searches track titles only — use `genre=` for styles, `tags=` for moods; search is flaky server-side (the server retries empty results automatically); downloads fall back to the streaming URL when `audio_download` is null
- **Licensing:** Pixabay = free commercial use; Freesound/Jamendo = check per-sound/track CC license (`license` / `license_ccurl` fields)
- **ToS compliance:** no bulk downloads, no hotlinking Pixabay URLs, respect rate limits

## Files

```
pixabay/
├── README.md                                   # This file
├── install.sh                                  # Git Bash installer (extension + skill)
├── install.ps1                                 # PowerShell installer (extension + skill)
├── extension/
│   ├── index.ts                                # pi extension (MCP provisioning, /pixabay command, prompt nudge)
│   └── mcp-server/
│       ├── pixabay_server.py                   # FastMCP stdio server (11 tools)
│       ├── requirements.txt                    # Dependencies (documentation only)
│       └── smoke_test.py                       # End-to-end smoke test
└── skills/
    └── stock-assets/                           # Shared skill (installed to ~/.agents/skills/)
        ├── SKILL.md                            # Agent skill instructions (auto-invoked)
        └── references/
            └── api.md                          # Complete API reference (Pixabay + Freesound + Jamendo)
```

## Uninstall

1. Remove the extension and skill junctions:
   ```bash
   rm -rf ~/.pi/agent/extensions/pixabay
   rm -rf ~/.agents/skills/stock-assets
   ```
2. Remove the `pixabay` entry from `~/.pi/agent/mcp.json`
3. Remove the config file (optional):
   ```bash
   rm ~/.pi/agent/pixabay-config.json
   ```
