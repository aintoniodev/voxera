#!/usr/bin/env python3
"""Pixabay MCP server — stdio FastMCP exposing Pixabay, Freesound, and Jamendo APIs."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("pixabay")

API_BASE = "https://pixabay.com/api/"
API_VIDEOS_BASE = "https://pixabay.com/api/videos/"
FREESOUND_BASE = "https://freesound.org"
JAMENDO_BASE = "https://api.jamendo.com/v3.0/tracks/"
USER_AGENT = "pixabay-mcp/1.1"
TIMEOUT = 30
CACHE_TTL = 86400  # 24 hours
CACHE_DIR = Path(tempfile.gettempdir()) / "pixabay-mcp-cache"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _config_path() -> Path:
    return Path(os.path.expanduser("~")) / ".pi" / "agent" / "pixabay-config.json"


def _legacy_config_path() -> Path:
    """Legacy config inside the extension dir (parent of mcp-server/)."""
    return Path(__file__).resolve().parent.parent / "config.json"


def _read_config() -> dict:
    """Read the config file (primary then legacy), returning a dict."""
    for cfg in (_config_path(), _legacy_config_path()):
        if cfg.is_file():
            try:
                return json.loads(cfg.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}


def _get_api_key() -> str:
    """Resolve the Pixabay API key from env, config, or legacy config."""
    key = os.environ.get("PIXABAY_API_KEY", "").strip()
    if key:
        return key

    data = _read_config()
    key = (data.get("apiKey") or "").strip()
    if key:
        return key

    raise RuntimeError(
        "Pixabay API key not configured. Run /pixabay setup or set PIXABAY_API_KEY."
    )


def _get_freesound_token() -> str:
    """Resolve the Freesound token from env, config, or legacy config."""
    token = os.environ.get("FREESOUND_TOKEN", "").strip()
    if token:
        return token

    data = _read_config()
    token = (data.get("freesoundToken") or "").strip()
    if token:
        return token

    raise RuntimeError(
        "Freesound token not configured. Run /pixabay setup or set FREESOUND_TOKEN."
    )


def _get_jamendo_client_id() -> str:
    """Resolve the Jamendo client_id from env, config, or legacy config."""
    cid = os.environ.get("JAMENDO_CLIENT_ID", "").strip()
    if cid:
        return cid

    data = _read_config()
    cid = (data.get("jamendoClientId") or "").strip()
    if cid:
        return cid

    raise RuntimeError(
        "Jamendo client_id not configured. Run /pixabay setup or set JAMENDO_CLIENT_ID."
    )


def _cache_key(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()


def _cache_get(url: str) -> dict | None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / (_cache_key(url) + ".json")
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - data.get("_cached_at", 0) > CACHE_TTL:
            path.unlink(missing_ok=True)
            return None
        return data
    except Exception:
        return None


def _cache_put(url: str, payload: dict, rate_headers: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / (_cache_key(url) + ".json")
    payload["_cached_at"] = time.time()
    payload["_rateLimit"] = rate_headers
    try:
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _parse_rate_headers(headers) -> dict:
    def _get(name: str) -> str | None:
        for k, v in headers.items():
            if k.lower() == name.lower():
                return v
        return None

    result: dict[str, Any] = {}
    limit = _get("X-RateLimit-Limit")
    remaining = _get("X-RateLimit-Remaining")
    reset = _get("X-RateLimit-Reset")
    if limit is not None:
        result["limit"] = int(limit)
    if remaining is not None:
        result["remaining"] = int(remaining)
    if reset is not None:
        result["reset"] = int(reset)
    return result


def _api_get(url: str) -> tuple[dict, dict]:
    """GET a Pixabay API endpoint. Returns (parsed_json, rate_headers).
    Raises RuntimeError on non-200 responses.
    """
    # Check cache
    cached = _cache_get(url)
    if cached is not None:
        rate = cached.pop("_rateLimit", {})
        cached.pop("_cached_at", None)
        return cached, rate

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            status = resp.getcode()
            body = resp.read().decode("utf-8")
            headers = dict(resp.headers)
    except urllib.error.HTTPError as e:
        status = e.code
        body = e.read().decode("utf-8", errors="replace")
        if status == 429:
            raise RuntimeError(f"Pixabay API rate limit exceeded: {body}")
        raise RuntimeError(f"Pixabay API error {status}: {body}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Pixabay API request failed: {e.reason}")

    if status != 200:
        raise RuntimeError(f"Pixabay API error {status}: {body}")

    rate_headers = _parse_rate_headers(headers)
    data = json.loads(body)
    _cache_put(url, data, rate_headers)
    return data, rate_headers


def _build_url(base: str, params: dict[str, Any]) -> str:
    """Build a URL with only non-None params (callers pre-normalize defaults)."""
    filtered = {}
    for k, v in params.items():
        if v is None:
            continue
        if isinstance(v, bool):
            filtered[k] = "true" if v else "false"
        else:
            filtered[k] = str(v)
    if filtered:
        return base + "?" + urllib.parse.urlencode(filtered)
    return base


def _trim_image_hit(hit: dict) -> dict:
    trimmed: dict[str, Any] = {
        "id": hit.get("id"),
        "type": hit.get("type"),
        "tags": hit.get("tags"),
        "pageURL": hit.get("pageURL"),
        "previewURL": hit.get("previewURL"),
        "webformatURL": hit.get("webformatURL"),
        "webformatWidth": hit.get("webformatWidth"),
        "webformatHeight": hit.get("webformatHeight"),
        "largeImageURL": hit.get("largeImageURL"),
        "imageWidth": hit.get("imageWidth"),
        "imageHeight": hit.get("imageHeight"),
        "imageSize": hit.get("imageSize"),
        "views": hit.get("views"),
        "downloads": hit.get("downloads"),
        "likes": hit.get("likes"),
        "user": hit.get("user"),
    }
    # Include optional keys only when present
    if hit.get("fullHDURL"):
        trimmed["fullHDURL"] = hit["fullHDURL"]
    if hit.get("imageURL"):
        trimmed["imageURL"] = hit["imageURL"]
    return trimmed


def _trim_video_hit(hit: dict) -> dict:
    videos_data = hit.get("videos", {})
    trimmed_videos: dict[str, Any] = {}
    for quality in ("large", "medium", "small", "tiny"):
        v = videos_data.get(quality, {})
        if v and (v.get("url") or v.get("size", 0) > 0):
            trimmed_videos[quality] = {
                "url": v.get("url", ""),
                "width": v.get("width", 0),
                "height": v.get("height", 0),
                "size": v.get("size", 0),
                "thumbnail": v.get("thumbnail", ""),
            }
    return {
        "id": hit.get("id"),
        "type": hit.get("type"),
        "tags": hit.get("tags"),
        "duration": hit.get("duration"),
        "pageURL": hit.get("pageURL"),
        "videos": trimmed_videos,
        "views": hit.get("views"),
        "downloads": hit.get("downloads"),
        "likes": hit.get("likes"),
        "user": hit.get("user"),
    }


# ---------------------------------------------------------------------------
# Freesound helpers (no caching — preview URLs expire)
# ---------------------------------------------------------------------------

def _fs_get(path_and_query: str) -> tuple[dict, dict]:
    """GET a Freesound API v2 endpoint. path_and_query starts with /apiv2/..."""
    token = _get_freesound_token()
    sep = "&" if "?" in path_and_query else "?"
    url = f"{FREESOUND_BASE}{path_and_query}{sep}token={token}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            status = resp.getcode()
            body = resp.read().decode("utf-8")
            headers = dict(resp.headers)
    except urllib.error.HTTPError as e:
        status = e.code
        body = e.read().decode("utf-8", errors="replace")
        detail = ""
        try:
            detail = json.loads(body).get("detail", body)
        except Exception:
            detail = body
        raise RuntimeError(f"Freesound API error {status}: {detail}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Freesound request failed: {e.reason}")

    data = json.loads(body)
    rate = _parse_rate_headers(headers)
    return data, rate


def _jm_get(params: dict[str, Any], retries: int = 3) -> tuple[dict, dict]:
    """GET a Jamendo API v3.0 endpoint (always /tracks/).

    Jamendo's search is flaky (load-balanced cache shards): the same query
    returns results or 0 depending on the shard. Retry empty searches.
    """
    client_id = _get_jamendo_client_id()
    params["client_id"] = client_id
    params["format"] = "json"
    url = JAMENDO_BASE + "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            status = resp.getcode()
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Jamendo HTTP error {e.code}: {e.read().decode('utf-8', errors='replace')}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Jamendo request failed: {e.reason}")

    data = json.loads(body)
    headers = data.get("headers", {})
    if headers.get("status") == "failed":
        raise RuntimeError(f"Jamendo API error: {headers.get('error_message', 'unknown')}")
    if not data.get("results") and retries > 0:
        time.sleep(0.6)
        return _jm_get(params, retries - 1)
    return data, {}


def _download_file(url: str, dest: Path, timeout: int = 60) -> Path:
    """Download a URL to dest, return the path. mkdir -p dest parent."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Download failed ({e.code}): {e.read().decode('utf-8', errors='replace')}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Download failed: {e.reason}")
    dest.write_bytes(content)
    return dest


