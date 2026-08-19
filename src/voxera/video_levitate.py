"""``voxera video levitate`` — efecto levitación (tutorial @serri.mp4).

Replicación del efecto de levitación del tutorial de @serri.mp4 (After
Effects): cámara fija en trípode, el sujeto salta/se mueve y en el punto más alto se
CONGELA (frame hold) y se eleva flotando sobre el fondo real (plate
reconstruido). El recorte congelado es la clave: no se re-segmenta frame a
frame (eso es el teleport), sino que se captura UNA vez y se anima hacia
arriba.

Receta (toma única, cámara fija):
  1. PLATE de fondo: mismo ``build_plate`` de video teleport (nanmedian
     consciente de persona + inpainting LaMa; fallbacks cv2.Telea / EDT).
     Con ``--plate`` se puede dar un plate externo (imagen o vídeo).
  2. FRAME HOLD en ``--at``: se segmenta el sujeto (persona con DeepLabV3 o
     cualquier objeto por diferencia temporal/plate) y se congela ese único
     recorte con feather. También admite una máscara externa.
  3. ELEVACIÓN: el recorte se pega sobre el plate desplazado hacia arriba
     (``--lift`` % de la altura) con la curva de easing de video zoom. El
     sujeto también admite una trayectoria completa: desplazamiento final
     (``--move``), giro (``--rotate``), escala (``--scale``), keyframes
     (``--keyframes``) y movimiento lateral periódico (``--motion drift
     --sway``). Con ``--shadow`` se dibuja una sombra blanda que se encoge y
     sigue al sujeto.

Límites (hereda de video teleport): el plate es un fondo CONGELADO en la zona
del sujeto; fuera de ella el vídeo original sigue vivo. El sujeto queda
congelada a propósito (es el efecto: frame hold + flotar), y su audio sigue
en la línea de tiempo (remux copiado).
"""

from __future__ import annotations

from collections.abc import Sequence
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.ndimage import binary_erosion, gaussian_filter, rotate as nd_rotate, zoom as nd_zoom

from voxera import video as video_mod
from voxera import video_enhance as ve
from voxera.errors import EnhancementError
from voxera.video_zoom import ease
from voxera.video_teleport import (
    build_plate,
    object_mask,
    person_mask,
    paste_person,
    _decode_all,
    _encode_video,
    _grab_frame,
    _lama_available,
    _torch_available,
)

DEFAULT_LIFT = 15.0             # % de la altura que sube la persona
DEFAULT_DUR = 1.5               # s de subida (curva de easing)
DEFAULT_BOB = 1.5               # % de la altura del balanceo al flotar (0 = quieto)
BOB_PERIOD_S = 2.4              # periodo del balanceo senoidal
DEFAULT_MOTION = "float"       # static | float | drift
DEFAULT_MOVE_X = 0.0            # % del ancho, desplazamiento horizontal final
DEFAULT_MOVE_Y = 0.0            # % de la altura, desplazamiento vertical adicional (+ = abajo)
DEFAULT_ROTATE = 0.0            # grados de giro final
DEFAULT_SCALE = 0.0             # % de escala final (+ crece, - encoge)
DEFAULT_SWAY = 2.0              # % del ancho en el modo drift
DEFAULT_SWAY_PERIOD = 2.4       # periodo del vaivén lateral
DEFAULT_CURVE = 62.0            # misma convención que video zoom (60-65 del tutorial)
DEFAULT_EASING = "smooth"
DEFAULT_PLATE_SAMPLES = 24      # frames muestreados para reconstruir el plate
DEFAULT_FEATHER = 1.5           # px de feather del recorte
DEFAULT_SHADOW_STRENGTH = 0.45  # opacidad de la sombra (0-1)
DEFAULT_SUBJECT = "auto"       # auto | person | object
LEVITATE_SUBJECTS = ("auto", "person", "object")
LEVITATE_MOTIONS = ("static", "float", "drift")
LEVITATE_EASINGS = ("smooth", "out", "in", "linear")
KEYFRAME_MAX = 64
KEYFRAME_EPS = 1e-6


@dataclass(frozen=True)
class LevitateKeyframe:
    """Punto de trayectoria en progreso normalizado después del frame hold.

    ``x`` y ``y`` son desplazamientos en porcentaje de W/H desde la pose
    congelada (``y`` positivo = abajo); ``rotation`` son grados y ``scale`` es
    cambio porcentual (0 = tamaño original).
    """

    progress: float
    x: float
    y: float
    rotation: float = 0.0
    scale: float = 0.0


