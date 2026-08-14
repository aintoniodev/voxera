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
   (33 tests: patrón, schedule shift/vanish, erase/paste, plate sintético,
   validación, plan, e2e shift/vanish). NOTA: usan fallback diff/EDT (sin
   torch); la segmentación+LaMa real se valida en `.venv-video`.
   Suite completa: en `.venv-video` (`.venv-ims` no tiene cv2 →
   test_video_silence/test_video_stabilize no coleccionan ahí).
2. Demo: `.venv-video/Scripts/voxera video teleport media/videos/long1.mp4
   -o media/videos/teleported/long1_teleport.mp4 --time 36`.
3. Verificación numérica: fases exactas por índice; empty → región persona
   == plate; after → persona en B (interior == fuente) y A == plate;
   antes de f0 bit-exacto; white_frac por fase.
4. QA visual: stills de empty/appear/white_b/after + preview del entorno
   del parpadeo. El fondo reconstruido debe leerse como follaje continuo
   (sin silueta humana, sin costuras duras, sin parche lavado).
