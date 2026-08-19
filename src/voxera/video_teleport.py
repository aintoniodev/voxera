"""``voxera video teleport`` — teletransportación real sobre toma única (cámara fija).

Evolución del parpadeo de silueta blanca del tutorial de @serri.mp4 (vídeo
7645000011205397782): el parpadeo 2-2-2 se conserva como TRANSICIÓN, pero
ahora la persona de verdad TELETRANSPORTA — en el parpadeo desaparece de su
posición (A) dejando ver el fondo real detrás y reaparece desplazada en B
(recorte vivo de segmentación, pegado frame a frame sobre el fondo).

Receta (toma única, cámara fija en trípode):
  1. PLATE de fondo: se muestrean N frames a lo largo del vídeo, se segmenta
     la persona en cada uno y se calcula la mediana temporal SOLO con los
     frames donde cada píxel no es persona (nanmedian consciente de persona)
     → fondo real en todo salvo el núcleo donde la persona está siempre.
     Ese núcleo (~18 % del frame en la demo) se rellena con inpainting LaMa
     (``simple-lama-inpainting``, GPU si hay CUDA) + corrección de color
     contra una corona real + grano sutil. Fallbacks: cv2.Telea, y relleno
     por EDT (sin cv2; solo para tests sintéticos).
  2. PARPADEO 2-2-2 (frames): blanco en A → hueco → blanco en B.
     El hueco reparte: primer frame = persona esfumada (plate), resto =
     persona ya en B. Con ``--vanish`` no hay B: la persona desaparece y no
     vuelve (se ve el fondo el resto del vídeo).
  3. Tras el parpadeo (modo shift): cada frame se borra a la persona de A
     (placa en su región) y se pega viva en B con máscara erosionada y
     feather — sigue hablando/gesticulando, pero desplazada; el audio
     continúa (timeline intacto, remux copiado).

Límites conocidos (medidos 2026-08-14, demo 720x1280@60):
  - La zona del plate es un fondo CONGELADO (los árboles no se mueven ahí);
     fuera de la persona el vídeo sigue vivo.
  - Segmentation por frame tras el parpadeo: ~0.1-0.35 s/frame en GPU
     (RTX 2060), ~1.1 s/frame en CPU.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.ndimage import (
    binary_closing,
    binary_erosion,
    binary_fill_holes,
    binary_opening,
    distance_transform_edt,
    gaussian_filter,
    label,
)

from voxera import video as video_mod
from voxera import video_enhance as ve
from voxera.errors import EnhancementError

DEFAULT_PATTERN = "2-2-2"     # 2 frames blanco, hueco, 2 frames blanco (tutorial)
DEFAULT_SHIFT = "-25,0"       # dx,dy en % del ancho/alto — reaparece a la izquierda
DEFAULT_DILATE = 3            # px de dilatación de la silueta (escala 720p)
DEFAULT_PLATE_SAMPLES = 24    # frames muestreados para el plate de fondo
DEFAULT_DIFF_THRESHOLD = 25   # umbral del fallback diff (sin torch)
DEFAULT_OBJECT_DIFF_THRESHOLD = 18  # umbral base para sujetos no humanos
ERASE_DILATE = 4              # px extra de dilatación al borrar (mata halos)
PERSON_CLASS = 15             # VOC labels en los pesos COCO_WITH_VOC_LABELS de torchvision
WHITE = np.array([255, 255, 255], dtype=np.uint8)

_HAS_TORCH = None
_SEG = None  # cache del modelo (carga ~1 vez)
_LAMA = None  # cache de LaMa


# ------------------------------------------------------------------ helpers


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
    """DeepLabV3 MobileNetV3 (lazy, cache) — en GPU si hay CUDA."""
    global _SEG
    if _SEG is None:
        import torch
        from torchvision.models.segmentation import (
            deeplabv3_mobilenet_v3_large,
            DeepLabV3_MobileNet_V3_Large_Weights,
        )
        weights = DeepLabV3_MobileNet_V3_Large_Weights.COCO_WITH_VOC_LABELS_V1
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = deeplabv3_mobilenet_v3_large(weights=weights).eval().to(device)
        _SEG = (model, weights.transforms(), device)
    return _SEG


def _lama_available() -> bool:
    try:
        import simple_lama_inpainting  # noqa: F401
        return True
    except Exception:
        return False


def _lama_model():
    global _LAMA
    if _LAMA is None:
        from simple_lama_inpainting import SimpleLama
        _LAMA = SimpleLama()
    return _LAMA


# ------------------------------------------------------------------- options


@dataclass(frozen=True)
class TeleportOptions:
    """Parámetros de la teletransportación."""

    time: float                                    # instante del parpadeo (primer frame blanco), s
    pattern: str = DEFAULT_PATTERN                 # "W-G-W" en frames
    shift: str | None = None                      # "dx,dy" % de W,H; None => DEFAULT_SHIFT
    vanish: bool = False                           # desaparece sin reaparecer
    dilate: int = DEFAULT_DILATE                   # px de dilatación de la silueta (escala 720p)
    plate_samples: int = DEFAULT_PLATE_SAMPLES     # frames para el plate de fondo
    crf: int = 18
    audio_bitrate: str = "192k"

    def validate(self) -> None:
        if self.time < 0:
            raise EnhancementError(f"time debe ser >= 0, got {self.time}")
        try:
            parse_pattern(self.pattern)
        except ValueError as exc:
            raise EnhancementError(str(exc)) from exc
        if self.shift is not None:
            try:
                parse_shift(self.shift)
            except ValueError as exc:
                raise EnhancementError(str(exc)) from exc
        if not 0 <= self.dilate <= 50:
            raise EnhancementError(f"dilate debe estar en [0, 50]px, got {self.dilate}")
        if not 2 <= self.plate_samples <= 240:
            raise EnhancementError(f"plate_samples debe estar en [2, 240], got {self.plate_samples}")
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


def parse_shift(shift: str | None) -> tuple[float, float]:
    """'dx,dy' en % del ancho/alto -> (dx, dy). '-25,0' = 25% a la izquierda."""
    if shift is None:
        shift = DEFAULT_SHIFT
    parts = [p.strip() for p in shift.split(",")]
    if len(parts) != 2:
        raise ValueError(f"shift debe ser 'dx,dy' en % (p.ej. {DEFAULT_SHIFT}), got {shift!r}")
    try:
        dx, dy = (float(p) for p in parts)
    except ValueError as exc:
        raise ValueError(f"shift debe ser numérico 'dx,dy' (p.ej. {DEFAULT_SHIFT}), got {shift!r}") from exc
    if not (-90 <= dx <= 90) or not (-90 <= dy <= 90):
        raise ValueError(f"shift fuera de rango (|dx|,|dy| <= 90 %), got {shift!r}")
    return dx, dy


# ------------------------------------------------------------------ schedule


def teleport_schedule(f0: int, total: int, pattern: str = DEFAULT_PATTERN,
                      vanish: bool = False) -> dict[int, str]:
    """Fase por índice de frame (puro, testable).

    Modo shift (por defecto) — el hueco reparte esfumado/aparición:
      - [f0, f0+w):         white_a   (silueta blanca en A)
      - [f0+w, f0+w+g/2):   empty     (persona esfumada: plate)
      - [f0+w+g/2, f0+w+g): appear    (persona ya pegada en B)
      - [f0+w+g, f0+2w+g):  white_b   (silueta blanca en B)
      - [f0+2w+g, total):   after     (persona viva en B, fondo en A)
    Modo vanish: white_a igual; TODO lo demás tras el blanco = empty.

    El resto (< f0) queda fuera del dict (frame original). f0 se clampa a
    [1, total-1].
    """
    w, g, w2 = parse_pattern(pattern)
    f0 = min(max(f0, 1), max(total - 1, 1))
    sched: dict[int, str] = {}
    gap_empty = max(g // 2, 1) if not vanish else g
    for i in range(f0, total):
        if i < f0 + w:
            sched[i] = "white_a"
        elif i < f0 + w + gap_empty:
            sched[i] = "empty"
        elif i < f0 + w + g:
            sched[i] = "empty" if vanish else "appear"
        elif i < f0 + w + g + w2:
            sched[i] = "empty" if vanish else "white_b"
        else:
            sched[i] = "empty" if vanish else "after"
    return sched


# --------------------------------------------------------------- masks/paste


def _dilate_radius(mask: np.ndarray, r: int) -> np.ndarray:
    """Dilatación por radio euclídeo en una pasada de EDT: EDT(~mask) <= r."""
    if r <= 0 or not mask.any():
        return mask
    return distance_transform_edt(~mask) <= r


def person_mask(frame: np.ndarray, dilate: int = DEFAULT_DILATE) -> np.ndarray:
    """Máscara de persona: segmentación DeepLabV3 (limpia) o diff (fallback).

    Devuelve bool HxW cubriendo a la persona en ese frame. La segmentación
    real es la que da una silueta con forma humana correcta; el diff contra
    un fondo mediano del borde es burdo (solo fallback/tests sintéticos).
    """
    h, w = frame.shape[:2]
    if _torch_available():
        import torch
        model, pre, device = _seg_model()
        x = pre(torch.from_numpy(frame.copy()).permute(2, 0, 1) / 255.0).unsqueeze(0).to(device)
        with torch.no_grad():
            out = model(x)["out"][0]
        m = (out.argmax(0) == PERSON_CLASS)
        m = torch.nn.functional.interpolate(
            m[None, None].float(), size=(h, w), mode="bilinear", align_corners=False
        )[0, 0] > 0.5
        m = m.cpu().numpy()
    else:
        # fallback sin torch: fondo estimado del borde del frame + diff.
        border = np.concatenate([frame[0, :], frame[-1, :], frame[:, 0], frame[:, -1]])
        bg = np.median(border, axis=0).astype(np.int16)
        m = np.max(np.abs(frame.astype(np.int16) - bg), axis=2) > DEFAULT_DIFF_THRESHOLD
    dilate_px = max(int(round(dilate * max(w, h) / 720.0)), 0)
    return _dilate_radius(m, dilate_px)


def object_mask(
    frame: np.ndarray,
    background: np.ndarray,
    threshold: float = DEFAULT_OBJECT_DIFF_THRESHOLD,
) -> np.ndarray:
    """Máscara de un sujeto arbitrario comparando el frame con un plate.

    No presupone la clase semántica del sujeto: sirve para una caja, juguete,
    mascota, herramienta o cualquier objeto que se mueva ante una cámara fija.
    ``background`` debe ser un plate limpio o la mediana temporal de la toma.
    La limpieza morfológica elimina ruido de compresión y componentes diminutos.
    """
    if frame.shape[:2] != background.shape[:2]:
        raise ValueError("frame y background deben tener la misma resolución")
    diff = np.max(
        np.abs(frame.astype(np.int16) - background.astype(np.int16)), axis=2
    ).astype(np.float32)
    median = float(np.median(diff))
    mad = float(np.median(np.abs(diff - median)))
    cutoff = max(float(threshold), median + 4.0 * max(mad, 1.0))
    mask = diff > cutoff

    # El radio escala con la resolución: no borra un objeto pequeño en 180p
    # ni deja dientes de compresión en 1080p.
    radius = max(1, int(round(max(frame.shape[:2]) / 720.0)))
    mask = binary_closing(mask, iterations=radius)
    mask = binary_opening(mask, iterations=max(1, radius // 2))
    mask = binary_fill_holes(mask)

    labels, count = label(mask)
    if count:
        areas = np.bincount(labels.reshape(-1))[1:]
        min_area = max(16, int(frame.shape[0] * frame.shape[1] * 0.00002))
        keep = np.flatnonzero(areas >= min_area) + 1
        mask = np.isin(labels, keep)
    return mask.astype(bool)


def composite_silhouette(frame: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Rellena la región de la máscara con blanco opaco (Tinción 100 %)."""
    out = frame.copy()
    out[mask] = WHITE
    return out


