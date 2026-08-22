"""``voxera video stabilize`` — estabilización de vídeo (anti-temblor de mano).

Elimina el temblor de cámara de vídeos grabados a mano (handheld), como el
Warp Stabilizer de Premiere en modo "Smooth Motion", pero 100 % local:
OpenCV (opencv-python, ya dependencia del extra ``video``) + ffmpeg, sin
GPU, sin Premiere.

Diseño (la misma disciplina de verificación numérica del resto de efectos):

1. **Estimación** (pass 1, streaming): features Shi-Tomasi
   (``goodFeaturesToTrack``) + seguimiento Lucas-Kanade
   (``calcOpticalFlowPyrLK``) entre frames consecutivos; la transformación
   relativa se estima con ``estimateAffinePartial2D`` + RANSAC (similitud:
   rotación + escala uniforme + traslación). Se estima a resolución
   reducida (lado mayor <= 640 px: 4x menos píxeles, misma calidad) y las
   traslaciones se escalan a la resolución nativa. Las estimaciones
   descartadas por RANSAC, por exceder ``--max-shift``/``--max-angle``
   (panos rápidos, cortes de escena) o sin suficientes inliers se
   "heredan" del frame anterior (el camino queda plano ahí: se quita
   temblor, el paneo rápido se congela como en cualquier estabilizador).
   Las features se refrescan cada 12 frames para no perder el rastro.

2. **Camino acumulado** (path): cada transformación relativa se encadena
   a una trayectoria absoluta C_t (misma referencia: frame 0). C_t siempre
   es una similitud (composición de similitudes), así que se descompone de
   forma exacta alrededor del centro del frame en (tx, ty, ángulo, escala).

3. **Suavizado** (cuánto): Gaussiano (``gaussian_filter1d``, sigma =
   ``--smoothing`` frames, default 15 ~ 0.5 s a 30 fps) sobre CADA
   parámetro de la trayectoria, modo ``nearest``. El suavizado mata el
   jitter de alta frecuencia (2-10 Hz del pulso humano) y conserva los
   movimientos lentos e intencionales (panos, seguimiento): la corrección
   por frame es W_t = D_t^-1 · C_t (marcos suavizados - camino real) —
   compone el contenido al marco DESEADO, no al revés.

4. **Recorte** (qué se ve): ``--crop keep`` (default) aplica un zoom
   mínimo adaptativo: z = min(w,h)/(min(w,h) - 2·e) donde e es la máxima
   excursión de las esquinas bajo la corrección — cubre los bordes que
   asoman sin recortar de más (capado a ``--max-zoom`` 1.2). ``--crop
   black`` deja los bordes negros a la vista (útil para inspeccionar lo
   que hace el estabilizador). El zoom se aplica centrado; el borde usa
   REPLICATE (los bordes restantes se rellenan del píxel de borde, no de
   negro).

5. **Métrica** (cuánto temblor): temblor de entrada = desplazamiento del
   centro entre frames consecutivos (mediana/σ); temblor de salida = idem
   sobre las correcciones aplicadas. El plan y el final imprimen la
   reducción %. Vídeo ya estable (mediana < 0.5 px — ruido subpixel del
   estimador) → copia directa con nota, como cutsilence.

6. **Encode**: los frames corregidos se re-encodifican (libx264 CRF 18,
   yuv420p, misma resolución/fps → misma duración) y el audio original se
   remuxea: copiado bit-exacto si el códec es compatible con el contenedor
   (mp4: aac/mp3; webm: opus/vorbis; mkv/mov: casi todo) o re-encodeado a
   AAC 192k si no. Verificación determinista post-encode (duración, fps,
   audio, conteo de frames).

Determinismo: GFTT, LK y RANSAC son deterministas (sin aleatoriedad);
``gaussian_filter1d`` también — mismo input → mismo output byte a byte.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter1d

from voxera import video as video_mod
from voxera import video_enhance as ve
from voxera.errors import EnhancementError

_CV2 = None


def _cv2():
    """OpenCV perezoso — solo el subcomando ``video stabilize`` lo necesita.

    El resto del CLI (audio) no debe arrastrar opencv-python; el import en
    carga rompía ``voxera`` en venvs de audio (sin cv2).
    """
    global _CV2
    if _CV2 is None:
        import cv2
        _CV2 = cv2
    return _CV2

DEFAULT_SMOOTHING = 15.0       # sigma del gaussiano sobre la trayectoria (frames)
DEFAULT_MAX_ANGLE = 1.5        # grados por frame; 0 = sin límite
DEFAULT_MAX_ZOOM = 1.2         # capa del zoom adaptativo (crop keep)
AUTO_MAX_SHIFT_FRAC = 0.05     # max_shift automático = 5% de min(w, h)
ESTIMATE_MAX_SIDE = 640.0      # lado mayor de la resolución de estimación (px)
STATIC_THRESHOLD_PX = 0.5      # mediana de temblor bajo la que se copia directo
REFRESH_EVERY = 12             # frames entre redetección de features
MAX_CORNERS = 300
MIN_INLIERS = 8
AUDIO_COPY_CODECS = {           # códecs copiables bit-exacto por contenedor
    "mp4": {"aac", "mp3"},
    "webm": {"opus", "vorbis"},
}


@dataclass(frozen=True)
class StabilizeOptions:
    """Parámetros de la estabilización. Un solo default sensato por eje.

    ``smoothing`` = sigma del gaussiano (frames): 0 = sin suavizado
    (escape de inspección), más = más "pegado" pero más lag en panos.
    ``max_shift``/``max_angle`` son guardas contra panos rápidos y cortes
    (None = auto: 5% de min(w,h)). ``crop`` keep = zoom adaptativo mínimo
    (default), black = bordes negros a la vista.
    """

    smoothing: float = DEFAULT_SMOOTHING
    max_shift: float | None = None      # px por frame; None = auto
    max_angle: float = DEFAULT_MAX_ANGLE  # grados por frame; 0 = sin límite
    crop: str = "keep"                  # keep | black
    max_zoom: float = DEFAULT_MAX_ZOOM
    crf: int = 18
    audio_bitrate: str = "192k"

    def validate(self) -> None:
        if not 0 <= self.smoothing <= 120:
            raise EnhancementError(
                f"smoothing debe estar en [0, 120] frames, got {self.smoothing}"
            )
        if self.max_shift is not None and not 1 <= self.max_shift <= 1000:
            raise EnhancementError(
                f"max_shift debe estar en [1, 1000] px o None (auto), got {self.max_shift}"
            )
        if not 0 <= self.max_angle <= 45:
            raise EnhancementError(
                f"max_angle debe estar en [0, 45] grados (0 = sin límite), got {self.max_angle}"
            )
        if self.crop not in ("keep", "black"):
            raise EnhancementError(f"crop debe ser keep|black, got {self.crop!r}")
        if not 1.0 <= self.max_zoom <= 2.0:
            raise EnhancementError(f"max_zoom debe estar en [1.0, 2.0], got {self.max_zoom}")
        if not 0 < self.crf <= 51:
            raise EnhancementError(f"crf debe estar en (0, 51], got {self.crf}")


# ---------------------------------------------------------------------------
# Álgebra de similitudes (rotación + escala uniforme + traslación)
# ---------------------------------------------------------------------------


def decompose_similarity(M: np.ndarray) -> tuple[float, float, float, float]:
    """(tx, ty, ángulo_grados, escala) de una similitud 2x3 (sin cizalla).

    ``M`` mapea puntos del frame anterior al actual; el ángulo se extrae de
    la parte lineal como atan2(M[1,0], M[0,0]) y la escala como
    hypot(M[0,0], M[0,1]) — exacto para similitudes.
    """
    M = np.asarray(M, dtype=np.float64)
    scale = float(np.hypot(M[0, 0], M[0, 1]))
    angle = float(np.degrees(np.arctan2(M[1, 0], M[0, 0])))
    return float(M[0, 2]), float(M[1, 2]), angle, scale


def assemble_similarity(
    cx: float, cy: float, tx: float, ty: float, angle_deg: float, scale: float
) -> np.ndarray:
    """Inverso de :func:`decompose_similarity` parametrizado por el centro.

    El movimiento del centro es exactamente (tx, ty): la rotación/escala se
    aplican alrededor de (cx, cy) y la traslación se corrige para que el
    centro quede en (cx + tx, cy + ty). Devuelve la 2x3.
    """
    th = np.radians(angle_deg)
    s, c = scale * np.sin(th), scale * np.cos(th)
    R = np.array([[c, -s], [s, c]])
    center = np.array([cx, cy])
    t = np.array([tx, ty]) + center - R @ center
    return np.array([[c, -s, t[0]], [s, c, t[1]]])


def to_h3(M: np.ndarray) -> np.ndarray:
    """2x3 -> 3x3 homogénea."""
    return np.vstack([np.asarray(M, dtype=np.float64), [0.0, 0.0, 1.0]])


def to_23(M: np.ndarray) -> np.ndarray:
    """3x3 -> 2x3."""
    return np.asarray(M, dtype=np.float64)[:2]


def inverse_similarity(M: np.ndarray) -> np.ndarray:
    """Inversa exacta de una similitud 2x3 (la inversa de una similitud
    es otra similitud; R^-1 = R^T / s^2)."""
    M = np.asarray(M, dtype=np.float64)
    a, b, c = M[0, 0], M[0, 1], M[0, 2]
    d, e, f = M[1, 0], M[1, 1], M[1, 2]
    det = a * e - b * d
    if abs(det) < 1e-9:
        raise EnhancementError(f"similitud degenerada (det {det:.2e})")
    inv = np.array([
        [e / det, -b / det, (b * f - e * c) / det],
        [-d / det, a / det, (d * c - a * f) / det],
    ])
    return inv


# ---------------------------------------------------------------------------
# Trayectoria: acumulación, suavizado, correcciones
# ---------------------------------------------------------------------------


def accumulate_path(rel: list[np.ndarray]) -> list[np.ndarray]:
    """C_t (3x3, coords frame t -> frame 0) a partir de las relativas.

    Cada M_t mapea t-1 -> t; el camino acumulado C_t = C_{t-1} · M_t^-1
    (el mapa que lleva el frame t a la referencia del frame 0).
    """
    C = np.eye(3)
    out: list[np.ndarray] = []
    for M in rel:
        C = C @ to_h3(inverse_similarity(M))
        out.append(C.copy())
    return out


def path_params(
    paths: list[np.ndarray], cx: float, cy: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(tx, ty, ángulo, escala) por frame del camino, alrededor del centro."""
    n = len(paths)
    tx = np.zeros(n)
    ty = np.zeros(n)
    ang = np.zeros(n)
    sc = np.ones(n)
    for i, C in enumerate(paths):
        txi, tyi, ai, si = decompose_similarity(to_23(C))
        # parametrización por centro: rotación sobre (cx, cy) y traslación del centro
        th = np.radians(ai)
        s, c = si * np.sin(th), si * np.cos(th)
        R = np.array([[c, -s], [s, c]])
        center = np.array([cx, cy])
        # desplazamiento del centro bajo la 2x3: R·c + t - c
        t_center = np.array([txi, tyi]) + R @ center - center
        tx[i], ty[i] = t_center
        ang[i], sc[i] = ai, si
    return tx, ty, ang, sc