# ---------------------------------------------------------------------------
# Pixabay Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def search_images(
    q: str | None = None,
    image_type: str = "all",
    orientation: str = "all",
    category: str | None = None,
    colors: str | None = None,
    min_width: int = 0,
    min_height: int = 0,
    editors_choice: bool = False,
    safesearch: bool = True,
    order: str = "popular",
    page: int = 1,
    per_page: int = 20,
    lang: str = "en",
) -> str:
    """Search Pixabay for images.

    Args:
        q: Search query (URL-encoded, max 100 chars). Omit for popular images.
        image_type: all | photo | illustration | vector
        orientation: all | horizontal | vertical
        category: backgrounds, fashion, nature, science, education, feelings, health, people, religion, places, animals, industry, computer, food, sports, transportation, travel, buildings, business, music
        colors: comma-separated from: grayscale, transparent, red, orange, yellow, green, turquoise, blue, lilac, pink, white, gray, black, brown
        min_width: Minimum image width in pixels
        min_height: Minimum image height in pixels
        editors_choice: Only editor's choice images
        safesearch: Enable safe search (default: True)
        order: popular (default) | latest
        page: Page number (default: 1)
        per_page: Results per page 3-200 (default: 20)
        lang: Language code (default: en)
    """
    if q and len(q) > 100:
        raise RuntimeError("Query 'q' must be 100 characters or fewer.")
    # Pixabay validates per_page 3-200 and page >= 1 — clamp instead of erroring
    if per_page < 3:
        per_page = 3
    if per_page > 200:
        per_page = 200
    if page < 1:
        page = 1

    api_key = _get_api_key()
    params: dict[str, Any] = {
        "key": api_key,
        "q": q if q else None,
        "image_type": image_type if image_type != "all" else None,
        "orientation": orientation if orientation != "all" else None,
        "category": category,
        "colors": colors,
        "min_width": min_width if min_width > 0 else None,
        "min_height": min_height if min_height > 0 else None,
        "editors_choice": editors_choice if editors_choice else None,
        "safesearch": safesearch,
        "order": order if order != "popular" else None,
        "page": page if page != 1 else None,
        "per_page": per_page if per_page != 20 else None,
        "lang": lang if lang != "en" else None,
    }
    url = _build_url(API_BASE, params)
    data, rate = _api_get(url)
    hits = [_trim_image_hit(h) for h in data.get("hits", [])]
    total_hits = data.get("totalHits", 0)
    return json.dumps(
        {"total": data.get("total", total_hits), "totalHits": total_hits, "rateLimit": rate, "hits": hits},
        ensure_ascii=False,
    )