def erase_person(frame: np.ndarray, mask: np.ndarray, plate: np.ndarray) -> np.ndarray:
    """Sustituye la región (dilatada) de la persona por el plate de fondo."""
    out = frame.copy()
    out[mask] = plate[mask]
    return out


def _shift_slices(shape: tuple[int, int], mask: np.ndarray, dy: int, dx: int):
    """Slices (src, dst) para pegar `mask` desplazada (dy, dx); None si sale toda."""
    if not mask.any():
        return None
    H, W = shape
    ys, xs = np.where(mask)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    sy0, sy1 = max(0, y0 + dy), min(H, y1 + dy)
    sx0, sx1 = max(0, x0 + dx), min(W, x1 + dx)
    if sy0 >= sy1 or sx0 >= sx1:
        return None
    src = (slice(sy0 - dy, sy1 - dy), slice(sx0 - dx, sx1 - dx))
    dst = (slice(sy0, sy1), slice(sx0, sx1))
    return src, dst


def paste_person(out: np.ndarray, frame: np.ndarray, mask: np.ndarray,
                 dy: int, dx: int, feather: float = 1.5) -> np.ndarray:
    """Pega la persona viva desplazada con borde feather (máscara erosionada)."""
    sl = _shift_slices(out.shape[:2], mask, dy, dx)
    if sl is None:
        return out
    (sy, sx), (dyy, dxx) = sl
    alpha = gaussian_filter(binary_erosion(mask, iterations=2).astype(np.float32), feather)
    a = np.clip(alpha[sy, sx], 0, 1)[..., None]
    dst = out[dyy, dxx].astype(np.float32)
    src = frame[sy, sx].astype(np.float32)
    out[dyy, dxx] = (dst * (1 - a) + src * a).astype(np.uint8)
    return out


