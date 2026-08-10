"""Video input/output (Track 4): ffmpeg extraction + muxing.

Contract (docs/SPECS-fase2.md, Track 4):

- ffprobe detects the video stream; audio is extracted to 48 kHz mono PCM
  (project-local temp, landmine #6).
- Output muxes the ORIGINAL video stream bit-identical (``-c:v copy``) with
  the pipeline's audio as AAC 192 kbps (``--audio-bitrate`` override).
- Drift check: container duration + audio stream duration preserved within
  tolerance (encoder-delay aware).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from voxera.errors import EnhancementError

VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".mkv", ".webm", ".m4v"})
VIDEO_AUDIO_BITRATE = "192k"
DRIFT_TOLERANCE_S = 0.05  # 50 ms container-level tolerance (encoder delay aware)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TMP_DIR = PROJECT_ROOT / "tmp"


def _tool(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    candidate = Path(f"C:/ffmpeg/bin/{name}.exe")
    if candidate.exists():
        return str(candidate)
    raise EnhancementError(f"{name} not found on PATH (ffmpeg is required for video)")


def is_video_path(path: str | Path) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTENSIONS


def has_video_stream(path: str | Path) -> bool:
    """True when the file actually carries a video stream (ffprobe)."""
    try:
        proc = subprocess.run(
            [_tool("ffprobe"), "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_type", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        data = json.loads(proc.stdout or "{}")
        return bool(data.get("streams"))
    except Exception as exc:  # noqa: BLE001
        raise EnhancementError(f"ffprobe failed on {path}: {exc}") from exc


def probe_duration(path: str | Path) -> float:
    proc = subprocess.run(
        [_tool("ffprobe"), "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    data = json.loads(proc.stdout or "{}")
    duration = data.get("format", {}).get("duration")
    if duration is None:
        raise EnhancementError(f"cannot read duration of {path}")
    return float(duration)


def extract_audio(video: str | Path, out_wav: str | Path) -> Path:
    """Extract 48 kHz mono PCM audio from ``video`` to ``out_wav``."""
    out = Path(out_wav)
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [_tool("ffmpeg"), "-y", "-v", "error", "-i", str(video),
         "-vn", "-ac", "1", "-ar", "48000", "-c:a", "pcm_s24le", str(out)],
        capture_output=True, text=True, timeout=600,
    )
    if proc.returncode != 0 or not out.exists():
        raise EnhancementError(f"ffmpeg audio extraction failed: {proc.stderr.strip()}")
    return out


def mux(video: str | Path, audio_wav: str | Path, out_path: str | Path, bitrate: str = VIDEO_AUDIO_BITRATE) -> Path:
    """Mux the original video stream (bit-identical) with the new audio (AAC)."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [_tool("ffmpeg"), "-y", "-v", "error",
         "-i", str(video), "-i", str(audio_wav),
         "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-c:a", "aac", "-b:a", bitrate,
         "-movflags", "+faststart",
         str(out)],
        capture_output=True, text=True, timeout=600,
    )
    if proc.returncode != 0 or not out.exists():
        raise EnhancementError(f"ffmpeg mux failed: {proc.stderr.strip()}")
    return out


def check_drift(video: str | Path, out_video: str | Path) -> float:
    """Container-duration drift in seconds; raises when > tolerance."""
    in_dur = probe_duration(video)
    out_dur = probe_duration(out_video)
    drift = abs(in_dur - out_dur)
    if drift > DRIFT_TOLERANCE_S:
        raise EnhancementError(
            f"A/V drift out of tolerance: input {in_dur:.3f}s vs output {out_dur:.3f}s"
        )
    return drift


def temp_wav() -> Path:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(suffix=".wav", dir=str(TMP_DIR))
    import os

    os.close(fd)
    return Path(name)
