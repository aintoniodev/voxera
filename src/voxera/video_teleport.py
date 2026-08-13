"""``voxera video teleport`` — teletransportación: silueta blanca con parpadeo (tutorial @serri.mp4).

Replicación programática del truco del tutorial de @serri.mp4 (Premiere,
vídeo 7645000011205397782, "teletransportación"): la persona "se teletransporta"
dejando un parpadeo de silueta blanca opaca, usado como transición entre tomas
(recurso de los vídeos de Ibai).

Receta del tutorial (medida del vídeo, 2026-08-13):
  1. Grabar con cámara FIJA (trípode) — condición del tutorial: "es importante
     grabar en un tripod, si no, no te va a salir".
  2. Rotoscopiar al sujeto (en Premiere: Selección de Objeto).
  3. Parpadeo: "necesitaremos dos fotogramas. Dejaremos un hueco y recortaremos
     otros dos fotogramas. Este será el momento donde apareceremos de color
     blanco" -> patrón de frames: 2 BLANCO, hueco, 2 BLANCO.
  4. Efecto Tinción con el rango negro a blanco al 100 % -> "seremos solo una
     silueta" (opaco total).
  5. El resultado final del tutorial deja la silueta blanca CONGELADA y al
     sujeto fuera de plano (corte de transición).

Implementación voxera (100 % numpy/scipy, sin Premiere, sin ML de segmentación):
  - Cámara fija => fondo = mediana de N fotogramas muestreados (solo como
    REFERENCIA de máscara); la máscara del sujeto por frame =
    |frame - fondo| > umbral + morfología (close/open).
  - Silueta = máscara del frame actual (roto de cada corte), dilatada,
    rellena de blanco opaco (equivalente a Tinción black->white 100 %); en
    el hold se congela la del último frame blanco.
  - Parpadeo = plan de fases por índice de frame (white/gap/white/hold/gone).
  - ``--remove``: tras el parpadeo el sujeto se elimina por INPAINT ESPACIAL
    (cada píxel de la máscara toma el color del píxel no-máscara más cercano
    del mismo frame — el fondo visible alrededor del sujeto, sin fantasmas
    de ninguna mediana) -> teletransportación completa incluso si en la
    fuente el sujeto sigue en plano. Sin ``--remove``: solo el parpadeo de
    silueta (el "flicker" usado como transición).
  - El audio se remuxea copiado (bit-exacto); los frames fuera de la ventana
    del efecto se pasan sin tocar (bit-exactos en el pipe rawvideo).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.ndimage import binary_closing, binary_dilation, binary_opening, distance_transform_edt

from voxera import video as video_mod
from voxera import video_enhance as ve
from voxera.errors import EnhancementError

DEFAULT_PATTERN = "2-2-2"   # 2 frames blanco, hueco, 2 frames blanco (tutorial)
DEFAULT_HOLD = 0.5          # segundos que la silueta congelada se mantiene tras el parpadeo
DEFAULT_DILATE = 3          # px de dilatación de la silueta (escala 720p)
DEFAULT_THRESHOLD = 18      # diff por canal RGB (0-255) para la máscara de sujeto
DEFAULT_BG_FRAMES = 30      # fotogramas muestreados para el fondo mediano
WHITE = np.array([255, 255, 255], dtype=np.uint8)

PHASES = ("white", "gap", "hold", "gone", "normal")


@dataclass(frozen=True)
class TeleportOptions:
    """Parámetros de la teletransportación. Un solo default sensato por eje.

    Medido del tutorial: patrón 2-2-2 (2 fotogramas blanco, hueco, 2 fotogramas
    blanco), silueta opaca total (Tinción negro->blanco 100 %), cámara fija.
    """

    time: float                      # instante del parpadeo (primer frame blanco), en segundos
    pattern: str = DEFAULT_PATTERN   # "W-G-W" en frames: blanco, hueco, blanco
    remove: bool = False             # tras el parpadeo el sujeto desaparece (inpaint fondo)
    hold: float = DEFAULT_HOLD       # segundos de silueta congelada tras el parpadeo (con --remove)
    dilate: int = DEFAULT_DILATE     # px de dilatación de la silueta (escala 720p)
    threshold: int = DEFAULT_THRESHOLD  # umbral de diff por canal para la máscara
    bg_frames: int = DEFAULT_BG_FRAMES  # fotogramas para el fondo mediano
    crf: int = 18
    audio_bitrate: str = "192k"

    def validate(self) -> None:
        if self.time < 0:
            raise EnhancementError(f"time debe ser >= 0, got {self.time}")
        try:
            parse_pattern(self.pattern)
        except ValueError as exc:
            raise EnhancementError(str(exc)) from exc
        if not 0 <= self.hold <= 10:
            raise EnhancementError(f"hold debe estar en [0, 10]s, got {self.hold}")
        if not 0 <= self.dilate <= 50:
            raise EnhancementError(f"dilate debe estar en [0, 50]px, got {self.dilate}")
        if not 1 <= self.threshold <= 127:
            raise EnhancementError(f"threshold debe estar en [1, 127], got {self.threshold}")
        if not 2 <= self.bg_frames <= 300:
            raise EnhancementError(f"bg_frames debe estar en [2, 300], got {self.bg_frames}")
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


def flicker_schedule(
    f0: int, total: int, pattern: str = DEFAULT_PATTERN,
    hold_frames: int = 0, remove: bool = False,
) -> dict[int, str]:
    """Fase por índice de frame (puro, testable).

    - [f0, f0+w):        white   (silueta blanca)
    - [f0+w, f0+w+g):    gap     (frame original — el sujeto vuelve a verse)
    - [f0+w+g, f0+2w+g): white   (silueta blanca)
    - [f0+2w+g, f0+2w+g+h): hold (silueta congelada; solo con --remove)
    - >= f0+2w+g+h:      gone    (sujeto eliminado; solo con --remove)
    - resto:             normal
    Se trunca al final del vídeo (fases recortadas) y f0 se clampa a [1, total-1].
    """
    w, g, _ = parse_pattern(pattern)
    f0 = min(max(f0, 1), max(total - 1, 1))
    sched: dict[int, str] = {}
    end_white2 = min(f0 + 2 * w + g, total)
    end_hold = min(f0 + 2 * w + g + hold_frames, total)
    for i in range(f0, total):
        if i < f0 + w:
            sched[i] = "white"
        elif i < f0 + w + g:
            sched[i] = "gap"
        elif i < end_white2:
            sched[i] = "white"
        elif remove and i < end_hold:
            sched[i] = "hold"
        elif remove:
            sched[i] = "gone"
        else:
            sched[i] = "normal"
    return sched


def _scale_kernel(k: int, width: int, height: int) -> int:
    """Kernel de morfología escalado a la resolución (base 720p)."""
    base = max(width, height)
    return max(int(round(k * base / 720.0)) | 1, 1)  # impar siempre


def median_background(frames: list[np.ndarray]) -> np.ndarray:
    """Fondo mediano de fotogramas muestreados (cámara fija). uint8 HxWx3.

    Es solo la REFERENCIA para la máscara de sujeto (diff por frame). El
    borrado real del sujeto es espacial (``inpaint_bg``, desde el fondo
    visible a su alrededor) — NO desde este fondo, que con un sujeto casi
    estático queda contaminado por el propio sujeto (el torso ES la
    mediana). Una pasada de exclusión por máscara no lo arregla: contra su
    propio fantasma, la máscara no detecta al sujeto (medido 2026-08-13).
    """
    return np.median(np.stack(frames), axis=0).astype(np.uint8)


def camera_stability(frames: list[np.ndarray], bg: np.ndarray | None = None,
                     threshold: int = DEFAULT_THRESHOLD) -> float:
    """Residuo medio del fondo fuera de la máscara del sujeto (0-255).

    Con cámara fija, todo lo que NO es sujeto debe coincidir con el fondo
    mediano (< ~2). Un valor alto indica cámara en mano (el "fondo" se
    mueve): el fondo mediano y la máscara por diff no serán fiables.
    Medir solo fuera de la máscara evita que el movimiento del propio
    sujeto (talking head) dispare falsos positivos.
    """
    if bg is None or len(frames) < 2:
        return 0.0
    d = 0.0
    cnt = 0
    for fr in frames:
        m = subject_mask(fr, bg, threshold)
        resid = np.abs(fr.astype(np.int16) - bg.astype(np.int16))
        resid = resid[~m]
        if resid.size:
            d += float(resid.mean())
            cnt += 1
    return d / max(cnt, 1)


def _close_radius(mask: np.ndarray, r: int) -> np.ndarray:
    """Cierre morfológico por radio euclídeo: dilatar r, luego erosionar r.

    dilate(A,r) = EDT(~A) <= r;  erode(A,r) = EDT(A) > r.  (EDT(x)[p] =
    distancia de p al píxel más cercano con x=False.)
    """
    if r <= 0:
        return mask
    dil = distance_transform_edt(~mask) <= r
    return distance_transform_edt(dil) > r


def _open_radius(mask: np.ndarray, r: int) -> np.ndarray:
    """Apertura morfológica por radio euclídeo: erosionar r, luego dilatar r."""
    if r <= 0:
        return mask
    er = distance_transform_edt(mask) > r
    return distance_transform_edt(~er) <= r


def subject_mask(frame: np.ndarray, bg: np.ndarray, threshold: int = DEFAULT_THRESHOLD,
                 width: int | None = None, height: int | None = None,
                 light: bool = False) -> np.ndarray:
    """Máscara del sujeto: diff por canal contra el fondo + morfología.

    Completa: close ~11px (rellena huecos del cuerpo) + open ~5px (quita
    ruido aislado), radios escalados a la resolución — para la silueta.
    ``light=True``: solo close radio 3, sin open — para los frames de gone
    (solo necesitan cobertura; la morfología pesada en 1000+ frames tarda
    ~10 min — medido 2026-08-13).
    """
    diff = np.max(np.abs(frame.astype(np.int16) - bg.astype(np.int16)), axis=2)
    m = diff > threshold
    if not m.any():
        return m
    h, w = m.shape
    if light:
        return _close_radius(m, max(_scale_kernel(7, w, h) // 2, 1))
    r_close = _scale_kernel(11, w, h) // 2
    r_open = _scale_kernel(5, w, h) // 2
    m = _close_radius(m, r_close)
    m = _open_radius(m, r_open)
    return m


def composite_silhouette(frame: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Rellena la región de la máscara con blanco opaco (Tinción 100 %)."""
    out = frame.copy()
    out[mask] = WHITE
    return out


