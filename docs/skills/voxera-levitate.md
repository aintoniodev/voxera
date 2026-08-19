# Skill: voxera-levitate

> Mirror del skill del agente (canonical en el skill store local de pi,
> fuera del repo).

## When to Use
Aplicar el efecto levitación del tutorial @serri.mp4 (un sujeto se congela
en el aire y flota hacia arriba) a un vídeo de toma única con cámara fija;
funciona tanto con personas como con objetos arbitrarios. Editar
src/voxera/video_levitate.py; diagnosticar recortes/plates con artefactos; o
extenderlo (plate externo, máscara externa, trayectoria, giro, escala, sombra,
auto-detección del pico).

## Procedure
1. Comando: `.venv-video/Scripts/voxera video levitate IN -o OUT --at T`
   `[--subject auto|person|object] [--mask MASK] [--lift 15] [--dur 1.5]
   [--bob 1.5] [--motion static|float|drift] [--move DX,DY]
   [--keyframes 'P:X,Y[,ROT[,SCALE]];...'] [--rotate DEG] [--scale PCT]
   [--sway PCT] [--sway-period 2.4] [--shadow] [--curve 62]
   [--easing smooth] [--plate PLATE]
   [--plate-samples 24] [--feather 1.5] [--dry-run]`. `--at` = frame hold
   (el pico del salto o el instante del objeto). Requiere
   `.venv-video` (torch+torchvision; LaMa via `simple-lama-inpainting`,
   `pip install simple-lama-inpainting`).
2. Efecto (toma única, cámara FIJA en trípode):
   - Antes de `--at`: passthrough bit-exacto (la acción se ve normal).
   - En `--at`: frame hold — el sujeto se segmenta UNA vez. `--subject person`
     usa DeepLabV3; `--subject object` compara contra la mediana temporal o el
     plate; `--subject auto` prueba persona y cae a objeto. Con `--mask` se
     usa una máscara blanca/negra externa alineada al frame congelado.
   - Después: el recorte congelado se anima sobre el plate con la curva de
     easing de video zoom. `--lift` es la subida base; `--move DX,DY` añade un
     desplazamiento final en porcentaje de W,H; `--rotate` y `--scale` animan
     giro y tamaño. Para una ruta no lineal usa `--keyframes` con puntos
     `P:X,Y[,ROT[,SCALE]]` separados por `;`: P va de 0 a 1 durante `--dur`,
     X/Y son desplazamientos porcentuales desde la pose congelada (Y positivo
     abajo), ROT son grados y SCALE es cambio porcentual. Debe existir el punto
     `0:0,0`; los keyframes reemplazan `--lift/--move/--rotate/--scale` y el
     último punto se mantiene después de `--dur`. `--bob` es el balanceo
     vertical; `--motion drift` suma un vaivén horizontal (`--sway`,
     `--sway-period`); `static` desactiva los vaivenes. `--shadow` dibuja una
     sombra blanda que se encoge y sigue al sujeto. Audio intacto (remux
     copiado, timeline continuo).
3. PLATE de fondo: para personas, mismo `build_plate` de video teleport
   (nanmedian consciente de persona + LaMa + color-match + grano; fallbacks
   cv2.Telea / EDT). Para `--subject object`, la mediana temporal elimina el
   objeto que se mueve y luego se repara el hueco. Con `--plate` se da un plate
   externo (imagen o primer frame de un vídeo) — es lo más fiable si el objeto
   no se mueve, comparte color con el fondo o la toma tiene mucho movimiento.
4. Matemática del movimiento (pura, testable): sin keyframes, con
   `p = clamp01((t-at)/dur)` y `e = ease(p)`,
   `dy = -lift_px*e + move_y_px*e`, `dx = move_x_px*e`,
   `rotation = rotate_deg*e`, `scale = 1 + scale_pct/100*e`.
   Con keyframes, `e` se usa como progreso de la ruta y cada canal se
   interpola linealmente entre los puntos `(x%, y%, rot°, scale%)`, convirtiendo
   X/Y a píxeles según W/H. Tras la subida, `float` añade
   `bob_px*sin(2π·(t-at-dur)/2.4)` y `drift` añade el mismo patrón a `dx` con
   `sway_px`/`sway_period`.

