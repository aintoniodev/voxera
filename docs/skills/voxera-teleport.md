# Skill: voxera-teleport

> Mirror del skill del agente (canonical en el skill store local de pi,
> fuera del repo).

## When to Use
Aplicar el efecto teletransportación de @serri.mp4 (parpadeo de silueta
blanca como transición entre tomas) a un vídeo; editar
src/voxera/video_teleport.py; diagnosticar siluetas con mala forma; o
extenderlo (más frames de parpadeo, auto-detección del momento).

## Procedure
1. Comando: `.venv-video/Scripts/voxera video teleport IN -o OUT --time T [--pattern 2-2-2] [--dilate 3] [--dry-run]`. `--time` = instante del parpadeo (primer frame blanco). Requiere el entorno `.venv-video` (torch + torchvision para la segmentación).
2. Defaults medidos del tutorial (vídeo 7645000011205397782, 2026-08-13): patrón 2-2-2 frames (2 blanco, hueco, 2 blanco — "necesitaremos dos fotogramas, dejaremos un hueco y recortaremos otros dos"), Tinción negro→blanco 100% = silueta blanca opaca. Uso declarado por el autor: transición entre tomas (vídeos de Ibai) — NO es una desaparición sostenida.
3. Motor: silueta = SEGMENTACIÓN DE PERSONA (torchvision `deeplabv3_mobilenet_v3_large`, pesos COCO_WITH_VOC_LABELS, clase person=15) sobre el frame actual, re-escalada a la resolución del vídeo y dilatada ~3px (escala 720p), rellena de blanco opaco. Solo se segmentan los frames blancos (4) → el render es rápido (~75 s para 3333 frames a 720x1280@60).
4. Fases por frame: white(2) → gap(2, frame original) → white(2). Todo lo demás pasa sin tocar (bit-exacto en el pipe rawvideo). Audio remux copiado.
5. Verificar SIEMPRE numéricamente: white_frac por fase (≈0.50 en la demo = coincide con la segmentación), gap/fuera-ventana bit≈fuente (diff <2), patrón exacto de fases por índice. Para verificación frame-exacta entre fuente y salida: decode completo por pipe contando frames (NUNCA -ss entre vídeos re-codificados — los GOPs desalinean).

## Pitfalls
- NO hay modo "desaparecer" (--remove): el inpaint naive (vecino más cercano) sobre un fondo con textura deja un borrón con formas raras visible; sin ML de inpainting no es creíble. La máscara por diff contra fondo mediano también deja "formas raras" (ropa oscura, bordes suaves, spill). La segmentación real es la que da silueta limpia.
- El subagente executor-glm (zai/glm-5.2) y researcher NO reciben imágenes en este setup (la herramienta read omite la imagen aunque el modelo soporte visión). El QA visual debe hacerlo un humano; no fiarse de veredictos de "QA creíble" basados solo en estadísticas de píxel (un parche plano "coincide" numéricamente con un fondo oscuro aunque visualmente sea un borrón obvio).
- `torch.from_numpy(frame)` donde frame viene de `np.frombuffer` → tensor no escribible (warning). Copiar el array primero: `torch.from_numpy(frame.copy())`. NO `from_numpy(frame).copy()` (los tensores tienen `.copy_()`, no `.copy()`).
- Contenedor off-by-one: duration*fps puede declarar N+1 frames (3334 vs 3333 decodificados) — tolerancia ±2 con aviso.
- `--time` fuera del vídeo = error; cerca del final las fases se recortan.
- Render en CPU: la seg tarda ~1.5 s/frame + ~2 s de carga del modelo (una sola vez); solo son 4 frames, el resto es decode/encode puro (~75 s total a 720p@60).

## Verification
1. tests: `.venv-ims/Scripts/python.exe -m pytest tests/test_video_teleport.py -q` (16 tests: patrón, schedule, composite, person_mask fallback diff, validación, plan, e2e). Suite completa 361 passed. NOTA: los tests usan el fallback diff (sin torch); la segmentación real se valida manualmente en `.venv-video`.
2. Demo: `.venv-video/Scripts/python.exe -m voxera.cli video teleport media/videos/long1.mp4 -o media/videos/teleported/long1_teleport.mp4 --time 36` (720x1280@60, ~75 s).
3. Verificación numérica: white_frac ≈0.50 en frames white (2160-61, 2164-65), gap (2162-63) y fuera-ventana diff <2, patrón exacto.
4. QA visual humano: `media/videos/teleported/still_white_f2160.png` (frame blanco quieto, fuente|resultado) + `preview_teleport.mp4`. La silueta debe tener forma humana limpia.
