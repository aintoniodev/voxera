"""``voxera video magnify`` — lente de aumento circular ("Magnify", sin Premiere).

Replicación del efecto "Magnify" de Adobe Premiere Pro 26.3 (tutorial de
@billycreative_, 2026-08): una lente circular que amplía la zona que hay
debajo, como una lupa al enseñar un paper. Medido en el propio tutorial:
lente circular estática, radio ~0.35 del ancho del frame, borde nítido,
colocada en la mitad superior del frame.

Implementación: 100 % ffmpeg + dos PNG (máscara circular con pluma y aro de
borde) generados con numpy + zlib (sin GPU, sin Premiere, sin dependencias
nuevas). Pipeline por frame:

    split -> crop del área bajo la lente (radio r/zoom, centrada en la
    lente) -> scale lanczos al diámetro de la lente -> alpha mask con pluma
    -> overlay sobre el original -> overlay del aro de borde.

Fuera de la lente el vídeo queda intacto (misma disciplina bit-exacta que
audio_lowpass: solo se toca la región del efecto).
"""

from __future__ import annotations

import struct
import subprocess
import tempfile
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from voxera import video as video_mod
from voxera import video_enhance as ve
from voxera.errors import EnhancementError

DEFAULT_CENTER = (0.5, 0.38)   # mitad superior: zona de contenido (talking-head/paper)
DEFAULT_SIZE = 0.35            # fracción de min(w,h) — medido en el tutorial: r ~ 0.35 del ancho
DEFAULT_ZOOM = 3.0             # 3x: la lente muestra la zona 3 veces más grande
DEFAULT_FEATHER = 0.05         # fracción del radio: pluma del borde (suave pero nítida)
DEFAULT_RING_WIDTH = 0.025     # fracción del radio: grosor del aro de borde
RING_COLOR = (255, 255, 255)   # aro blanco, como el borde de una lupa


@dataclass(frozen=True)
class MagnifyOptions:
    """Parámetros de la lente de aumento. Un solo default sensato; escapes.

    Medición del tutorial de @billycreative_ (anillo circular detectado por
    Hough + continuidad de borde, 720x1280): lente estática centrada en
    ~(0.36, 0.29), radio ~255 px = 0.35 del ancho, borde nítido (feather
    pequeño), presente varios segundos. El factor de ampliación real no es
    medible de forma fiable (el vídeo está muy editado, sin frame de
    referencia limpio): default 3x, el aspecto típico de "lupa de paper".
    """

    center: tuple[float, float] = DEFAULT_CENTER
    size: float = DEFAULT_SIZE
    zoom: float = DEFAULT_ZOOM
    feather: float = DEFAULT_FEATHER
    ring_width: float = DEFAULT_RING_WIDTH
    start: float | None = None
    end: float | None = None
    crf: int = 18
    audio_bitrate: str = "192k"

    def validate(self) -> None:
        ax, ay = self.center
        if not (0 <= ax <= 1 and 0 <= ay <= 1):
            raise EnhancementError(f"center debe estar en [0,1]x[0,1], got {self.center}")
        if not 0.02 <= self.size <= 0.5:
            raise EnhancementError(f"size debe estar en [0.02, 0.5] (fracción de min(w,h)), got {self.size}")
        if not 1.05 <= self.zoom <= 20:
            raise EnhancementError(f"zoom debe estar en (1, 20], got {self.zoom}")
        if not 0 <= self.feather <= 0.5:
            raise EnhancementError(f"feather debe estar en [0, 0.5] (fracción del radio), got {self.feather}")
        if not 0 <= self.ring_width <= 0.3:
            raise EnhancementError(f"ring_width debe estar en [0, 0.3], got {self.ring_width}")
        if not 0 < self.crf <= 51:
            raise EnhancementError(f"crf debe estar en (0, 51], got {self.crf}")
        if self.start is not None and self.end is not None and self.end <= self.start:
            raise EnhancementError(f"end ({self.end}) debe ser > start ({self.start})")


def lens_geometry(width: int, height: int, opts: MagnifyOptions) -> dict:
    """Geometría de la lente en píxeles: radio, centro (disco dentro del
    frame), lado del crop y zoom efectivo tras redondeos."""
    opts.validate()
    radius = int(round(opts.size * min(width, height)))
    radius = max(radius, 4)
    ax, ay = opts.center
    cx = min(max(ax * width, radius), width - radius)
    cy = min(max(ay * height, radius), height - radius)
    crop = max(_even(int(2.0 * radius / opts.zoom)), 4)
    zoom_eff = 2.0 * radius / crop
    return {
        "radius": radius,
        "cx": cx,
        "cy": cy,
        "crop": crop,
        "zoom_eff": zoom_eff,
        "feather_px": opts.feather * radius,
        "ring_px": max(1.0, opts.ring_width * radius),
    }


