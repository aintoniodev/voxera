"""``voxera video magnify`` — lente de aumento circular ("Magnify", sin Premiere).

Replicación del efecto "Magnify" de Adobe Premiere Pro 26.3 (tutorial de
@billycreative_, 2026-08): una lente circular que amplía la zona que hay
debajo, como una lupa al enseñar un paper. Medido en el propio tutorial:
lente circular, radio ~0.35 del ancho del frame, borde nítido, mitad
superior del frame.

La lente se mueve por la escena (decisión del usuario, 2026-08-13):
- ``--motion auto`` (default): los movimientos se disparan con los picos de
  energía de la voz (misma envolvente RMS que el zoom), y si no hay voz,
  barrido automático en celdas (grid) con pausa en cada zona.
- ``--motion scan``: barrido automático (grid en orden de lectura).
- ``--motion voice``: solo con momentos de voz.
- ``--motion static``: lente quieta (el comportamiento original).

Calidad (prioridad del usuario, 2026-08-13): el pipeline trabaja TODO en
YUV — sin conversiones RGB — con la máscara circular aplicada por
``maskedmerge`` (blend lineal por píxel con máscara en luma) y el upscale
del patch con lanczos + unsharp leve opcional. La única pérdida posible es
la del re-encode x264, no la del efecto.

Implementación: 100 % ffmpeg + dos PNG en gris (máscara del disco con pluma
y aro de borde) generados con numpy + zlib. Pipeline:

    split -> crop de una VENTANA (2r + pluma + margen) que sigue a la lente
    (crop x/y animados con 't') -> split -> crop local del área bajo la
    lente (lado 2r/zoom) -> scale lanczos a 2r (+ unsharp) -> overlay del
    patch centrado en la ventana -> maskedmerge(ventana base, patch,
    máscara disco) -> maskedmerge(aro) -> overlay de la ventana sobre el
    original en la posición animada.

Fuera del disco, la ventana contiene exactamente los mismos píxeles que el
base (crop a coordenadas pares, alineado a croma) -> el overlay es
invisible. Sin conversiones de color: calidad máxima.
"""

from __future__ import annotations

import struct
import subprocess
import tempfile
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from voxera import video as video_mod
from voxera import video_enhance as ve
from voxera import video_zoom
from voxera.errors import EnhancementError

DEFAULT_CENTER = (0.5, 0.38)   # mitad superior: zona de contenido (talking-head/paper)
DEFAULT_SIZE = 0.35            # fracción de min(w,h) — medido en el tutorial: r ~ 0.35 del ancho
DEFAULT_ZOOM = 3.0             # 3x: la lente muestra la zona 3 veces más grande
DEFAULT_FEATHER = 0.05         # fracción del radio: pluma del borde (suave pero nítida)
DEFAULT_RING_WIDTH = 0.025     # fracción del radio: grosor del aro de borde
DEFAULT_MOTION = "auto"        # voz si hay, barrido automático si no
DEFAULT_GRID = (2, 2)          # celdas del barrido (orden de lectura)
DEFAULT_HOLD = 2.5             # s de pausa en cada celda (scan / auto sin voz)
DEFAULT_MOVE_DUR = 1.2         # s de transición entre celdas
DEFAULT_MIN_GAP = 3.0          # separación mínima entre momentos de voz
DEFAULT_SHARPEN = 0.5          # unsharp leve tras el upscale (0 = sin)
RING_COLOR = (255, 255, 255)   # aro blanco, como el borde de una lupa
WINDOW_MARGIN = 8              # px extra alrededor del disco (marco de la ventana)

MOTIONS = ("static", "scan", "voice", "auto")