def _validate_keyframe_sequence(
    keyframes: Sequence[LevitateKeyframe],
) -> tuple[LevitateKeyframe, ...]:
    """Ordena y valida una secuencia de keyframes ya parseada."""
    ordered = tuple(sorted(tuple(keyframes), key=lambda k: k.progress))
    if not ordered:
        raise ValueError("keyframes no puede estar vacío")
    if len(ordered) > KEYFRAME_MAX:
        raise ValueError(f"keyframes admite como máximo {KEYFRAME_MAX} puntos")
    for index, keyframe in enumerate(ordered):
        values = (keyframe.progress, keyframe.x, keyframe.y,
                  keyframe.rotation, keyframe.scale)
        if not all(math.isfinite(float(value)) for value in values):
            raise ValueError("keyframes no puede contener NaN o infinito")
        if not 0.0 <= keyframe.progress <= 1.0:
            raise ValueError(
                f"progreso de keyframe debe estar en [0, 1], got {keyframe.progress}"
            )
        if not -100.0 <= keyframe.x <= 100.0:
            raise ValueError(f"x de keyframe debe estar en [-100, 100]%, got {keyframe.x}")
        if not -100.0 <= keyframe.y <= 100.0:
            raise ValueError(f"y de keyframe debe estar en [-100, 100]%, got {keyframe.y}")
        if not -180.0 <= keyframe.rotation <= 180.0:
            raise ValueError(
                f"rotación de keyframe debe estar en [-180, 180]°, got {keyframe.rotation}"
            )
        if not -75.0 <= keyframe.scale <= 300.0:
            raise ValueError(
                f"escala de keyframe debe estar en [-75, 300]%, got {keyframe.scale}"
            )
        if index and keyframe.progress - ordered[index - 1].progress <= KEYFRAME_EPS:
            raise ValueError("keyframes no puede repetir el mismo progreso")

    first = ordered[0]
    if abs(first.progress) > KEYFRAME_EPS:
        raise ValueError("keyframes debe empezar en progreso 0")
    if any(abs(value) > KEYFRAME_EPS for value in
           (first.x, first.y, first.rotation, first.scale)):
        raise ValueError("el keyframe 0 debe conservar la pose original (todo 0)")
    return ordered


def parse_keyframes(spec: str) -> tuple[LevitateKeyframe, ...]:
    """Parsea ``P:X,Y[,ROT[,SCALE]];...`` para la trayectoria del sujeto.

    ``P`` va de 0 a 1 y representa el progreso de ``--dur``. X/Y son % de
    ancho/alto desde la pose congelada (Y positivo abajo), ROT son grados y
    SCALE es el cambio porcentual. Se permite omitir ROT y SCALE.
    """
    if not isinstance(spec, str) or not spec.strip():
        raise ValueError("keyframes debe tener la forma '0:0,0;1:5,-15,4,8'")
    points: list[LevitateKeyframe] = []
    for raw in spec.split(";"):
        token = raw.strip()
        if not token:
            continue
        if ":" in token:
            progress_text, values_text = token.split(":", 1)
        elif "=" in token:
            progress_text, values_text = token.split("=", 1)
        else:
            raise ValueError(
                f"keyframe inválido {token!r}; usa 'P:X,Y[,ROT[,SCALE]]'"
            )
        values = [value.strip() for value in values_text.split(",")]
        if len(values) not in (2, 3, 4):
            raise ValueError(
                f"keyframe {token!r} necesita X,Y[,ROT[,SCALE]]"
            )
        try:
            progress = float(progress_text.strip())
            x, y = float(values[0]), float(values[1])
            rotation = float(values[2]) if len(values) >= 3 else 0.0
            scale = float(values[3]) if len(values) == 4 else 0.0
        except ValueError as exc:
            raise ValueError(f"keyframe no numérico: {token!r}") from exc
        points.append(LevitateKeyframe(progress, x, y, rotation, scale))
    return _validate_keyframe_sequence(points)


def normalize_keyframes(
    keyframes: str | Sequence[LevitateKeyframe] | None,
) -> tuple[LevitateKeyframe, ...] | None:
    """Normaliza keyframes desde la API o desde el parser del CLI."""
    if keyframes is None:
        return None
    if isinstance(keyframes, str):
        return parse_keyframes(keyframes)
    try:
        points = tuple(keyframes)
    except TypeError as exc:
        raise ValueError("keyframes debe ser texto o una secuencia de LevitateKeyframe") from exc
    if not all(isinstance(point, LevitateKeyframe) for point in points):
        raise ValueError("keyframes debe contener LevitateKeyframe")
    return _validate_keyframe_sequence(points)