def _even(x: int) -> int:
    return int(x) // 2 * 2


def _fmt(x: float) -> str:
    return f"{x:.6f}"


def _write_png(path: Path, rgba: np.ndarray) -> Path:
    """PNG RGBA 8-bit mínimo (numpy + zlib; sin dependencias nuevas)."""
    h, w = rgba.shape[:2]

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    raw = b"".join(b"\x00" + rgba[y].tobytes() for y in range(h))
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)
    return path


def build_lens_masks(radius: int, feather: float, ring_width: float,
                     out_dir: str | Path) -> tuple[Path, Path]:
    """Genera la máscara circular (pluma) y el aro de borde como PNG RGBA.

    - mask.png: disco de alpha 1 dentro de (r - feather) que cae
      linealmente a 0 en el borde (la 'pluma' del Magnify de Premiere).
    - ring.png: aro blanco centrado en el radio, ancho ring_width,
      ~1 px de antialias (el borde visible de la lupa).
    """
    n = 2 * radius
    y, x = np.mgrid[0:n, 0:n]
    d = np.hypot(x - radius + 0.5, y - radius + 0.5)
    f = max(feather * radius, 0.01)
    a_disc = np.clip((radius - d) / f, 0.0, 1.0)
    mask = np.dstack(
        [np.full((n, n, 3), 255, np.uint8), (a_disc * 255).astype(np.uint8)]
    )
    w = max(ring_width * radius, 0.5)
    # aro: opaco en |d-r| <= w/2, antialias de ~1 px hacia fuera
    a_ring = np.clip((w / 2 + 1.0 - np.abs(d - radius)) / 2.0, 0.0, 1.0)
    ring_rgb = np.zeros((n, n, 3), np.uint8)
    ring_rgb[...] = RING_COLOR
    ring = np.dstack([ring_rgb, (a_ring * 255).astype(np.uint8)])
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    return (
        _write_png(out_dir / "lens_mask.png", mask),
        _write_png(out_dir / "lens_ring.png", ring),
    )


def build_magnify_filter(width: int, height: int, opts: MagnifyOptions,
                         duration: float, fps: float = 30.0) -> str:
    """Cadena de filtros ffmpeg para la lente de aumento (estática).

    Entradas esperadas: [0] vídeo, [1] aro (PNG rgba), [2] máscara (PNG rgba).
    Fuera de la lente el frame pasa intacto (overlay de la lente encima).
    """
    opts.validate()
    g = lens_geometry(width, height, opts)
    r, cx, cy, crop = g["radius"], g["cx"], g["cy"], g["crop"]
    dur = max(duration, 0.001)
    x0, y0 = cx - r, cy - r
    x_crop, y_crop = cx - crop / 2.0, cy - crop / 2.0
    return (
        f"[0:v]split=2[base][mag];"
        f"[mag]crop={crop}:{crop}:{_fmt(x_crop)}:{_fmt(y_crop)},"
        f"scale={2 * r}:{2 * r}:flags=lanczos,setsar=1,format=rgba[magc];"
        f"[2:v]trim=duration={_fmt(dur)},setpts=PTS-STARTPTS,alphaextract[maska];"
        f"[magc][maska]alphamerge[magm];"
        f"[1:v]trim=duration={_fmt(dur)},setpts=PTS-STARTPTS[ringf];"
        f"[base][magm]overlay=x={_fmt(x0)}:y={_fmt(y0)}[v1];"
        f"[v1][ringf]overlay=x={_fmt(x0)}:y={_fmt(y0)},format=yuv420p[vout]"
    )


def _segment_duration(probe: dict, opts: MagnifyOptions) -> float:
    start = opts.start if opts.start is not None else 0.0
    end = opts.end if opts.end is not None else probe["duration_s"]
    return max(end - start, 0.001)


