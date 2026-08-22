# API Reference

## Pixabay API

### Authentication

All requests require the `key` query parameter with a valid API key from https://pixabay.com/api/docs/

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `https://pixabay.com/api/` | GET | Search images |
| `https://pixabay.com/api/videos/` | GET | Search videos |

### Rate Limits

- **100 requests per 60 seconds** per API key
- Response headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` (Unix timestamp)
- On 429: body text is "API rate limit exceeded"

### Image Search Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `key` | string | **required** | Your API key |
| `q` | string | "" | URL-encoded search term, max 100 chars. Omit for popular images. |
| `lang` | string | `en` | Language: cs, da, de, en, es, fr, id, it, hu, nl, no, pl, pt, ro, sk, fi, sv, tr, vi, th, bg, ru, el, ja, ko, zh |
| `id` | int | — | Return a single image by ID |
| `image_type` | string | `all` | `all`, `photo`, `illustration`, `vector` |
| `orientation` | string | `all` | `all`, `horizontal`, `vertical` |
| `category` | string | — | One of: backgrounds, fashion, nature, science, education, feelings, health, people, religion, places, animals, industry, computer, food, sports, transportation, travel, buildings, business, music |
| `min_width` | int | 0 | Minimum width in pixels |
| `min_height` | int | 0 | Minimum height in pixels |
| `colors` | string | — | Comma-separated: grayscale, transparent, red, orange, yellow, green, turquoise, blue, lilac, pink, white, gray, black, brown |
| `editors_choice` | bool | false | Only editor's choice images |
| `safesearch` | bool | true | Enable safe search |
| `order` | string | `popular` | `popular` or `latest` |
| `page` | int | 1 | Page number |
| `per_page` | int | 20 | Results per page (3–200) |

### Video Search Parameters

Same as images, except:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `video_type` | string | `all` | `all`, `film`, `animation` |

**Not available for videos:** `image_type`, `orientation`, `colors`

### Image Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Unique image ID |
| `pageURL` | string | Pixabay page URL |
| `type` | string | "photo", "illustration", or "vector" |
| `tags` | string | Comma-separated tags |
| `previewURL` | string | 150px thumbnail |
| `previewWidth` / `previewHeight` | int | Thumbnail dimensions |
| `webformatURL` | string | 640px image (**expires in 24h**) |
| `webformatWidth` / `webformatHeight` | int | webformat dimensions |
| `largeImageURL` | string | 1280px image |
| `fullHDURL` | string | 1920px (approved accounts only, may be empty) |
| `imageURL` | string | Original resolution (approved accounts only, may be empty) |
| `imageWidth` / `imageHeight` | int | Original dimensions |
| `imageSize` | int | Original file size in bytes |
| `views` | int | View count |
| `downloads` | int | Download count |
| `likes` | int | Like count |
| `comments` | int | Comment count |
| `user_id` | int | Uploader ID |
| `user` | string | Uploader username |
| `userImageURL` | string | Uploader avatar URL |

### Video Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Unique video ID |
| `pageURL` | string | Pixabay page URL |
| `type` | string | "Film" or "Animation" |
| `tags` | string | Comma-separated tags |
| `duration` | int | Duration in seconds |
| `videos` | object | Quality variants (see below) |
| `views` | int | View count |
| `downloads` | int | Download count |
| `likes` | int | Like count |
| `comments` | int | Comment count |
| `user_id` | int | Uploader ID |
| `user` | string | Uploader username |
| `userImageURL` | string | Uploader avatar URL |

#### Video quality variants

Each quality level (`large`, `medium`, `small`, `tiny`) contains:

| Field | Type | Description |
|-------|------|-------------|
| `url` | string | Video URL (**may be empty for `large`**) |
| `width` | int | Width in pixels |
| `height` | int | Height in pixels |
| `size` | int | File size in bytes |
| `thumbnail` | string | Thumbnail URL |

### Common Response Shape

```json
{
  "total": 1234,
  "totalHits": 500,
  "hits": [...]
}
```

`totalHits` is capped at 500 — use `page` and `per_page` to paginate.

### curl Examples

```bash
# Search images
curl "https://pixabay.com/api/?key=YOUR_KEY&q=sunset&image_type=photo&per_page=3"