def interpolate_keyframes(
    progress: float,
    keyframes: Sequence[LevitateKeyframe],
) -> tuple[float, float, float, float]:
    """Interpola linealmente ``(x%, y%, rot°, scale%)`` en una trayectoria."""
    if not keyframes:
        raise ValueError("se necesita al menos un keyframe")
    p = min(max(float(progress), 0.0), 1.0)
    if p <= keyframes[0].progress:
        first = keyframes[0]
        return first.x, first.y, first.rotation, first.scale
    for left, right in zip(keyframes, keyframes[1:]):
        if p <= right.progress:
            span = right.progress - left.progress
            alpha = (p - left.progress) / span
            return tuple(
                getattr(left, name) + (getattr(right, name) - getattr(left, name)) * alpha
                for name in ("x", "y", "rotation", "scale")
            )
    last = keyframes[-1]
    return last.x, last.y, last.rotation, last.scale


@dataclass(frozen=True)
class LevitateOptions:
    """Parámetros de la levitación. Un solo default sensato; el resto escapes."""

    at: float                                    # instante del frame hold (s)
    lift: float = DEFAULT_LIFT                   # % de la altura que sube
    dur: float = DEFAULT_DUR                     # s de la subida
    bob: float = DEFAULT_BOB                     # % de la altura del balanceo
    curve: float = DEFAULT_CURVE                 # curva de easing 0-100
    easing: str = DEFAULT_EASING                 # smooth | out | in | linear
    plate: str | None = None                     # plate externo (imagen/vídeo)
    plate_samples: int = DEFAULT_PLATE_SAMPLES   # muestras si no hay --plate
    feather: float = DEFAULT_FEATHER             # px de feather del recorte
    shadow: bool = False                         # dibujar sombra blanda
    shadow_strength: float = DEFAULT_SHADOW_STRENGTH
    crf: int = 18
    audio_bitrate: str = "192k"
    subject: str = DEFAULT_SUBJECT             # auto | person | object
    mask: str | None = None                    # máscara externa blanca/negra
    # Transformación animada del recorte (se mantienen al final para no romper
    # la firma posicional de la primera versión de la API).
    motion: str = DEFAULT_MOTION                # static | float | drift
    move_x: float = DEFAULT_MOVE_X              # % W, final (+ = derecha)
    move_y: float = DEFAULT_MOVE_Y              # % H, final (+ = abajo)
    rotate: float = DEFAULT_ROTATE              # grados finales
    scale: float = DEFAULT_SCALE                # % final (+ crece, - encoge)
    sway: float = DEFAULT_SWAY                  # % W, vaivén lateral en drift
    sway_period: float = DEFAULT_SWAY_PERIOD   # s del vaivén lateral
    # Trayectoria opcional P:X,Y[,ROT[,SCALE]]; reemplaza lift/move/rotate/scale.
    keyframes: str | tuple[LevitateKeyframe, ...] | None = None

    def validate(self) -> None:
        if self.at < 0:
            raise EnhancementError(f"at debe ser >= 0, got {self.at}")
        if not 0 <= self.lift <= 60:
            raise EnhancementError(f"lift debe estar en [0, 60]% de la altura, got {self.lift}")
        if not 0.05 <= self.dur <= 30:
            raise EnhancementError(f"dur debe estar en [0.05, 30]s, got {self.dur}")
        if not 0 <= self.bob <= 30:
            raise EnhancementError(f"bob debe estar en [0, 30]% de la altura, got {self.bob}")
        if self.motion not in LEVITATE_MOTIONS:
            raise EnhancementError(
                f"motion debe ser uno de {LEVITATE_MOTIONS}, got {self.motion!r}"
            )
        if not -100 <= self.move_x <= 100:
            raise EnhancementError(f"move_x debe estar en [-100, 100]% del ancho, got {self.move_x}")
        if not -100 <= self.move_y <= 100:
            raise EnhancementError(f"move_y debe estar en [-100, 100]% de la altura, got {self.move_y}")
        if not -180 <= self.rotate <= 180:
            raise EnhancementError(f"rotate debe estar en [-180, 180] grados, got {self.rotate}")
        if not -75 <= self.scale <= 300:
            raise EnhancementError(f"scale debe estar en [-75, 300]%, got {self.scale}")
        if not 0 <= self.sway <= 30:
            raise EnhancementError(f"sway debe estar en [0, 30]% del ancho, got {self.sway}")
        if not 0.2 <= self.sway_period <= 30:
            raise EnhancementError(f"sway_period debe estar en [0.2, 30]s, got {self.sway_period}")
        if self.keyframes is not None:
            try:
                normalize_keyframes(self.keyframes)
            except ValueError as exc:
                raise EnhancementError(f"keyframes inválidos: {exc}") from exc
        if not 0 <= self.curve <= 100:
            raise EnhancementError(f"curve debe estar en [0, 100], got {self.curve}")
        if self.easing not in LEVITATE_EASINGS:
            raise EnhancementError(f"easing debe ser uno de {LEVITATE_EASINGS}, got {self.easing!r}")
        if self.subject not in LEVITATE_SUBJECTS:
            raise EnhancementError(
                f"subject debe ser uno de {LEVITATE_SUBJECTS}, got {self.subject!r}"
            )
        if self.plate is not None and not Path(self.plate).exists():
            raise EnhancementError(f"plate no existe: {self.plate}")
        if self.mask is not None and not Path(self.mask).exists():
            raise EnhancementError(f"mask no existe: {self.mask}")
        if not 2 <= self.plate_samples <= 240:
            raise EnhancementError(f"plate_samples debe estar en [2, 240], got {self.plate_samples}")
        if not 0 <= self.feather <= 20:
            raise EnhancementError(f"feather debe estar en [0, 20]px, got {self.feather}")
        if not 0 <= self.shadow_strength <= 1:
            raise EnhancementError(f"shadow_strength debe estar en [0, 1], got {self.shadow_strength}")
        if not 0 < self.crf <= 51:
            raise EnhancementError(f"crf debe estar en (0, 51], got {self.crf}")