@mcp.tool()
def search_videos(
    q: str | None = None,
    video_type: str = "all",
    category: str | None = None,
    min_width: int = 0,
    min_height: int = 0,
    editors_choice: bool = False,
    safesearch: bool = True,
    order: str = "popular",
    page: int = 1,
    per_page: int = 20,
    lang: str = "en",
) -> str:
    """Search Pixabay for videos.

    Args:
        q: Search query (URL-encoded, max 100 chars). Omit for popular videos.
        video_type: all | film | animation
        category: backgrounds, fashion, nature, science, education, feelings, health, people, religion, places, animals, industry, computer, food, sports, transportation, travel, buildings, business, music
        min_width: Minimum video width in pixels
        min_height: Minimum video height in pixels
        editors_choice: Only editor's choice videos
        safesearch: Enable safe search (default: True)
        order: popular (default) | latest
        page: Page number (default: 1)
        per_page: Results per page 3-200 (default: 20)
        lang: Language code (default: en)
    """
    if q and len(q) > 100:
        raise RuntimeError("Query 'q' must be 100 characters or fewer.")
    # Pixabay validates per_page 3-200 and page >= 1 — clamp instead of erroring
    if per_page < 3:
        per_page = 3
    if per_page > 200:
        per_page = 200
    if page < 1:
        page = 1

    api_key = _get_api_key()
    params: dict[str, Any] = {
        "key": api_key,
        "q": q if q else None,
        "video_type": video_type if video_type != "all" else None,
        "category": category,
        "min_width": min_width if min_width > 0 else None,
        "min_height": min_height if min_height > 0 else None,
        "editors_choice": editors_choice if editors_choice else None,
        "safesearch": safesearch,
        "order": order if order != "popular" else None,
        "page": page if page != 1 else None,
        "per_page": per_page if per_page != 20 else None,
        "lang": lang if lang != "en" else None,
    }
    url = _build_url(API_VIDEOS_BASE, params)
    data, rate = _api_get(url)
    hits = [_trim_video_hit(h) for h in data.get("hits", [])]
    total_hits = data.get("totalHits", 0)
    return json.dumps(
        {"total": data.get("total", total_hits), "totalHits": total_hits, "rateLimit": rate, "hits": hits},
        ensure_ascii=False,
    )