def build_plan(input: str | Path, opts: MagnifyOptions) -> str:
    """Plan legible para --dry-run (misma convención que zoom/enhance)."""
    opts.validate()
    inp = Path(input)
    probe = ve.probe_video(inp)
    seg_dur = _segment_duration(probe, opts)
    g = lens_geometry(probe["width"], probe["height"], opts)
    vf = build_magnify_filter(probe["width"], probe["height"], opts,
                              seg_dur, fps=probe["fps"])
    ax, ay = opts.center
    lines = [
        "VOXERA PLAN (video magnify)",
        f"  entrada : {inp} ({probe['width']}x{probe['height']} @{probe['fps']:.2f}fps, "
        f"{probe['duration_s']:.2f}s)",
        f"  salida  : misma resolución que la entrada",
        f"  lente   : r={g['radius']}px centro=({g['cx']:.1f},{g['cy']:.1f}) "
        f"({ax:.2f},{ay:.2f})  zoom={g['zoom_eff']:.2f}x  "
        f"pluma={g['feather_px']:.1f}px  aro={g['ring_px']:.1f}px",
        f"  rango   : {opts.start if opts.start is not None else 0:.2f}s .. "
        f"{opts.end if opts.end is not None else probe['duration_s']:.2f}s "
        f"({seg_dur:.2f}s)",
        f"  encoder : libx264 crf {opts.crf} + aac {opts.audio_bitrate} "
        f"(audio original, sin masterizar)",
        f"  filtro  : {vf}",
    ]
    return "\n".join(lines)


def magnify_video(input: str | Path, output: str | Path, opts: MagnifyOptions) -> Path:
    """Aplica la lente de aumento y devuelve la ruta de salida (verificada)."""
    opts.validate()
    inp = Path(input)
    out = Path(output)
    if not inp.exists():
        raise EnhancementError(f"input no existe: {inp}")
    out.parent.mkdir(parents=True, exist_ok=True)

    probe = ve.probe_video(inp)
    seg_dur = _segment_duration(probe, opts)
    g = lens_geometry(probe["width"], probe["height"], opts)
    vf = build_magnify_filter(probe["width"], probe["height"], opts,
                              seg_dur, fps=probe["fps"])
    # PNGs de máscara/aro en un dir temporal (no ensuciar la carpeta de salida).
    with tempfile.TemporaryDirectory(prefix="voxera-magnify-") as tmp:
        mask_png, ring_png = build_lens_masks(
            g["radius"], opts.feather, opts.ring_width, tmp)
        return _encode(inp, out, probe, seg_dur, vf, mask_png, ring_png, opts)


def _encode(inp: Path, out: Path, probe: dict, seg_dur: float, vf: str,
            mask_png: Path, ring_png: Path, opts: MagnifyOptions) -> Path:
    cmd = [video_mod._tool("ffmpeg"), "-y", "-v", "error"]
    cmd += ["-i", str(inp)]
    cmd += ["-loop", "1", "-framerate", f"{probe['fps']:.6f}",
            "-t", f"{seg_dur:.6f}", "-i", str(ring_png)]
    cmd += ["-loop", "1", "-framerate", f"{probe['fps']:.6f}",
            "-t", f"{seg_dur:.6f}", "-i", str(mask_png)]
    cmd += ["-filter_complex", vf, "-map", "[vout]"]
    cmd += ["-c:v", "libx264", "-crf", str(opts.crf), "-pix_fmt", "yuv420p"]
    if opts.start is not None:
        cmd += ["-ss", f"{opts.start:.6f}"]  # después de -i: decode-seek exacto
    if opts.end is not None:
        cmd += ["-to", f"{opts.end:.6f}"]
    if probe["has_audio"]:
        cmd += ["-c:a", "aac", "-b:a", opts.audio_bitrate, "-shortest"]
    else:
        cmd += ["-an"]
    cmd += [str(out)]

    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=7200)
    except subprocess.CalledProcessError as exc:
        raise EnhancementError(
            f"ffmpeg falló: {exc.stderr.decode(errors='replace')[-800:]}"
        ) from exc

    # Verificación determinista (misma disciplina que zoom/enhance).
    oprobe = ve.probe_video(out)
    if oprobe["width"] != probe["width"] or oprobe["height"] != probe["height"]:
        raise EnhancementError(
            f"salida con resolución inesperada: {oprobe['width']}x{oprobe['height']}"
        )
    if abs(oprobe["duration_s"] - seg_dur) > 0.25:
        raise EnhancementError(
            f"duración inesperada: {oprobe['duration_s']:.2f}s (esperada ~{seg_dur:.2f}s)"
        )
    return out