## Ejemplos (plantillas de trayectoria)

Los keyframes se escalan al tamaño del vídeo (X/Y en % de W/H) y el último
punto se mantiene hasta el final, así que los mismos valores sirven para
720p, 1080p o 4K. El 0 de P es el frame hold en `--at`; P=1 es `--at + --dur`.

**Subida clásica con deriva lateral y balanceo** (la del tutorial):

```bash
voxera video levitate IN.mp4 -o OUT.mp4 --at 10 \
  --motion drift --bob 1.2 --sway 1.5 \
  --keyframes "0:0,0;0.5:2,-8;1:4,-15"
```

**Zigzag ascendente** (objeto que sube serpenteando; P define los picos):

```bash
voxera video levitate IN.mp4 -o OUT.mp4 --at 8 --dur 2.0 \
  --subject object --motion static --curve 50 \
  --keyframes "0:0,0;0.25:5,-5;0.5:-5,-10;0.75:5,-15;1:-4,-20"
```

**Ruta circular** (vuelta completa alrededor de la pose original; conviene
`--dur` más largo para que se lea el giro):

```bash
voxera video levitate IN.mp4 -o OUT.mp4 --at 6 --dur 4.0 \
  --subject object --motion static --curve 50 \
  --keyframes "0:0,0;0.25:8,0;0.5:0,-8;0.75:-8,0;1:0,0"
```

**Subida con giro y crecimiento progresivo** (rotación/escale por tramos):

```bash
voxera video levitate IN.mp4 -o OUT.mp4 --at 12 --dur 2.5 \
  --subject person --motion static --curve 62 \
  --keyframes "0:0,0;0.4:0,-6,10,3;0.7:2,-10,20,6;1:3,-14,30,10"
```

**Flotar suspendido con levitón** (sube rápido, se queda meciendo y bajando
lento):

```bash
voxera video levitate IN.mp4 -o OUT.mp4 --at 9 --dur 0.8 \
  --subject object --motion float --bob 1.8 \
  --keyframes "0:0,0;0.6:0,-12;1:1,-13"
```

Regla general: sin `--keyframes` el efecto usa `--lift/--move/--rotate/
--scale`; con ellos, la ruta manda y esos cuatro flags se ignoran. El balanceo
`--bob` y el vaivén `--motion drift --sway` se suman SIEMPRE encima de la
ruta, así que con una ruta circular conviene `--motion static` o `--bob 0`.

## Pitfalls
- El sujeto queda CONGELADO a propósito (frame hold + flotar); para una
  persona que sigue viva desplazada usa `video teleport`, no levitate.
- El plate es un fondo CONGELADO en la zona del sujeto (hereda de teleport).
  Si la cámara tiembla, estabilizar antes (`video stabilize`).
- `--at` debe caer dentro del vídeo; si cae en el último frame no hay nada
  que flotar (error). El recorte sube con redondeo a píxel entero — para
  `--bob` muy pequeño (<1% en 1080p) el balanceo se ve a pasos de 1 px.
- La sombra se pinta SOBRE el plate ANTES de pegar al sujeto, para que el
  recorte quede siempre encima; si no, el borde inferior se oscurece.
- `--keyframes` requiere un punto inicial `0:0,0` para evitar un salto al
  abandonar el frame hold. Los puntos se ordenan por progreso y puede omitirse
  el punto 1: el último se mantiene hasta el final del vídeo.
- Segmentación vacía (sujeto no detectado) → el efecto degenera a "solo
  plate" desde `--at` (aviso en consola, no crash). Para objetos difíciles,
  usar `--plate PLATE --mask MASK`; la máscara debe ser blanca sobre el objeto
  y negra fuera, a la resolución de la entrada (se escala automáticamente).
- Off-by-one del contenedor: `duration*fps` puede declarar N+1 frames —
  tolerancia ±2 con aviso.