def parse_move(move: str) -> tuple[float, float]:
    """Parsea ``DX,DY`` en porcentaje de W,H (+x derecha, +y abajo)."""
    parts = [p.strip() for p in move.split(",")]
    if len(parts) != 2:
        raise ValueError(f"move debe ser 'dx,dy' en %% (p.ej. 8,-3), got {move!r}")
    try:
        dx, dy = (float(p) for p in parts)
    except ValueError as exc:
        raise ValueError(f"move debe ser numérico 'dx,dy', got {move!r}") from exc
    if not -100 <= dx <= 100 or not -100 <= dy <= 100:
        raise ValueError(f"move fuera de rango ([-100,100]%% por eje), got {move!r}")
    return dx, dy


def levitation_offset(
    t: float,
    at: float,
    lift_px: float,
    dur: float,
    bob_px: float,
    curve: float = DEFAULT_CURVE,
    easing: str = DEFAULT_EASING,
    motion: str = DEFAULT_MOTION,
) -> float:
    """dy en px en el instante ``t`` (negativo = arriba). t <= at => 0.

    Subida con la curva de easing (0..1 en [at, at+dur]); después, un balanceo
    senoidal de amplitud ``bob_px`` alrededor de la posición levantada. El modo
    ``static`` conserva la subida pero desactiva el balanceo periódico.
    """
    if t <= at:
        return 0.0
    dt = t - at
    p = min(dt / max(dur, 1e-6), 1.0)
    dy = -lift_px * ease(p, curve, easing)
    if motion != "static" and bob_px > 0 and dt > dur:
        dy += bob_px * math.sin(2 * math.pi * (dt - dur) / BOB_PERIOD_S)
    return dy


def lift_progress(t: float, at: float, dur: float) -> float:
    """Progreso 0..1 de la subida (para la sombra: encoger/aclarar al subir)."""
    if t <= at:
        return 0.0
    return min((t - at) / max(dur, 1e-6), 1.0)


