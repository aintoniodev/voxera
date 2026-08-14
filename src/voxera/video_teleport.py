"""``voxera video teleport`` — teletransportación: parpadeo de silueta blanca (tutorial @serri.mp4).

Replicación del truco del tutorial de @serri.mp4 (Premiere, vídeo
7645000011205397782, "teletransportación"): la persona parpadea como
SILUETA BLANCA OPACA y eso sirve de transición entre dos tomas (recurso de
los vídeos de Ibai). Nada de "la persona se esfuma y queda el cuarto vacío"
— el tutorial lo usa como CORTE de transición.

Receta del tutorial (medida del vídeo + transcripción, 2026-08-13):
  1. Cámara FIJA (trípode) — "es importante grabar en un tripod".
  2. Rotoscopiar al sujeto (Premiere: Selección de Objeto).
  3. Parpadeo: "necesitaremos dos fotogramas. Dejaremos un hueco y
     recortaremos otros dos fotogramas. Este será el momento donde
     apareceremos de color blanco" -> patrón 2-2-2 (blanco, hueco, blanco).
  4. Efecto Tinción con el rango negro a blanco al 100 % -> "seremos solo
     una silueta" (opaco total).

Implementación voxera (sin Premiere):
  - Silueta = SEGMENTACIÓN DE PERSONA (torchvision DeepLabV3 MobileNetV3,
    clase person) sobre el frame actual, dilatada ~3px, rellena de blanco
    opaco. Una segmentación real da una silueta limpia (la roto del
    tutorial); la máscara por diff contra fondo es burda y deja "formas
    raras" (medido 2026-08-13). Fallback a diff solo si torch no está.
  - Parpadeo = plan de fases por índice de frame (white/gap/white). Los
    frames fuera del parpadeo pasan sin tocar (bit-exactos en el pipe).
  - El audio se remuxea copiado.

NO hay modo "desaparecer" (--remove): el inpaint naive (vecino más cercano)
sobre un fondo con textura deja un borrón con formas raras visible; sin ML
de inpainting no se hace creíble. El efecto del tutorial es el parpadeo de
transición, no la desaparición sostenida.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.ndimage import distance_transform_edt

from voxera import video as video_mod
from voxera import video_enhance as ve
from voxera.errors import EnhancementError

DEFAULT_PATTERN = "2-2-2"   # 2 frames blanco, hueco, 2 frames blanco (tutorial)
DEFAULT_DILATE = 3          # px de dilatación de la silueta (escala 720p)
DEFAULT_DIFF_THRESHOLD = 25  # solo para el fallback sin torch
PERSON_CLASS = 15           # VOC labels en los pesos COCO_WITH_VOC_LABELS de torchvision
WHITE = np.array([255, 255, 255], dtype=np.uint8)

_HAS_TORCH = None
_SEG = None  # cache del modelo (carga ~1 vez)


def _torch_available() -> bool:
    global _HAS_TORCH
    if _HAS_TORCH is None:
        try:
            import torch  # noqa: F401
            from torchvision.models.segmentation import deeplabv3_mobilenet_v3_large  # noqa: F401
            _HAS_TORCH = True
        except Exception:
            _HAS_TORCH = False
    return _HAS_TORCH


def _seg_model():
    """Modelo de segmentación DeepLabV3 MobileNetV3 (cargado perezoso, cache)."""
    global _SEG
    if _SEG is None:
        import torch
        from torchvision.models.segmentation import (
            deeplabv3_mobilenet_v3_large,
            DeepLabV3_MobileNet_V3_Large_Weights,
        )
        weights = DeepLabV3_MobileNet_V3_Large_Weights.COCO_WITH_VOC_LABELS_V1
        model = deeplabv3_mobilenet_v3_large(weights=weights).eval()
        _SEG = (model, weights.transforms())
    return _SEG


@dataclass(frozen=True)
class TeleportOptions:
    """Parámetros del parpadeo de teletransportación."""

    time: float                              # instante del parpadeo (primer frame blanco), s
    pattern: str = DEFAULT_PATTERN           # "W-G-W" en frames
    dilate: int = DEFAULT_DILATE             # px de dilatación de la silueta (escala 720p)
    crf: int = 18
    audio_bitrate: str = "192k"

    def validate(self) -> None:
        if self.time < 0:
            raise EnhancementError(f"time debe ser >= 0, got {self.time}")
        try:
            parse_pattern(self.pattern)
        except ValueError as exc:
            raise EnhancementError(str(exc)) from exc
        if not 0 <= self.dilate <= 50:
            raise EnhancementError(f"dilate debe estar en [0, 50]px, got {self.dilate}")
        if not 0 < self.crf <= 51:
            raise EnhancementError(f"crf debe estar en (0, 51], got {self.crf}")


def parse_pattern(pattern: str) -> tuple[int, int, int]:
    """'W-G-W' en frames -> (blanco, hueco, blanco). '2-2-2' del tutorial."""
    parts = [p.strip() for p in pattern.split("-")]
    if len(parts) != 3:
        raise ValueError(f"pattern debe ser 'W-G-W' en frames (p.ej. {DEFAULT_PATTERN}), got {pattern!r}")
    try:
        w, g, w2 = (int(p) for p in parts)
    except ValueError as exc:
        raise ValueError(f"pattern debe ser numérico (p.ej. {DEFAULT_PATTERN}), got {pattern!r}") from exc
    if min(w, g, w2) < 1 or max(w, g, w2) > 120:
        raise ValueError(f"patrón fuera de rango (1..120 frames por fase), got {pattern!r}")
    return w, g, w2


def flicker_schedule(f0: int, total: int, pattern: str = DEFAULT_PATTERN) -> dict[int, str]:
    """Fase por índice de frame (puro, testable).

    - [f0, f0+w):        white   (silueta blanca)
    - [f0+w, f0+w+g):    gap     (frame original)
    - [f0+w+g, f0+2w+g): white   (silueta blanca)
    - resto:             normal (sin tocar)
    f0 se clampa a [1, total-1].
    """
    w, g, _ = parse_pattern(pattern)
    f0 = min(max(f0, 1), max(total - 1, 1))
    sched: dict[int, str] = {}
    end_white2 = min(f0 + 2 * w + g, total)
    for i in range(f0, total):
        if i < f0 + w:
            sched[i] = "white"
        elif i < f0 + w + g:
            sched[i] = "gap"
        elif i < end_white2:
            sched[i] = "white"
        else:
            sched[i] = "normal"
    return sched


def _dilate_radius(mask: np.ndarray, r: int) -> np.ndarray:
    """Dilatación por radio euclídeo en una pasada de EDT: EDT(~mask) <= r."""
    if r <= 0 or not mask.any():
        return mask
    return distance_transform_edt(~mask) <= r


def person_mask(frame: np.ndarray, dilate: int = DEFAULT_DILATE) -> np.ndarray:
    """Máscara de persona: segmentación DeepLabV3 (limpia) o diff (fallback).

    Devuelve bool HxW cubriendo a la persona en ese frame. La segmentación
    real es la que da una silueta con forma humana correcta; el diff contra
    un fondo mediano es burdo (ropa oscura, bordes) y deja formas raras.
    """
    h, w = frame.shape[:2]
    if _torch_available():
        import torch
        model, pre = _seg_model()
        x = pre(torch.from_numpy(frame.copy()).permute(2, 0, 1) / 255.0).unsqueeze(0)
        with torch.no_grad():
            out = model(x)["out"][0]
        m = (out.argmax(0) == PERSON_CLASS)
        m = torch.nn.functional.interpolate(
            m[None, None].float().cpu(), size=(h, w), mode="nearest"
        )[0, 0] > 0.5
        m = m.numpy()
    else:
        # fallback sin torch: fondo estimado del borde del frame + diff.
        # Burdo para vídeo real (por eso se usa torch), pero suficiente para
        # los tests sintéticos (fondo uniforme).
        border = np.concatenate([frame[0, :], frame[-1, :], frame[:, 0], frame[:, -1]])
        bg = np.median(border, axis=0).astype(np.int16)
        m = np.max(np.abs(frame.astype(np.int16) - bg), axis=2) > DEFAULT_DIFF_THRESHOLD
    dilate_px = max(int(round(dilate * max(w, h) / 720.0)), 0)
    return _dilate_radius(m, dilate_px)


def composite_silhouette(frame: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Rellena la región de la máscara con blanco opaco (Tinción 100 %)."""
    out = frame.copy()
    out[mask] = WHITE
    return out


