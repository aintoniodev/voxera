# Skill: voxera-teleport

> Mirror del skill del agente (canonical en el skill store local de pi,
> fuera del repo).

## When to Use
Aplicar la teletransportación REAL (parpadeo de silueta blanca 2-2-2 del
tutorial @serri.mp4 + persona que desaparece de A y reaparece viva en B) a
un vídeo de toma única con cámara fija; editar
src/voxera/video_teleport.py; diagnosticar plates/pegados con artefactos;
o extenderlo (--shift a otro destino, --vanish, auto-detección del momento).

## Procedure
1. Comando: `.venv-video/Scripts/voxera video teleport IN -o OUT --time T`
   `[--shift DX,DY] [--vanish] [--pattern 2-2-2] [--dilate 3]
   [--plate-samples 24] [--dry-run]`. `--time` = primer frame blanco.
   Requiere `.venv-video` (torch+torchvision; LaMa via
   `simple-lama-inpainting`, `pip install simple-lama-inpainting`).
2. Efecto (toma única, cámara FIJA en trípode):
   - white_a(2): silueta blanca opaca en A (Tinción negro→blanco 100%).
   - hueco(2): frame 1 = persona esfumada (plate); frame 2 = ya pegada en B.
   - white_b(2): silueta blanca en B.
   - after: cada frame se borra a la persona de A y se pega VIVA en B
     (máscara erosionada + feather 1.5px) — sigue hablando/gesticulando
     desplazada; audio intacto (remux copiado, timeline continuo).
   - `--vanish`: sin B; tras el blanco la persona no vuelve (fondo siempre).
3. PLATE de fondo: N=24 frames muestreados (seek exacto ffmpeg), persona
   segmentada en cada uno (DeepLabV3 MobileNetV3 clase person=15, GPU si
   hay CUDA), mediana temporal SOLO con frames donde cada píxel no es
   persona (nanmedian consciente) → fondo real salvo el núcleo persistente
   (~18% del frame en la demo); ese núcleo se inpainta con LaMa
   (big-lama.pt ~196MB, auto-descarga 1ª vez) + corrección de color contra
   corona real + grano σ2. Fallbacks sin LaMa: cv2.Telea, sin cv2: EDT.
4. `--shift` = destino B como "dx,dy" en % del ancho/alto (default `-25,0`
   = izquierda). dx=+25 → derecha; dy negativo → arriba.

## Pitfalls
- El plate es un fondo CONGELADO: en la zona de la persona los árboles no
  se mecen. Fuera de esa zona el vídeo sigue vivo. Si la cámara tiembla,
  el plate desentona → estabilizar antes (`video stabilize`).
- LaMa con el agujero ENORME (56% si se inpainta TODO con mediana simple)
  da un relleno plano/lavado — QA visual 4-5/10. La nanmedian consciente
  reduce el agujero al núcleo persistente (~18%) y LaMa + color-match +
  grano sube el plate a 7/10 y el composite a 8/10 (medido 2026-08-14).
- Pegar la persona con máscara dura deja halo (píxeles del fondo viejo en
  el borde): erosionar 2px + gaussian 1.5px.
- El paste lee del frame ORIGINAL, nunca del ya borrado (erase primero,
  paste después con fuente distinta).
- `_fill_hole_nearest`: `distance_transform_edt(hole, ...)` — la entrada
  es el AGUJERO (True dentro); con `~hole` los índices apuntan a sí
  mismos y quedan ceros (bug medido).
- `torch.from_numpy(frame)` con buffer read-only → copiar antes
  (`frame.copy()`). Interpolación de máscara: bilinear+0.5 (nearest da
  bordes de bloque).
- Contenedor off-by-one: duration*fps puede declarar N+1 frames —
  tolerancia ±2 con aviso. `--time` fuera del vídeo = error.
- Segmentation tras el parpadeo: ~0.1-0.35 s/frame GPU (RTX 2060),
  ~1.1 s/frame CPU. Demo 720x1280@60 completa: plate ~1 min + render
  ~8-10 min. Solo el parpadeo (fases white) es barato.
- El subagente executor-glm NO recibe imágenes en este setup; el QA visual
  lo hace el agente principal con la tool de visión o un humano.

## Verification
1. tests: `.venv-ims/Scripts/python.exe -m pytest tests/test_video_teleport.py -q`
   (34 tests: patrón, schedule shift/vanish, erase/paste + máscara vacía, plate
   sintético, validación, plan, e2e shift/vanish). Un fixture autouse fuerza
   diff-borde y sin LaMa (el cuadrado sintético no es 'person' para DeepLabV3)
   → pasan IGUAL en .venv-ims y .venv-video en ~30 s, sin cargar modelos.
   La segmentación+LaMa real se valida con la demo.
   Suite completa: en `.venv-video` (`.venv-ims` no tiene cv2 →
   test_video_silence/test_video_stabilize no coleccionan ahí).
2. Demo: `.venv-video/Scripts/voxera video teleport media/videos/long1.mp4
   -o media/videos/teleported/long1_teleport_v2.mp4 --time 36`
   (~9 min RTX 2060: plate ~1 min + render; verificado 2026-08-14: 18/18
   checks numéricos + QA visual 7.5-8/10).
3. Verificación numérica: fases exactas por índice; empty → región persona
   == plate; after → persona en B (interior == fuente) y A == plate;
   antes de f0 bit-exacto; white_frac por fase.