def _dilate_radius(mask: np.ndarray, r: int) -> np.ndarray:
    """Dilatación por radio euclídeo en UNA pasada de EDT.

    Sustituye a binary_dilation iterativo (37 iteraciones 3x3 por frame =
    lento en 1000+ frames; medido: render >30 min). El EDT de la máscara
    negada da la distancia al fondo; r = radio.
    """
    if r <= 0:
        return mask
    return distance_transform_edt(~mask) <= r


def inpaint_bg(frame: np.ndarray, mask: np.ndarray, bg: np.ndarray,
               cover: int = 25, margin: int = 12) -> np.ndarray:
    """Elimina al sujeto rellenando con fondo desde fuera de su silueta.

    Tres piezas (cada una medida en la demo real, 2026-08-13):
    1. ``cover``: la región a rellenar es la máscara dilatada ~25px. La
       máscara por diff NO llega al borde real del sujeto (ropa oscura,
       bordes suaves) y el vecino más cercano SIN cover caería en el borde
       de la ropa (relleno oscuro con forma humana).
    2. ``margin``: la fuente del relleno se toma FUERA de la región+cover.
    3. Color: el fondo mediano ``bg`` en la posición fuente, no el frame
       actual (en el frame actual la posición fuente puede tener sombra o
       ropa; en la mediana la pared está limpia y el fantasma del sujeto
       vive solo DENTRO de la región que nunca se muestrea).
    """
    if not mask.any():
        return frame.copy()
    edt_d = distance_transform_edt(~mask)
    m = edt_d <= cover
    src = edt_d <= (cover + margin)
    idx = distance_transform_edt(src, return_distances=False, return_indices=True)
    out = frame.copy()
    out[m] = bg[tuple(idx)][m]
    return out