def build_plan(input: str | Path, opts: TeleportOptions) -> str:
    """Plan legible para --dry-run."""
    opts.validate()
    inp = Path(input)
    probe = ve.probe_video(inp)
    w, g, w2 = parse_pattern(opts.pattern)
    f0 = max(int(round(opts.time * probe["fps"])), 1)
    total = max(int(round(probe["duration_s"] * probe["fps"])), 1)
    engine = "segmentación DeepLabV3 MobileNetV3 (clase person)" if _torch_available() else "diff contra fondo (fallback, sin torch)"
    lines = [
        "VOXERA PLAN (video teleport)",
        f"  entrada : {inp} ({probe['width']}x{probe['height']} @{probe['fps']:.2f}fps, "
        f"{probe['duration_s']:.2f}s, {total} frames)",
        f"  salida  : misma resolución/fps que entrada (audio remux copiado)",
        f"  parpadeo: t={opts.time:.2f}s (frame {f0}) — patrón {opts.pattern} "
        f"({w} blanco, {g} hueco, {w2} blanco)",
        f"  silueta : blanco opaco, dilatación {opts.dilate}px",
        f"  máscara : {engine}",
        f"  encoder : libx264 crf {opts.crf} + aac {opts.audio_bitrate} (audio original)",
    ]
    return "\n".join(lines)