# Search videos
curl "https://pixabay.com/api/videos/?key=YOUR_KEY&q=nature&per_page=3"

# Get single image
curl "https://pixabay.com/api/?key=YOUR_KEY&id=12345"
```

### Caching and ToS Rules

1. **24-hour response cache:** All API responses MUST be cached for 24 hours. The MCP server does this automatically in a temp directory.
2. **No bulk scraping:** Do not iterate through hundreds of pages or make mass automated downloads.
3. **Images must be downloaded:** Hotlinking Pixabay image URLs is not allowed. Always download images before use.
4. **Videos may be embedded** but local download is recommended.
5. **`webformatURL` expires in 24 hours** — if you need the file long-term, download it.

---

## Freesound API v2 (Sound Effects)

**Docs:** https://freesound.org/docs/api/  
**Base URL:** `https://freesound.org/apiv2/`  
**Auth:** `token` query parameter (free token from https://freesound.org/apiv2/apply/)

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/apiv2/search/text/` | GET | Search sounds by text query |
| `/apiv2/sounds/{id}/` | GET | Get sound details by ID |

### Rate Limits

- ~2000 requests per day
- Response headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`
- Preview URLs (cdn.freesound.org) are downloadable without token but **expire** (signed URLs) — always resolve fresh before downloading

### Search Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `token` | string | **required** | API token |
| `query` | string | **required** | Search text |
| `filter` | string | — | Filter syntax (see below) |
| `sort` | string | `score` | `score`, `duration_desc`, `duration_asc`, `downloads_desc`, `created_desc`, `created_asc` |
| `page` | int | 1 | Page number |
| `page_size` | int | 15 | Results per page (max 50) |
| `fields` | string | — | Comma-separated fields to return |

#### Filter Syntax

| Filter | Example | Description |
|--------|---------|-------------|
| Duration range | `duration:[0.0 TO 10.0]` | Sounds between 0 and 10 seconds |
| Duration min only | `duration:[2.0 TO *]` | Sounds 2+ seconds |
| License | `license:"Creative Commons 0"` | Exact license match |
| Combined | `duration:[1.0 TO 5.0] AND license:"Attribution"` | Multiple filters |

**License values:** `"Attribution"`, `"Attribution Noncommercial"`, `"Attribution Share Alike"`, `"Attribution Noncommercial Share Alike"`, `"Creative Commons 0"`

### Sound Detail Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `token` | string | **required** |
| `fields` | string | Comma-separated fields: `id,name,duration,previews,username,license,url,tags` |

### Response Fields (per sound)

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Unique sound ID |
| `name` | string | Sound name |
| `tags` | list[str] | Tag list |
| `username` | string | Uploader username |
| `license` | string | License name |
| `url` | string | Freesound page URL |
| `duration` | float | Duration in seconds |
| `previews` | object | Preview URLs (see below) |

#### Preview URLs

| Key | Format | Quality |
|-----|--------|---------|
| `preview-hq-mp3` | MP3 | High quality (~128kbps) |
| `preview-hq-ogg` | OGG | High quality |
| `preview-lq-mp3` | MP3 | Low quality |
| `preview-lq-ogg` | OGG | Low quality |

**Important:** Preview URLs are on `cdn.freesound.org`, are downloadable without token, but **expire** after some time. The MCP `download_sfx` tool resolves fresh before every download.

### Error Responses

| Status | Body | Meaning |
|--------|------|---------|
| 401 | `{"detail": "Authentication credentials were not provided."}` | Missing/invalid token |
| 403 | `{"detail": "You do not have permission to perform this action."}` | Insufficient permissions |
| 404 | `{"detail": "Not found."}` | Sound/resource not found |

### curl Examples

```bash
# Search for rain sounds (CC0, max 10 seconds)
curl "https://freesound.org/apiv2/search/text/?query=rain&filter=duration:[0.0+TO+10.0]+AND+license:%22Creative+Commons+0%22&fields=id,name,duration,previews,username,license,url&token=YOUR_TOKEN"

# Get sound details
curl "https://freesound.org/apiv2/sounds/12345/?fields=id,name,duration,previews,username,license,url&token=YOUR_TOKEN"
```

### Notes

- Only **previews** are available via API (no original file downloads)
- The MCP tool `search_sfx` remaps preview keys: `preview-hq-mp3` → `hq_mp3`, etc.
- The MCP tool `download_sfx` always resolves the sound fresh before downloading

---

## Jamendo API v3 (Music)

**Docs:** https://developer.jamendo.com/v3.0  
**Base URL:** `https://api.jamendo.com/v3.0/tracks/`  
**Auth:** `client_id` query parameter (free from https://developer.jamendo.com)

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v3.0/tracks/` | GET | Search tracks (with optional `&id=N` for single track) |

### Rate Limits

- No strict documented rate limit; be reasonable
- No rate limit headers returned

### Track Search Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `client_id` | string | **required** | Your client ID |
| `format` | string | `json` | Response format (`json`) |
| `search` | string | — | **Title-only search** — matches track titles, NOT styles/genres. `search=ambient` returns 0 results; use `genre` or `tags` instead. |
| `genre` | string | — | Genre filter (ambient, rock, pop, electronic, classical, jazz, lounge, ...) — use for style search |
| `tags` | string | — | Comma-separated tags — use for keyword/mood search (cinematic, epic, sad, lo-fi) |
| `vocalinstrumental` | string | — | `instrumental` or `vocal` |
| `order` | string | `popularity_total` | `popularity_total`, `popularity_week`, `popularity_month`, `rating`, `random` |
| `limit` | int | 10 | Results per page (max 200) |
| `offset` | int | 0 | Pagination offset |
| `audioformat` | string | `mp32` | `mp31` (128k), `mp32` (320k), `ogg` |
| `include` | string | — | `musicinfo` for genre/mood data |
| `id` | int | — | Fetch a single track by ID |

### Response Structure

```json
{
  "headers": {
    "status": "success",
    "code": 0,
    "results_count": 42
  },
  "results": [...]
}
```

On **invalid client_id**: `{"headers": {"status": "failed", "code": 5, "error_message": "..."}, "results": []}`

### Track Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Unique track ID |
| `name` | string | Track name |
| `duration` | float | Duration in seconds |
| `artist_name` | string | Artist name |
| `artist_id` | int | Artist ID |
| `album_name` | string | Album name |
| `license_ccurl` | string | CC license URL (e.g., `http://creativecommons.org/licenses/by-nc-nd/3.0/`) |
| `shareurl` | string | Jamendo page URL (e.g., `https://www.jamendo.com/track/123`) |
| `audio` | string | Streaming MP3 URL |
| `audio_download` | string | Direct MP3 download URL |
| `image` | string | Album art URL |
| `musicinfo` | object | Genre/mood data (when `include=musicinfo`) |

#### musicinfo object

```json
{
  "genres": ["electronic", "ambient"],
  "tags": {...},
  ...
}
```

The MCP `search_music` tool extracts the first genre from `musicinfo.genres`.

### curl Examples

```bash
# Search for instrumental electronic music
curl "https://api.jamendo.com/v3.0/tracks/?client_id=YOUR_ID&format=json&search=electronic+ambient&vocalinstrumental=instrumental&limit=5&include=musicinfo"

# Get track by ID
curl "https://api.jamendo.com/v3.0/tracks/?client_id=YOUR_ID&format=json&id=12345"
```

### Notes

- `audio_download` URLs are direct GET-able MP3s — no auth required to download
- The MCP tool `download_music` uses `audio_download` (falls back to `audio` streaming URL)
- License types vary per track — always check `license_ccurl` before commercial use
- Common licenses: CC-BY-3.0, CC-BY-NC-3.0, CC-BY-NC-ND-3.0

---

## License Summary

| Provider | License | Attribution | Commercial |
|----------|---------|-------------|------------|
| Pixabay | Pixabay License | Not required | ✅ Yes |
| Freesound | Varies (CC0 to CC-BY-NC-SA) | Depends on sound | Depends on sound |
| Jamendo | Varies (CC-BY to CC-BY-NC-ND) | Depends on track | Depends on track |

**For commercial projects:** Use CC0 or CC-BY content only. Check `license`/`license_ccurl` before downloading.
