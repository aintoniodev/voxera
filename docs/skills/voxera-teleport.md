# Skill: voxera-teleport

> Mirror del skill del agente (canonical en el skill store local de pi,
> fuera del repo).

## When to Use
Aplicar el efecto teletransportación de @serri.mp4 (silueta blanca con
parpadeo + desaparición) a vídeos de cámara fija; editar
src/voxera/video_teleport.py; diagnosticar renders del efecto (fantasmas,
siluetas perforadas, inpaint oscuro); o extenderlo (nuevos patrones,
auto-detección del momento).

## Procedure
1. Comando: `.venv-ims/Scripts/voxera video teleport IN -o OUT --time T [--remove] [--pattern 2-2-2] [--hold 0.5] [--dilate 3] [--threshold 18] [--bg-frames 30] [--dry-run]`. --time = instante del parpadeo (primer frame blanco); --remove = el sujeto además desaparece tras el parpadeo (teletransportación completa).
2. Defaults medidos del tutorial (vídeo 7645000011205397782, 2026-08-13): patrón 2-2-2 frames (2 blanco, hueco, 2 blanco — "necesitaremos dos fotogramas, dejaremos un hueco y recortaremos otros dos"), Tinción negro→blanco 100% = silueta blanca opaca, cámara fija obligatoria ("es importante grabar en un tripod"). Uso declarado: transición entre tomas (vídeos de Ibai).
3. Motor: fondo = mediana de N muestras (SOLO referencia de máscara — con sujeto casi estático la mediana queda contaminada por el propio sujeto y NO sirve como color de relleno). Máscara por frame: max-diff RGB vs fondo > umbral + close ~11px + open ~5px (radios EDT escalados a 720p).
4. Silueta: máscara del frame ACTUAL (roto de cada corte del tutorial), dilatada ~5px, relleno blanco opaco. En hold se congela la del último frame blanco. Fases por frame: white(2) → gap(2, frame original) → white(2) → hold(--remove, silueta congelada) → gone(--remove, sujeto eliminado).
5. Inpaint (gone/hold/white con --remove): región = máscara ∪ ref dilatada cover=25px; fuente = píxel no-máscara más cercano FUERA de cover+margin=12px; color = fondo mediano en esa posición (no el frame actual: el borde del sujeto es oscuro y rellena el fantasma con el color de la ropa — medido).
6. Morfología y dilataciones SIEMPRE por radio EDT (1-2 pasadas), nunca binary_dilation/binary_closing iterativos con kernels grandes: 611ms/frame → 147-272ms; el render completo pasó de 18min a 9.4min (medido, 720x1280@60, 3333 frames).
7. Verificar SIEMPRE numéricamente: fracción de píxeles blancos por fase (white ≈0.58 en la demo), hueco bit≈fuente (diff <2), frames lejanos intactos (diff ~1.8 = re-encode), consistencia de gone entre frames, patrón exacto de fases por índice (decode completo por pipe, NUNCA -ss para alinear frames entre vídeos re-codificados — los GOPs difieren y desalinea).

## Pitfalls
- scipy binary_dilation(iterations=0 o <1) dilata HASTA NO CAMBIAR (todo True) — guard explícito o usar EDT.
- Semántica EDT (verificada 2026-08-13): dilate(A,r) = EDT(~A) <= r; erode(A,r) = EDT(A) > r. Invertir la polaridad produce máscaras complementarias (frac 0.9 en vez de 0.08).
- El fondo mediano contaminado deja un FANTASMA oscuro en el inpaint si se usa como color dentro de la máscara; y el relleno desde el vecino más cercano del frame actual rellena con el borde de la ropa del sujeto (fantasma R2). La combinación ganadora: cover 25px + fuente fuera + color del fondo mediano en la posición fuente (la pared está limpia en la mediana; el fantasma vive solo dentro de la máscara, que nunca se muestrea).
- Ropa oscura sobre fondo oscuro → diff < umbral → zonas del cuerpo sin máscara → quedan visibles en gone. Mitigación: umbral 18 (no 25) + unión con la máscara de la silueta (ref) + cover 25px.
- Contenedor off-by-one: duration*fps puede declarar N+1 frames (3334 vs 3333 decodificados) — tolerancia ±2 con aviso, no error.
- Muestreo de fondo: el último ~0.5s del contenedor puede devolver vacío al hacer seek — muestrear en [0.3s, dur-0.5s] con reintentos y saltar muestras fallidas (mínimo 2).
- Métrica de cámara fija: medir el residuo fuera de la máscara vs fondo (no diff entre muestras crudas — un talking head mueve el sujeto y dispara falsos positivos).
- Para verificación frame-exacta entre fuente y salida re-codificada: decodificar completo por pipe contando frames y quedarse con la ventana (select=between con escapes falla; -ss desalinea entre GOPs).
- El sujeto debe ocupar una fracción razonable del frame y NO tocar los bordes por completo: si la máscara llega al borde del frame no hay fuente de relleno en esa dirección.
- --time cerca del final: las fases se recortan (nunca gone sin frames); --time fuera del vídeo = error.

## Verification
1. tests: `.venv-ims/Scripts/python.exe -m pytest tests/test_video_teleport.py -q` (25 tests: patrón, schedule, máscara, inpaint, validación, plan, e2e ghost/remove/audio). Suite completa 301 passed.
2. Demo: `.venv/Scripts/python.exe -m voxera.cli video teleport media/videos/long1.mp4 -o media/videos/teleported/long1_teleport.mp4 --time 36 --remove` (720x1280@60, ~9.5min).
3. Verificación numérica del render: white_frac ≈0.58 en frames white, gap/fuera-ventana diff <2, gone sin silueta (white=0) y consistente entre frames, frames lejanos diff ~1.8.
4. QA visual (subagente GLM-5.2 con visión): montaje fuente|resultado de 6 momentos + zoom del torso — ronda 4 aprobada: sin fantasma, sin costura, siluetas 248-255 sólidas.
5. Preview: media/videos/teleported/preview_teleport.mp4 (t 35.7-38.3s).