4. QA visual: stills de empty/appear/white_b/after + preview del entorno
   del parpadeo. El fondo reconstruido debe leerse como follaje continuo
   (sin silueta humana, sin costuras duras, sin parche lavado).

## Reference Implementation (código núcleo)

Tres piezas: (1) el schedule de fases por frame, (2) borrar/pegar con máscara, (3) el plate de fondo. La magia está en el plate (nanmedian consciente de persona + LaMa + color-match + grano) — sin eso el fondo reconstruido es un borrón (QA 4-5/10 en vez de 7-8/10).

```python
import numpy as np
from scipy.ndimage import binary_erosion, gaussian_filter

# --- 1) schedule: fase por índice de frame (patrón '2-2-2' del tutorial) ---
def teleport_schedule(f0: int, total: int, w: int = 2, g: int = 2, w2: int = 2,
                      vanish: bool = False) -> dict[int, str]:
    """[f0,f0+w)=white_a · [f0+w,f0+w+g/2)=empty (esfumado: plate) ·
    [..,+g)=appear (ya en B) · [..,+w2)=white_b · resto=after (viva en B).
    vanish: todo lo posterior al blanco = empty (no reaparece). f0 clamp [1,total-1]."""
    f0 = min(max(f0, 1), max(total - 1, 1))
    gap_empty = max(g // 2, 1) if not vanish else g
    sched = {}
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
```

```python
# --- 2) erase/paste con máscara (persona segmentada: DeepLabV3 clase 15) ---
def erase_person(frame: np.ndarray, mask: np.ndarray, plate: np.ndarray) -> np.ndarray:
    """Borra la persona (máscara dilatada) sustituyéndola por el plate."""
    out = frame.copy()
    out[mask] = plate[mask]
    return out

def paste_person(out: np.ndarray, frame: np.ndarray, mask: np.ndarray,
                 dy: int, dx: int, feather: float = 1.5) -> np.ndarray:
    """Pega la persona VIVA desplazada (dy,dx) con borde suave.
    OJO: lee del frame ORIGINAL, nunca del ya borrado."""
    if not mask.any():
        return out  # persona no detectada: no-op (ys.min() sobre vacío explota)
    H, W = out.shape[:2]
    ys, xs = np.where(mask)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    sy0, sy1 = max(0, y0 + dy), min(H, y1 + dy)
    sx0, sx1 = max(0, x0 + dx), min(W, x1 + dx)
    if sy0 >= sy1 or sx0 >= sx1:
        return out
    src = (slice(sy0 - dy, sy1 - dy), slice(sx0 - dx, sx1 - dx))
    dst = (slice(sy0, sy1), slice(sx0, sx1))
    alpha = gaussian_filter(binary_erosion(mask, iterations=2).astype(np.float32), feather)
    a = np.clip(alpha[src], 0, 1)[..., None]
    out[dst] = (out[dst].astype(np.float32) * (1 - a)
                + frame[src].astype(np.float32) * a).astype(np.uint8)
    return out

def composite_silhouette(frame: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Silueta blanca opaca (Tinción 100%): out[mask] = 255."""
    out = frame.copy()
    out[mask] = np.array([255, 255, 255], dtype=np.uint8)
    return out
```

```python
# --- 3) plate de fondo: nanmedian consciente de persona + inpaint + color-match + grano ---
def build_plate(frames: list[np.ndarray], masks: list[np.ndarray]):
    """frames/masks: N frames muestreados y sus máscaras de persona (DeepLabV3).
    Mediana temporal SOLO donde el píxel NO es persona en ningún frame;
    el núcleo persistente (persona siempre ahí) queda NaN y se inpainta."""
    stack = np.stack(frames).astype(np.float32)
    stack_nan = stack.copy()
    stack_nan[np.stack(masks)] = np.nan
    with np.errstate(all="ignore"):
        plate = np.nanmedian(stack_nan, axis=0)
    hole = np.isnan(plate[..., 0])
    plate = np.nan_to_num(plate, nan=0).astype(np.uint8)
    if hole.any():
        filled = lama_inpaint(plate, hole)          # LaMa; fallbacks: cv2.Telea, EDT
        ring = dilate(hole, 30) & ~hole             # corona de fondo real
        for c in range(3):                          # color-match del relleno
            s = plate[..., c][ring]; f = filled[..., c][hole]
            filled[..., c] = np.clip((filled[..., c].astype(np.float32) - f.mean())
                                     * (s.std() / (f.std() + 1e-6)) + s.mean(), 0, 255)
        plate[hole] = filled[hole]
        # grano sigma 2 solo en la zona inpainta (mata el aspecto plástico)
        soft = gaussian_filter(hole.astype(np.float32), 6)[..., None]
        grain = np.random.default_rng(7).normal(0, 2.0, plate.shape).astype(np.float32)
        plate = np.clip(plate.astype(np.float32) + grain * soft, 0, 255).astype(np.uint8)
    return plate
```

Notas de réplica: la máscara de persona = DeepLabV3 MobileNetV3 (torchvision, pesos COCO_WITH_VOC_LABELS, clase person=15) re-escalada y dilatada ~3 px; segmentar SOLO los frames blancos y los del plate (~0.1-0.35 s/frame GPU, ~1.1 s CPU); `torch.from_numpy(frame)` con buffer read-only → `frame.copy()` primero; el paste con máscara dura deja halo → erosionar 2 px + gaussian 1.5 px.