def _sample_frames(input: Path, n: int) -> list[np.ndarray]:
    """Muestrea n fotogramas uniformes (para fondo mediano + estabilidad).

    Tolerante al borde final: el seek en el último ~0.5 s de un contenedor
    puede devolver vacío; las muestras fallidas se reintentan antes y se
    saltan (hacen falta >= 2 para el fondo mediano).
    """
    probe = ve.probe_video(input)
    w, h = probe["width"], probe["height"]
    dur = probe["duration_s"]
    fps = probe["fps"]
    total = max(int(round(dur * fps)), 1)
    hi = min(max(total - 3, 1), max(int(round((dur - 0.5) * fps)), 1))
    lo = max(int(round(0.3 * fps)), 1)
    if hi <= lo:
        hi = lo + 1
    idx = np.linspace(lo, hi, n).astype(int) if n > 1 else np.array([(lo + hi) // 2])
    frames: list[np.ndarray] = []
    for i in idx:
        for attempt in range(3):
            t = max(i / fps - attempt * 0.5, 0.1)
            proc = subprocess.run(
                [video_mod._tool("ffmpeg"), "-v", "error", "-ss", f"{t:.6f}", "-i", str(input),
                 "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                capture_output=True, timeout=120,
            )
            if len(proc.stdout) == w * h * 3:
                frames.append(np.frombuffer(proc.stdout, dtype=np.uint8).reshape(h, w, 3))
                break
        else:
            print(f"[teleport] AVISO: no se pudo muestrear el fotograma {i} (se omite)")
    if len(frames) < 2:
        raise EnhancementError("no se pudieron muestrear suficientes fotogramas para el fondo")
    return frames


def build_plan(input: str | Path, opts: TeleportOptions) -> str:
    """Plan legible para --dry-run (misma convención que zoom/enhance)."""
    opts.validate()
    inp = Path(input)
    probe = ve.probe_video(inp)
    w, g, w2 = parse_pattern(opts.pattern)
    f0 = max(int(round(opts.time * probe["fps"])), 1)
    total = max(int(round(probe["duration_s"] * probe["fps"])), 1)
    hold_f = int(round(opts.hold * probe["fps"]))
    mode = "teletransportación completa (sujeto eliminado)" if opts.remove else "solo parpadeo de silueta"
    lines = [
        "VOXERA PLAN (video teleport)",
        f"  entrada : {inp} ({probe['width']}x{probe['height']} @{probe['fps']:.2f}fps, "
        f"{probe['duration_s']:.2f}s, {total} frames)",
        f"  salida  : misma resolución/fps que entrada (audio remux copiado)",
        f"  parpadeo: t={opts.time:.2f}s (frame {f0}) — patrón {opts.pattern} "
        f"({w} blanco, {g} hueco, {w2} blanco)",
        f"  silueta : blanco opaco, dilatación {opts.dilate}px, "
        f"umbral diff {opts.threshold}, fondo mediano de {opts.bg_frames} frames (solo referencia de máscara; borrado espacial)",
        f"  modo    : {mode}" + (f", silueta congelada {opts.hold:.2f}s" if opts.remove else ""),
        f"  encoder : libx264 crf {opts.crf} + aac {opts.audio_bitrate} (audio original)",
    ]
    return "\n".join(lines)


def _decode_all(input: Path, w: int, h: int):
    """Pipe de decodificación completa en rgb24 (streaming, sin tocar disco)."""
    return subprocess.Popen(
        [video_mod._tool("ffmpeg"), "-v", "error", "-i", str(input),
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE,
    )


def _encode_video(w: int, h: int, fps: float, crf: int, out: Path):
    """Pipe de codificación rawvideo -> h264 (solo vídeo; audio se remuxea)."""
    return subprocess.Popen(
        [video_mod._tool("ffmpeg"), "-y", "-v", "error",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", f"{fps:.6f}",
         "-i", "-", "-c:v", "libx264", "-crf", str(crf), "-pix_fmt", "yuv420p",
         str(out)],
        stdin=subprocess.PIPE,
    )


def teleport_video(input: str | Path, output: str | Path, opts: TeleportOptions) -> Path:
    """Aplica la teletransportación y devuelve la ruta de salida (verificada).

    Streaming frame a frame (nunca materializa el vídeo completo en RAM):
      1. muestra frames -> fondo mediano + chequeo de cámara fija
      2. decode pipe -> por frame: fase del plan, composición/inpaint -> encode pipe
      3. remux del audio original copiado + verificación determinista
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

    print(f"[teleport] muestreando {opts.bg_frames} frames para el fondo mediano...")
    samples = _sample_frames(inp, opts.bg_frames)
    bg = median_background(samples)
    stab = camera_stability(samples, bg, opts.threshold)
    if stab > 6.0:
        print(f"[teleport] AVISO: cámara NO fija (diff media {stab:.1f}/255). "
              "El tutorial exige trípode; la máscara puede ser basura.")
    elif stab > 2.0:
        print(f"[teleport] AVISO: ligero movimiento de cámara (diff media {stab:.1f}/255).")

    w_pat, g_pat, _ = parse_pattern(opts.pattern)
    hold_f = int(round(opts.hold * fps))
    sched = flicker_schedule(f0, total, opts.pattern, hold_f, opts.remove)
    white_frames = [i for i, ph in sched.items() if ph == "white"]
    print(f"[teleport] parpadeo en frames {white_frames[0]}..{white_frames[-1]} "
          f"(t≈{white_frames[0] / fps:.2f}s), {len(sched) - len([p for p in sched.values() if p == 'normal'])} frames tocados")

    # Máscara de referencia (silueta congelada del hold): la del último frame
    # blanco del parpadeo, dilatada. Durante las fases white la silueta usa la
    # máscara del frame actual (como la roto de cada corte de 2 frames del
    # tutorial — sigue al sujeto en ese instante).
    ref_mask: np.ndarray | None = None
    dilate = max(int(round(opts.dilate * max(w, h) / 720.0)), 0)
    k_dil = np.ones((3, 3), dtype=bool)

    dec = _decode_all(inp, w, h)
    enc = _encode_video(w, h, fps, opts.crf, out)
    frame_size = w * h * 3
    n_frames = 0
    try:
        while True:
            raw = dec.stdout.read(frame_size)
            if not raw or len(raw) < frame_size:
                break
            frame = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3)
            i = n_frames
            phase = sched.get(i, "normal")

            if phase in ("white", "hold"):
                cur = subject_mask(frame, bg, opts.threshold, w, h)
                for _ in range(dilate):
                    cur = binary_dilation(cur, structure=k_dil)
                if opts.remove:
                    if ref_mask is not None:
                        frame = inpaint_bg(frame, cur | ref_mask, bg)
                    else:
                        frame = inpaint_bg(frame, cur, bg)
                frame = composite_silhouette(frame, cur)
                if phase == "white":
                    ref_mask = cur  # congelada: la del último frame blanco
            elif phase == "gone":
                cur = subject_mask(frame, bg, opts.threshold, w, h, light=True)
                if ref_mask is not None:
                    cur = cur | ref_mask  # la silueta (sólida) cubre ropa oscura
                frame = inpaint_bg(frame, cur, bg)
            elif phase == "gap":
                pass  # frame original — el sujeto vuelve a verse (el "hueco")
            # normal: bit-exacto

            enc.stdin.write(frame.tobytes())
            n_frames += 1
    finally:
        try:
            enc.stdin.close()
        except BrokenPipeError:
            pass
        dec.wait(timeout=600)
        enc.wait(timeout=1800)

    if n_frames != total:
        if abs(n_frames - total) > 2:
            raise EnhancementError(
                f"frames procesados {n_frames} != esperados {total} (fuente inconsistente)"
            )
        print(f"[teleport] AVISO: el contenedor declara {total} frames pero el decode "
              f"entrega {n_frames} (off-by-one de contenedor); se usa {n_frames}.")
    if ref_mask is None:
        raise EnhancementError("no se pudo calcular la máscara de referencia (¿f0 fuera de rango?)")

    # Remux del audio original (copiado, bit-exacto) sobre el vídeo re-encodeado.
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

    # Verificación determinista (misma disciplina que zoom/enhance).
    oprobe = ve.probe_video(out)
    if oprobe["width"] != w or oprobe["height"] != h:
        raise EnhancementError(f"salida con resolución inesperada: {oprobe['width']}x{oprobe['height']}")
    if abs(oprobe["duration_s"] - probe["duration_s"]) > 0.25:
        raise EnhancementError(
            f"duración inesperada: {oprobe['duration_s']:.2f}s (esperada ~{probe['duration_s']:.2f}s)"
        )
    return out
