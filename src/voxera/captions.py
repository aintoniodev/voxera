"""``voxera video captions`` — subtítulos/karaoke con ASR word-level (faster-whisper).

Pipeline: ASR word-level → cues (packing greedy con segmentación sintáctica) →
ASS karaoke o estático → burn-in con ffmpeg ``subtitles=`` (libass) en un solo
paso.

Diseño (R1 Theme 3 + Síntesis §7 — scientific-synthesis 2026-08-19):

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

Cambios científicos aplicados (Síntesis §7, ver synthesis-subtitles-captions.md):

- CAMBIO 1 — QA de lectura: ``audit_cues`` valida cps por cue (warn >18,
  fail >20 para español intralingual), duración mínima 0.83 s y out-time
  (+0.15 s tras la última palabra, regla Netflix: 20 frames mín, out +0.5 s).
- CAMBIO 2 — Segmentación sintáctica: reglas negativas (nunca partir
  artículo+nombre, preposición+frase, verbo auxiliar/negación, nombre+apellido)
  y cortes preferidos tras puntuación / antes de conjunciones y preposiciones
  (BBC + Netflix). Con backtrack al último buen corte.
- CAMBIO 2b — Dos líneas en vertical: ``_group_two_lines`` agrupa cues
  medianos en eventos de 2 líneas (Li 2026: en vertical 9:16 las 2 líneas
  capturan más atención que 1, N=211).
- CAMBIO 3 — Primitivo ``hook``: texto de pantalla arriba (≤4 palabras,
  0.8–2.0 s, MAYÚSCULAS, fade), sincronizado a una palabra ancla del
  transcript. Se descarta (con nota) si solapa otro hook o un cue ancho.
- CAMBIO 4 — Variante de español: ``es_variant`` (es-ES / es-LATAM) para
  decimales y hora (Netflix ES); el modo playful NUNCA elimina ¿/¡.
- CAMBIO 5 — A/B de estilo: variante B = ``style="static"`` + highlight
  (baseline ya disponible; el gate de métricas vive en la skill).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
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
ES_VARIANTS = ("es-ES", "es-LATAM")

# --- QA de lectura (Síntesis Theme 1: rango validado 15–20 cps) ------------
QA_WARN_CPS = 18.0           # objetivo español intralingual 16–18
QA_FAIL_CPS = 20.0           # capacidad lectora medida (Szarkowska & Gerber-Morón 2018)
MIN_CUE_DUR = 0.83           # Netflix: mínimo 20 frames por cue (1–2 palabras)
OUT_PAD = 0.15               # out-time tras la última palabra (regla +0.1–0.5 s)
FRAME_GAP = 2.0 / 30.0       # chaining: hueco de 2 frames entre cues

# --- Hooks de texto arriba (Síntesis Theme 5) ------------------------------
HOOK_MIN_DUR = 0.8
HOOK_MAX_DUR = 2.0
HOOK_DEFAULT_DUR = 0.9
HOOK_MAX_WORDS = 4
HOOK_Y_FRAC = 0.14           # 14% desde arriba (bajo la franja de UI)
HOOK_FADE = 80
HOOK_ANCHOR_PAD = 0.1        # el hook aparece 0.1 s tras terminar la palabra ancla
HOOK_WIDE_CUE_CHARS = 30     # un hook no debe convivir con un cue ancho/2 líneas
HOOK_OVERLAP_DROP = 0.35      # solape sustancial (>0.35 s) con un cue ocupado → descartar

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
# Segmentación sintáctica (Síntesis Theme 2 — BBC / Netflix / UNE)
# ---------------------------------------------------------------------------

_PUNCT_BREAK = set(".,!?;:")
_MAX_CHARS_LINE = 34         # voxera: compromiso entre BBC (37) y Netflix (42)
_TWO_LINE_CHARS = 25         # vertical 9:16: ~90% del ancho (BBC)

_ARTICLES = {"el", "la", "los", "las", "un", "una", "unos", "unas"}
_PREPOSITIONS = {
    "a", "ante", "bajo", "cabe", "con", "contra", "de", "desde", "durante",
    "en", "entre", "hacia", "hasta", "mediante", "para", "por", "según",
    "sin", "so", "sobre", "tras", "vía",
}
_CONJUNCTIONS = {
    "y", "e", "o", "u", "ni", "pero", "sino", "aunque", "porque", "que",
    "cuando", "mientras", "si", "como", "pues", "además",
}
_AUX_NEG = {
    # auxiliares haber / estar / ser / ir + negación
    "he", "has", "ha", "hemos", "habéis", "han",
    "había", "habías", "habíamos", "habíais", "habían",
    "habré", "habrás", "habrá", "habremos", "habréis", "habrán",
    "hube", "hubiste", "hubo", "hubimos", "hubisteis", "hubieron",
    "estoy", "estás", "está", "estamos", "estáis", "están",
    "estaba", "estabas", "estábamos", "estabais", "estaban",
    "estaré", "estarás", "estará", "estaremos", "estaréis", "estarán",
    "seré", "serás", "será", "seremos", "seréis", "serán",
    "era", "eras", "éramos", "erais", "eran",
    "fui", "fuiste", "fue", "fuimos", "fuisteis", "fueron",
    "voy", "vas", "va", "vamos", "vais", "van",
    "iba", "ibas", "íbamos", "ibais", "iban",
    "iré", "irás", "irá", "iremos", "iréis", "irán",
    "no", "tampoco", "nunca", "jamás",
}
_DANGLING = _ARTICLES | _PREPOSITIONS | _AUX_NEG


def _norm_token(w: str) -> str:
    """Palabra normalizada (lowercase, sin puntuación trailing) para las reglas."""
    return w.strip().lower().rstrip(".,!?;:")


def _good_break(prev: dict, nxt: dict) -> bool:
    """¿Es buen punto de corte entre ``prev`` y ``nxt``?

    Tras puntuación, antes de conjunciones o antes de preposiciones
    (BBC + Netflix ES: "romper después de puntuación, antes de
    conjunciones y preposiciones").
    """
    if prev["w"][-1] in _PUNCT_BREAK:
        return True
    nt = _norm_token(nxt["w"])
    return nt in _CONJUNCTIONS or nt in _PREPOSITIONS


def _bad_break(prev: dict, nxt: dict) -> bool:
    """¿Es mal punto de corte? Deja una palabra colgante al final de línea.

    Reglas negativas (BBC/Netflix): nunca separar artículo+nombre,
    preposición+frase, verbo auxiliar/negación+verbo, nombre+apellido.
    """
    pt = _norm_token(prev["w"])
    if pt in _DANGLING:
        return True
    pw, nw = prev["w"].strip(), nxt["w"].strip()
    # Heurística ligera de nombre+apellido: dos palabras capitalizadas
    if (len(pw) > 1 and len(nw) > 1
            and pw[0].isupper() and nw[0].isupper()
            and pt not in _CONJUNCTIONS):
        return True
    return False


def words_to_cues(
    words: list[dict],
    max_lines: int = DEFAULT_MAX_LINES,
    chars_per_sec: float = DEFAULT_CHARS_PER_SEC,
) -> list[list[dict]]:
    """Empaqueta palabras en líneas de cues con segmentación sintáctica.

    Reglas:
    - Romper línea cuando la duración exceda ``len(chars) / chars_per_sec`` o
      la línea tenga > ~34 chars.
    - Preferir romper tras puntuación / antes de conjunciones y preposiciones.
    - NUNCA partir artículo+nombre, preposición+frase, auxiliar+verbo,
      nombre+apellido: si el punto de ruptura cae ahí, se retrocede al último
      buen corte de la línea (backtrack).

    Devuelve lista de ``[{w, s, e}, ...]`` por línea.
    """
    if not words:
        return []

    cues: list[list[dict]] = []
    current: list[dict] = []

    def _line_duration(line: list[dict]) -> float:
        if not line:
            return 0.0
        chars = sum(len(w["w"]) for w in line)
        return chars / chars_per_sec if chars_per_sec > 0 else 999.0

    def _break_point() -> int | None:
        """Último buen punto de corte dentro de ``current`` (índice), o None."""
        for i in range(len(current) - 2, -1, -1):
            if _good_break(current[i], current[i + 1]):
                return i
        return None

    for word in words:
        if current:
            gap = word["s"] - current[-1]["e"]
            if gap > 0.5:
                # Pausa real (≥0.5 s): frontera de frase, no de unidad
                # sintáctica (BBC: hueco ≥1 s si hay pausa; Netflix
                # chaining: cerrar solo huecos de 3–11 frames).
                cues.append(current)
                current = []
            else:
                candidate = current + [word]
                duration_ok = (
                    _line_duration(candidate)
                    <= (current[-1]["e"] - current[0]["s"]) + 0.5
                )
                chars_ok = sum(len(w["w"]) for w in candidate) <= _MAX_CHARS_LINE

                if not duration_ok or not chars_ok:
                    if _bad_break(current[-1], word):
                        # No partir una unidad sintáctica: retroceder al
                        # último buen corte de la línea (o aceptar el corte
                        # si no hay).
                        idx = _break_point()
                        if idx is not None:
                            cues.append(current[: idx + 1])
                            current = current[idx + 1:]
                        else:
                            cues.append(current)
                            current = []
                    else:
                        cues.append(current)
                        current = []

        current.append(word)

    if current:
        cues.append(current)

    return cues


def _group_two_lines(
    cues: list[list[dict]],
    chars_per_sec: float,
    max_lines: int,
) -> list[list[list[dict]]]:
    """Agrupa pares de cues consecutivos en eventos de 2 líneas.

    Síntesis Theme 2 (Li 2026, N=211): en vertical 9:16 las 2 líneas capturan
    más atención que 1 (incluso controlando caracteres). Punto dulce: cada
    línea ≤ 25 chars, corte sintácticamente bueno, duración combinada viable.
    Nunca 3 líneas (BBC: máx 3 solo en 9:16; 2 es el óptimo de procesado).

    Devuelve lista de eventos; cada evento es una lista de líneas (1 o 2),
    y cada línea es una lista de palabras.
    """
    if max_lines < 2 or chars_per_sec <= 0:
        return [[c] for c in cues]

    events: list[list[list[dict]]] = []
    i = 0
    while i < len(cues):
        a = cues[i]
        if i + 1 < len(cues) and _good_break(a[-1], cues[i + 1][0]):
            b = cues[i + 1]
            chars_a = sum(len(w["w"]) for w in a)
            chars_b = sum(len(w["w"]) for w in b)
            # Solo frases encadenadas (hueco ≤ 0.5 s entre cues): dos
            # pensamientos separados por una pausa no comparten evento.
            gap = b[0]["s"] - a[-1]["e"]
            if (gap <= 0.5 and chars_a <= _TWO_LINE_CHARS and chars_b <= _TWO_LINE_CHARS
                    and (chars_a + chars_b) <= _TWO_LINE_CHARS * 2):
                span = b[-1]["e"] - a[0]["s"]
                if span > 0 and (chars_a + chars_b) / chars_per_sec <= span + 0.5:
                    events.append([a, b])
                    i += 2
                    continue
        events.append([a])
        i += 1
    return events


# ---------------------------------------------------------------------------
# QA de lectura (Síntesis §7 CAMBIO 1)
# ---------------------------------------------------------------------------

def audit_cues(
    events: list[list[list[dict]]],
    chars_per_sec: float = DEFAULT_CHARS_PER_SEC,
    warn_cps: float = QA_WARN_CPS,
    fail_cps: float = QA_FAIL_CPS,
    min_dur: float = MIN_CUE_DUR,
) -> list[dict]:
    """Auditoría de lectura por evento.

    - cps por cue: warn > 18, fail > 20 (español intralingual; objetivo 16–18).
    - duración mínima por cue: 0.83 s (20 frames, Netflix).
    Devuelve lista de ``{cue, cps, duration, severity, message}``.
    """
    issues: list[dict] = []
    for i, ev in enumerate(events):
        chars = sum(len(w["w"]) for line in ev for w in line)
        start = ev[0][0]["s"]
        end = ev[-1][-1]["e"]
        dur = end - start
        cps = chars / dur if dur > 0 else float("inf")
        if cps > fail_cps:
            issues.append({
                "cue": i, "cps": round(cps, 1), "duration": round(dur, 2),
                "severity": "fail",
                "message": (
                    f"cue {i}: {cps:.1f} cps > {fail_cps:.0f} cps "
                    "(límite de lectura medido)"
                ),
            })
        elif cps > warn_cps:
            issues.append({
                "cue": i, "cps": round(cps, 1), "duration": round(dur, 2),
                "severity": "warn",
                "message": (
                    f"cue {i}: {cps:.1f} cps > {warn_cps:.0f} cps "
                    "(objetivo 16–18 para español)"
                ),
            })
        if dur < min_dur:
            issues.append({
                "cue": i, "cps": round(cps, 1), "duration": round(dur, 2),
                "severity": "warn",
                "message": (
                    f"cue {i}: {dur:.2f}s < {min_dur:.2f}s "
                    "(mínimo de lectura por cue)"
                ),
            })
    return issues


# ---------------------------------------------------------------------------
# Hooks de texto arriba (Síntesis §7 CAMBIO 3)
# ---------------------------------------------------------------------------

def resolve_hooks(
    words: list[dict],
    hooks: list[dict],
    default_dur: float = HOOK_DEFAULT_DUR,
) -> list[dict]:
    """Resuelve hooks ``{text, anchor, dur?}`` a ``{text, start, end, anchor}``.

    El hook aparece 0.1 s después de que termina la palabra ancla
    (``anchor=after``, Síntesis Theme 5: sincronizado al ritmo del audio).
    La duración se clampa a [0.8, 2.0] s.

    Raises ``EnhancementError`` si el texto supera 4 palabras o si la palabra
    ancla no existe en el transcript.
    """
    resolved: list[dict] = []
    index: dict[str, int] = {}
    for i, w in enumerate(words):
        index.setdefault(_norm_token(w["w"]), i)

    for h in hooks:
        text = h["text"].strip()
        n_words = len(text.split())
        if n_words > HOOK_MAX_WORDS:
            raise EnhancementError(
                f"hook '{text}': {n_words} palabras (máx {HOOK_MAX_WORDS}); "
                "el hook debe ser breve (≤4 palabras, Síntesis Theme 5)"
            )
        anchor = _norm_token((h.get("anchor") or "").strip())
        if anchor not in index:
            raise EnhancementError(
                f"hook '{text}': palabra ancla '{anchor}' no está en el "
                "transcript (el hook se sincroniza al ritmo del audio)"
            )
        word = words[index[anchor]]
        start = word["e"] + HOOK_ANCHOR_PAD
        dur = float(h.get("dur") or default_dur)
        dur = min(HOOK_MAX_DUR, max(HOOK_MIN_DUR, dur))
        resolved.append({
            "text": text, "start": start, "end": start + dur, "anchor": anchor,
        })
    return resolved


def place_hooks(
    events: list[list[list[dict]]],
    hooks: list[dict],
    wide_chars: int = HOOK_WIDE_CUE_CHARS,
) -> tuple[list[dict], list[str]]:
    """Coloca los hooks contra los cues; devuelve ``(hooks_ok, notas)``.

    Reglas (Síntesis Theme 5): máximo 1 hook simultáneo; nunca un hook sobre
    un cue ancho/2 líneas (dos regiones de texto simultáneas cuestan; el 62%
    de usuarios encuentra los overlays molestos — Amir et al. 2026).
    Los hooks en conflicto se descartan con una nota (no rompen el burn-in).
    """
    kept: list[dict] = []
    notes: list[str] = []
    for h in hooks:
        if any(not (h["end"] <= k["start"] or h["start"] >= k["end"]) for k in kept):
            notes.append(f"hook '{h['text']}' descartado: solapa con otro hook")
            continue
        for ev in events:
            ev_start = ev[0][0]["s"]
            ev_end = ev[-1][-1]["e"]
            chars = sum(len(w["w"]) for line in ev for w in line)
            # Regla: nunca hook simultáneo a un cue de 2+ líneas abajo
            # (dos regiones de texto activas cuestan — Síntesis Theme 5).
            # El solape se mide en tiempo: un hook que arranca justo al
            # terminar su propio cue (cola de ~0.05 s del out-pad) es válido;
            # un hook encajado en un cue ocupado (>0.35 s) se descarta.
            busy = len(ev) > 1 or chars > wide_chars
            if busy:
                overlap = min(h["end"], ev_end) - max(h["start"], ev_start)
                if overlap > HOOK_OVERLAP_DROP:
                    notes.append(
                        f"hook '{h['text']}' descartado: solapa {overlap:.2f}s un "
                        f"cue de {chars} chars/2 líneas (no mezclar hook con "
                        "diálogo largo)"
                    )
                    break
        else:
            kept.append(h)
    return kept, notes


# ---------------------------------------------------------------------------
# Variante de español (Síntesis §7 CAMBIO 4 — Netflix ES)
# ---------------------------------------------------------------------------

def _to_ampm(m: re.Match) -> str:
    h, mm = int(m.group(1)), m.group(2)
    if h == 0:
        return f"12:{mm} a. m."
    if h < 12:
        return f"{h}:{mm} a. m."
    if h == 12:
        return f"12:{mm} p. m."
    return f"{h - 12}:{mm} p. m."


def _apply_es_variant(text: str, variant: str | None) -> str:
    """Ajustes regionales de español (Netflix ES: "Spanish (Latin America &
    Spain) Timed Text Style Guide").

    - es-ES: decimales con coma ("3,5").
    - es-LATAM: decimales con punto ("3.5") y hora en formato 12h a. m./p. m.
    Nunca toca ¿/¡ — son obligatorios en español y el modo playful los
    conserva (RAE / Netflix ES).
    """
    if not variant:
        return text
    if variant == "es-ES":
        return re.sub(r"(\d)\.(\d)", r"\1,\2", text)
    if variant == "es-LATAM":
        text = re.sub(r"(\d),(\d)", r"\1.\2", text)
        return re.sub(r"(?<!\d)(\d{1,2}):(\d{2})(?![:\d])", _to_ampm, text)
    raise EnhancementError(
        f"es_variant debe ser uno de {ES_VARIANTS}, got {variant!r}"
    )


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


def _build_events(
    words: list[dict],
    max_lines: int,
    chars_per_sec: float,
    two_lines: bool,
) -> list[list[list[dict]]]:
    """Cues → eventos ASS (lista de líneas por evento, 1 o 2 líneas)."""
    cues = words_to_cues(words, max_lines=max_lines, chars_per_sec=chars_per_sec)
    if two_lines:
        return _group_two_lines(cues, chars_per_sec, max_lines)
    return [[c] for c in cues]


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
    es_variant: str | None = None,
    hooks: list[dict] | None = None,
    notes: list | None = None,
    two_lines: bool = True,
) -> str:
    """Genera un documento ASS completo.

    ``style``: ``karaoke`` (\\k por palabra) o ``static`` (fade in/out).
    ``text_style``: ``classic`` (tal cual) o ``playful`` (minúsculas, sin
    puntuación trailing; conserva ? ! ¿ ¡).
    ``highlight``: tupla de palabras a resaltar en naranja.
    ``es_variant``: ``es-ES`` / ``es-LATAM`` (decimales, hora).
    ``hooks``: lista de ``{text, anchor, dur?}`` — texto de pantalla arriba
    (Síntesis Theme 5). Los hooks en conflicto se descartan con una nota
    que se añade a ``notes`` (lista mutable opcional).
    ``two_lines``: agrupar cues medianos en eventos de 2 líneas (default True,
    Li 2026 — punto dulce en vertical).

    Los cues respetan la duración mínima de lectura (0.83 s) y el out-time
    (+0.15 s tras la última palabra), con hueco de 2 frames antes del cue
    siguiente (Netflix Timing Guidelines).
    """
    if style not in STYLES:
        raise EnhancementError(f"style debe ser uno de {STYLES}, got {style!r}")
    if text_style not in TEXT_STYLES:
        raise EnhancementError(f"text_style debe ser uno de {TEXT_STYLES}, got {text_style!r}")
    if es_variant is not None and es_variant not in ES_VARIANTS:
        raise EnhancementError(f"es_variant debe ser uno de {ES_VARIANTS}, got {es_variant!r}")

    events = _build_events(words, max_lines, chars_per_sec, two_lines)
    if not events:
        raise EnhancementError("sin cues para generar ASS")

    margin_l = (1080 - safe_box[0]) // 2
    margin_r = margin_l
    hook_margin_top = round(HOOK_Y_FRAC * 1920)
    hook_font_size = round(font_size * 1.15)

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
        f"Style: Hook,DejaVu Sans Bold,{hook_font_size},"
        "&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        f"-1,0,0,0,100,100,0,0,1,{outline},1,"
        f"8,{margin_l},{margin_r},{hook_margin_top},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    # --- Hooks: resolver + colocar (Síntesis Theme 5) --------------------------
    hook_lines: list[str] = []
    if hooks:
        try:
            resolved = resolve_hooks(words, hooks)
        except EnhancementError as exc:
            if notes is not None:
                notes.append(f"hooks: {exc}")
            resolved = []
        placed, hook_notes = place_hooks(events, resolved)
        if notes is not None:
            notes.extend(hook_notes)
        for h in placed:
            txt = h["text"].upper()
            hook_lines.append(
                f"Dialogue: 2,{_fmt_ass_time(h['start'])},{_fmt_ass_time(h['end'])},"
                f"Hook,,0,0,0,,{{\\an8}}{{\\fad({HOOK_FADE},{HOOK_FADE})}}"
                f"{_escape_ass(txt)}"
            )

    # --- Events -----------------------------------------------------------------
    events_out: list[str] = []
    seen_start: set[float] = set()

    for idx, ev in enumerate(events):
        start_s = ev[0][0]["s"]
        speech_end = ev[-1][-1]["e"]

        # Out-time / duración mínima (Netflix: mín 20 frames, out +0.5 s;
        # voxera: out +0.15 s y hueco de 2 frames antes del siguiente cue).
        end_s = max(speech_end + OUT_PAD, start_s + MIN_CUE_DUR)
        if idx < len(events) - 1:
            nxt_start = events[idx + 1][0][0]["s"]
            end_s = min(end_s, nxt_start - FRAME_GAP)
        if end_s <= start_s:
            end_s = start_s + 0.04  # mínimo 1 frame a 30fps

        key = round(start_s, 3)
        if key in seen_start:
            continue
        seen_start.add(key)

        # --- Texto de cada línea ------------------------------------------------
        text_parts: list[str] = []

        def _highlight_word(ww: str) -> str:
            if highlight_set and ww.lower() in highlight_set:
                return "{\\c&H0000D7FF&}" + _escape_ass(ww) + "{\\c&H00FFFFFF&}"
            return _escape_ass(ww)

        highlight_set = {h.lower() for h in highlight} if highlight else set()

        for line in ev:
            raw_words = [w["w"] for w in line]
            line_text = " ".join(raw_words)

            if text_style == "playful":
                line_text = line_text.lower()
                line_text = re.sub(r"[.,;:]+$", "", line_text)
            line_text = _apply_es_variant(line_text, es_variant)

            if style == "karaoke":
                parts: list[str] = []
                for w in line:
                    cs = max(1, round((w["e"] - w["s"]) * 100))
                    ww = w["w"]
                    if text_style == "playful":
                        ww = ww.lower()
                        ww = re.sub(r"[.,;:]+$", "", ww)
                    ww = _apply_es_variant(ww, es_variant)
                    parts.append(f"{{\\k{cs}}}{_highlight_word(ww)}")
                text_parts.append("".join(parts))
            else:
                text_parts.append(f"{{\\fad(80,80)}}{_highlight_word(line_text)}")

        text_line = "\\N".join(text_parts)

        events_out.append(
            f"Dialogue: 0,{_fmt_ass_time(start_s)},{_fmt_ass_time(end_s)},"
            f"Karaoke,,0,0,0,,{text_line}"
        )

    return header + "\n".join(hook_lines + events_out) + "\n"


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
    es_variant: str | None = None,
    hooks: list[dict] | None = None,
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
    hooks_str = f"{len(hooks)} arriba" if hooks else "ninguno"
    lines = [
        "VOXERA PLAN (video captions)",
        f"  entrada   : {inp} ({probe['width']}x{probe['height']} "
        f"@{probe['fps']:.2f}fps, {probe['duration_s']:.2f}s)",
        f"  palabras  : {words_count}",
        f"  estilo    : {style} / text_style={text_style}",
        f"  fuente    : DejaVu Sans Bold {font_size}px, outline {outline}px",
        f"  línea     : máx {max_lines} líneas, {chars_per_sec:.1f} chars/s, "
        "2 líneas en vertical (punto dulce)",
        f"  es        : {es_variant or '(genérico)'}",
        f"  hooks     : {hooks_str} (≤4 palabras, 0.8–2.0 s, ancla palabra)",
        f"  highlight : {hl_str}",
        f"  QA        : warn >{QA_WARN_CPS:.0f} cps · fail >{QA_FAIL_CPS:.0f} cps · "
        f"mín {MIN_CUE_DUR:.2f}s/cue",
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
    es_variant: str | None = None,
    hooks: list[dict] | None = None,
    strict_qa: bool = False,
    qa: list | None = None,
    ass_only: str | None = None,
    crf: int = 18,
    audio_bitrate: str = "192k",
) -> str:
    """Genera subtítulos en un vídeo.

    Pipeline completa:
    1. Carga palabras (desde JSON o ASR).
    2. Genera ASS (segmentación sintáctica, 2 líneas, hooks, es_variant).
    3. Auditoría QA de lectura (cps por cue, duración mínima); los hallazgos
       se imprimen en stderr y se añaden a ``qa`` (lista mutable opcional).
       Con ``strict_qa=True``, un cue que supere el límite (fail) aborta.
    4. Si ``ass_only`` → escribe ASS y devuelve su ruta (sin burn-in).
    5. Burn-in con ffmpeg ``subtitles=`` (libass).
    6. Verifica duración ± 1 frame.
    7. Limpia ASS temporal (salvo que se pida ``ass_only``).

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
    notes: list[str] = []
    ass_text = build_ass(
        words,
        style=style,
        text_style=text_style,
        font_size=font_size,
        outline=outline,
        max_lines=max_lines,
        chars_per_sec=chars_per_sec,
        highlight=highlight,
        es_variant=es_variant,
        hooks=hooks,
        notes=notes,
    )

    # 3. Auditoría QA de lectura (Síntesis §7 CAMBIO 1)
    events = _build_events(words, max_lines, chars_per_sec, two_lines=True)
    issues = audit_cues(events, chars_per_sec=chars_per_sec)
    for note in notes:
        print(f"QA: {note}", file=sys.stderr)
    for issue in issues:
        print(f"QA: [{issue['severity']}] {issue['message']}", file=sys.stderr)
    if qa is not None:
        qa.extend(issues)
        qa.extend({"note": n} for n in notes)
    if strict_qa and any(i["severity"] == "fail" for i in issues):
        fails = [i["message"] for i in issues if i["severity"] == "fail"]
        raise EnhancementError(
            f"QA estricto: {len(fails)} cue(s) superan el límite de lectura:\n"
            + "\n".join(f"  - {m}" for m in fails)
        )

    # 4. Si ass_only → escribir y devolver
    if ass_only:
        ass_path = Path(ass_only)
        ass_path.parent.mkdir(parents=True, exist_ok=True)
        ass_path.write_text(ass_text, encoding="utf-8")
        return str(ass_path)

    # 5. Escribir ASS temporal al lado del output
    ass_temp = out.parent / (out.stem + ".ass")
    ass_temp.write_text(ass_text, encoding="utf-8")

    try:
        # 6. Burn-in con ffmpeg
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

        # 7. Verificar duración ± tolerancia de re-encode: 1 frame de vídeo +
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
        # 8. Limpiar ASS temporal (salvo que se pida ass_only)
        if ass_temp.exists():
            ass_temp.unlink(missing_ok=True)