def _decode_all(input: Path):
    return subprocess.Popen(
        [video_mod._tool("ffmpeg"), "-v", "error", "-i", str(input),
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE,
    )


def _encode_video(w: int, h: int, fps: float, crf: int, out: Path):
    return subprocess.Popen(
        [video_mod._tool("ffmpeg"), "-y", "-v", "error",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", f"{fps:.6f}",
         "-i", "-", "-c:v", "libx264", "-crf", str(crf), "-pix_fmt", "yuv420p",
         str(out)],
        stdin=subprocess.PIPE,
    )


def teleport_video(input: str | Path, output: str | Path, opts: TeleportOptions) -> Path:
    """Aplica el parpadeo de teletransportación y devuelve la ruta de salida.

    Streaming frame a frame: solo los frames 'white' se segmentan y
    rellenan de blanco; el resto pasa sin tocar.
    """
    opts.validate()
    inp, out = Path(input), Path(output)
    if not inp.exists():
        raise EnhancementError(f"input no existe: {inp}")
    out.parent.mkdir(parents=True, exist_ok=True)

    probe = ve.probe_video(inp)
    w, h = probe["width"], probe["height"]
    fps = probe["fps"]
    total = max(int(round(probe["duration_s"] * fps)), 1)
    f0 = max(int(round(opts.time * fps)), 1)
    if f0 >= total - 1:
        raise EnhancementError(f"time={opts.time:.2f}s cae fuera del vídeo ({probe['duration_s']:.2f}s)")

    sched = flicker_schedule(f0, total, opts.pattern)
    white_frames = sorted(i for i, ph in sched.items() if ph == "white")
    print(f"[teleport] parpadeo en frames {white_frames[0]}..{white_frames[-1]} "
          f"(t≈{white_frames[0] / fps:.2f}s), {len(white_frames)} frames a siluetear")

    dec = _decode_all(inp)
    enc = _encode_video(w, h, fps, opts.crf, out)
    frame_size = w * h * 3
    n_frames = 0
    try:
        while True:
            raw = dec.stdout.read(frame_size)
            if not raw or len(raw) < frame_size:
                break
            frame = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3)
            phase = sched.get(n_frames, "normal")
            if phase == "white":
                m = person_mask(frame, opts.dilate)
                frame = composite_silhouette(frame, m)
            # gap / normal: bit-exacto
            enc.stdin.write(frame.tobytes())
            n_frames += 1
    finally:
        try:
            enc.stdin.close()
        except BrokenPipeError:
            pass
        dec.wait(timeout=600)
        enc.wait(timeout=1800)

    if abs(n_frames - total) > 2:
        raise EnhancementError(f"frames procesados {n_frames} != esperados {total} (fuente inconsistente)")
    if n_frames != total:
        print(f"[teleport] AVISO: contenedor declara {total} frames, el decode entrega {n_frames}.")

    # Remux del audio original (copiado).
    if probe["has_audio"]:
        tmp = out.with_suffix(".novideo.mp4")
        out.replace(tmp)
        try:
            proc = subprocess.run(
                [video_mod._tool("ffmpeg"), "-y", "-v", "error",
                 "-i", str(tmp), "-i", str(inp),
                 "-map", "0:v:0", "-map", "1:a:0",
                 "-c:v", "copy", "-c:a", "copy", str(out)],
                capture_output=True, timeout=1200,
            )
            if proc.returncode != 0:
                raise EnhancementError(f"remux de audio falló: {proc.stderr.decode(errors='replace')[-500:]}")
        finally:
            tmp.unlink(missing_ok=True)

    oprobe = ve.probe_video(out)
    if oprobe["width"] != w or oprobe["height"] != h:
        raise EnhancementError(f"salida con resolución inesperada: {oprobe['width']}x{oprobe['height']}")
    if abs(oprobe["duration_s"] - probe["duration_s"]) > 0.25:
        raise EnhancementError(
            f"duración inesperada: {oprobe['duration_s']:.2f}s (esperada ~{probe['duration_s']:.2f}s)"
        )
    return out