def smooth_params(
    tx: np.ndarray, ty: np.ndarray, ang: np.ndarray, sc: np.ndarray, sigma: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Gaussiano por parámetro (sigma en frames, modo nearest)."""
    if sigma <= 0:
        return tx.copy(), ty.copy(), ang.copy(), sc.copy()
    return tuple(
        gaussian_filter1d(p, sigma=sigma, mode="nearest") for p in (tx, ty, ang, sc)
    )


def compute_zoom(warps: list[np.ndarray], w: int, h: int, max_zoom: float) -> float:
    """Zoom mínimo que cubre la excursión de las esquinas de los warps.

    e = máxima |A·esquina - esquina|; el zoom centrado z deja un margen
    (1 - 1/z)·min/2 por lado, y se necesita que cubra e:
    z = min(w,h)/(min(w,h) - 2·e), capado a [1, max_zoom].
    """
    corners = np.array([[0.0, 0.0, 1.0], [w, 0.0, 1.0], [0.0, h, 1.0], [w, h, 1.0]])
    excursion = 0.0
    for A in warps:
        moved = (np.asarray(A, dtype=np.float64) @ corners.T).T[:, :2] - corners[:, :2]
        excursion = max(excursion, float(np.max(np.linalg.norm(moved, axis=1))))
    if excursion <= 0:
        return 1.0
    min_dim = float(min(w, h))
    z = min_dim / max(min_dim - 2.0 * excursion, 1e-6)
    return float(min(max(z, 1.0), max_zoom))


def correction_transforms(
    paths: list[np.ndarray],
    stx: np.ndarray, sty: np.ndarray, sang: np.ndarray, ssc: np.ndarray,
    w: int, h: int, crop: str, max_zoom: float,
) -> tuple[list[np.ndarray], float]:
    """Corrección por frame W_t = D_t^-1 · C_t (2x3) + zoom adaptativo.

    ``C_t`` mapea el frame t a la referencia (frame 0) y ``D_t`` es la
    similitud suavizada (marco deseado, también hacia la referencia). La
    corrección lleva el contenido del frame t al marco deseado:
    W_t = D_t^-1 · C_t (INVERTIDA respecto a D·C^-1: la versión al revés
    duplica el temblor en la salida, medido con phase correlation).
    Devuelve las warps finales Z∘W_t (zoom centrado) y el zoom aplicado
    (1.0 con ``crop=black``). El zoom mínimo (compute_zoom) cubre la
    máxima excursión de las esquinas bajo la corrección.
    """
    cx, cy = w / 2.0, h / 2.0
    warps: list[np.ndarray] = []
    for i, C in enumerate(paths):
        D = to_h3(
            assemble_similarity(cx, cy, float(stx[i]), float(sty[i]),
                                float(sang[i]), float(ssc[i]))
        )
        W = to_h3(inverse_similarity(to_23(D))) @ C  # D^-1 · C
        warps.append(W)
    if crop == "keep":
        zoom = compute_zoom(warps, w, h, max_zoom)
    else:
        zoom = 1.0
    # warp final: zoom centrado compuesto con la corrección
    out: list[np.ndarray] = []
    for A in warps:
        Z = to_h3(
            np.array([[zoom, 0.0, cx * (1 - zoom)], [0.0, zoom, cy * (1 - zoom)]])
        )
        out.append(to_23(Z @ A))
    return out, zoom


# ---------------------------------------------------------------------------
# Métricas de temblor
# ---------------------------------------------------------------------------


def center_motion(M: np.ndarray, cx: float, cy: float) -> float:
    """Desplazamiento del centro bajo una 2x3 (píxeles)."""
    c = np.array([cx, cy, 1.0])
    moved = np.asarray(M, dtype=np.float64) @ c
    return float(np.hypot(moved[0] - cx, moved[1] - cy))


def shake_stats(
    transforms: list[np.ndarray], w: int, h: int
) -> tuple[float, float]:
    """(mediana, σ) del movimiento del centro por frame (píxeles)."""
    cx, cy = w / 2.0, h / 2.0
    if not transforms:
        return 0.0, 0.0
    moves = np.array([center_motion(M, cx, cy) for M in transforms])
    return float(np.median(moves)), float(np.std(moves))


def residual_stats(
    stx: np.ndarray, sty: np.ndarray, zoom: float = 1.0
) -> tuple[float, float]:
    """(mediana, σ) del temblor visible en la salida (píxeles).

    El contenido en la salida se mueve como la trayectoria SUAVIZADA
    (escala zoom): delta_t = zoom · |Δ(tx, ty)| entre frames consecutivos
    del marco deseado. La corrección bruta no se mide: cancela el temblor
    de entrada, así que su diferencia entre frames NO es el movimiento
    visible (cada frame corrige contenido distinto).
    """
    if len(stx) < 2:
        return 0.0, 0.0
    deltas = zoom * np.hypot(np.diff(stx), np.diff(sty))
    return float(np.median(deltas)), float(np.std(deltas))


# ---------------------------------------------------------------------------
# Estimación de movimiento entre frames (OpenCV)
# ---------------------------------------------------------------------------


def estimate_motion(
    prev_gray: np.ndarray, gray: np.ndarray, prev_pts: np.ndarray | None
) -> tuple[np.ndarray | None, np.ndarray | None]:
    """Similitud relativa prev -> cur (2x3) por LK + RANSAC.

    Devuelve (M, cur_pts): M = None si no hay suficientes features/inliers
    (el llamador hereda la transformación anterior). ``prev_pts`` None
    fuerza redetección de features Shi-Tomasi.
    """
    cv = _cv2()
    if prev_pts is None or len(prev_pts) < 2:
        prev_pts = cv.goodFeaturesToTrack(
            prev_gray, MAX_CORNERS, qualityLevel=0.01, minDistance=8
        )
        if prev_pts is None or len(prev_pts) < 2:
            return None, None
    cur_pts, status, err = cv.calcOpticalFlowPyrLK(
        prev_gray, gray, prev_pts, None,
        winSize=(21, 21), maxLevel=3,
        criteria=(cv.TERM_CRITERIA_EPS | cv.TERM_CRITERIA_COUNT, 30, 0.01),
    )
    if cur_pts is None:
        return None, prev_pts
    ok = status.ravel() == 1
    if ok.sum() < MIN_INLIERS:
        return None, prev_pts
    err_ok = err[ok].ravel()
    thr = 3.0 * float(np.median(err_ok)) if len(err_ok) else 0.0
    keep = ok & (err.ravel() <= max(thr, 1e-6))
    if keep.sum() < MIN_INLIERS:
        return None, prev_pts
    M, inliers = cv.estimateAffinePartial2D(
        prev_pts[keep], cur_pts[keep], method=cv.RANSAC, ransacReprojThreshold=3.0
    )
    good = cur_pts[keep]
    if M is None or inliers is None or int(inliers.sum()) < MIN_INLIERS:
        return None, good
    return M, good


@dataclass
class Trajectory:
    """Resultado de la pass de estimación (todo a resolución nativa)."""

    rel: list[np.ndarray]          # 2x3 relativas por frame (t-1 -> t)
    low_confidence: int            # frames heredados (sin estimación válida)
    features_ok: bool              # hubo features suficientes en general

    def __init__(self) -> None:
        self.rel = []
        self.low_confidence = 0
        self.features_ok = False


def _audio_copy_ok(codec: str | None, container: str) -> bool:
    """¿Se puede remuxear el audio copiado (bit-exacto) en este contenedor?"""
    if codec is None:
        return True
    allowed = AUDIO_COPY_CODECS.get(container.lower())
    return allowed is None or codec.lower() in allowed


def _probe_audio_codec(path: str | Path) -> str | None:
    proc = subprocess.run(
        [video_mod._tool("ffprobe"), "-v", "error",
         "-select_streams", "a:0", "-show_entries", "stream=codec_name",
         "-of", "json", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    import json

    data = json.loads(proc.stdout or "{}")
    streams = data.get("streams") or []
    return streams[0].get("codec_name") if streams else None


def _decode_all(input: str | Path, w: int, h: int):
    """Pipe de decodificación rgb24 (streaming, sin audio, sin tocar disco)."""
    return subprocess.Popen(
        [video_mod._tool("ffmpeg"), "-v", "error", "-i", str(input), "-an",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE,
    )


def estimate_trajectory(input: str | Path, opts: StabilizeOptions) -> tuple[Trajectory, dict]:
    """Pass 1: estima el temblor frame a frame (decodifica el vídeo una vez).

    Devuelve (trajectory, info) con info = {w, h, fps, est_scale, max_shift}.
    """
    opts.validate()
    cv = _cv2()
    inp = Path(input)
    probe = ve.probe_video(inp)
    w, h = probe["width"], probe["height"]
    fps = probe["fps"] if probe["fps"] > 0 else 30.0
    est_scale = min(1.0, ESTIMATE_MAX_SIDE / max(w, h))
    max_shift = opts.max_shift if opts.max_shift is not None else (
        AUTO_MAX_SHIFT_FRAC * min(w, h)
    )
    cx, cy = w / 2.0, h / 2.0

    traj = Trajectory()
    prev_full: np.ndarray | None = None   # 2x3 heredada (resolución nativa)
    prev_pts: np.ndarray | None = None
    prev_gray_small: np.ndarray | None = None
    carried_streak = 0

    dec = _decode_all(inp, w, h)
    frame_size = w * h * 3
    n = 0
    try:
        while True:
            raw = dec.stdout.read(frame_size)
            if not raw or len(raw) < frame_size:
                break
            frame = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3)
            gray = cv.cvtColor(frame, cv.COLOR_RGB2GRAY)
            small = (
                cv.resize(gray, (max(int(round(w * est_scale)), 2),
                                  max(int(round(h * est_scale)), 2)),
                           interpolation=cv.INTER_AREA)
                if est_scale < 1.0 else gray
            )
            if prev_gray_small is None:
                traj.rel.append(np.eye(2, 3))
                prev_pts = cv.goodFeaturesToTrack(
                    small, MAX_CORNERS, qualityLevel=0.01, minDistance=8
                )
                traj.features_ok = prev_pts is not None and len(prev_pts) >= 2
                prev_gray_small = small
                n += 1
                continue
            # redetección periódica (o tras 2 frames heredados seguidos)
            refresh = (n % REFRESH_EVERY == 0) or carried_streak >= 2
            M_small, cur_pts = estimate_motion(
                prev_gray_small, small, None if refresh else prev_pts
            )
            if M_small is None:
                # sin estimación válida: heredar la anterior (camino plano)
                traj.low_confidence += 1
                traj.rel.append(prev_full if prev_full is not None else np.eye(2, 3))
                carried_streak += 1
            else:
                tx, ty, ang, sc = decompose_similarity(M_small)
                # guardas: pano rápido/corte de escena no es temblor
                if (np.hypot(tx, ty) > max_shift
                        or (opts.max_angle > 0 and abs(ang) > opts.max_angle)
                        or not 0.5 <= sc <= 2.0):
                    traj.low_confidence += 1
                    traj.rel.append(prev_full if prev_full is not None else np.eye(2, 3))
                    carried_streak += 1
                else:
                    carried_streak = 0
                    M_full = np.array([
                        [M_small[0, 0], M_small[0, 1], M_small[0, 2] / est_scale],
                        [M_small[1, 0], M_small[1, 1], M_small[1, 2] / est_scale],
                    ])
                    traj.rel.append(M_full)
                    prev_full = M_full
                    traj.features_ok = True
                    prev_pts = cur_pts
            prev_gray_small = small
            n += 1
    finally:
        dec.wait(timeout=600)
    if n == 0:
        raise EnhancementError(f"no se pudieron decodificar frames de {inp}")
    info = {
        "w": w, "h": h, "fps": fps, "est_scale": est_scale,
        "max_shift": max_shift, "frames": n,
    }
    return traj, info


def stabilize_paths(
    traj: Trajectory, info: dict, opts: StabilizeOptions
) -> tuple[list[np.ndarray], dict]:
    """Camino -> suavizado -> correcciones + zoom + métricas (puro, testable)."""
    w, h = info["w"], info["h"]
    cx, cy = w / 2.0, h / 2.0
    paths = accumulate_path(traj.rel)
    tx, ty, ang, sc = path_params(paths, cx, cy)
    stx, sty, sang, ssc = smooth_params(tx, ty, ang, sc, opts.smoothing)
    warps, zoom = correction_transforms(
        paths, stx, sty, sang, ssc, w, h, opts.crop, opts.max_zoom
    )
    in_med, in_std = shake_stats(traj.rel, w, h)
    out_med, out_std = residual_stats(stx, sty, zoom)
    reduction = (1.0 - out_std / in_std) * 100.0 if in_std > 1e-6 else 0.0
    metrics = {
        "in_median": in_med, "in_std": in_std,
        "out_median": out_med, "out_std": out_std,
        "reduction_pct": reduction, "zoom": zoom,
        "low_confidence": traj.low_confidence, "frames": len(traj.rel),
    }
    return warps, metrics


def build_plan(input: str | Path, opts: StabilizeOptions) -> str:
    """Plan legible para --dry-run (misma convención que zoom/enhance)."""
    opts.validate()
    inp = Path(input)
    probe = ve.probe_video(inp)
    traj, info = estimate_trajectory(inp, opts)
    warps, metrics = stabilize_paths(traj, info, opts)
    fps = info["fps"]
    max_shift = info["max_shift"]
    audio = "copiado bit-exacto" if _audio_copy_ok(
        _probe_audio_codec(inp), inp.suffix) else f"re-encodeado aac {opts.audio_bitrate}"
    return "\n".join([
        "VOXERA PLAN (video stabilize)",
        f"  entrada : {inp} ({probe['width']}x{probe['height']} @{fps:.2f}fps, "
        f"{probe['duration_s']:.2f}s, {info['frames']} frames"
        + (", con audio" if probe["has_audio"] else ", sin audio") + ")",
        f"  temblor : {metrics['in_median']:.2f} px (mediana) / {metrics['in_std']:.2f} px (σ)"
        f" -> {metrics['out_median']:.2f} / {metrics['out_std']:.2f} px"
        f" (-{metrics['reduction_pct']:.0f}%)",
        f"  suavizado: sigma {opts.smoothing:g} frames · max_shift {max_shift:.1f} px"
        f" · max_angle {opts.max_angle:g}° · estimación @{int(info['w'] * info['est_scale'])}px"
        f" · {traj.low_confidence}/{info['frames']} frames heredados",
        f"  recorte : {opts.crop} (zoom adaptativo {metrics['zoom']:.3f}x, capa {opts.max_zoom:g})"
        if opts.crop == "keep" else f"  recorte : black (bordes negros, sin zoom)",
        f"  audio   : {audio}",
        f"  encoder : libx264 crf {opts.crf} + yuv420p, misma resolución/fps "
        f"(duración sin cambios)",
    ])


def stabilize_video(input: str | Path, output: str | Path, opts: StabilizeOptions) -> Path:
    """Estabiliza el vídeo y devuelve la ruta de salida (verificada).

    Streaming (nunca materializa el vídeo completo en RAM): pass 1 estima
    el temblor; si el vídeo ya es estable se copia directo; si no, pass 2
    corrige frame a frame (warpAffine) hacia el encoder y se remuxea el
    audio original.
    """
    opts.validate()
    inp, out = Path(input), Path(output)
    if not inp.exists():
        raise EnhancementError(f"input no existe: {inp}")
    out.parent.mkdir(parents=True, exist_ok=True)

    probe = ve.probe_video(inp)
    w, h = probe["width"], probe["height"]
    fps = probe["fps"] if probe["fps"] > 0 else 30.0
    total = max(int(round(probe["duration_s"] * fps)), 1)

    print(f"[stabilize] pass 1/2: estimando temblor de {inp} ...")
    traj, info = estimate_trajectory(inp, opts)
    warps, metrics = stabilize_paths(traj, info, opts)

    print(
        f"[stabilize] temblor {metrics['in_median']:.2f} px (mediana) / "
        f"{metrics['in_std']:.2f} px (σ) → {metrics['out_median']:.2f} / "
        f"{metrics['out_std']:.2f} px (-{metrics['reduction_pct']:.0f}%)"
        + (f" · zoom {metrics['zoom']:.3f}x" if opts.crop == "keep" else " · bordes negros")
    )
    if traj.low_confidence / max(len(traj.rel), 1) > 0.5:
        print(
            f"[stabilize] AVISO: {traj.low_confidence}/{len(traj.rel)} frames sin "
            "estimación válida (escena sin textura o paneos muy rápidos)"
        )

    # Vídeo ya estable: copia directa (como cutsilence).
    if metrics["in_median"] < STATIC_THRESHOLD_PX:
        print(
            f"[stabilize] vídeo ya estable ({metrics['in_median']:.2f} px < "
            f"{STATIC_THRESHOLD_PX:g} px): copia directa"
        )
        shutil.copyfile(inp, out)
        return out

    # Pass 2: corregir y re-encodificar.
    cv = _cv2()
    border = cv.BORDER_REPLICATE if opts.crop == "keep" else cv.BORDER_CONSTANT
    dec = _decode_all(inp, w, h)
    audio_codec = _probe_audio_codec(inp) if probe["has_audio"] else None
    a_mode = "copy" if _audio_copy_ok(audio_codec, inp.suffix) else "aac"
    audio_args = (["-c:a", "copy"] if a_mode == "copy"
                  else ["-c:a", "aac", "-b:a", opts.audio_bitrate])
    enc = subprocess.Popen(
        [video_mod._tool("ffmpeg"), "-y", "-v", "error",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", f"{fps:.6f}",
         "-i", "-", "-i", str(inp),
         "-map", "0:v:0", "-map", "1:a:0?",
         "-c:v", "libx264", "-crf", str(opts.crf), "-pix_fmt", "yuv420p",
         *audio_args,
         "-movflags", "+faststart", str(out)],
        stdin=subprocess.PIPE,
    )
    frame_size = w * h * 3
    n_frames = 0
    try:
        while True:
            raw = dec.stdout.read(frame_size)
            if not raw or len(raw) < frame_size:
                break
            frame = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3)
            if n_frames < len(warps):
                frame = cv.warpAffine(
                    frame, warps[n_frames], (w, h),
                    flags=cv.INTER_LINEAR, borderMode=border,
                )
            enc.stdin.write(frame.tobytes())
            n_frames += 1
    finally:
        try:
            enc.stdin.close()
        except BrokenPipeError:
            pass
        dec.wait(timeout=600)
        enc.wait(timeout=1800)

    if enc.returncode != 0:
        raise EnhancementError(
            f"ffmpeg falló en el encode/remux: {out} (¿códec de audio incompatible?)"
        )
    if n_frames != total:
        if abs(n_frames - total) > 2:
            raise EnhancementError(
                f"frames procesados {n_frames} != esperados {total} (fuente inconsistente)"
            )
        print(f"[stabilize] AVISO: el contenedor declara {total} frames pero el decode "
              f"entrega {n_frames} (off-by-one de contenedor); se usa {n_frames}.")

    # Verificación determinista (misma disciplina que zoom/enhance).
    oprobe = ve.probe_video(out)
    if abs(oprobe["duration_s"] - probe["duration_s"]) > 0.15:
        raise EnhancementError(
            f"duración inesperada: {oprobe['duration_s']:.2f}s (esperada ~{probe['duration_s']:.2f}s)"
        )
    if oprobe["fps"] and abs(oprobe["fps"] - fps) > 0.5:
        raise EnhancementError(
            f"fps inesperado en salida: {oprobe['fps']} (esperado {fps})"
        )
    if probe["has_audio"] and not oprobe["has_audio"]:
        raise EnhancementError("se perdió la pista de audio en la salida")
    return out
