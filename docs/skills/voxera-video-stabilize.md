# voxera-video-stabilize — estabilización de vídeo (anti-temblor de mano)

> Mirror en repo del skill del agente (`project:improve-my-sound:voxera-video-stabilize`).
> Canonical: skill store local de pi; este archivo versiona el conocimiento en el repo.

## When to Use

Aplicar estabilización de vídeo (`voxera video stabilize`), editar
`src/voxera/video_stabilize.py`, diagnosticar temblor residual o panes
congelados, o replicar el "Warp Stabilizer" de Premiere en modo *Smooth
Motion* sin Premiere.

## Procedure

1. Comando:
   `.venv-video/Scripts/voxera video stabilize IN -o OUT [--smoothing S] [--max-shift PX] [--max-angle DEG] [--crop keep|black] [--max-zoom Z] [--dry-run]`.
   Defaults: `smoothing` 15 (≈0.5 s a 30 fps), `max_shift` auto (5 % de
   min(w,h)), `max_angle` 1.5°, `crop` keep (zoom adaptativo mínimo),
   `max_zoom` 1.2.
2. Estimación (pass 1): `goodFeaturesToTrack` (Shi-Tomasi, 300 corners) +
   `calcOpticalFlowPyrLK` + `estimateAffinePartial2D` RANSAC entre frames
   consecutivos, a resolución ≤ 640 px (las traslaciones se escalan a la
   nativa). Features refrescadas cada 12 frames (o tras 2 frames
   heredados). Estimaciones inválidas, o que exceden `--max-shift`/
   `--max-angle` (paneos rápidos, cortes de escena), se **heredan** del
   frame anterior (camino plano → se congelan).
3. Camino y suavizado: C_t = C_{t-1}·M_t^-1 (similitud exacta, se
   descompone alrededor del centro en tx/ty/ángulo/escala) → Gaussiano
   por parámetro (sigma = smoothing, modo `nearest`). La corrección por
   frame es **W_t = D_t⁻¹·C_t** (lleva el contenido al marco suavizado).
4. Recorte: `crop keep` calcula la excursión máxima de las esquinas bajo
   la corrección y aplica zoom z = min/(min−2·e) (capado a max_zoom);
   `crop black` = sin zoom, bordes negros (inspección). Borde del warp:
   REPLICATE (keep) o CONSTANT negro (black).
5. Métrica: temblor de entrada = desplazamiento del centro entre frames
   consecutivos (mediana/σ); temblor de salida = idem sobre la
   trayectoria suavizada × zoom. Mediana < 0.5 px → vídeo ya estable →
   **copia directa** con nota. La salida imprime `-NN%` y el zoom.
6. Encode: pass 2 corrige frame a frame (warpAffine) → libx264 CRF 18,
   yuv420p, misma resolución/fps (duración sin cambios) + audio
   remuxado: copiado bit-exacto si el códec es compatible con el
   contenedor (mp4: aac/mp3; webm: opus/vorbis; mkv/mov: casi todo), si
   no re-encode AAC 192k. Verificación post-encode: duración ±0.15 s,
   fps ±0.5, audio preservado, frames ±1.
7. Verificación del módulo:
   `python -m pytest tests/test_video_stabilize.py -q --import-mode=importlib`
   (44 tests: álgebra de similitudes, trayectoria, suavizado, zoom,
   métricas, estimación, e2e sintéticos + demo real si `media/` presente).

## Pitfalls

- **La corrección es W_t = D_t⁻¹·C_t, NO D_t·C_t⁻¹.** La versión invertida
  DUPLICA el temblor en la salida (medido con phase correlation: 2.65 px
  de salida vs 1.18 px de entrada, con el módulo reportando -90 %). El
  orden correcto se verifica a nivel de píxel: la posición de un punto
  del contenido tras el warp debe seguir el marco suavizado, no el
  temblor (regresión cubierta por `test_warps_actually_cancel_shake`).
- La métrica interna (residual_stats sobre la trayectoria suavizada) NO
  basta para validar: mide el marco deseado, no los píxeles. En los e2e
  medir SIEMPRE la salida con un método ajeno al módulo (phase
  correlation `cv2.phaseCorrelate` entre frames consecutivos).
- Phase correlation se confunde con los bordes: con `crop black` los
  bordes negros estáticos dominan la correlación y el resultado es
  basura. Medir SIEMPRE sobre un recorte central (~75 %) del frame.
- Sintético para e2e: escena estática con textura rica (blobs
  aleatorios) + temblor determinista (sinusoides lentas + rápidas,
  amplitudes ~12-16 px), frames generados con `warpAffine` + borde
  REPLICATE. Un temblor puramente aleatorio (random walk) no es
  reproducible y un vídeo sin textura no da features.
- ffmpeg: las opciones de un segundo input (`-f lavfi -i sine=...`)
  deben ir ANTES de las opciones de salida y de `-shortest`; opciones de
  audio (`-b:a`) no se pasan con `-c:a copy` (se ignoran/fallan).
- En el e2e la posición del contenido en el frame t es
  `p + cumsum(desplazamientos)`, no `p + desplazamiento_t` (los
  desplazamientos relativos son pasos entre frames).
- Los venvs `.venv-video`/`.venv-ims` no existen en todos los checkouts:
  probar con `PYTHONPATH=src python -m voxera.cli` + Python global
  (requiere opencv-python + numpy + scipy; ffmpeg en `C:/ffmpeg/bin`).
- Determinismo: GFTT, LK y RANSAC no tienen aleatoriedad — mismo input →
  mismo output byte a byte (verificado en tests).

## Verification

