"""``voxera video captions`` — subtítulos/karaoke con ASR word-level (faster-whisper).

Pipeline: ASR word-level → cues (packing greedy) → ASS karaoke o estático →
burn-in con ffmpeg ``subtitles=`` (libass) en un solo paso.

Diseño (R1 Theme 3 + Síntesis §7):

- faster-whisper es la ÚNICA dependencia nueva del módulo; se importa bajo
  demanda para que ``import voxera.captions`` no falle sin el paquete.
- Palabras cuantizadas a la rejilla de frames a 30 fps (``round(t*30)/30``)
  para que cada cue arranque y termine exactamente en un frame.
- ``karaoke``: cada palabra lleva ``\k<cs>`` (cs = duración en centésimas)
  para el efecto de iluminación progresivo de libass.
- ``static``: texto plano con fade in/out (``\fad(80,80)``).
- ``playful``: minúsculas + sin puntuación trailing (conservando ? y !).
- ``highlight``: palabras marcadas en naranja (``\c&H0000D7FF&``).
- ``safe_box`` 900×1160 px en 1080×1920 = zona segura cross-plataforma.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

from voxera.errors import EnhancementError
from voxera import video_enhance as ve

# Windows: torch y ctranslate2 (faster-whisper) empaquetan CADA UNO su copia
# de libiomp5md.dll (Intel OpenMP). Si torch se carga primero, ctranslate2
# aborta con "OMP: Error #15" al inicializar su OpenMP. Es el workaround
# documentado por Intel; debe fijarse ANTES de que el segundo runtime se
# inicialice, por eso va a nivel de módulo (no dentro de la función lazy).
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "base"
DEFAULT_LANG = None          # auto
DEFAULT_FONT_SIZE = 72
DEFAULT_OUTLINE = 3
DEFAULT_MAX_LINES = 3
DEFAULT_CHARS_PER_SEC = 18.0
DEFAULT_MARGIN_V = 380
SAFE_BOX = (900, 1160)      # px en 1080×1920
STYLES = ("karaoke", "static")
TEXT_STYLES = ("classic", "playful")

# ---------------------------------------------------------------------------
# ASR (lazy import)
# ---------------------------------------------------------------------------

def _get_whisper_model(model: str):
    """Devuelve WhisperModel de faster-whisper; ImportError → EnhancementError."""
    try:
        from faster_whisper import WhisperModel  # type: ignore[import-untyped]
    except ImportError:
        raise EnhancementError(
            "faster-whisper no instalado. Instalar con: pip install faster-whisper"
        )
    return WhisperModel(model, device="cpu", compute_type="int8")


def _quantize_frame(t: float, fps: float = 30.0) -> float:
    """Snap temporal a la rejilla de frames: round(t*fps)/fps."""
    return round(t * fps) / fps


def transcribe_words(
    path: str,
    model: str = DEFAULT_MODEL,
    lang: str | None = None,
    vad: bool = True,
) -> dict:
    """Transcribe ``path`` y devuelve ``{"language": ..., "words": [...]}``.

    Cada palabra tiene ``w``, ``s`` (start) y ``e`` (end) cuantizados a 30 fps.
    ``faster_whisper`` se importa bajo demanda — el módulo se puede importar
    sin tener el paquete instalado (solo falla al llamar esta función).

    Raises ``EnhancementError`` si no se detecta voz o si faster-whisper
    no está instalado.
    """
    wm = _get_whisper_model(model)
    segs_gen, info = wm.transcribe(
        path,
        word_timestamps=True,
        vad_filter=vad,
        language=lang or None,
    )
    words: list[dict] = []
    for seg in segs_gen:
        for w in seg.words:
            words.append({
                "w": w.word,
                "s": _quantize_frame(w.start),
                "e": _quantize_frame(w.end),
            })
    if not words:
        raise EnhancementError("sin voz detectable (0 palabras transcritas)")
    return {"language": getattr(info, "language", None), "words": words}


# ---------------------------------------------------------------------------
# Cues (greedy packing)
# ---------------------------------------------------------------------------

_PUNCT_BREAK = set(".,!?;:")


def words_to_cues(
    words: list[dict],
    max_lines: int = DEFAULT_MAX_LINES,
    chars_per_sec: float = DEFAULT_CHARS_PER_SEC,
) -> list[list[dict]]:
    """Empaqueta palabras en líneas de cues.

    Reglas:
    - Romper línea cuando la duración exceda ``len(chars) / chars_per_sec`` o
      la línea tenga > ~34 chars.
    - Preferir romper tras puntuación (inicio de palabra tras .,!?;:).
    - Cada cue es una línea (no se solapan); ``max_lines`` limita las líneas
      por pantalla visible (aquí simplificado: 1 línea por evento ASS).

    Devuelve lista de ``[{w, s, e}, ...]`` por línea.
    """
    if not words:
        return []

    MAX_CHARS_LINE = 34
    cues: list[list[dict]] = []
    current: list[dict] = []

    def _line_duration(line: list[dict]) -> float:
        if not line:
            return 0.0
        chars = sum(len(w["w"]) for w in line)
        return chars / chars_per_sec if chars_per_sec > 0 else 999.0

    for word in words:
        candidate = current + [word]
        # ¿Romper antes de añadir esta palabra?
        if current:
            duration_ok = _line_duration(candidate) <= (current[-1]["e"] - current[0]["s"]) + 0.5
            chars_ok = sum(len(w["w"]) for w in candidate) <= MAX_CHARS_LINE
            # Preferir break tras puntuación
            prev_char = current[-1]["w"][-1] if current else ""
            punct_break = prev_char in _PUNCT_BREAK

            if (not duration_ok or not chars_ok) and current:
                cues.append(current)
                current = []
                # También Limitar max_lines agrupadas
                if max_lines > 0 and len(cues) >= max_lines:
                    # Emitimos y reseteamos — cada cue es un evento independiente
                    pass

        current.append(word)

    if current:
        cues.append(current)

    return cues


# ---------------------------------------------------------------------------
# ASS builder
# ---------------------------------------------------------------------------

def _fmt_ass_time(seconds: float) -> str:
    """Formatea segundos a H:MM:SS.cc (centésimas) para ASS."""
    if seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    cs = int(round((s - int(s)) * 100))
    if cs >= 100:
        cs = 99
    return f"{h}:{m:02d}:{int(s):02d}.{cs:02d}"


def _escape_ass(text: str) -> str:
    """Escape para ASS (newlines → \\N)."""
    return text.replace("\n", "\\N")


def build_ass(
    words: list[dict],
    *,
    style: str = "karaoke",
    text_style: str = "classic",
    font_size: int = DEFAULT_FONT_SIZE,
    outline: int = DEFAULT_OUTLINE,
    max_lines: int = DEFAULT_MAX_LINES,
    chars_per_sec: float = DEFAULT_CHARS_PER_SEC,
    margin_v: int = DEFAULT_MARGIN_V,
    safe_box: tuple = SAFE_BOX,
    highlight: tuple[str, ...] = (),
) -> str:
    """Genera un documento ASS completo.

    ``style``: ``karaoke`` (\\k por palabra) o ``static`` (fade in/out).
    ``text_style``: ``classic`` (tal cual) o ``playful`` (minúsculas, sin puntuación trailing).
    ``highlight``: tupla de palabras a resaltar en naranja.
    """
    if style not in STYLES:
        raise EnhancementError(f"style debe ser uno de {STYLES}, got {style!r}")
    if text_style not in TEXT_STYLES:
        raise EnhancementError(f"text_style debe ser uno de {TEXT_STYLES}, got {text_style!r}")

    cues = words_to_cues(words, max_lines=max_lines, chars_per_sec=chars_per_sec)
    if not cues:
        raise EnhancementError("sin cues para generar ASS")

    margin_l = (1080 - safe_box[0]) // 2
    margin_r = margin_l

    # --- Header ----------------------------------------------------------------
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "WrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n"
        "YCbCr Matrix: None\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Karaoke,DejaVu Sans Bold,{font_size},"
        "&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        f"-1,0,0,0,100,100,0,0,1,{outline},1,"
        f"2,{margin_l},{margin_r},{margin_v},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    # --- Events ---------------------------------------------------------------
    events: list[str] = []
    seen_start: set[float] = set()

    for cue in cues:
        if not cue:
            continue

        start_s = cue[0]["s"]
        end_s = cue[-1]["e"]

        # Evitar eventos con start == end
        if end_s <= start_s:
            end_s = start_s + 0.04  # mínimo 1 frame a 30fps

        # Evitar duplicados exactos
        key = round(start_s, 3)
        if key in seen_start:
            continue
        seen_start.add(key)

        # --- Texto de la línea -------------------------------------------------
        raw_words = [w["w"] for w in cue]
        line_text = " ".join(raw_words)

        if text_style == "playful":
            # minúsculas y quitar puntuación trailing (conservar ? y !)
            line_text = line_text.lower()
            line_text = re.sub(r"[.,;:]+$", "", line_text)

        # --- Highlight ---------------------------------------------------------
        highlight_set = {h.lower() for h in highlight} if highlight else set()

        def _highlight_word(ww: str) -> str:
            if highlight_set and ww.lower() in highlight_set:
                return (
                    "{\\c&H0000D7FF&}" + _escape_ass(ww) + "{\\c&H00FFFFFF&}"
                )
            return _escape_ass(ww)

        # --- Construir texto con tags ------------------------------------------
        if style == "karaoke":
            parts: list[str] = []
            for w in cue:
                cs = max(1, round((w["e"] - w["s"]) * 100))
                ww = w["w"]
                if text_style == "playful":
                    ww = ww.lower()
                    ww = re.sub(r"[.,;:]+$", "", ww)
                highlighted = _highlight_word(ww)
                parts.append(f"{{\\k{cs}}}{highlighted}")
            text_line = "".join(parts)
        else:
            # static con fade
            if text_style == "playful":
                highlighted = _highlight_word(line_text)
            else:
                highlighted = _highlight_word(line_text)
            text_line = f"{{\\fad(80,80)}}{highlighted}"

        start_fmt = _fmt_ass_time(start_s)
        end_fmt = _fmt_ass_time(end_s)
        events.append(
            f"Dialogue: 0,{start_fmt},{end_fmt},Karaoke,,0,0,0,,{text_line}"
        )

    return header + "\n".join(events) + "\n"


# ---------------------------------------------------------------------------
# Path escaping (Windows)
# ---------------------------------------------------------------------------

def _escape_ffmpeg_path(path: str) -> str:
    """Escapa una ruta para el filtro ``subtitles='...'`` de ffmpeg.

    Reemplaza ``\\`` → ``/``, ``:`` → ``\\:``, ``'`` → ``\\'``, y envuelve
    en comillas simples.
    """
    p = path.replace("\\", "/").replace(":", "\\:")
    p = p.replace("'", "\\'")
    return f"'{p}'"


# ---------------------------------------------------------------------------
# Build plan (--dry-run)
# ---------------------------------------------------------------------------

def build_plan(
    input: str,
    *,
    model: str = DEFAULT_MODEL,
    lang: str | None = None,
    style: str = "karaoke",
    text_style: str = "classic",
    font_size: int = DEFAULT_FONT_SIZE,
    outline: int = DEFAULT_OUTLINE,
    max_lines: int = DEFAULT_MAX_LINES,
    chars_per_sec: float = DEFAULT_CHARS_PER_SEC,
    highlight: tuple[str, ...] = (),
    words_json: str | None = None,
    ass_only: str | None = None,
    crf: int = 18,
    audio_bitrate: str = "192k",
) -> str:
    """Plan legible para ``--dry-run`` (misma convención que video_zoom)."""
    inp = Path(input)
    if not inp.exists():
        raise EnhancementError(f"input no existe: {inp}")
    probe = ve.probe_video(inp)
    words_count = "desde JSON" if words_json else f"ASR ({model})"
    hl_str = ", ".join(highlight) if highlight else "(ninguna)"
    ass_action = f"→ {ass_only} (sin burn-in)" if ass_only else "→ burn-in con libass"
    lines = [
        "VOXERA PLAN (video captions)",
        f"  entrada   : {inp} ({probe['width']}x{probe['height']} "
        f"@{probe['fps']:.2f}fps, {probe['duration_s']:.2f}s)",
        f"  palabras  : {words_count}",
        f"  estilo    : {style} / text_style={text_style}",
        f"  fuente    : DejaVu Sans Bold {font_size}px, outline {outline}px",
        f"  línea     : máx {max_lines} líneas, {chars_per_sec:.1f} chars/s",
        f"  highlight : {hl_str}",
        f"  safe box  : {SAFE_BOX[0]}x{SAFE_BOX[1]} px "
        f"(margin_l/r={(1080 - SAFE_BOX[0])//2}, margin_v={DEFAULT_MARGIN_V})",
        f"  salida    : {ass_action}",
        f"  encoder   : libx264 crf {crf} + aac {audio_bitrate}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def captions_video(
    input: str,
    output: str,
    *,
    words_json: str | None = None,
    model: str = DEFAULT_MODEL,
    lang: str | None = None,
    style: str = "karaoke",
    text_style: str = "classic",
    font_size: int = DEFAULT_FONT_SIZE,
    outline: int = DEFAULT_OUTLINE,
    max_lines: int = DEFAULT_MAX_LINES,
    chars_per_sec: float = DEFAULT_CHARS_PER_SEC,
    highlight: tuple[str, ...] = (),
    ass_only: str | None = None,
    crf: int = 18,
    audio_bitrate: str = "192k",
) -> str:
    """Genera subtítulos en un vídeo.

    Pipeline completa:
    1. Carga palabras (desde JSON o ASR).
    2. Genera ASS.
    3. Si ``ass_only`` → escribe ASS y devuelve su ruta (sin burn-in).
    4. Burn-in con ffmpeg ``subtitles=`` (libass).
    5. Verifica duración ± 1 frame.
    6. Limpia ASS temporal (salvo que se pida ``ass_only``).

    Devuelve la ruta del fichero de salida.
    """
    inp = Path(input)
    out = Path(output)
    if not inp.exists():
        raise EnhancementError(f"input no existe: {inp}")
    out.parent.mkdir(parents=True, exist_ok=True)

    # 1. Obtener palabras
    if words_json:
        import json
        wpath = Path(words_json)
        if not wpath.exists():
            raise EnhancementError(f"words_json no existe: {wpath}")
        data = json.loads(wpath.read_text(encoding="utf-8"))
        # Soporta {"words": [...]} o {"segments": [{"words": [...]}]}
        if "words" in data:
            words = data["words"]
        elif "segments" in data:
            words = []
            for seg in data["segments"]:
                words.extend(seg.get("words", []))
        else:
            raise EnhancementError(
                f"words_json formato no reconocido (esperaba 'words' o 'segments'): {wpath}"
            )
    else:
        result = transcribe_words(str(inp), model=model, lang=lang)
        words = result["words"]

    # 2. Generar ASS
    ass_text = build_ass(
        words,
        style=style,
        text_style=text_style,
        font_size=font_size,
        outline=outline,
        max_lines=max_lines,
        chars_per_sec=chars_per_sec,
        highlight=highlight,
    )

    # 3. Si ass_only → escribir y devolver
    if ass_only:
        ass_path = Path(ass_only)
        ass_path.parent.mkdir(parents=True, exist_ok=True)
        ass_path.write_text(ass_text, encoding="utf-8")
        return str(ass_path)

    # 4. Escribir ASS temporal al lado del output
    ass_temp = out.parent / (out.stem + ".ass")
    ass_temp.write_text(ass_text, encoding="utf-8")

    try:
        # 5. Burn-in con ffmpeg
        escaped = _escape_ffmpeg_path(str(ass_temp))
        vf = f"subtitles={escaped}"
        cmd = [
            "ffmpeg", "-y",
            "-i", str(inp),
            "-vf", vf,
            "-c:v", "libx264", "-crf", str(crf),
            "-preset", "medium",
            "-c:a", "aac", "-b:a", audio_bitrate,
            "-shortest",
            str(out),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if proc.returncode != 0:
            raise EnhancementError(
                f"ffmpeg falló (exit {proc.returncode}):\n{proc.stderr[-1000:]}"
            )

        # 6. Verificar duración ± tolerancia de re-encode: 1 frame de vídeo +
        #    granularidad AAC (1024 muestras @48k = 21.3 ms) + redondeo de
        #    contenedor (~1 frame). El burn-in NO cambia la línea de tiempo,
        #    pero el re-encode sí cuantiza la duración del contenedor.
        probe_in = ve.probe_video(inp)
        probe_out = ve.probe_video(out)
        fps_in = probe_in["fps"] or 30.0
        frame_dur = 1.0 / fps_in
        aac_granularity = 1024 / 48000  # 21.3 ms
        tol = frame_dur * 2.0 + aac_granularity
        dur_diff = abs(probe_out["duration_s"] - probe_in["duration_s"])
        if dur_diff > tol:
            raise EnhancementError(
                f"duración de salida ({probe_out['duration_s']:.3f}s) difiere "
                f"de la entrada ({probe_in['duration_s']:.3f}s) en {dur_diff:.3f}s "
                f"(> tolerancia {tol:.3f}s = 2 frames + granularidad AAC)"
            )

        return str(out)
    finally:
        # 7. Limpiar ASS temporal (salvo que se pida ass_only)
        if ass_temp.exists():
            ass_temp.unlink(missing_ok=True)