@dataclass(frozen=True)
class MagnifyOptions:
    """Parámetros de la lente de aumento. Un solo default sensato; escapes.

    Medición del tutorial de @billycreative_ (anillo circular detectado por
    Hough + continuidad de borde, 720x1280): lente estática en ~(0.36, 0.29),
    radio ~255 px = 0.35 del ancho, borde nítido (feather pequeño), presente
    varios segundos. El factor de ampliación real no es medible de forma
    fiable (el vídeo está muy editado, sin frame de referencia limpio):
    default 3x, el aspecto típico de "lupa de paper".
    """

    center: tuple[float, float] = DEFAULT_CENTER
    size: float = DEFAULT_SIZE
    zoom: float = DEFAULT_ZOOM
    feather: float = DEFAULT_FEATHER
    ring_width: float = DEFAULT_RING_WIDTH
    motion: str = DEFAULT_MOTION
    grid: tuple[int, int] = DEFAULT_GRID
    hold: float = DEFAULT_HOLD
    move_dur: float = DEFAULT_MOVE_DUR
    min_gap: float = DEFAULT_MIN_GAP
    sharpen: float = DEFAULT_SHARPEN
    start: float | None = None
    end: float | None = None
    crf: int = 18
    audio_bitrate: str = "192k"

    def validate(self) -> None:
        ax, ay = self.center
        if not (0 <= ax <= 1 and 0 <= ay <= 1):
            raise EnhancementError(f"center debe estar en [0,1]x[0,1], got {self.center}")
        if not 0.02 <= self.size <= 0.5:
            raise EnhancementError(f"size debe estar en [0.02, 0.5] (fracción de min(w,h)), got {self.size}")
        if not 1.05 <= self.zoom <= 20:
            raise EnhancementError(f"zoom debe estar en (1, 20], got {self.zoom}")
        if not 0 <= self.feather <= 0.5:
            raise EnhancementError(f"feather debe estar en [0, 0.5] (fracción del radio), got {self.feather}")
        if not 0 <= self.ring_width <= 0.3:
            raise EnhancementError(f"ring_width debe estar en [0, 0.3], got {self.ring_width}")
        if self.motion not in MOTIONS:
            raise EnhancementError(f"motion debe ser uno de {MOTIONS}, got {self.motion!r}")
        cols, rows = self.grid
        if not (1 <= cols <= 3 and 1 <= rows <= 3 and cols * rows <= 6):
            raise EnhancementError(f"grid debe ser COLSxROWS con 1-3 y máx 6 celdas, got {self.grid}")
        if not 0.2 <= self.hold <= 20:
            raise EnhancementError(f"hold debe estar en [0.2, 20]s, got {self.hold}")
        if not 0.2 <= self.move_dur <= 8:
            raise EnhancementError(f"move_dur debe estar en [0.2, 8]s, got {self.move_dur}")
        if not 0.5 <= self.min_gap <= 15:
            raise EnhancementError(f"min_gap debe estar en [0.5, 15]s, got {self.min_gap}")
        if not 0 <= self.sharpen <= 2:
            raise EnhancementError(f"sharpen debe estar en [0, 2], got {self.sharpen}")
        if not 0 < self.crf <= 51:
            raise EnhancementError(f"crf debe estar en (0, 51], got {self.crf}")
        if self.start is not None and self.end is not None and self.end <= self.start:
            raise EnhancementError(f"end ({self.end}) debe ser > start ({self.start})")