def paste_white(out: np.ndarray, mask: np.ndarray, dy: int, dx: int) -> np.ndarray:
    """Pega la silueta blanca (dura) desplazada en B."""
    sl = _shift_slices(out.shape[:2], mask, dy, dx)
    if sl is None:
        return out
    (sy, sx), (dyy, dxx) = sl
    out[dyy, dxx][mask[sy, sx]] = WHITE
    return out


# --------------------------------------------------------------------- plate


def _fill_hole_nearest(img: np.ndarray, hole: np.ndarray) -> np.ndarray:
    """Relleno por vecino más cercano (EDT) — fallback sin cv2 ni LaMa."""
    out = img.copy()
    if not hole.any():
        return out
    # edt(hole): para cada píxel del agujero, índices del fondo más cercano
    _, (iy, ix) = distance_transform_edt(hole, return_indices=True)
    out[hole] = img[iy[hole], ix[hole]]
    return out


def _grab_frame(input: Path, t: float, w: int, h: int) -> np.ndarray | None:
    p = subprocess.run(
        [video_mod._tool("ffmpeg"), "-v", "error", "-i", str(input), "-ss", f"{t:.3f}",
         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True,
    )
    if len(p.stdout) < w * h * 3:
        return None
    return np.frombuffer(p.stdout, dtype=np.uint8).reshape(h, w, 3)


def build_plate(
    input: str | Path,
    samples: int = DEFAULT_PLATE_SAMPLES,
    subject: str = "person",
) -> tuple[np.ndarray, str]:
    """Construye un plate para una persona o para un objeto arbitrario.

    ``subject='person'`` conserva la segmentación DeepLabV3 original.
    ``subject='object'`` estima una mediana temporal y detecta lo que cambia
    contra ella; ``'auto'`` usa DeepLab cuando encuentra una persona y cae a
    esa detección genérica cuando no la encuentra.

    Devuelve (plate uint8 HxWx3, engine). Engine: 'lama' | 'telea' | 'edt'.
    """
    if subject not in {"person", "object", "auto"}:
        raise ValueError(f"subject debe ser 'person', 'object' o 'auto', got {subject!r}")
    inp = Path(input)
    probe = ve.probe_video(inp)
    w, h, dur = probe["width"], probe["height"], probe["duration_s"]
    n = max(2, min(samples, max(int(round(dur * probe["fps"])), 2)))
    times = np.linspace(min(0.5, dur / 2), dur - min(0.5, dur / 4), n)

    frames = []
    for t in times:
        fr = _grab_frame(inp, float(t), w, h)
        if fr is not None:
            frames.append(fr)
    if not frames:
        raise EnhancementError(f"no se pudo muestrear ni un frame de {inp}")

    stack_u8 = np.stack(frames)
    if subject == "object" or (subject == "auto" and not _torch_available()):
        # Sin torch no hay clasificación semántica: el fallback genérico es
        # más honesto y funciona igual para personas y objetos.
        reference = np.median(stack_u8, axis=0).astype(np.uint8)
        masks = np.stack([object_mask(fr, reference) for fr in frames])
    else:
        person_masks = np.stack([person_mask(fr, dilate=0) for fr in frames])
        if subject == "person" or person_masks.any():
            masks = person_masks
        else:
            # DeepLab puede no reconocer una caja, una mascota o un objeto
            # abstracto: la mediana temporal permite continuar sin clase VOC.
            reference = np.median(stack_u8, axis=0).astype(np.uint8)
            masks = np.stack([object_mask(fr, reference) for fr in frames])

    stack = stack_u8.astype(np.float32)
    stack_nan = stack.copy()
    stack_nan[masks] = np.nan
    with np.errstate(all="ignore"):
        plate = np.nanmedian(stack_nan, axis=0)
    hole = np.isnan(plate[..., 0])
    plate = np.nan_to_num(plate, nan=0).astype(np.uint8)

    hole_d = _dilate_radius(hole, max(4, max(w, h) // 72))
    if hole_d.any():
        if _lama_available():
            from PIL import Image
            res = _lama_model()(Image.fromarray(plate), Image.fromarray((hole_d * 255).astype(np.uint8)))
            filled = np.array(res)
            # corrección de color del relleno contra una corona de fondo real + grano
            ring = _dilate_radius(hole_d, max(30, w // 12)) & ~hole_d
            for c in range(3):
                s = plate.reshape(-1, 3)[ring.reshape(-1), c]
                f = filled.reshape(-1, 3)[hole_d.reshape(-1), c]
                s_mu, s_sd = s.mean(), s.std() + 1e-6
                f_mu, f_sd = f.mean(), f.std() + 1e-6
                ch = (filled[..., c].astype(np.float32) - f_mu) * (s_sd / f_sd) + s_mu
                filled[..., c] = np.clip(ch, 0, 255)
            plate[hole_d] = filled[hole_d]
            soft = gaussian_filter(hole_d.astype(np.float32), 6)[..., None]
            grain = np.random.default_rng(7).normal(0, 2.0, plate.shape).astype(np.float32)
            plate = np.clip(plate.astype(np.float32) + grain * soft, 0, 255).astype(np.uint8)
            engine = "lama"
        else:
            try:
                import cv2
                plate = cv2.inpaint(plate, (hole_d * 255).astype(np.uint8), 5, cv2.INPAINT_TELEA)
                engine = "telea"
            except Exception:
                plate = _fill_hole_nearest(plate, hole_d)
                engine = "edt"
    else:
        engine = "nanmedian"
    return plate, engine


# ------------------------------------------------------------------ pipeline


def build_plan(input: str | Path, opts: TeleportOptions) -> str:
    """Plan legible para --dry-run."""
    opts.validate()
    inp = Path(input)
    probe = ve.probe_video(inp)
    w, g, w2 = parse_pattern(opts.pattern)
    f0 = max(int(round(opts.time * probe["fps"])), 1)
    total = max(int(round(probe["duration_s"] * probe["fps"])), 1)
    if opts.vanish:
        destino = "desaparece (no reaparece): fondo el resto del vídeo"
    else:
        dx, dy = parse_shift(opts.shift)
        destino = (f"reaparece desplazada en B: shift {dx:+.0f}%,{dy:+.0f}% "
                   f"(dx={int(round(dx * probe['width'] / 100))}px, dy={int(round(dy * probe['height'] / 100))}px)")
    if _torch_available():
        seg_engine = "DeepLabV3 MobileNetV3 (" + (
            "GPU" if __import__("torch").cuda.is_available() else "CPU") + ")"
    else:
        seg_engine = "diff contra fondo (fallback, sin torch)"
    plate_engine = ("LaMa + nanmedian consciente de persona" if _lama_available()
                    else "cv2.Telea/EDT + nanmedian (fallback sin LaMa)")
    lines = [
        "VOXERA PLAN (video teleport)",
        f"  entrada : {inp} ({probe['width']}x{probe['height']} @{probe['fps']:.2f}fps, "
        f"{probe['duration_s']:.2f}s, {total} frames)",
        f"  salida  : misma resolución/fps que entrada (audio remux copiado)",
        f"  parpadeo: t={opts.time:.2f}s (frame {f0}) — patrón {opts.pattern} "
        f"({w} blanco A, {g} hueco [esfumado→aparición], {w2} blanco B)",
        f"  destino : {destino}",
        f"  plate   : {opts.plate_samples} muestras — {plate_engine}",
        f"  máscara : {seg_engine}, dilatación silueta {opts.dilate}px",
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
    """Aplica la teletransportación y devuelve la ruta de salida.

    Streaming frame a frame: los frames con fase != normal se segmentan; el
    resto pasa sin tocar. El plate se construye antes del pase principal.
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

    dx, dy = parse_shift(None if opts.vanish else opts.shift)
    dpx = int(round(dx * w / 100.0))
    dpy = int(round(dy * h / 100.0))

    sched = teleport_schedule(f0, total, opts.pattern, vanish=opts.vanish)
    touched = [i for i, ph in sched.items() if ph != "normal"]
    print(f"[teleport] parpadeo en frame {f0} (t≈{f0 / fps:.2f}s), {len(touched)} frames "
          f"afectados hasta {touched[-1] if touched else f0}")
    if opts.vanish:
        print(f"[teleport] modo vanish: la persona desaparece y no reaparece")
    else:
        print(f"[teleport] reaparición en B: shift {dpx:+d}px,{dpy:+d}px")

    print(f"[teleport] construyendo plate de fondo ({opts.plate_samples} muestras)…")
    plate, plate_engine = build_plate(inp, opts.plate_samples)
    print(f"[teleport] plate listo (engine: {plate_engine})")

    erase_px = max(int(round(ERASE_DILATE * max(w, h) / 720.0)), 1)

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
            if phase == "normal":
                pass  # bit-exacto
            elif phase == "white_a":
                m = person_mask(frame, opts.dilate)
                frame = composite_silhouette(frame, m)
            else:
                # empty / appear / white_b / after: borrar a la persona de A
                m = person_mask(frame, dilate=0)
                m_erase = _dilate_radius(m, erase_px)
                erased = erase_person(frame, m_erase, plate)
                if phase == "appear" or phase == "after":
                    frame = paste_person(erased, frame, m, dpy, dpx)
                elif phase == "white_b":
                    frame = paste_white(erased, _dilate_radius(m, opts.dilate), dpy, dpx)
                else:
                    frame = erased
                # 'empty': solo fondo
            enc.stdin.write(frame.tobytes())
            n_frames += 1
            if n_frames % 300 == 0:
                print(f"[teleport] {n_frames}/{total} frames…")
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