@mcp.tool()
def get_image(id: int) -> str:
    """Get a single image by its Pixabay ID.

    Args:
        id: Pixabay image ID (numeric)
    """
    api_key = _get_api_key()
    url = _build_url(API_BASE, {"key": api_key, "id": str(id)})
    data, rate = _api_get(url)
    hits = data.get("hits", [])
    if not hits:
        return json.dumps({"found": False, "message": "not found"})
    return json.dumps(
        {"found": True, "rateLimit": rate, "hit": _trim_image_hit(hits[0])},
        ensure_ascii=False,
    )


@mcp.tool()
def get_video(id: int) -> str:
    """Get a single video by its Pixabay ID.

    Args:
        id: Pixabay video ID (numeric)
    """
    api_key = _get_api_key()
    url = _build_url(API_VIDEOS_BASE, {"key": api_key, "id": str(id)})
    data, rate = _api_get(url)
    hits = data.get("hits", [])
    if not hits:
        return json.dumps({"found": False, "message": "not found"})
    return json.dumps(
        {"found": True, "rateLimit": rate, "hit": _trim_video_hit(hits[0])},
        ensure_ascii=False,
    )


@mcp.tool()
def download_image(id: int, size: str, dest_dir: str) -> str:
    """Download a Pixabay image to a local directory.

    Args:
        id: Pixabay image ID (numeric)
        size: preview | webformat | large | fullhd | original
        dest_dir: Destination directory (created if missing)
    """
    if size not in ("preview", "webformat", "large", "fullhd", "original"):
        raise RuntimeError(f"Invalid size '{size}'. Use: preview, webformat, large, fullhd, original.")

    api_key = _get_api_key()
    url = _build_url(API_BASE, {"key": api_key, "id": str(id)})
    data, rate = _api_get(url)
    hits = data.get("hits", [])
    if not hits:
        return json.dumps({"error": "Image not found"})

    hit = hits[0]
    size_map = {
        "preview": "previewURL",
        "webformat": "webformatURL",
        "large": "largeImageURL",
        "fullhd": "fullHDURL",
        "original": "imageURL",
    }
    field = size_map[size]
    download_url = hit.get(field)
    if not download_url:
        raise RuntimeError(
            f"URL not available for size '{size}' on this image (field '{field}' is empty). "
            f"fullHD and original are only available for approved accounts. Try size=large."
        )

    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    # Determine extension from URL
    url_path = urllib.parse.urlparse(download_url).path
    ext = Path(url_path).suffix or ".jpg"
    filename = f"pixabay_{id}{ext}"
    filepath = dest / filename

    req = urllib.request.Request(download_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            content = resp.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Download failed ({e.code}): {e.read().decode('utf-8', errors='replace')}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Download failed: {e.reason}")

    filepath.write_bytes(content)

    return json.dumps(
        {
            "file": str(filepath),
            "bytes": len(content),
            "source_url": download_url,
            "pageURL": hit.get("pageURL", ""),
            "user": hit.get("user", ""),
            "tags": hit.get("tags", ""),
        },
        ensure_ascii=False,
    )


@mcp.tool()
def download_video(id: int, quality: str, dest_dir: str) -> str:
    """Download a Pixabay video to a local directory.

    Args:
        id: Pixabay video ID (numeric)
        quality: tiny | small | medium | large
        dest_dir: Destination directory (created if missing)
    """
    if quality not in ("tiny", "small", "medium", "large"):
        raise RuntimeError(f"Invalid quality '{quality}'. Use: tiny, small, medium, large.")

    api_key = _get_api_key()
    url = _build_url(API_VIDEOS_BASE, {"key": api_key, "id": str(id)})
    data, rate = _api_get(url)
    hits = data.get("hits", [])
    if not hits:
        return json.dumps({"error": "Video not found"})

    hit = hits[0]
    videos = hit.get("videos", {})
    video_data = videos.get(quality, {})
    download_url = video_data.get("url", "")
    if not download_url:
        available = [q for q in ("tiny", "small", "medium", "large") if videos.get(q, {}).get("url")]
        raise RuntimeError(
            f"Video quality '{quality}' URL is not available for this video. "
            f"Available qualities: {', '.join(available) or 'none'}. Try quality=medium or small."
        )

    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    filename = f"pixabay_{id}_{quality}.mp4"
    filepath = dest / filename

    req = urllib.request.Request(download_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            content = resp.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Download failed ({e.code}): {e.read().decode('utf-8', errors='replace')}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Download failed: {e.reason}")

    filepath.write_bytes(content)

    return json.dumps(
        {
            "file": str(filepath),
            "bytes": len(content),
            "source_url": download_url,
            "pageURL": hit.get("pageURL", ""),
            "user": hit.get("user", ""),
        },
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# Freesound Tools (SFX)
# ---------------------------------------------------------------------------

@mcp.tool()
def search_sfx(
    q: str,
    filter_duration_min: float | None = None,
    filter_duration_max: float | None = None,
    license: str | None = None,
    sort: str = "score",
    page: int = 1,
    per_page: int = 15,
) -> str:
    """Search Freesound for sound effects.

    Args:
        q: Search query (max 100 chars). Required.
        filter_duration_min: Minimum duration in seconds (e.g. 0.0).
        filter_duration_max: Maximum duration in seconds (e.g. 15.0). Use None for no upper bound.
        license: License filter, e.g. "Creative Commons 0", "Attribution", "Attribution Noncommercial".
        sort: score (default) | duration_desc | duration_asc | downloads_desc | created_desc | created_asc
        page: Page number (default: 1)
        per_page: Results per page 1-50 (default: 15)
    """
    if not q:
        raise RuntimeError("Query 'q' is required.")
    if len(q) > 100:
        raise RuntimeError("Query 'q' must be 100 characters or fewer.")
    if per_page > 50:
        per_page = 50
    if per_page < 1:
        per_page = 1

    # Build filter string
    filters: list[str] = []
    if filter_duration_min is not None or filter_duration_max is not None:
        lo = filter_duration_min if filter_duration_min is not None else "*"
        hi = filter_duration_max if filter_duration_max is not None else "*"
        filters.append(f"duration:[{lo} TO {hi}]")
    if license:
        filters.append(f'license:"{license}"')
    filter_str = " AND ".join(filters) if filters else ""

    params: dict[str, Any] = {
        "query": q,
        "sort": sort if sort != "score" else None,
        "page": page if page != 1 else None,
        "page_size": per_page if per_page != 15 else None,
        "fields": "id,name,duration,previews,username,license,url,tags",
    }
    if filter_str:
        params["filter"] = filter_str

    # Build path_and_query
    qp = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    path_q = f"/apiv2/search/text/?{qp}"

    data, rate = _fs_get(path_q)
    results = []
    for hit in data.get("results", []):
        previews_raw = hit.get("previews", {})
        results.append({
            "id": hit.get("id"),
            "name": hit.get("name"),
            "duration": hit.get("duration"),
            "username": hit.get("username"),
            "license": hit.get("license"),
            "pageURL": hit.get("url"),
            "tags": hit.get("tags"),
            "previews": {
                "hq_mp3": previews_raw.get("preview-hq-mp3", ""),
                "hq_ogg": previews_raw.get("preview-hq-ogg", ""),
                "lq_mp3": previews_raw.get("preview-lq-mp3", ""),
                "lq_ogg": previews_raw.get("preview-lq-ogg", ""),
            },
        })

    return json.dumps(
        {"count": data.get("count", 0), "rateLimit": rate, "results": results},
        ensure_ascii=False,
    )


@mcp.tool()
def download_sfx(id: int, dest_dir: str, format: str = "hq") -> str:
    """Download a Freesound SFX to a local directory (preview MP3 only).

    Args:
        id: Freesound sound ID (numeric)
        dest_dir: Destination directory (created if missing)
        format: hq (default) or lq — determines which preview quality to fetch
    """
    if format not in ("hq", "lq"):
        raise RuntimeError(f"Invalid format '{format}'. Use: hq, lq.")

    # Resolve fresh sound (preview URLs expire)
    data, _ = _fs_get(f"/apiv2/sounds/{id}/?fields=id,name,duration,previews,username,license,url")
    previews = data.get("previews", {})
    if format == "hq":
        download_url = previews.get("preview-hq-mp3", "")
    else:
        download_url = previews.get("preview-lq-mp3", "")

    if not download_url:
        raise RuntimeError(f"No {format} MP3 preview available for sound {id}.")

    dest = Path(dest_dir)
    filepath = dest / f"freesound_{id}.mp3"
    _download_file(download_url, filepath, timeout=60)

    return json.dumps(
        {
            "file": str(filepath),
            "bytes": filepath.stat().st_size,
            "pageURL": data.get("url", ""),
            "username": data.get("username", ""),
            "license": data.get("license", ""),
            "duration": data.get("duration"),
            "attribution": f"Freesound.org sound {id} by {data.get('username', '?')} — {data.get('license', '?')} ({data.get('url', '')})",
        },
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# Jamendo Tools (Music)
# ---------------------------------------------------------------------------

@mcp.tool()
def search_music(
    q: str | None = None,
    genre: str | None = None,
    tags: str | None = None,
    vocalinstrumental: str | None = None,
    order: str = "popularity_total",
    limit: int = 10,
    offset: int = 0,
    audioformat: str = "mp32",
) -> str:
    """Search Jamendo for music tracks.

    IMPORTANT: Jamendo's `q` (search) matches TRACK TITLES only — a style
    query like "ambient" returns 0 results. For styles/genres use
    `genre` (e.g. genre=ambient, rock, electronic, classical, lounge) and
    for keywords use `tags` (e.g. tags=cinematic, epic, lo-fi).

    Args:
        q: Track-title text search. Omit to get popular tracks.
        genre: Genre filter (ambient, rock, pop, electronic, classical, jazz, lounge, ...).
        tags: Keyword/tag search (cinematic, epic, sad, lo-fi, ...).
        vocalinstrumental: instrumental (for BGM) | vocal
        order: popularity_total (default) | popularity_week | popularity_month | rating | random
        limit: Number of results 1-200 (default: 10)
        offset: Pagination offset (default: 0)
        audioformat: mp31 (128k) | mp32 (320k, default) | ogg
    """
    if limit < 1:
        limit = 1
    if limit > 200:
        limit = 200

    params: dict[str, Any] = {
        "search": q if q else None,
        "genre": genre,
        "tags": tags,
        "vocalinstrumental": vocalinstrumental,
        "order": order if order != "popularity_total" else None,
        "limit": limit if limit != 10 else None,
        "offset": offset if offset != 0 else None,
        # Always send audioformat explicitly: Jamendo returns 0 results for
        # some tag searches when it is omitted, and this picks 320k mp3.
        "audioformat": audioformat,
    }

    data, rate = _jm_get(params)
    results = []
    for track in data.get("results", []):
        results.append({
            "id": track.get("id"),
            "name": track.get("name"),
            "duration": track.get("duration"),
            "artist_name": track.get("artist_name"),
            "album_name": track.get("album_name"),
            "license_ccurl": track.get("license_ccurl"),
            "pageURL": track.get("shareurl"),
            "audio": track.get("audio"),
            "audio_download": track.get("audio_download"),
            "image": track.get("image"),
        })

    return json.dumps(
        {"results_count": data.get("headers", {}).get("results_count", 0), "results": results},
        ensure_ascii=False,
    )


@mcp.tool()
def download_music(id: int, dest_dir: str) -> str:
    """Download a Jamendo music track to a local directory.

    Args:
        id: Jamendo track ID (numeric)
        dest_dir: Destination directory (created if missing)
    """
    data, _ = _jm_get({"id": str(id)})
    tracks = data.get("results", [])
    if not tracks:
        return json.dumps({"error": f"Track {id} not found."})

    track = tracks[0]
    download_url = track.get("audio_download") or track.get("audio", "")
    if not download_url:
        raise RuntimeError(f"No download URL available for track {id}.")

    dest = Path(dest_dir)
    filepath = dest / f"jamendo_{id}.mp3"
    _download_file(download_url, filepath, timeout=120)

    return json.dumps(
        {
            "file": str(filepath),
            "bytes": filepath.stat().st_size,
            "pageURL": track.get("shareurl", ""),
            "artist_name": track.get("artist_name", ""),
            "name": track.get("name", ""),
            "duration": track.get("duration"),
            "license_ccurl": track.get("license_ccurl", ""),
            "attribution": f"Jamendo track {id} by {track.get('artist_name', '?')} — {track.get('license_ccurl', '?')} ({track.get('shareurl', '')})",
        },
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# Combined API status
# ---------------------------------------------------------------------------

@mcp.tool()
def api_status() -> str:
    """Check API provider status and rate limits for all configured providers.

    Returns a per-provider report for Pixabay, Freesound, and Jamendo.
    Does NOT raise on errors — always returns a JSON object.
    """
    report: dict[str, Any] = {}

    # --- Pixabay ---
    try:
        api_key = _get_api_key()
    except RuntimeError as e:
        report["pixabay"] = {"ok": False, "message": str(e), "rateLimit": {}}
    else:
        url = _build_url(API_BASE, {"key": api_key, "per_page": "3"})
        try:
            data, rate = _api_get(url)
            total = data.get("totalHits", 0)
            report["pixabay"] = {"ok": True, "message": f"API key valid. {total} total images available.", "rateLimit": rate}
        except RuntimeError as e:
            report["pixabay"] = {"ok": False, "message": str(e), "rateLimit": {}}

    # --- Freesound ---
    try:
        _get_freesound_token()
    except RuntimeError as e:
        report["freesound"] = {"ok": False, "message": str(e)}
    else:
        try:
            _fs_get("/apiv2/search/text/?query=test&page_size=1&fields=id")
            report["freesound"] = {"ok": True, "message": "Freesound token valid."}
        except RuntimeError as e:
            report["freesound"] = {"ok": False, "message": str(e)}

    # --- Jamendo ---
    try:
        _get_jamendo_client_id()
    except RuntimeError as e:
        report["jamendo"] = {"ok": False, "message": str(e)}
    else:
        try:
            _jm_get({"search": "test", "limit": "1"})
            report["jamendo"] = {"ok": True, "message": "Jamendo client_id valid."}
        except RuntimeError as e:
            report["jamendo"] = {"ok": False, "message": str(e)}

    return json.dumps(report, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()