## Verification
1. tests: `.venv-ims/Scripts/python.exe -m pytest tests/test_video_levitate.py -q`
   (tests de offset/easing/bob, parser/interpolación de keyframes, máscara
   genérica, sombra, validación, plan, e2e de objeto "sube y su hueco queda
   de fondo" + shadow/bob + trayectoria multipunto + audio remux).

   Fixture
   autouse fuerza diff-borde y sin LaMa → pasan IGUAL en `.venv-ims` y
   `.venv-video`, sin cargar modelos.
2. Verificación numérica: antes de `--at` bit-exacto; en el frame hold el
   sujeto sigue en su sitio; sin keyframes, tras `--at+--dur` el sujeto está en
   `y0 - lift_px + move_y_px`, `x0 + move_x_px`; con keyframes está en
   `y0 + keyframe_y*H/100`, `x0 + keyframe_x*W/100`, con la escala/giro pedidos,
   y la región original es el plate.
3. QA visual: still del frame hold, de la subida y del flotar final. La
   silueta debe leerse como el sujeto suspendido (sin halo, sin fondo viejo
   en el borde), la trayectoria debe ser suave y el hueco inferior debe ser
   fondo continuo.

## Reference Implementation (código núcleo)

La magia está en reutilizar las primitivas ya medidas de `video_teleport`
(plate + máscara + paste con feather) y añadir el frame hold más una
transformación animada del recorte:

```python
import math
from voxera.video_zoom import ease  # misma curva 0-100 que video zoom

def levitation_transform(t: float, at: float, lift_px: float, dur: float,
                         bob_px: float, move_x_px: float = 0,
                         move_y_px: float = 0, rotate_deg: float = 0,
                         scale_pct: float = 0, motion: str = "float",
                         sway_px: float = 0, sway_period: float = 2.4,
                         curve: float = 62.0,
                         easing: str = "smooth") -> tuple[float, float, float, float]:
    """(dy, dx, rotación, escala), todo interpolado desde el frame hold."""
    if t <= at:
        return 0.0, 0.0, 0.0, 1.0
    dt = t - at
    p = min(dt / dur, 1.0)
    e = ease(p, curve, easing)
    dy = -lift_px * e + move_y_px * e
    dx = move_x_px * e
    if motion != "static" and bob_px > 0 and dt > dur:
        dy += bob_px * math.sin(2 * math.pi * (dt - dur) / 2.4)
    if motion == "drift" and sway_px > 0 and dt > dur:
        dx += sway_px * math.sin(2 * math.pi * (dt - dur) / sway_period)
    return dy, dx, rotate_deg * e, 1 + scale_pct / 100 * e
```

Con una ruta multipunto, `parse_keyframes("0:0,0;0.5:4,-8,3,5;1:8,-15,6,10")`
produce los puntos y `levitation_transform(..., keyframes=points,
frame_width=w, frame_height=h)` interpola X/Y/rotación/escala; la curva
`--curve/--easing` controla el progreso global a través de la ruta.

```python
# frame por frame (streaming rawvideo), reusando video_teleport:
#   plate = build_plate(inp)          # o _grab_frame(plate_externo, 0, w, h)
#   frozen = _grab_frame(inp, f0/fps, w, h)
#   mask   = subject_mask(frozen, plate, mode="object")  # o --mask externo
#   si n >= f0:
#       dy, dx, rot, scale = levitation_transform(
#           n/fps, at, lift_px, dur, bob_px,
#           move_x_px, move_y_px, rotate_deg, scale_pct,
#           motion, sway_px, sway_period, curve, easing)
#       out = plate.copy()
#       if shadow: out = render_shadow(out, mask, lift_progress(...), strength, dx, scale)
#       out = paste_transformed_subject(out, frozen, mask, dy, dx, rot, scale)
#   si n < f0: passthrough (bit-exacto)
```

Notas de réplica: la máscara se calcula UNA sola vez (el frame congelado),
no frame a frame — eso es lo que hace el efecto barato (~1 segmentación por
vídeo en vez de N); `paste_transformed_subject` lee del frame ORIGINAL
congelado, nunca del ya compuesto, y transforma solo el parche del bbox;
la sombra usa una elipse con caída cuadrática + gaussian blur, escalada por
`(1 - 0.7*lift_norm)` para encogerse/aclararse al subir y desplazada en X con
la trayectoria.