def lens_geometry(width: int, height: int, opts: MagnifyOptions) -> dict:
    """Geometría de la lente en píxeles: radio, ventana, lado del crop y
    zoom efectivo tras redondeos. El centro de la lente puede moverse dentro
    de [r, w-r] x [r, h-r] (el disco siempre dentro del frame)."""
    opts.validate()
    radius = int(round(opts.size * min(width, height)))
    radius = max(radius, 4)
    feather_px = opts.feather * radius
    win = int(2 * radius + 2 * feather_px + WINDOW_MARGIN)
    win = max(win // 2 * 2, 2 * radius)  # par y >= disco
    if win >= min(width, height):
        raise EnhancementError(
            f"lente demasiado grande para {width}x{height}: ventana {win}px "
            f"(reduzca --size; default {DEFAULT_SIZE:g} necesita ~{0.7 + 2 * DEFAULT_FEATHER:.2f} "
            f"de min(w,h))"
        )
    crop = max(_even(int(2.0 * radius / opts.zoom)), 4)
    zoom_eff = 2.0 * radius / crop
    return {
        "radius": radius,
        "win": win,
        "crop": crop,
        "zoom_eff": zoom_eff,
        "feather_px": feather_px,
        "ring_px": max(1.0, opts.ring_width * radius),
    }


def waypoint_plan(opts: MagnifyOptions, width: int, height: int,
                  duration: float, moments: list[float] | None = None) -> list[tuple]:
    """Plan de movimiento: lista de (T_i, D_i, objetivo) — la lente parte de
    la celda anterior y llega al objetivo durante [T_i, T_i + D_i].

    - static: un solo punto (el centro elegido), sin movimiento.
    - scan: celdas del grid en orden de lectura, pausa ``hold`` en cada una
      y transición de ``move_dur``.
    - voice: la transición i-ésima arranca en el momento de voz i-ésimo
      (picos de energía). Con menos momentos que celdas, visita las
      primeras; con más, se quedan sin usar.
    - auto: voice si hay momentos, scan si no.
    """
    opts.validate()
    g = lens_geometry(width, height, opts)
    r, win = g["radius"], g["win"]
    if opts.motion == "static":
        ax, ay = opts.center
        cx = min(max(ax * width, r), width - r)
        cy = min(max(ay * height, r), height - r)
        return [(0.0, 0.0, (cx, cy))]

    cols, rows = opts.grid
    cells = []
    for iy in range(rows):
        for ix in range(cols):
            fx, fy = (ix + 0.5) / cols, (iy + 0.5) / rows
            cx = min(max(fx * width, r), width - r)
            cy = min(max(fy * height, r), height - r)
            cells.append((cx, cy))
    # El plan incluye el punto de partida (celda 0) como primer elemento:
    # plan[0] = (0, 0, P0), y cada segmento i>0 mueve de plan[i-1] a plan[i].
    plan = [(0.0, 0.0, cells[0])]

    if opts.motion == "scan" or not moments:
        t = 0.0
        for i in range(len(cells) - 1):
            plan.append((t, opts.move_dur, cells[i + 1]))
            t += opts.move_dur + opts.hold
        return plan

    # voice (y auto con voz): un movimiento por momento, en orden de celdas
    n = min(len(cells) - 1, len(moments))
    for i in range(n):
        t = min(max(moments[i], 0.0), max(duration - opts.move_dur, 0.0))
        plan.append((t, opts.move_dur, cells[i + 1]))
    return plan


def _even(x: int) -> int:
    return int(x) // 2 * 2


def _fmt(x: float) -> str:
    return f"{x:.6f}"


def _clamp01_expr(x: str) -> str:
    return f"(min(max({x},0),1))"


def _ease_expr(p: str, curve: float = 62.0) -> str:
    """S-curva (misma convención que el zoom): p^a/(p^a+(1-p)^a)."""
    a = _fmt(1 + curve / 25)
    return f"(pow({p},{a})/(pow({p},{a})+pow(1-{p},{a})))"


def _axis_expr(plan: list, axis: int, limit: int, win: int, tvar: str = "t") -> str:
    """Expresión ffmpeg de la posición del borde de la ventana en un eje
    (crop x/y y overlay x/y usan la MISMA expresión; 't' coincide porque
    ambos filtros reciben el mismo frame). Redondeo a par (2*floor(v/2))
    para mantener la alineación de croma 4:2:0 de la ventana con el base."""
    inner = _center_expr(plan, axis, tvar)
    return f"(min(max(2*floor((({inner})-{_fmt(win / 2)})/2),0),{_even(limit - win)}))"


def _center_expr(plan: list, axis: int, tvar: str = "t") -> str:
    """Expresión de la posición del centro de la lente (px) con ifs anidados:
    if(t < S0, P0, if(t < E0, ease(P0->P1), if(t < S1, P1, if(t < E1, ... Pn))))"""
    expr = f"{_fmt(plan[-1][2][axis])}"  # objetivo final
    for i in range(len(plan) - 1, -1, -1):
        t_i, d_i, target = plan[i]
        start = _fmt(t_i)
        end = _fmt(t_i + d_i)
        if i == 0:
            origin = plan[0][2]
        else:
            origin = plan[i - 1][2]
        p = _clamp01_expr(f"({tvar}-{start})/{_fmt(max(d_i, 0.001))}")
        ease = _ease_expr(p)
        moved = f"({_fmt(origin[axis])}+({_fmt(target[axis])}-{_fmt(origin[axis])})*{ease})"
        expr = f"(if(lt({tvar},{start}),{_fmt(origin[axis])},if(lt({tvar},{end}),{moved},{expr})))"
    return expr


def _write_png_gray(path: Path, gray: np.ndarray) -> Path:
    """PNG gris 8-bit mínimo (numpy + zlib; sin dependencias nuevas)."""
    h, w = gray.shape

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    raw = b"".join(b"\x00" + gray[y].tobytes() for y in range(h))
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)
    return path


