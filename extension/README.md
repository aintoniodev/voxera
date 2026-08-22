# Pixabay Agent Plugin for pi

A pi agent plugin that exposes the [Pixabay](https://pixabay.com/) stock image/video API, [Freesound](https://freesound.org/) sound effects API, and [Jamendo](https://www.jamendo.com/) music API as both an MCP server and an agent skill, so pi agents can fetch royalty-free media on demand.

## Architecture

```
┌───────────────────────────────────────────────────────────────────────┐
│  pi agent                                                             │
│                                                                       │
│  resources_discover ──► skills/pixabay-assets/SKILL.md                │
│  /pixabay setup/status ──► index.ts (extension)                       │
│                            │                                          │
│                            ▼                                          │
│                     mcp.json entry                                    │
│                     "pixabay" server                                  │
│                            │                                          │
│                            ▼                                          │
│              mcp-server/pixabay_server.py                             │
│              (FastMCP stdio, 11 tools)                                │
│                            │                                          │
│              ┌─────────────┼─────────────┐                            │
│              ▼             ▼             ▼                            │
│        pixabay.com    freesound.org   api.jamendo.com                 │
│           /api/         /apiv2/         /v3.0/                        │
│        (images/video)   (SFX)          (music)                        │
└───────────────────────────────────────────────────────────────────────┘
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

### Then:
Restart pi or run `/reload` to activate the extension.

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

3. **Ask pi for assets** — the skill loads automatically. Just ask:
   - "Find me some sunset photos for a thumbnail"
   - "Download a 1080p ocean video clip"
   - "Search for rain sound effects under 5 seconds"
   - "Find instrumental ambient music for a background track"

## Tools (11)

| Tool | Provider | Description |
|------|----------|-------------|
| `search_images` | Pixabay | Search images with filters (type, orientation, colors, category) |
| `search_videos` | Pixabay | Search videos with filters (video_type, category) |
| `get_image` | Pixabay | Get a single image by Pixabay ID |
| `get_video` | Pixabay | Get a single video by Pixabay ID |
| `download_image` | Pixabay | Download an image (preview/webformat/large/fullhd/original) locally |
| `download_video` | Pixabay | Download a video (tiny/small/medium/large) locally |
| `api_status` | All | Validate API keys and check rate limits for all providers |
| `search_sfx` | Freesound | Search sound effects with duration/license/sort filters |
| `download_sfx` | Freesound | Download a sound effect (hq/lq MP3 preview) locally |
| `search_music` | Jamendo | Search music with genre/vocal/popularity filters |
| `download_music` | Jamendo | Download a music track (MP3) locally |

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
- **Freesound** only provides preview MP3s (not original files) via API — preview URLs expire, resolved fresh by `download_sfx`
- **Jamendo** provides direct MP3 downloads via `audio_download` URL
- **Licensing:** Pixabay = free commercial use; Freesound/Jamendo = check per-sound/track CC license
- **ToS compliance:** no bulk downloads, no hotlinking Pixabay URLs, respect rate limits

## Files

```
pixabay/
├── README.md                                   # This file
├── install.sh                                  # Git Bash installer
├── install.ps1                                 # PowerShell installer
└── extension/
    ├── index.ts                                # pi extension entry point (setup/status for 3 providers)
    ├── mcp-server/
    │   ├── pixabay_server.py                   # FastMCP stdio server (11 tools)
    │   ├── requirements.txt                    # Dependencies (documentation only)
    │   └── smoke_test.py                       # End-to-end smoke test
    └── skills/
        └── pixabay-assets/
            ├── SKILL.md                        # Agent skill instructions
            └── references/
                └── api.md                      # Complete API reference (Pixabay + Freesound + Jamendo)
```

## Uninstall

1. Remove the extension:
   ```bash
   rm -rf ~/.pi/agent/extensions/pixabay
   ```
2. Remove the `pixabay` entry from `~/.pi/agent/mcp.json`
3. Remove the config file (optional):
   ```bash
   rm ~/.pi/agent/pixabay-config.json
   ```