def levitation_transform(
    t: float,
    at: float,
    lift_px: float,
    dur: float,
    bob_px: float,
    move_x_px: float = 0.0,
    move_y_px: float = 0.0,
    rotate_deg: float = 0.0,
    scale_pct: float = 0.0,
    motion: str = DEFAULT_MOTION,
    sway_px: float = 0.0,
    sway_period: float = DEFAULT_SWAY_PERIOD,
    curve: float = DEFAULT_CURVE,
    easing: str = DEFAULT_EASING,
    keyframes: Sequence[LevitateKeyframe] | str | None = None,
    frame_width: float | None = None,
    frame_height: float | None = None,
) -> tuple[float, float, float, float]:
    """Devuelve ``(dy, dx, rotación, escala)`` para el sujeto congelado.

    Sin keyframes, ``move_x_px/move_y_px``, giro y escala llegan
    progresivamente al valor final durante la subida. Con keyframes, la ruta
    ``P:X,Y[,ROT[,SCALE]]`` reemplaza esos cuatro canales y se interpola entre
    puntos; ``frame_width/height`` convierten X/Y porcentuales a píxeles. En
    ambos modos ``float`` conserva el balanceo vertical, ``drift`` añade el
    vaivén horizontal después de la subida y ``static`` deja la pose quieta.
    Antes/en ``at`` se devuelve la identidad para conservar el frame hold.
    """
    if t <= at:
        return 0.0, 0.0, 0.0, 1.0
    dt = t - at
    p = min(dt / max(dur, 1e-6), 1.0)
    progress = ease(p, curve, easing)
    trajectory = parse_keyframes(keyframes) if isinstance(keyframes, str) else keyframes
    if trajectory is not None:
        if frame_width is None or frame_height is None:
            raise ValueError("frame_width y frame_height son necesarios con keyframes")
        x_pct, y_pct, rotation, trajectory_scale = interpolate_keyframes(progress, trajectory)
        dx = x_pct / 100.0 * frame_width
        dy = y_pct / 100.0 * frame_height
        subject_scale = max(0.25, 1.0 + trajectory_scale / 100.0)
    else:
        dy = -lift_px * progress + move_y_px * progress
        dx = move_x_px * progress
        rotation = rotate_deg * progress
        subject_scale = max(0.25, 1.0 + scale_pct / 100.0 * progress)
    if motion != "static" and bob_px > 0 and dt > dur:
        dy += bob_px * math.sin(2 * math.pi * (dt - dur) / BOB_PERIOD_S)
    if motion == "drift" and sway_px > 0 and dt > dur:
        dx += sway_px * math.sin(2 * math.pi * (dt - dur) / max(sway_period, 1e-6))
    return dy, dx, rotation, subject_scale


def render_shadow(
    frame: np.ndarray,
    mask: np.ndarray,
    lift_norm: float,
    strength: float = DEFAULT_SHADOW_STRENGTH,
    dx: float = 0.0,
    subject_scale: float = 1.0,
) -> np.ndarray:
    """Dibuja una sombra elíptica blanda bajo la persona (sujeto en ``mask``).

    La sombra se encoge y se aclara con ``lift_norm`` (0 = en el suelo,
    1 = subida completa). Se pinta sobre el plate ANTES de pegar a la persona,
    para que el sujeto quede siempre encima.
    """
    if not mask.any() or strength <= 0:
        return frame
    H, W = frame.shape[:2]
    ys, xs = np.where(mask)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    cx = (x0 + x1) / 2.0 + dx
    width = float(x1 - x0) * max(subject_scale, 0.25)
    rx = max(width * 0.45 * (1 - 0.4 * lift_norm), 2.0)
    ry = max(rx * 0.25, 1.0)
    cy = min(y1 + ry * 0.5, H - 1)

    y0r = int(max(0, cy - ry * 4))
    y1r = int(min(H, cy + ry * 4 + 1))
    x0r = int(max(0, cx - rx * 4))
    x1r = int(min(W, cx + rx * 4 + 1))
    yy, xx = np.mgrid[y0r:y1r, x0r:x1r].astype(np.float32)
    norm = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2
    alpha = np.clip(1.0 - norm, 0.0, 1.0) ** 2
    alpha *= strength * (1.0 - 0.7 * lift_norm)
    a = gaussian_filter(alpha, max(rx / 6.0, 0.5))[..., None]

    out = frame.copy()
    region = out[y0r:y1r, x0r:x1r].astype(np.float32)
    region = region * (1.0 - a)
    out[y0r:y1r, x0r:x1r] = np.clip(region, 0, 255).astype(np.uint8)
    return out


def _load_external_plate(plate_path: str, w: int, h: int) -> np.ndarray:
    """Primer frame de un plate externo (imagen o vídeo) a la resolución WxH."""
    fr = _grab_frame(Path(plate_path), 0.0, w, h)
    if fr is None:
        raise EnhancementError(f"no se pudo leer el plate: {plate_path}")
    return fr