def build_lens_masks(radius: int, feather: float, ring_width: float, win: int,
                     out_dir: str | Path) -> tuple[Path, Path]:
    """Genera la máscara del disco (pluma) y el aro de borde como PNG gris.

    - disc.png: 255 dentro del disco, caída lineal en la pluma, 0 fuera.
    - ring.png: aro blanco (255) sobre negro, ancho ring_width, ~1 px de
      antialias. Se aplican con maskedmerge (blend lineal por luma) — el
      pipeline nunca sale de YUV.
    """
    y, x = np.mgrid[0:win, 0:win]
    d = np.hypot(x - win / 2 + 0.5, y - win / 2 + 0.5)
    f = max(feather * radius, 0.01)
    a_disc = np.clip((radius - d) / f, 0.0, 1.0)
    disc = (a_disc * 255).astype(np.uint8)
    w = max(ring_width * radius, 0.5)
    a_ring = np.clip(np.minimum(1.0, w / 2 + 1.0 - np.abs(d - radius)), 0.0, 1.0)
    ring = (a_ring * 255).astype(np.uint8)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    return (
        _write_png_gray(out_dir / "lens_disc.png", disc),
        _write_png_gray(out_dir / "lens_ring.png", ring),
    )


def build_magnify_filter(width: int, height: int, opts: MagnifyOptions,
                         duration: float, moments: list[float] | None = None,
                         fps: float = 30.0) -> str:
    """Cadena de filtros ffmpeg para la lente de aumento móvil (todo YUV).

    Entradas esperadas: [0] vídeo, [1] disco (PNG gris), [2] aro (PNG gris).
    La ventana sigue a la lente con crop/overlay animados por 't'; el resto
    de operaciones son locales a la ventana (máscaras estáticas). Fuera del
    disco el frame pasa intacto.
    """
    opts.validate()
    g = lens_geometry(width, height, opts)
    r, win, crop, feather_px = g["radius"], g["win"], g["crop"], g["feather_px"]
    plan = waypoint_plan(opts, width, height, duration, moments)
    # Tras -ss (decode-seek de salida) 't' NO se reinicia a 0 (medido en
    # ffmpeg 7.1): el tiempo del filtro queda offseteado por opts.start.
    tvar = f"(t-{_fmt(opts.start or 0.0)})"
    x_expr = _axis_expr(plan, 0, width, win, tvar)
    y_expr = _axis_expr(plan, 1, height, win, tvar)
    # crop y overlay usan la MISMA posición; 't' coincide (mismo frame).
    dur = max(duration, 0.001)
    ploc = (win - 2 * r) // 2            # patch centrado en la ventana
    cloc = (win - crop) / 2.0            # crop local centrado en la ventana
    sharp = ""
    if opts.sharpen > 0:
        sharp = f",unsharp=5:5:{_fmt(opts.sharpen)}:5:5:0.0"
    return (
        f"[0:v]split=2[bg][src];"
        f"[src]crop={win}:{win}:x='{x_expr}':y='{y_expr}'[wn];"
        f"[wn]split=3[wb][wm][wq];"
        f"[wm]crop={crop}:{crop}:{_fmt(cloc)}:{_fmt(cloc)},"
        f"scale={2 * r}:{2 * r}:flags=lanczos,setsar=1{sharp}[pch];"
        f"[1:v]format=yuv420p[dsc];"
        f"[2:v]format=yuv420p[rgm];"
        f"[wb][pch]overlay=x={ploc}:y={ploc}[pps];"
        f"[wq][pps][dsc]maskedmerge[mgd];"
        f"color=c=white:s={win}x{win}:r={_fmt(max(fps, 1))}:d={_fmt(dur)}[wht];"
        f"[mgd][wht][rgm]maskedmerge[fin];"
        f"[bg][fin]overlay=x='{x_expr}':y='{y_expr}',format=yuv420p[vout]"
    )


