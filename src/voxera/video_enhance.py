"""``voxera video`` — neural video enhancement (fase 3, vertical 9:16).

Decision record (AB humano en vídeo, 2026-08-12):

- **Default ``animevideov3``** — ganó la comparación AB en dos contenidos
  (talking-head 720p y walking/animación 1080p) y es ~7-10x más rápido.
- ``x4plus`` = escape hatch "natural": más textura real, ~10x más lento.

Pipeline: frames -> RealESRGANer (CUDA) -> target 1080x1920 @30fps -> remux.
Hardware: CUDA obligatoria (CPU medido ~67x más lento que realtime — no
shippable). Velocidades medidas en RTX 2060 6 GB (tile=512, fp16, 2026-08-12):
animevideov3 0.85 fps @720p / 0.39 fps @1080p; x4plus 0.12 / 0.04 fps.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from voxera import video as video_mod
from voxera.errors import EnhancementError

VIDEO_MODEL_ANIME = "animevideov3"
VIDEO_MODEL_X4PLUS = "x4plus"
DEFAULT_VIDEO_MODEL = VIDEO_MODEL_ANIME
VIDEO_MODELS = (VIDEO_MODEL_ANIME, VIDEO_MODEL_X4PLUS)

WEIGHT_FILES = {
    VIDEO_MODEL_ANIME: "realesr-animevideov3.pth",
    VIDEO_MODEL_X4PLUS: "RealESRGAN_x4plus.pth",
}
WEIGHT_URLS = {
    VIDEO_MODEL_ANIME: (
        "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/"
        "realesr-animevideov3.pth"
    ),
    VIDEO_MODEL_X4PLUS: (
        "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/"
        "RealESRGAN_x4plus.pth"
    ),
}
MODELS_DIR = Path(__file__).resolve().parents[2] / "models" / "video"

# Medido en RTX 2060 6 GB (tile=512, fp16) — clave por altura de frame fuente.
MEASURED_FPS = {
    VIDEO_MODEL_ANIME: {720: 0.85, 1080: 0.39},
    VIDEO_MODEL_X4PLUS: {720: 0.12, 1080: 0.04},
}

INSTALL_HINT = (
    "voxera video necesita el extra 'video' con torch CUDA. En Windows:\n"
    "  uv venv --python 3.11 .venv-video\n"
    "  uv pip install -p .venv-video torch torchvision torchaudio "
    "--index-url https://download.pytorch.org/whl/cu121\n"
    "  uv pip install -p .venv-video -e '.[video]'\n"
    "y los pesos en models/video/ (ver README, sección vídeo)."
)


@dataclass(frozen=True)
class VideoOptions:
    """Frozen parameters of a video enhancement run.

    Un solo default (``animevideov3``); el resto son escapes, no un menú:
    ``model=x4plus`` (natural), ``fps``, ``master_audio``, ``crf``...
    """

    model: str = DEFAULT_VIDEO_MODEL
    fps: int = 30
    outscale: int = 2
    width: int = 1080
    height: int = 1920
    tile: int = 512
    half: bool = True
    crf: int = 18
    audio_bitrate: str = "192k"
    master_audio: bool = False
    master_preset: str = "creator"
    keep_frames: bool = False
    seg: tuple[float, float] | None = None

    def validate(self) -> None:
        if self.model not in VIDEO_MODELS:
            raise EnhancementError(
                f"modelo de vídeo desconocido: {self.model!r} "
                f"(válidos: {', '.join(VIDEO_MODELS)})"
            )
        if self.fps <= 0:
            raise EnhancementError(f"fps inválido: {self.fps}")
        if self.outscale not in (1, 2, 3, 4):
            raise EnhancementError(f"outscale inválido: {self.outscale}")
        if self.tile and self.tile < 32:
            raise EnhancementError(f"tile inválido: {self.tile} (<32)")
        if self.seg and not (0 <= self.seg[0] < self.seg[1]):
            raise EnhancementError(f"segmento inválido: {self.seg}")


# ---------------------------------------------------------------------------
# probe
# ---------------------------------------------------------------------------


def probe_video(path: str | Path) -> dict:
    """ffprobe summary: {width, height, fps, fps_ratio, duration_s, codec, bitrate, size, has_audio}."""
    p = Path(path)
    if not p.exists():
        raise EnhancementError(f"no existe: {p}")
    if not video_mod.has_video_stream(p):
        raise EnhancementError(f"sin stream de vídeo: {p}")
    proc = subprocess.run(
        [video_mod._tool("ffprobe"), "-v", "error",
         "-show_streams",
         "-show_entries", "stream=codec_type,width,height,r_frame_rate,codec_name",
         "-show_entries", "format=duration,bit_rate,size",
         "-of", "json", str(p)],
        capture_output=True, text=True, timeout=60,
    )
    data = json.loads(proc.stdout or "{}")
    streams = data.get("streams", [])
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    fmt = data.get("format", {})
    fps_ratio = video_stream.get("r_frame_rate", "0/0")
    try:
        num, den = fps_ratio.split("/")
        fps = float(num) / float(den) if float(den) else 0.0
    except (ValueError, ZeroDivisionError):
        fps = 0.0
    bitrate = fmt.get("bit_rate")
    return {
        "width": video_stream.get("width"),
        "height": video_stream.get("height"),
        "fps": round(fps, 3),
        "fps_ratio": fps_ratio,
        "duration_s": float(fmt.get("duration") or 0.0),
        "codec": video_stream.get("codec_name"),
        "bitrate": int(bitrate) if bitrate else None,
        "size": int(fmt.get("size") or 0),
        "has_audio": audio_stream is not None,
    }


def _estimate_seconds(probe: dict, options: VideoOptions) -> float:
    """Estimated processing time from measured fps (RTX 2060)."""
    short = min(probe["width"] or 0, probe["height"] or 0)
    base = 720 if short <= 900 else 1080
    rate = MEASURED_FPS[options.model].get(base, 0.1)
    frames = int((probe["duration_s"] or 0.0) * options.fps)
    return frames / rate


def build_plan(path: str | Path, options: VideoOptions) -> str:
    """The ``VOXERA PLAN`` dry-run text. Never loads NN, never writes."""
    options.validate()
    probe = probe_video(path)
    est = _estimate_seconds(probe, options)
    lines = ["VOXERA PLAN (video)", ""]
    lines.append("Input:")
    lines.append(
        f"  {Path(path).name} · {probe['width']}x{probe['height']} · "
        f"{probe['fps_ratio']} fps · {probe['duration_s']:.1f} s · "
        f"{probe['codec']} · {(probe['bitrate'] or 0) / 1e6:.1f} Mbps"
    )
    lines.append("")
    lines.append("Pipeline:")
    lines.append(f"  ✓ Real-ESRGAN {options.model} (CUDA, tile={options.tile}, "
                 f"{'fp16' if options.half else 'fp32'})")
    lines.append(f"  ✓ frames @ {options.fps} fps -> {options.width}x{options.height} "
                 f"({options.outscale}x interno + downscale lanczos)")
    lines.append(f"  ✓ audio {'master: ' + options.master_preset if options.master_audio else 'original (remux)'}")
    lines.append("")
    lines.append("Expected:")
    short = min(probe["width"] or 0, probe["height"] or 0)
    base = 720 if short <= 900 else 1080
    lines.append(f"  ~{est / 60:.0f} min en RTX 2060 (medido: "
                 f"{MEASURED_FPS[options.model].get(base, 0.1)} fps)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# backend (lazy: imports solo cuando se procesa)
# ---------------------------------------------------------------------------


def resolve_weight_path(model: str) -> Path:
    base = Path(os.environ.get("VOXERA_VIDEO_MODELS", MODELS_DIR))
    path = base / WEIGHT_FILES[model]
    if not path.exists():
        raise EnhancementError(
            f"pesos no encontrados: {path}\nDescarga:\n"
            f"  curl -L --fail -o {path} {WEIGHT_URLS[model]}"
        )
    return path


def require_backend() -> tuple:
    """Import Real-ESRGAN stack + cv2 + torch; verify CUDA. Called only when enhancing."""
    try:
        import cv2  # noqa: F401
        import torch
        from basicsr.archs.rrdbnet_arch import RRDBNet
        from realesrgan import RealESRGANer
        from realesrgan.archs.srvgg_arch import SRVGGNetCompact
    except ImportError as exc:
        raise EnhancementError(
            f"dependencias de vídeo no instaladas (falta: {exc.name}).\n{INSTALL_HINT}"
        ) from exc
    if not torch.cuda.is_available():
        raise EnhancementError(
            "voxera video requiere CUDA (GPU NVIDIA). CPU medido a ~67x más lento "
            "que realtime — no soportado."
        )
    return cv2, torch, RRDBNet, SRVGGNetCompact, RealESRGANer


def _build_upsampler(model: str, tile: int, half: bool):
    cv2, torch, RRDBNet, SRVGGNetCompact, RealESRGANer = require_backend()
    if model == VIDEO_MODEL_ANIME:
        net = SRVGGNetCompact(num_in_ch=3, num_out_ch=3, num_feat=64, num_conv=16,
                              upscale=4, act_type="prelu")
    else:
        net = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23,
                      num_grow_ch=32, scale=4)
    return RealESRGANer(scale=4, model_path=str(resolve_weight_path(model)), model=net,
                        tile=tile, tile_pad=10, pre_pad=0, half=half, gpu_id=0), cv2


# ---------------------------------------------------------------------------
# enhance
# ---------------------------------------------------------------------------


def enhance_video(
    input_path: str | Path,
    output_path: str | Path,
    options: VideoOptions | None = None,
    progress=None,
) -> Path:
    """Enhance ``input_path`` (frames -> Real-ESRGAN -> target res -> remux audio).

    ``progress`` is a callable(line: str) for [extract]/[enhance i/n]/[still]/[assemble]
    lines; defaults to print. Emits machine-parseable ``[tag]`` lines for the web UI.
    """
    opts = options or VideoOptions()
    opts.validate()
    log = progress or (lambda line: print(line, flush=True))
    inp = Path(input_path)
    out = Path(output_path)
    if out.suffix.lower() not in video_mod.VIDEO_EXTENSIONS:
        raise EnhancementError(
            f"salida de vídeo requiere extensión de vídeo (p.ej. .mp4), got: {out.suffix}"
        )
    probe = probe_video(inp)
    fps = opts.fps
    out.parent.mkdir(parents=True, exist_ok=True)
    log(f"[plan] {inp.name} · {probe['width']}x{probe['height']} · {probe['fps_ratio']} fps"
        f" · {probe['duration_s']:.1f} s · modelo {opts.model} -> {opts.width}x{opts.height}@{fps}fps")

    tmp = video_mod.TMP_DIR / f"venh_{os.getpid()}_{int(time.time() * 1000)}"
    (tmp / "in").mkdir(parents=True)
    (tmp / "out").mkdir()
    ss = ["-ss", str(opts.seg[0])] if opts.seg else []
    tt = ["-t", str(opts.seg[1] - opts.seg[0])] if opts.seg else []
    try:
        # 1. frames
        subprocess.run(
            [video_mod._tool("ffmpeg"), "-y", *ss, *tt, "-i", str(inp),
             "-vf", f"fps={fps}", "-qscale:v", "2", str(tmp / "in" / "%08d.png")],
            check=True, capture_output=True, timeout=3600,
        )
        frames = sorted((tmp / "in").glob("*.png"))
        if not frames:
            raise EnhancementError(
                f"sin frames extraídos de {inp.name} (¿segmento fuera de rango o vídeo corrupto?)"
            )
        log(f"[extract] {len(frames)} frames @ {fps}fps")

        # 2. audio
        wav = tmp / "audio.wav"
        if probe["has_audio"]:
            video_mod.extract_audio(inp, wav)
            if opts.master_audio:
                from voxera.master import master_file
                from voxera.errors import NoSpeechError
                mastered = tmp / "audio_mastered.wav"
                try:
                    master_file(wav, mastered, preset_name=opts.master_preset)
                    wav = mastered
                    log(f"[audio] master: {opts.master_preset}")
                except (NoSpeechError, EnhancementError) as exc:
                    log(f"[audio] master fallback (original): {exc}")
        else:
            log("[audio] sin pista de audio — salida solo vídeo")

        # 3. enhance
        upsampler, cv2 = _build_upsampler(opts.model, opts.tile, opts.half)
        t0 = time.time()
        n = len(frames)
        for i, f in enumerate(frames):
            img = cv2.imread(str(f), cv2.IMREAD_COLOR)
            enhanced, _ = upsampler.enhance(img, outscale=opts.outscale)
            cv2.imwrite(str(tmp / "out" / f.name), enhanced)
            if i % 30 == 0 or i == n - 1:
                el = time.time() - t0
                log(f"[enhance] {i + 1}/{n} · {el:.0f}s · {(i + 1) / max(el, 1e-9):.2f}fps")
        log(f"[enhance] done · {n} frames en {time.time() - t0:.1f}s")

        # 4. comparison still (fair: both at target res)
        mid = frames[n // 2]
        src = cv2.imread(str(mid))
        enh = cv2.imread(str(tmp / "out" / mid.name))
        src_u = cv2.resize(src, (opts.width, opts.height), interpolation=cv2.INTER_LANCZOS4)
        enh_r = cv2.resize(enh, (opts.width, opts.height), interpolation=cv2.INTER_LANCZOS4)
        still = Path(str(out) + ".compare.png")
        cv2.imwrite(str(still), np_hstack(src_u, enh_r))
        log(f"[still] {still}")

        # 5. assemble
        vf = f"scale={opts.width}:{opts.height}:flags=lanczos"
        cmd = [video_mod._tool("ffmpeg"), "-y", "-framerate", str(fps),
               "-i", str(tmp / "out" / "%08d.png")]
        if probe["has_audio"]:
            cmd += ["-i", str(wav)]
        cmd += ["-vf", vf, "-r", str(fps), "-c:v", "libx264", "-crf", str(opts.crf),
                "-pix_fmt", "yuv420p"]
        if probe["has_audio"]:
            cmd += ["-c:a", "aac", "-b:a", opts.audio_bitrate, "-shortest"]
        else:
            cmd += ["-an"]
        cmd += [str(out)]
        subprocess.run(cmd, check=True, capture_output=True, timeout=3600)
        log(f"[assemble] {out}")
    except subprocess.CalledProcessError as exc:
        raise EnhancementError(
            f"ffmpeg/inferencia falló: {exc.stderr.decode(errors='replace')[-800:]}"
        ) from exc
    finally:
        if opts.keep_frames:
            log(f"[keep] frames en {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)
    return out


def np_hstack(a, b):
    import numpy as np

    return np.hstack([a, b])


# ---------------------------------------------------------------------------
# compare (herramienta AB)
# ---------------------------------------------------------------------------


def compare_videos(
    path_a: str | Path,
    path_b: str | Path,
    output_path: str | Path,
    *,
    source: str | Path | None = None,
    seg: tuple[float, float] | None = None,
    fps: int = 30,
) -> Path:
    """Side-by-side AB video (2 paneles, o 3 con ``source``). Para evaluación humana."""
    import cv2
    import numpy as np

    out = Path(output_path)
    tmp = video_mod.TMP_DIR / f"venh_cmp_{os.getpid()}_{int(time.time() * 1000)}"
    tmp.mkdir(parents=True)
    panels = {"a": path_a, "b": path_b}
    if source is not None:
        panels = {"src": source, **panels}
    try:
        extracted = {}
        for name, vid in panels.items():
            d = tmp / name
            d.mkdir()
            ss = ["-ss", str(seg[0])] if seg else []
            tt = ["-t", str(seg[1] - seg[0])] if seg else []
            subprocess.run(
                [video_mod._tool("ffmpeg"), "-y", *ss, *tt, "-i", str(vid),
                 "-vf", f"fps={fps}", "-qscale:v", "2", str(d / "%08d.png")],
                check=True, capture_output=True, timeout=1800,
            )
            extracted[name] = sorted(d.glob("*.png"))
        n = min(len(v) for v in extracted.values())
        if n == 0:
            raise EnhancementError("sin frames para comparar (¿segmento fuera de rango?)")
        stack_dir = tmp / "stack"
        stack_dir.mkdir()
        for i in range(n):
            panels_imgs = []
            for name in panels:
                img = cv2.imread(str(extracted[name][i]))
                img = cv2.resize(img, (1080, 1920), interpolation=cv2.INTER_LANCZOS4)
                panels_imgs.append(img)
            cv2.imwrite(str(stack_dir / f"{i + 1:08d}.png"), np.hstack(panels_imgs))
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [video_mod._tool("ffmpeg"), "-y", "-framerate", str(fps),
             "-i", str(stack_dir / "%08d.png"), "-c:v", "libx264", "-crf", "18",
             "-pix_fmt", "yuv420p", str(out)],
            check=True, capture_output=True, timeout=1800,
        )
    except subprocess.CalledProcessError as exc:
        raise EnhancementError(
            f"ffmpeg compare falló: {exc.stderr.decode(errors='replace')[-800:]}"
        ) from exc
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out