1. Suite del módulo: 44 passed (`tests/test_video_stabilize.py --import-mode=importlib`).
2. E2E sintético (240x320@30, 3 s, temblor ~12-16 px): el temblor medido
   con phase correlation (central crop) cae ≥ 50 % (en la práctica:
   in 1.18-2.4 px → out 0.3-0.6 px); duración ±0.15 s, fps ±0.5, audio
   preservado, frames ±1.
3. Estático (sin temblor) → copia directa bit-exacta (bytes idénticos).
4. `--crop black` y vídeo sin audio funcionan; plan `--dry-run` imprime
   VOXERA PLAN con temblor antes/después y zoom; `-o` obligatorio
   (argparse exit 2); input inexistente → `EnhancementError` exit 1.
5. Demo real: `media/demo-video.mp4` (render Remotion, cámara fija) →
   procesa sin error, duración y audio preservados.

## Reference Implementation (código núcleo)

El corazón es el álgebra de similitudes 2x3 y el ORDEN de la corrección: `W_t = D_t⁻¹ · C_t` (INVERTIDA respecto a `D·C⁻¹` — la versión al revés DUPLICA el temblor en la salida, medido con phase correlation: 2.65 px out vs 1.18 px in). Estimación de movimiento: goodFeaturesToTrack (300 corners) + calcOpticalFlowPyrLK + estimateAffinePartial2D RANSAC entre frames consecutivos a resolución ≤ 640 px.

```python
import numpy as np
from scipy.ndimage import gaussian_filter1d

def decompose_similarity(M: np.ndarray) -> tuple[float, float, float, float]:
    """(tx, ty, ángulo_grados, escala) de una similitud 2x3 (sin cizalla)."""
    M = np.asarray(M, dtype=np.float64)
    scale = float(np.hypot(M[0, 0], M[0, 1]))
    angle = float(np.degrees(np.arctan2(M[1, 0], M[0, 0])))
    return float(M[0, 2]), float(M[1, 2]), angle, scale

def assemble_similarity(cx, cy, tx, ty, angle_deg, scale) -> np.ndarray:
    """Inverso de decompose, parametrizado por el centro: la rotación/escala
    se aplican alrededor de (cx, cy) y el centro queda en (cx+tx, cy+ty)."""
    th = np.radians(angle_deg); s, c = scale * np.sin(th), scale * np.cos(th)
    R = np.array([[c, -s], [s, c]])
    center = np.array([cx, cy])
    t = np.array([tx, ty]) + center - R @ center
    return np.array([[c, -s, t[0]], [s, c, t[1]]])

def inverse_similarity(M: np.ndarray) -> np.ndarray:
    """Inversa exacta de una similitud 2x3 (R⁻¹ = Rᵀ/s²)."""
    M = np.asarray(M, dtype=np.float64)
    a, b, c, d, e, f = M[0, 0], M[0, 1], M[0, 2], M[1, 0], M[1, 1], M[1, 2]
    det = a * e - b * d
    return np.array([[e / det, -b / det, (b * f - e * c) / det],
                     [-d / det, a / det, (d * c - a * f) / det]])

def accumulate_path(rel: list[np.ndarray]) -> list[np.ndarray]:
    """C_t (3x3, frame t -> frame 0): C_t = C_{t-1} · M_t⁻¹ (M_t: t-1 -> t)."""
    C, out = np.eye(3), []
    for M in rel:
        C = C @ np.vstack([inverse_similarity(M), [0, 0, 1]])
        out.append(C.copy())
    return out

def smooth_params(tx, ty, ang, sc, sigma: float):
    """Gaussiano por parámetro (sigma en frames, modo nearest)."""
    if sigma <= 0:
        return tx.copy(), ty.copy(), ang.copy(), sc.copy()
    return tuple(gaussian_filter1d(p, sigma=sigma, mode="nearest")
                 for p in (tx, ty, ang, sc))
```

```python
# --- corrección por frame + zoom adaptativo ---
def correction_transforms(paths, stx, sty, sang, ssc, w, h, crop="keep", max_zoom=1.2):
    """W_t = D_t⁻¹ · C_t (2x3). C_t: frame t -> referencia; D_t: marco suavizado
    -> referencia. El warp final = Z∘W_t con zoom centrado (crop keep) que cubre
    la máxima excursión de las esquinas: z = min/(min-2e), cap max_zoom."""
    cx, cy = w / 2.0, h / 2.0
    warps = []
    for i, C in enumerate(paths):
        D = np.vstack([assemble_similarity(cx, cy, stx[i], sty[i], sang[i], ssc[i]), [0, 0, 1]])
        W = np.vstack([inverse_similarity(D[:2]), [0, 0, 1]]) @ C   # D⁻¹ · C
        warps.append(W)
    zoom = compute_zoom(warps, w, h, max_zoom) if crop == "keep" else 1.0
    out = []
    for A in warps:
        Z = np.array([[zoom, 0, cx * (1 - zoom)], [0, zoom, cy * (1 - zoom)]])
        out.append((Z @ A)[:2])   # warpAffine por frame: pass 2
    return out, zoom
```

Notas de réplica: estimaciones inválidas o que exceden max_shift/max_angle (paneos rápidos, cortes) se HEREDAN del frame anterior (camino plano → se congelan); features refrescadas cada 12 frames; mediana de temblor < 0.5 px → copia directa bit-exacta; la métrica interna NO basta — medir la salida con phase correlation (`cv2.phaseCorrelate`) sobre recorte central ~75% (los bordes negros con `crop black` dominan la correlación); e2e sintético: escena estática con blobs + temblor determinista sinusoidal ~12-16 px (random walk no es reproducible); la posición en el frame t es `p + cumsum(desplazamientos)`.