def _segment_duration(probe: dict, opts: MagnifyOptions) -> float:
    start = opts.start if opts.start is not None else 0.0
    end = opts.end if opts.end is not None else probe["duration_s"]
    return max(end - start, 0.001)


def _voice_moments(inp: Path, opts: MagnifyOptions, n_cells: int) -> list[float] | None:
    """Momentos de voz para voice/auto; None si no hay voz (-> scan).

    La detección extrae el audio del clip COMPLETO, así que los momentos son
    tiempos absolutos; el plan usa tiempos relativos al segmento -> se
    desplazan por opts.start y se descartan los que quedan fuera."""
    if opts.motion not in ("voice", "auto"):
        return None
    try:
        moments = video_zoom.detect_emphasis_moments(
            inp, max_pulses=min(max(n_cells - 1, 1), 8), min_gap=opts.min_gap
        )
    except EnhancementError:
        if opts.motion == "voice":
            raise EnhancementError(
                "motion=voice: no se detectaron momentos de voz en el audio "
                "(pruebe --motion auto o scan)"
            ) from None
        return None
    off = opts.start or 0.0
    rel = [m - off for m in moments]
    dur = (opts.end if opts.end is not None else float("inf")) - off
    return [m for m in rel if -0.5 <= m <= dur - 0.5]


def build_plan(input: str | Path, opts: MagnifyOptions) -> str:
    """Plan legible para --dry-run (misma convención que zoom/enhance)."""
    opts.validate()
    inp = Path(input)
    probe = ve.probe_video(inp)
    seg_dur = _segment_duration(probe, opts)
    g = lens_geometry(probe["width"], probe["height"], opts)
    cols, rows = opts.grid
    moments = _voice_moments(inp, opts, cols * rows)
    plan = waypoint_plan(opts, probe["width"], probe["height"], seg_dur, moments)
    vf = build_magnify_filter(probe["width"], probe["height"], opts,
                              seg_dur, moments=moments, fps=probe["fps"])
    motion_label = {
        "static": "estática",
        "scan": f"barrido {cols}x{rows} (pausa {opts.hold:g}s, transición {opts.move_dur:g}s)",
        "voice": f"voz ({len(moments) if moments else 0} momentos -> {len(plan)} movimientos)",
        "auto": f"auto: {'voz' if moments else 'barrido'} "
                f"({len(moments) if moments else cols * rows} zonas)",
    }[opts.motion if not (opts.motion == "auto" and moments) else "voice"]
    if opts.motion == "auto" and not moments:
        motion_label = f"auto: barrido {cols}x{rows} (sin voz detectada; pausa {opts.hold:g}s)"
    ax, ay = opts.center
    lines = [
        "VOXERA PLAN (video magnify)",
        f"  entrada : {inp} ({probe['width']}x{probe['height']} @{probe['fps']:.2f}fps, "
        f"{probe['duration_s']:.2f}s)",
        f"  salida  : misma resolución que la entrada",
        f"  lente   : r={g['radius']}px  zoom={g['zoom_eff']:.2f}x  "
        f"pluma={g['feather_px']:.1f}px  aro={g['ring_px']:.1f}px  "
        f"sharpen={opts.sharpen:g}",
        f"  motion  : {motion_label}",
        f"  rango   : {opts.start if opts.start is not None else 0:.2f}s .. "
        f"{opts.end if opts.end is not None else probe['duration_s']:.2f}s "
        f"({seg_dur:.2f}s)",
        f"  encoder : libx264 crf {opts.crf} + aac {opts.audio_bitrate} "
        f"(audio original, sin masterizar)",
        f"  filtro  : {vf}",
    ]
    return "\n".join(lines)