def _load_external_mask(mask_path: str, w: int, h: int) -> np.ndarray:
    """Carga una máscara blanca/negra externa y la escala a la entrada."""
    proc = subprocess.run(
        [video_mod._tool("ffmpeg"), "-v", "error", "-i", str(mask_path),
         "-vf", f"scale={w}:{h}:flags=area", "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True,
    )
    expected = w * h
    if len(proc.stdout) < expected:
        raise EnhancementError(f"no se pudo leer la máscara: {mask_path}")
    return np.frombuffer(proc.stdout[:expected], dtype=np.uint8).reshape(h, w) > 127


def paste_transformed_subject(
    out: np.ndarray,
    frame: np.ndarray,
    mask: np.ndarray,
    dy: float,
    dx: float,
    rotation_deg: float = 0.0,
    scale: float = 1.0,
    feather: float = DEFAULT_FEATHER,
) -> np.ndarray:
    """Pega el recorte congelado con posición, escala y giro animados.

    La ruta sin giro/escala delega en ``paste_person`` para conservar el
    comportamiento y el coste de la primera versión. Para una transformación
    real se transforma un parche alrededor del bbox, no el frame completo, y
    se mezcla con alfa para no introducir un rectángulo de fondo.
    """
    if not mask.any() or scale <= 0:
        return out
    if abs(rotation_deg) < 1e-6 and abs(scale - 1.0) < 1e-6:
        return paste_person(out, frame, mask, int(round(dy)), int(round(dx)), feather=feather)

    ys, xs = np.where(mask)
    pad = max(4, int(round(max(ys.max() - ys.min() + 1, xs.max() - xs.min() + 1) * 0.2)))
    y0, y1 = max(0, ys.min() - pad), min(frame.shape[0], ys.max() + pad + 1)
    x0, x1 = max(0, xs.min() - pad), min(frame.shape[1], xs.max() + pad + 1)
    patch = frame[y0:y1, x0:x1]
    alpha = binary_erosion(mask[y0:y1, x0:x1], iterations=2).astype(np.float32)
    if not alpha.any():
        alpha = mask[y0:y1, x0:x1].astype(np.float32)
    if feather > 0:
        alpha = gaussian_filter(alpha, feather)

    if abs(scale - 1.0) >= 1e-6:
        patch = nd_zoom(patch, (scale, scale, 1.0), order=1, mode="nearest", prefilter=False)
        alpha = nd_zoom(alpha, (scale, scale), order=1, mode="constant", cval=0.0, prefilter=False)
    if abs(rotation_deg) >= 1e-6:
        patch = nd_rotate(patch, rotation_deg, reshape=True, order=1,
                          mode="constant", cval=0.0, prefilter=False)
        alpha = nd_rotate(alpha, rotation_deg, reshape=True, order=1,
                          mode="constant", cval=0.0, prefilter=False)

    ph, pw = alpha.shape
    if patch.shape[:2] != (ph, pw):
        ph, pw = min(ph, patch.shape[0]), min(pw, patch.shape[1])
        patch, alpha = patch[:ph, :pw], alpha[:ph, :pw]
    cx = (x0 + x1 - 1) / 2.0 + dx
    cy = (y0 + y1 - 1) / 2.0 + dy
    tx0, ty0 = int(round(cx - pw / 2.0)), int(round(cy - ph / 2.0))
    tx1, ty1 = tx0 + pw, ty0 + ph
    sx0, sy0 = max(0, -tx0), max(0, -ty0)
    sx1, sy1 = pw - max(0, tx1 - out.shape[1]), ph - max(0, ty1 - out.shape[0])
    dx0, dy0 = max(0, tx0), max(0, ty0)
    dx1, dy1 = min(out.shape[1], tx1), min(out.shape[0], ty1)
    if sx0 >= sx1 or sy0 >= sy1:
        return out
    a = np.clip(alpha[sy0:sy1, sx0:sx1], 0.0, 1.0)[..., None]
    dst = out[dy0:dy1, dx0:dx1].astype(np.float32)
    src = patch[sy0:sy1, sx0:sx1].astype(np.float32)
    out[dy0:dy1, dx0:dx1] = np.clip(dst * (1.0 - a) + src * a, 0, 255).astype(np.uint8)
    return out


def _subject_mask(
    frozen: np.ndarray,
    plate: np.ndarray,
    opts: LevitateOptions,
    w: int,
    h: int,
) -> np.ndarray:
    """Resuelve la máscara congelada según modo semántico o archivo externo."""
    if opts.mask:
        return _load_external_mask(opts.mask, w, h)
    if opts.subject == "object" or (opts.subject == "auto" and not _torch_available()):
        return object_mask(frozen, plate)
    mask = person_mask(frozen, dilate=0)
    if opts.subject == "auto" and not mask.any():
        mask = object_mask(frozen, plate)
    return mask


def build_plan(input: str | Path, opts: LevitateOptions) -> str:
    """Plan legible para --dry-run (misma convención que zoom/teleport)."""
    opts.validate()
    inp = Path(input)
    probe = ve.probe_video(inp)
    f0 = max(int(round(opts.at * probe["fps"])), 1)
    total = max(int(round(probe["duration_s"] * probe["fps"])), 1)
    lift_px = opts.lift / 100.0 * probe["height"]
    bob_px = opts.bob / 100.0 * probe["height"]
    move_x_px = opts.move_x / 100.0 * probe["width"]
    move_y_px = opts.move_y / 100.0 * probe["height"]
    sway_px = opts.sway / 100.0 * probe["width"]
    keyframes = normalize_keyframes(opts.keyframes)

    if keyframes:
        keyframe_text = "; ".join(
            f"{point.progress:g}:{point.x:+.1f},{point.y:+.1f},"
            f"{point.rotation:+.1f},{point.scale:+.1f}"
            for point in keyframes
        )
        elevation_line = (
            f"  elevar  : trayectoria de {len(keyframes)} keyframes "
            f"(reemplaza lift/move/rotate/scale; curva {opts.curve:.0f}, "
            f"easing {opts.easing})"
        )
        movement_line = f"  keyframes: {keyframe_text} (x/y en %; y + abajo)"
    else:
        elevation_line = (
            f"  elevar  : {opts.lift:.1f}% de la altura = {lift_px:.0f}px en {opts.dur:.2f}s "
            f"(curva {opts.curve:.0f}, easing {opts.easing})"
        )
        movement_line = (
            f"  movimiento: move {opts.move_x:+.1f}%,{opts.move_y:+.1f}% "
            f"({move_x_px:+.0f}px,{move_y_px:+.0f}px), sway {opts.sway:.1f}% "
            f"({sway_px:.0f}px/{opts.sway_period:.1f}s), rotate {opts.rotate:+.1f}°, "
            f"scale {opts.scale:+.1f}%"
        )

    if opts.mask:
        seg_engine = f"máscara externa: {opts.mask}"
    elif opts.subject == "object":
        seg_engine = "diferencia temporal contra plate (objeto arbitrario)"
    elif opts.subject == "auto":
        seg_engine = "DeepLabV3 persona + diferencia temporal para objetos"
    elif _torch_available():
        seg_engine = "DeepLabV3 MobileNetV3 (" + (
            "GPU" if __import__("torch").cuda.is_available() else "CPU") + ")"
    else:
        seg_engine = "diff contra fondo (fallback, sin torch)"
    if opts.plate:
        plate_engine = f"externo: {opts.plate}"
    elif opts.subject == "object":
        plate_engine = (f"{opts.plate_samples} muestras — mediana temporal + "
                        f"objeto fuera (LaMa/Telea/EDT)")
    else:
        plate_engine = (f"{opts.plate_samples} muestras — "
                        f"LaMa + nanmedian consciente de persona" if _lama_available()
                        else f"{opts.plate_samples} muestras — Telea/EDT + nanmedian (sin LaMa)")

    lines = [
        "VOXERA PLAN (video levitate)",
        f"  entrada : {inp} ({probe['width']}x{probe['height']} @{probe['fps']:.2f}fps, "
        f"{probe['duration_s']:.2f}s, {total} frames)",
        f"  salida  : misma resolución/fps que entrada (audio remux copiado)",
        f"  congelar: t={opts.at:.2f}s (frame {f0}) — frame hold + flotar",
        elevation_line,
        f"  flotar  : motion={opts.motion}, balanceo {opts.bob:.1f}% = {bob_px:.1f}px "
        f"(periodo {BOB_PERIOD_S:.1f}s)",
        movement_line,
        f"  sombra  : {'sí, fuerza ' + str(opts.shadow_strength) if opts.shadow else 'no'}",
        f"  plate   : {plate_engine}",
        f"  máscara : {seg_engine}, feather {opts.feather}px",
        f"  sujeto  : {opts.subject} (cualquier objeto si se elige object)",
        f"  encoder : libx264 crf {opts.crf} + aac {opts.audio_bitrate} (audio original)",
    ]
    return "\n".join(lines)


def levitate_video(input: str | Path, output: str | Path, opts: LevitateOptions) -> Path:
    """Aplica la levitación y devuelve la ruta de salida (streaming frame a frame)."""
    opts.validate()
    inp, out = Path(input), Path(output)
    if not inp.exists():
        raise EnhancementError(f"input no existe: {inp}")
    out.parent.mkdir(parents=True, exist_ok=True)

    probe = ve.probe_video(inp)
    w, h = probe["width"], probe["height"]
    fps = probe["fps"]
    total = max(int(round(probe["duration_s"] * fps)), 1)
    f0 = max(int(round(opts.at * fps)), 1)
    if f0 >= total - 1:
        raise EnhancementError(
            f"at={opts.at:.2f}s cae fuera del vídeo ({probe['duration_s']:.2f}s)"
        )

    lift_px = opts.lift / 100.0 * h
    bob_px = opts.bob / 100.0 * h
    move_x_px = opts.move_x / 100.0 * w
    move_y_px = opts.move_y / 100.0 * h
    sway_px = opts.sway / 100.0 * w
    keyframes = normalize_keyframes(opts.keyframes)

    print(f"[levitate] frame hold en {f0} (t≈{f0 / fps:.2f}s), "
          f"elevación {lift_px:.0f}px en {opts.dur:.2f}s")
    if opts.motion != "static" and opts.bob > 0:
        print(f"[levitate] flotar: motion={opts.motion}, balanceo {bob_px:.1f}px "
              f"(periodo {BOB_PERIOD_S:.1f}s)")
    if keyframes:
        print(f"[levitate] trayectoria: {len(keyframes)} keyframes "
              f"(reemplazan lift/move/rotate/scale)")
    elif opts.move_x or opts.move_y or opts.rotate or opts.scale:
        print(f"[levitate] trayectoria: move {move_x_px:+.1f}px,{move_y_px:+.1f}px, "
              f"rotate {opts.rotate:+.1f}°, scale {opts.scale:+.1f}%")
    if opts.motion == "drift" and opts.sway > 0:
        print(f"[levitate] drift: sway {sway_px:.1f}px/{opts.sway_period:.1f}s")
    if opts.shadow:
        print(f"[levitate] sombra blanda bajo el sujeto (fuerza {opts.shadow_strength})")

    if opts.plate:
        print(f"[levitate] cargando plate externo: {opts.plate}")
        plate = _load_external_plate(opts.plate, w, h)
        plate_engine = "externo"
    else:
        print(f"[levitate] construyendo plate de fondo ({opts.plate_samples} muestras, "
              f"sujeto={opts.subject})…")
        plate, plate_engine = build_plate(inp, opts.plate_samples, subject=opts.subject)
        print(f"[levitate] plate listo (engine: {plate_engine})")

    frozen = _grab_frame(inp, f0 / fps, w, h)
    if frozen is None:
        raise EnhancementError(f"no se pudo leer el frame {f0} de {inp}")
    frozen_mask = _subject_mask(frozen, plate, opts, w, h)
    if not frozen_mask.any():
        print("[levitate] AVISO: no se detectó sujeto en el frame de congelado "
              "(el resultado será solo el plate)")

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
            if n_frames >= f0:
                t = n_frames / fps
                dy, dx, rotation, subject_scale = levitation_transform(
                    t, opts.at, lift_px, opts.dur, bob_px,
                    move_x_px=move_x_px, move_y_px=move_y_px,
                    rotate_deg=opts.rotate, scale_pct=opts.scale,
                    motion=opts.motion, sway_px=sway_px,
                    sway_period=opts.sway_period,
                    curve=opts.curve, easing=opts.easing,
                    keyframes=keyframes, frame_width=w, frame_height=h,
                )
                lift_norm = lift_progress(t, opts.at, opts.dur)
                out_frame = plate.copy()
                if opts.shadow:
                    out_frame = render_shadow(
                        out_frame, frozen_mask, lift_norm, opts.shadow_strength,
                        dx=dx, subject_scale=subject_scale,
                    )
                out_frame = paste_transformed_subject(
                    out_frame, frozen, frozen_mask, dy, dx,
                    rotation_deg=rotation, scale=subject_scale,
                    feather=opts.feather,
                )
                frame = out_frame
            enc.stdin.write(frame.tobytes())
            n_frames += 1
            if n_frames % 300 == 0:
                print(f"[levitate] {n_frames}/{total} frames…")
    finally:
        try:
            enc.stdin.close()
        except BrokenPipeError:
            pass
        dec.wait(timeout=600)
        enc.wait(timeout=1800)

    if abs(n_frames - total) > 2:
        raise EnhancementError(
            f"frames procesados {n_frames} != esperados {total} (fuente inconsistente)"
        )
    if n_frames != total:
        print(f"[levitate] AVISO: contenedor declara {total} frames, el decode entrega {n_frames}.")

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
                raise EnhancementError(
                    f"remux de audio falló: {proc.stderr.decode(errors='replace')[-500:]}"
                )
        finally:
            tmp.unlink(missing_ok=True)

    oprobe = ve.probe_video(out)
    if oprobe["width"] != w or oprobe["height"] != h:
        raise EnhancementError(
            f"salida con resolución inesperada: {oprobe['width']}x{oprobe['height']}"
        )
    if abs(oprobe["duration_s"] - probe["duration_s"]) > 0.25:
        raise EnhancementError(
            f"duración inesperada: {oprobe['duration_s']:.2f}s "
            f"(esperada ~{probe['duration_s']:.2f}s)"
        )
    return out