def magnify_video(input: str | Path, output: str | Path, opts: MagnifyOptions) -> Path:
    """Aplica la lente de aumento (estática o móvil) y devuelve la ruta
    verificada."""
    opts.validate()
    inp = Path(input)
    out = Path(output)
    if not inp.exists():
        raise EnhancementError(f"input no existe: {inp}")
    out.parent.mkdir(parents=True, exist_ok=True)

    probe = ve.probe_video(inp)
    seg_dur = _segment_duration(probe, opts)
    g = lens_geometry(probe["width"], probe["height"], opts)
    cols, rows = opts.grid
    moments = _voice_moments(inp, opts, cols * rows)
    if moments:
        print(
            "[magnify] momentos de voz: " + ", ".join(f"{m:.2f}s" for m in moments)
        )
    vf = build_magnify_filter(probe["width"], probe["height"], opts,
                              seg_dur, moments=moments, fps=probe["fps"])
    # PNGs de máscara/aro en un dir temporal (no ensuciar la carpeta de salida).
    with tempfile.TemporaryDirectory(prefix="voxera-magnify-") as tmp:
        disc_png, ring_png = build_lens_masks(g["radius"], opts.feather,
                                              opts.ring_width, g["win"], tmp)
        return _encode(inp, out, probe, seg_dur, vf, disc_png, ring_png, opts)


def _encode(inp: Path, out: Path, probe: dict, seg_dur: float, vf: str,
            disc_png: Path, ring_png: Path, opts: MagnifyOptions) -> Path:
    cmd = [video_mod._tool("ffmpeg"), "-y", "-v", "error"]
    cmd += ["-i", str(inp)]
    cmd += ["-loop", "1", "-framerate", f"{probe['fps']:.6f}",
            "-t", f"{seg_dur:.6f}", "-i", str(disc_png)]
    cmd += ["-loop", "1", "-framerate", f"{probe['fps']:.6f}",
            "-t", f"{seg_dur:.6f}", "-i", str(ring_png)]
    cmd += ["-filter_complex", vf, "-map", "[vout]"]
    cmd += ["-c:v", "libx264", "-crf", str(opts.crf), "-pix_fmt", "yuv420p"]
    if opts.start is not None:
        cmd += ["-ss", f"{opts.start:.6f}"]  # después de -i: decode-seek exacto
    if opts.end is not None:
        cmd += ["-to", f"{opts.end:.6f}"]
    if probe["has_audio"]:
        cmd += ["-c:a", "aac", "-b:a", opts.audio_bitrate, "-shortest"]
    else:
        cmd += ["-an"]
    cmd += [str(out)]

    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=7200)
    except subprocess.CalledProcessError as exc:
        raise EnhancementError(
            f"ffmpeg falló: {exc.stderr.decode(errors='replace')[-800:]}"
        ) from exc

    # Verificación determinista (misma disciplina que zoom/enhance).
    oprobe = ve.probe_video(out)
    if oprobe["width"] != probe["width"] or oprobe["height"] != probe["height"]:
        raise EnhancementError(
            f"salida con resolución inesperada: {oprobe['width']}x{oprobe['height']}"
        )
    if abs(oprobe["duration_s"] - seg_dur) > 0.25:
        raise EnhancementError(
            f"duración inesperada: {oprobe['duration_s']:.2f}s (esperada ~{seg_dur:.2f}s)"
        )
    return out
