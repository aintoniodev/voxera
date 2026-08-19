"""``voxera autopilot`` — edit-spec planner + executor + A/B harness.

Pipeline raw→short: un LLM o un conjunto de reglas deterministas planifica
un edit-spec JSON (contrato declarativo), el executor compone las APIs de
los módulos existentes de voxera, y un harness A/B produce ambas variantes
con un checklist de publicación.

El agente **planifica, nunca ejecuta directamente** — cada decisión queda
registrada en el spec y es verificable contra la QA del manifest.

Design rules (síntesis §7):
  - LLM plans, never executes.
  - Captions are always-on (mute 38–52%).
  - Transcribe AFTER cuts (caption times match final timeline).
  - Validate specs before execution.
  - Failure isolation in A/B harness (one variant failing ≠ crash).
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from voxera.errors import EnhancementError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SPEC_VERSION = 1

# cmd → {allowed_keys: set[str], validators: {key: validator_fn}}
# validators return True/False; missing key = optional (not required)
def _is_num(v: object) -> bool:
    return isinstance(v, (int, float))

def _is_str(v: object) -> bool:
    return isinstance(v, str)

def _is_bool(v: object) -> bool:
    return isinstance(v, bool)

def _is_xy(v: object) -> bool:
    """[x, y] numeric pair."""
    return isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v)

def _is_str_in(choices: tuple[str, ...]):
    def _check(v: object) -> bool:
        return isinstance(v, str) and v in choices
    return _check

def _is_num_range(lo: float | None, hi: float | None):
    def _check(v: object) -> bool:
        if not isinstance(v, (int, float)):
            return False
        if lo is not None and v < lo:
            return False
        if hi is not None and v > hi:
            return False
        return True
    return _check

ALLOWED_CMDS: dict[str, dict[str, object]] = {
    "video zoom": {
        "pct": _is_num,
        "curve": _is_num,
        "easing": _is_str_in(("smooth", "out", "in", "linear")),
        "direction": _is_str_in(("grow", "shrink", "pulse")),
        "anchor": _is_xy,
        "start": _is_num,
        "end": _is_num,
        "hold": _is_num,
        "pulse_dur": _is_num,
        "max_pulses": _is_num,
    },
    "video magnify": {
        "center": _is_xy,
        "radius": _is_num,
        "grid": _is_str,
        "hold": _is_num,
        "move_dur": _is_num,
        "sharpen": _is_num,
        "start": _is_num,
        "end": _is_num,
    },
    "video teleport": {
        "start": _is_num,
        "end": _is_num,
        "shift": _is_str,
    },
    "video stabilize": {
        "smoothing": _is_num,
        "max_shift": _is_num,
    },
    "audio lowpass": {
        "cutoff": _is_num,
        "transition": _is_num,
        "start": _is_num,
        "end": _is_num,
    },
    "audio transition": {
        "from": _is_str,
        "to": _is_str,
        "at": _is_num,
        "dur": _is_num,
        "mood": _is_str,
        "key": _is_str,
        "curve": _is_num,
        "easing": _is_str,
        "gain": _is_num,
    },
    "audio riser": {
        "mood": _is_str,
        "hit": _is_num,
        "dur": _is_num,
        "gain": _is_num,
        "seed": _is_num,
        "tail": _is_num,
    },
    "audio melody": {
        "mood": _is_str,
        "from": _is_str,
        "to": _is_str,
        "duck": _is_num,
        "seed": _is_num,
        "gain": _is_num,
        "bars": _is_num,
        "start": _is_num,
    },
}

VALID_LEVELS = ("light", "medium", "aggressive")
VALID_ASPECTS = ("9:16", "keep")

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_edit_spec(spec: dict) -> dict:
    """Valida y normaliza un edit-spec JSON. Devuelve el spec normalizado.

    Raises EnhancementError con mensaje preciso si:
      - version != 1
      - cmd desconocido
      - key de arg desconocida
      - valores malformados
      - target.max_dur <= 0
      - keep_spans con entries no [s,e] con s < e
      - hook type != "zoom-grow"
      - captions falta key requerida
    """
    if not isinstance(spec, dict):
        raise EnhancementError("edit-spec debe ser un dict")

    # version
    v = spec.get("version")
    if v != SPEC_VERSION:
        raise EnhancementError(
            f"edit-spec version debe ser {SPEC_VERSION}, got {v}"
        )

    # source
    source = spec.get("source")
    if not isinstance(source, str) or not source:
        raise EnhancementError("edit-spec 'source' debe ser str no vacío")

    # level
    level = spec.get("level", "medium")
    if level not in VALID_LEVELS:
        raise EnhancementError(
            f"edit-spec 'level' debe ser uno de {VALID_LEVELS}, got {level!r}"
        )
    spec["level"] = level

    # keep_spans
    keep_spans = spec.get("keep_spans", [])
    if not isinstance(keep_spans, list):
        raise EnhancementError("edit-spec 'keep_spans' debe ser una lista")
    for i, span in enumerate(keep_spans):
        if (
            not isinstance(span, list)
            or len(span) != 2
            or not all(isinstance(x, (int, float)) for x in span)
        ):
            raise EnhancementError(
                f"edit-spec keep_spans[{i}] debe ser [s, e] numéricos, got {span}"
            )
        if span[0] >= span[1]:
            raise EnhancementError(
                f"edit-spec keep_spans[{i}]: s ({span[0]}) debe ser < e ({span[1]})"
            )
    spec["keep_spans"] = keep_spans

    # hook
    hook = spec.get("hook")
    if hook is not None:
        if not isinstance(hook, dict):
            raise EnhancementError("edit-spec 'hook' debe ser dict o null")
        hook_type = hook.get("type")
        if hook_type != "zoom-grow":
            raise EnhancementError(
                f"edit-spec hook type debe ser 'zoom-grow', got {hook_type!r}"
            )
        for key in ("at", "pct", "curve"):
            if key not in hook:
                raise EnhancementError(f"edit-spec hook falta '{key}'")
        if not _is_num(hook.get("at")):
            raise EnhancementError(f"edit-spec hook.at debe ser numérico")
        if not _is_num(hook.get("pct")):
            raise EnhancementError(f"edit-spec hook.pct debe ser numérico")
        if not _is_num(hook.get("curve")):
            raise EnhancementError(f"edit-spec hook.curve debe ser numérico")
        anchor = hook.get("anchor")
        if anchor is not None and not _is_xy(anchor):
            raise EnhancementError("edit-spec hook.anchor debe ser [x, y] numérico")
    spec["hook"] = hook

    # effects
    effects = spec.get("effects", [])
    if not isinstance(effects, list):
        raise EnhancementError("edit-spec 'effects' debe ser una lista")
    for i, eff in enumerate(effects):
        if not isinstance(eff, dict):
            raise EnhancementError(f"edit-spec effects[{i}] debe ser dict")
        cmd = eff.get("cmd")
        if cmd not in ALLOWED_CMDS:
            raise EnhancementError(
                f"edit-spec effects[{i}] cmd desconocido: {cmd!r}. "
                f"cmds válidos: {sorted(ALLOWED_CMDS)}"
            )
        allowed_keys = ALLOWED_CMDS[cmd]
        args = eff.get("args", {})
        if not isinstance(args, dict):
            raise EnhancementError(f"edit-spec effects[{i}] args debe ser dict")
        for arg_key in args:
            if arg_key not in allowed_keys:
                raise EnhancementError(
                    f"edit-spec effects[{i}] arg key desconocida: {arg_key!r}. "
                    f"Keys válidas para '{cmd}': {sorted(allowed_keys)}"
                )
        # Validate arg values
        for arg_key, arg_val in args.items():
            validator = allowed_keys[arg_key]
            if not validator(arg_val):
                raise EnhancementError(
                    f"edit-spec effects[{i}].args.{arg_key} valor inválido: {arg_val!r}"
                )
    spec["effects"] = effects

    # captions
    captions = spec.get("captions")
    if captions is not None:
        if not isinstance(captions, dict):
            raise EnhancementError("edit-spec 'captions' debe ser dict o null")
        for key in ("enabled", "style", "text_style"):
            if key not in captions:
                raise EnhancementError(f"edit-spec captions falta '{key}'")
        if not _is_bool(captions["enabled"]):
            raise EnhancementError("edit-spec captions.enabled debe ser bool")
        if captions["style"] not in ("karaoke", "static"):
            raise EnhancementError(
                f"edit-spec captions.style debe ser 'karaoke' o 'static', "
                f"got {captions['style']!r}"
            )
        if captions["text_style"] not in ("classic", "playful"):
            raise EnhancementError(
                f"edit-spec captions.text_style debe ser 'classic' o 'playful', "
                f"got {captions['text_style']!r}"
            )
        hl = captions.get("highlight", [])
        if not isinstance(hl, list):
            raise EnhancementError("edit-spec captions.highlight debe ser lista")
        captions["highlight"] = hl
        # hooks: lista de {text, anchor, dur?} — texto de pantalla arriba
        # (≤4 palabras, 0.8–2.0 s, anclado a una palabra del transcript).
        # Los límites finales los impone captions.resolve_hooks al quemar;
        # aquí solo se valida el contrato del JSON.
        hooks = captions.get("hooks", [])
        if not isinstance(hooks, list):
            raise EnhancementError("edit-spec captions.hooks debe ser lista")
        for i, h in enumerate(hooks):
            if not isinstance(h, dict):
                raise EnhancementError(f"edit-spec captions.hooks[{i}] debe ser dict")
            for key in ("text", "anchor"):
                if key not in h:
                    raise EnhancementError(f"edit-spec captions.hooks[{i}] falta '{key}'")
            if not isinstance(h["text"], str) or not h["text"].strip():
                raise EnhancementError(
                    f"edit-spec captions.hooks[{i}].text debe ser str no vacío"
                )
            if not isinstance(h["anchor"], str) or not h["anchor"].strip():
                raise EnhancementError(
                    f"edit-spec captions.hooks[{i}].anchor debe ser str no vacío "
                    "(palabra del transcript)"
                )
            if "dur" in h and (not _is_num(h["dur"]) or h["dur"] <= 0):
                raise EnhancementError(
                    f"edit-spec captions.hooks[{i}].dur debe ser num > 0"
                )
        captions["hooks"] = hooks
        ev = captions.get("es_variant")
        if ev is not None and ev not in ("es-ES", "es-LATAM"):
            raise EnhancementError(
                "edit-spec captions.es_variant debe ser 'es-ES', 'es-LATAM' o null"
            )
        sq = captions.get("strict_qa")
        if sq is not None and not _is_bool(sq):
            raise EnhancementError("edit-spec captions.strict_qa debe ser bool o null")
    spec["captions"] = captions

    # target
    target = spec.get("target")
    if target is not None:
        if not isinstance(target, dict):
            raise EnhancementError("edit-spec 'target' debe ser dict o null")
        aspect = target.get("aspect", "9:16")
        if aspect not in VALID_ASPECTS:
            raise EnhancementError(
                f"edit-spec target.aspect debe ser uno de {VALID_ASPECTS}, got {aspect!r}"
            )
        target["aspect"] = aspect
        max_dur = target.get("max_dur", 45.0)
        if not _is_num(max_dur) or max_dur <= 0:
            raise EnhancementError(
                f"edit-spec target.max_dur debe ser > 0, got {max_dur}"
            )
        target["max_dur"] = float(max_dur)
        crf = target.get("crf", 18)
        if not isinstance(crf, int) or crf <= 0 or crf > 51:
            raise EnhancementError(
                f"edit-spec target.crf debe ser int en (0, 51], got {crf}"
            )
        target["crf"] = crf
    spec["target"] = target

    return spec


# ---------------------------------------------------------------------------
# Rule planner (determinista)
# ---------------------------------------------------------------------------


def rule_plan(
    words: list[dict],
    *,
    max_dur: float = 45.0,
    level: str = "medium",
    target_aspect: str = "9:16",
    crf: int = 18,
    source: str = "",
) -> dict:
    """Plan determinista basado en reglas. Misma entrada → mismo output.

    - keep_spans = [] (cutsilence decide via level)
    - hook = zoom-grow al inicio
    - effects = [audio riser] si hay words, con hit = último word end
    - captions = karaoke, enabled, classic, sin highlight
    - target desde args
    """
    hit = 0.0
    if words:
        hit = round(words[-1].get("e", 0.0), 2)

    effects: list[dict] = []
    if words:
        effects.append({
            "cmd": "audio riser",
            "args": {"mood": "tension", "hit": hit},
        })

    spec: dict = {
        "version": SPEC_VERSION,
        "source": source,
        "level": level,
        "keep_spans": [],
        "hook": {
            "type": "zoom-grow",
            "at": 0.0,
            "pct": 35.0,
            "curve": 62.0,
            "anchor": [0.5, 0.33],
        },
        "effects": effects,
        "captions": {
            "enabled": True,
            "style": "karaoke",
            "text_style": "classic",
            "highlight": [],
        },
        "target": {
            "aspect": target_aspect,
            "max_dur": max_dur,
            "crf": crf,
        },
    }
    return validate_edit_spec(spec)


# ---------------------------------------------------------------------------
# LLM planner (shells out to configurable command)
# ---------------------------------------------------------------------------

_DEFAULT_LLM_CMD = "opencode run -m opencode/mimo-v2.5-free"

_LLM_PROMPT_TEMPLATE = """Eres un editor de vídeo. Dado el siguiente transcript word-level
y el esquema de edit-spec, genera UN SOLO objeto JSON (sin markdown, sin
explicaciones) que siga exactamente el contrato.

TRANSCRIPT (palabras con timestamps):
{words_str}

EDIT-SCHEMA (v1):
- version: 1 (siempre)
- source: str (nombre del fichero)
- level: "light" | "medium" | "aggressive"
- keep_spans: [[s,e],...] (vacio = cutsilence decide)
- hook: {{"type": "zoom-grow", "at": float, "pct": float, "curve": float, "anchor": [x,y]}} | null
- effects: [{{"cmd": str, "args": {{...}}}}, ...]
  Cmds válidos y sus args:
    "video zoom": pct, curve, easing (smooth|out|in|linear), direction (grow|shrink|pulse), anchor [x,y], start, end, hold, pulse_dur, max_pulses
    "video magnify": center [x,y], radius, grid (str), hold, move_dur, sharpen, start, end
    "video teleport": start, end, shift (str)
    "video stabilize": smoothing, max_shift
    "audio lowpass": cutoff, transition, start, end
    "audio transition": from, to, at, dur, mood, key, curve, easing, gain
    "audio riser": mood, hit, dur, gain, seed, tail
    "audio melody": mood, from, to, duck, seed, gain, bars, start
- captions: {{"enabled": bool, "style": "karaoke"|"static", "text_style": "classic"|"playful", "highlight": [str,...]}}
- target: {{"aspect": "9:16"|"keep", "max_dur": float, "crf": int}}

RESTRICCIONES:
- max_dur = {max_dur} s
- NO cortes en medio de frase (mantener frases enteras)
- Solo usar subcomandos de voxera que existen (los listados arriba)
- Solo generar 1 efecto de audio riser como máximo
- Determinismo: si el transcript es el mismo, el plan debe ser similar

Devuelve SOLO el JSON, nada más."""


def llm_plan(
    words: list[dict],
    *,
    llm_cmd: str | None = None,
    max_dur: float = 45.0,
    level: str = "medium",
    source: str = "",
) -> dict:
    """Plan generado por un LLM. Shell-out con timeout 600s.

    Raises EnhancementError si llm_cmd es None, si el LLM falla, o si
    el spec resultante no valida.
    """
    if llm_cmd is None:
        llm_cmd = _DEFAULT_LLM_CMD
        if not llm_cmd:
            raise EnhancementError(
                "llm_cmd no especificado. Para planner=llm, proporciona "
                "--llm-cmd o configura la variable."
            )

    words_str = "\n".join(
        f"  {w.get('w', '?')} [{w.get('s', 0):.2f}-{w.get('e', 0):.2f}]"
        for w in words
    ) if words else "(sin transcript)"

    prompt = _LLM_PROMPT_TEMPLATE.format(
        words_str=words_str, max_dur=max_dur
    )

    try:
        proc = subprocess.run(
            llm_cmd,
            input=prompt,
            capture_output=True,
            text=True,
            shell=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        raise EnhancementError("LLM timeout (600s)")
    except Exception as exc:
        raise EnhancementError(f"LLM shell error: {exc}") from exc

    if proc.returncode != 0:
        stderr_tail = (proc.stderr or "")[-200:]
        raise EnhancementError(
            f"LLM falló (exit {proc.returncode}): {stderr_tail}"
        )

    raw_output = (proc.stdout or "").strip()
    if not raw_output:
        stderr_tail = (proc.stderr or "")[-200:]
        raise EnhancementError(
            f"LLM output vacío. stderr: {stderr_tail}"
        )

    # Strip markdown fences if present
    if raw_output.startswith("```"):
        lines = raw_output.split("\n")
        # Remove first and last fence lines
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw_output = "\n".join(lines).strip()

    try:
        spec = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        stderr_tail = (proc.stderr or "")[-200:]
        raise EnhancementError(
            f"LLM output no es JSON válido: {exc}. "
            f"Output: {raw_output[:200]}. stderr: {stderr_tail}"
        ) from exc

    spec["source"] = source or spec.get("source", "")
    spec["level"] = level
    return validate_edit_spec(spec)


# ---------------------------------------------------------------------------
# Executor (compone APIs de módulos existentes)
# ---------------------------------------------------------------------------


def _probe_duration(path: str | Path) -> float:
    """Duración de un fichero multimedia via ffprobe."""
    import subprocess as _sp
    proc = _sp.run(
        ["ffprobe", "-v", "error",
         "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    data = json.loads(proc.stdout or "{}")
    return float(data.get("format", {}).get("duration") or 0.0)


def execute_spec(
    spec: dict,
    input: str,
    output: str,
    *,
    words_json: str | None = None,
    temp_dir: str | None = None,
    model: str = "base",
    keep_stage_files: bool = False,
) -> list[dict]:
    """Ejecuta el pipeline de edición componiendo APIs de módulos.

    Pipeline:
      1. cutsilence → temp S1
      2. hook zoom sobre S1 → temp S2
      3. por cada effect: riser/lowpass/transition/etc → S3, S4...
      4. captions sobre el resultado final → output

    Words para captions: si words_json dado, usarlo; si no, transcribir
    del vídeo CUT (S1) para que los tiempos reflejen la timeline final.

    Devuelve lista de stages con {"stage", "cmd", "args", "ok", "dur"}.
    """
    inp = Path(input)
    out = Path(output)
    if not inp.exists():
        raise EnhancementError(f"input no existe: {inp}")
    out.parent.mkdir(parents=True, exist_ok=True)

    if temp_dir is None:
        temp_dir = str(out.parent)
    tdir = Path(temp_dir)
    tdir.mkdir(parents=True, exist_ok=True)

    stem = inp.stem
    stages: list[dict] = []
    current = str(inp)

    def _stage_path(suffix: str) -> str:
        return str(tdir / f"{stem}._autopilot_{suffix}.mp4")

    try:
        # ---- Stage 1: cutsilence ----
        stage_name = "cutsilence"
        t0 = time.monotonic()
        try:
            from voxera.video_silence import CutSilenceOptions, cutsilence_video
            opts = CutSilenceOptions(level=spec.get("level", "medium"))
            cutsilence_video(current, _stage_path("s1"), opts)
            dur = time.monotonic() - t0
            s1_path = _stage_path("s1")
            stages.append({
                "stage": stage_name,
                "cmd": "video cutsilence",
                "args": {"level": spec.get("level", "medium")},
                "ok": True,
                "dur": dur,
            })
            current = s1_path
        except EnhancementError as exc:
            dur = time.monotonic() - t0
            stages.append({
                "stage": stage_name,
                "cmd": "video cutsilence",
                "args": {"level": spec.get("level", "medium")},
                "ok": False,
                "dur": dur,
            })
            raise EnhancementError(f"[stage: {stage_name}] {exc}") from exc

        # ---- Stage 2: hook zoom ----
        hook = spec.get("hook")
        if hook and hook.get("type") == "zoom-grow":
            stage_name = "hook_zoom"
            t0 = time.monotonic()
            try:
                from voxera.video_zoom import ZoomOptions, zoom_video
                anchor = hook.get("anchor", [0.5, 0.33])
                opts = ZoomOptions(
                    pct=hook.get("pct", 35.0),
                    curve=hook.get("curve", 62.0),
                    anchor=(anchor[0], anchor[1]),
                    start=hook.get("at"),
                )
                zoom_video(current, _stage_path("s2"), opts)
                dur = time.monotonic() - t0
                stages.append({
                    "stage": stage_name,
                    "cmd": "video zoom",
                    "args": hook,
                    "ok": True,
                    "dur": dur,
                })
                current = _stage_path("s2")
            except EnhancementError as exc:
                dur = time.monotonic() - t0
                stages.append({
                    "stage": stage_name,
                    "cmd": "video zoom",
                    "args": hook,
                    "ok": False,
                    "dur": dur,
                })
                raise EnhancementError(f"[stage: {stage_name}] {exc}") from exc

        # ---- Stage 3: per-effect ----
        for idx, eff in enumerate(spec.get("effects", [])):
            cmd = eff["cmd"]
            args = eff.get("args", {})
            stage_name = f"effect_{cmd.replace(' ', '_')}_{idx}"
            t0 = time.monotonic()
            try:
                if cmd == "audio riser":
                    _apply_riser(current, args, _stage_path(f"e{idx}"), stage_name)
                elif cmd == "video zoom":
                    _apply_zoom(current, args, _stage_path(f"e{idx}"))
                elif cmd == "audio lowpass":
                    _apply_lowpass(current, args, _stage_path(f"e{idx}"))
                elif cmd == "audio transition":
                    _apply_transition(current, args, _stage_path(f"e{idx}"))
                elif cmd == "audio melody":
                    _apply_melody(current, args, _stage_path(f"e{idx}"))
                else:
                    # Unknown cmd already rejected by validate_edit_spec
                    raise EnhancementError(f"cmd no implementado en executor: {cmd}")
                dur = time.monotonic() - t0
                stages.append({
                    "stage": stage_name,
                    "cmd": cmd,
                    "args": args,
                    "ok": True,
                    "dur": dur,
                })
                current = _stage_path(f"e{idx}")
            except EnhancementError as exc:
                dur = time.monotonic() - t0
                stages.append({
                    "stage": stage_name,
                    "cmd": cmd,
                    "args": args,
                    "ok": False,
                    "dur": dur,
                })
                raise EnhancementError(f"[stage: {stage_name}] {exc}") from exc

        # ---- Stage 4: captions ----
        captions_cfg = spec.get("captions")
        if captions_cfg and captions_cfg.get("enabled"):
            stage_name = "captions"
            t0 = time.monotonic()
            try:
                from voxera.captions import captions_video
                highlight = tuple(captions_cfg.get("highlight", []))
                hooks = captions_cfg.get("hooks") or None
                captions_video(
                    current, str(out),
                    words_json=words_json,
                    model=model,
                    style=captions_cfg.get("style", "karaoke"),
                    text_style=captions_cfg.get("text_style", "classic"),
                    highlight=highlight,
                    hooks=hooks,
                    es_variant=captions_cfg.get("es_variant"),
                    strict_qa=captions_cfg.get("strict_qa", False),
                    crf=spec.get("target", {}).get("crf", 18),
                )
                dur = time.monotonic() - t0
                stages.append({
                    "stage": stage_name,
                    "cmd": "video captions",
                    "args": {
                        "style": captions_cfg.get("style"),
                        "text_style": captions_cfg.get("text_style"),
                        "hooks": len(hooks) if hooks else 0,
                        "es_variant": captions_cfg.get("es_variant"),
                    },
                    "ok": True,
                    "dur": dur,
                })
            except EnhancementError as exc:
                dur = time.monotonic() - t0
                stages.append({
                    "stage": stage_name,
                    "cmd": "video captions",
                    "args": {},
                    "ok": False,
                    "dur": dur,
                })
                raise EnhancementError(f"[stage: {stage_name}] {exc}") from exc
        else:
            # No captions: copy current to output
            import shutil
            shutil.copy2(current, str(out))

        return stages

    finally:
        # Clean up temp stage files unless requested
        if not keep_stage_files:
            for s in stages:
                if s.get("ok"):
                    # Find the temp file for this stage
                    pass  # Files cleaned up by next stage overwrite or by caller
            # Clean up any remaining _autopilot_ temp files
            for f in tdir.glob(f"{stem}._autopilot_*.mp4"):
                try:
                    f.unlink(missing_ok=True)
                except OSError:
                    pass


def _apply_riser(current: str, args: dict, output: str, stage_name: str) -> None:
    """Aplica audio riser sobre el vídeo actual."""
    from voxera.audio_tonal import RiserOptions, riser_file, mix_element
    from voxera import audioio
    from voxera import video as video_mod
    from voxera import audio_tonal

    # Extract audio, apply riser, remux
    tmp_wav_in = video_mod.temp_wav()
    tmp_wav_out = video_mod.temp_wav()
    try:
        video_mod.extract_audio(current, tmp_wav_in)
        data = audioio.load_audio(tmp_wav_in)
        opts = RiserOptions(
            mood=args.get("mood", "tension"),
            hit=args.get("hit"),
            dur=args.get("dur", 2.0),
            gain_db=args.get("gain", -16.0),
            tail=args.get("tail", 0.3),
        )
        opts.validate()
        # Resolve hit if needed
        if opts.hit is None:
            from dataclasses import replace
            opts = replace(opts, hit=data.duration_s - opts.tail)
            opts.validate()
        t0 = max(opts.hit - opts.dur, 0.0)
        element = audio_tonal.render_riser(audioio.INTERNAL_SAMPLE_RATE, opts)
        mixed = audio_tonal.mix_element(
            data.samples, audioio.INTERNAL_SAMPLE_RATE,
            element, t0, opts.gain_db,
        )
        audioio.write_wav(tmp_wav_out, mixed, sample_rate=audioio.INTERNAL_SAMPLE_RATE)
        # Remux: video from current, audio from riser
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        import subprocess
        cmd = [
            video_mod._tool("ffmpeg"), "-y", "-v", "error",
            "-i", current,
            "-i", str(tmp_wav_out),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", str(out_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=7200)
    finally:
        tmp_wav_in.unlink(missing_ok=True)
        tmp_wav_out.unlink(missing_ok=True)


def _apply_zoom(current: str, args: dict, output: str) -> None:
    """Aplica video zoom sobre el vídeo actual."""
    from voxera.video_zoom import ZoomOptions, zoom_video
    anchor = args.get("anchor", [0.5, 0.5])
    opts = ZoomOptions(
        pct=args.get("pct", 40.0),
        curve=args.get("curve", 62.0),
        easing=args.get("easing", "smooth"),
        direction=args.get("direction", "grow"),
        anchor=(anchor[0], anchor[1]),
        start=args.get("start"),
        end=args.get("end"),
        hold=args.get("hold", 0.0),
        pulse_dur=args.get("pulse_dur", 3.0),
        max_pulses=args.get("max_pulses", 4),
    )
    zoom_video(current, output, opts)


def _apply_lowpass(current: str, args: dict, output: str) -> None:
    """Aplica audio lowpass sobre el vídeo actual."""
    from voxera.audio_lowpass import LowPassOptions, lowpass_file
    from voxera import video as video_mod
    import subprocess as _sp

    tmp_wav_in = video_mod.temp_wav()
    tmp_wav_out = video_mod.temp_wav()
    try:
        video_mod.extract_audio(current, tmp_wav_in)
        opts = LowPassOptions(
            cutoff=args.get("cutoff", 800.0),
            transition=args.get("transition", 1.0),
            start=args.get("start"),
            end=args.get("end"),
        )
        lowpass_file(tmp_wav_in, tmp_wav_out, opts)
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        _sp.run([
            video_mod._tool("ffmpeg"), "-y", "-v", "error",
            "-i", current,
            "-i", str(tmp_wav_out),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", str(out_path),
        ], check=True, capture_output=True, timeout=7200)
    finally:
        tmp_wav_in.unlink(missing_ok=True)
        tmp_wav_out.unlink(missing_ok=True)


def _apply_transition(current: str, args: dict, output: str) -> None:
    """Aplica audio transition sobre el vídeo actual."""
    from voxera.audio_tonal import TransitionOptions, transition_file
    from voxera import video as video_mod
    import subprocess as _sp

    tmp_wav_in = video_mod.temp_wav()
    tmp_wav_out = video_mod.temp_wav()
    try:
        video_mod.extract_audio(current, tmp_wav_in)
        opts = TransitionOptions(
            from_mood=args.get("from", "calm"),
            to_mood=args.get("to", "hope"),
            from_key=args.get("key"),
            at=args.get("at", 0.0),
            dur=args.get("dur", 3.0),
            gain_db=args.get("gain", -18.0),
            curve=args.get("curve", 62.0),
            easing=args.get("easing", "smooth"),
        )
        transition_file(tmp_wav_in, tmp_wav_out, opts)
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        _sp.run([
            video_mod._tool("ffmpeg"), "-y", "-v", "error",
            "-i", current,
            "-i", str(tmp_wav_out),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", str(out_path),
        ], check=True, capture_output=True, timeout=7200)
    finally:
        tmp_wav_in.unlink(missing_ok=True)
        tmp_wav_out.unlink(missing_ok=True)


def _apply_melody(current: str, args: dict, output: str) -> None:
    """Aplica audio melody sobre el vídeo actual."""
    from voxera.audio_tonal import MelodyOptions, melody_file
    from voxera import video as video_mod
    import subprocess as _sp

    tmp_wav_in = video_mod.temp_wav()
    tmp_wav_out = video_mod.temp_wav()
    try:
        video_mod.extract_audio(current, tmp_wav_in)
        opts = MelodyOptions(
            mood=args.get("mood", "wonder"),
            key=args.get("mood"),
            start=args.get("start", 0.0),
            bars=args.get("bars", 4),
            seed=args.get("seed", 0),
            gain_db=args.get("gain", -20.0),
            duck_db=args.get("duck", 0.0),
        )
        melody_file(tmp_wav_in, tmp_wav_out, opts)
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        _sp.run([
            video_mod._tool("ffmpeg"), "-y", "-v", "error",
            "-i", current,
            "-i", str(tmp_wav_out),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", str(out_path),
        ], check=True, capture_output=True, timeout=7200)
    finally:
        tmp_wav_in.unlink(missing_ok=True)
        tmp_wav_out.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# run_autopilot (main entry point)
# ---------------------------------------------------------------------------


def run_autopilot(
    input: str,
    output: str,
    *,
    planner: str = "llm",
    words_json: str | None = None,
    llm_cmd: str | None = None,
    max_dur: float = 45.0,
    level: str = "medium",
    aspect: str = "9:16",
    crf: int = 18,
    model: str = "base",
    dry_run: bool = False,
) -> dict:
    """Orquesta plan + ejecución. Devuelve manifest dict.

    planner: "llm" (default) o "rule"
    dry_run: solo devuelve manifest sin ejecutar (stages listados, spec shown)
    """
    if planner not in ("rule", "llm"):
        raise EnhancementError(f"planner debe ser 'rule' o 'llm', got {planner!r}")

    # Step 1: Transcribe words (for planning and for captions timing)
    words: list[dict] = []
    if words_json:
        wpath = Path(words_json)
        if not wpath.exists():
            raise EnhancementError(f"words_json no existe: {wpath}")
        data = json.loads(wpath.read_text(encoding="utf-8"))
        if "words" in data:
            words = data["words"]
        elif "segments" in data:
            for seg in data["segments"]:
                words.extend(seg.get("words", []))
    else:
        # Transcribe original for planning (not for captions — captions
        # will re-transcribe from the cut video)
        try:
            from voxera.captions import transcribe_words
            result = transcribe_words(input, model=model)
            words = result.get("words", [])
        except EnhancementError:
            # No speech detected — continue with empty words
            words = []

    # Step 2: Plan (llm por defecto, fallback a reglas si falla)
    spec: dict | None = None
    try:
        if planner == "rule":
            spec = rule_plan(
                words, max_dur=max_dur, level=level,
                target_aspect=aspect, crf=crf, source=input,
            )
        else:
            spec = llm_plan(
                words, llm_cmd=llm_cmd, max_dur=max_dur,
                level=level, source=input,
            )
    except EnhancementError:
        if planner == "llm":
            # Fallback: si el LLM falla, usar reglas
            spec = rule_plan(
                words, max_dur=max_dur, level=level,
                target_aspect=aspect, crf=crf, source=input,
            )
        else:
            raise

    if dry_run:
        # Build manifest without executing
        manifest = {
            "version": SPEC_VERSION,
            "source": input,
            "planner": planner,
            "spec": spec,
            "stages": _list_stages(spec),
            "qa": {},
            "notes": ["dry_run: sin ejecución"],
        }
        return manifest

    # Step 3: Execute
    stages = execute_spec(
        spec, input, output,
        words_json=words_json,
        model=model,
    )

    # Step 4: QA
    qa: dict = {}
    notes: list[str] = []
    try:
        dur_in = _probe_duration(input)
        dur_out = _probe_duration(output)
        qa["dur_in"] = dur_in
        qa["dur_out"] = dur_out
        # Probe fps/frames
        from voxera.video_enhance import probe_video
        pin = probe_video(input)
        pout = probe_video(output)
        qa["fps"] = pout.get("fps", 0.0)
        qa["frames_in"] = int(round(dur_in * pin.get("fps", 30.0)))
        qa["frames_out"] = int(round(dur_out * pout.get("fps", 30.0)))
        # Notes
        if dur_out > max_dur:
            notes.append(
                f"dur_out ({dur_out:.2f}s) > max_dur ({max_dur:.2f}s)"
            )
        failed = [s for s in stages if not s.get("ok")]
        if failed:
            notes.append(f"stages fallidos: {[s['stage'] for s in failed]}")
    except Exception as exc:
        notes.append(f"QA error: {exc}")

    manifest = {
        "version": SPEC_VERSION,
        "source": input,
        "planner": planner,
        "spec": spec,
        "stages": stages,
        "qa": qa,
        "notes": notes,
    }

    # Write manifest
    manifest_path = Path(output).with_suffix("") .parent / (
        Path(output).stem + ".manifest.json"
    )
    # Use the same path as output + .manifest.json
    manifest_path = Path(output + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    return manifest


def _list_stages(spec: dict) -> list[dict]:
    """Lista de stages esperados (para dry_run)."""
    stages = []
    stages.append({"stage": "cutsilence", "cmd": "video cutsilence", "args": {"level": spec.get("level")}})
    if spec.get("hook"):
        stages.append({"stage": "hook_zoom", "cmd": "video zoom", "args": spec["hook"]})
    for i, eff in enumerate(spec.get("effects", [])):
        stages.append({"stage": f"effect_{eff['cmd'].replace(' ', '_')}_{i}", "cmd": eff["cmd"], "args": eff.get("args", {})})
    if spec.get("captions", {}).get("enabled"):
        stages.append({"stage": "captions", "cmd": "video captions", "args": spec.get("captions", {})})
    return stages


# ---------------------------------------------------------------------------
# run_ab — A/B harness
# ---------------------------------------------------------------------------


def run_ab(
    input: str,
    prefix: str,
    *,
    planner_a: str = "rule",
    planner_b: str = "llm",
    llm_cmd: str | None = None,
    max_dur: float = 45.0,
    level: str = "medium",
    aspect: str = "9:16",
    crf: int = 18,
    model: str = "base",
    words_json: str | None = None,
) -> dict:
    """Ejecuta ambas variantes y genera ab_manifest con checklist.

    Devuelve {prefix}.{planner_a}.mp4 y {prefix}.{planner_b}.mp4;
    escribe {prefix}.ab_manifest.json.

    Si planner_b falla, lo registra pero NO crashea el harness.
    """
    variants: dict = {}
    notes: list[str] = []

    # Transcribe words once (shared)
    words: list[dict] = []
    words_json_path: str | None = words_json
    if words_json_path is None:
        try:
            from voxera.captions import transcribe_words
            result = transcribe_words(input, model=model)
            words = result.get("words", [])
        except EnhancementError:
            words = []

        # Write temp words file if we have words (so run_autopilot can use them)
        if words:
            tmp_words = Path(prefix + ".words.json")
            tmp_words.write_text(json.dumps({"words": words}), encoding="utf-8")
            words_json_path = str(tmp_words)

    for label, planner in [("rule", planner_a), ("llm", planner_b)]:
        out_path = f"{prefix}.{label}.mp4"
        try:
            manifest = run_autopilot(
                input, out_path,
                planner=planner,
                words_json=words_json_path,
                llm_cmd=llm_cmd if planner == "llm" else None,
                max_dur=max_dur,
                level=level,
                aspect=aspect,
                crf=crf,
                model=model,
            )
            variants[label] = {
                "output": out_path,
                "spec": manifest.get("spec"),
                "qa": manifest.get("qa", {}),
            }
        except EnhancementError as exc:
            variants[label] = {
                "output": out_path,
                "spec": None,
                "qa": {},
                "error": str(exc),
            }
            notes.append(f"{label} planner falló: {exc}")

    ab_manifest = {
        "version": SPEC_VERSION,
        "source": input,
        "words_json": words_json_path,
        "variants": variants,
        "checklist": [
            "publicar ambas variantes el mismo día (mismo contenido, solo difiere la edición)",
            "registrar medianas (no medias) de views/completion/3s-retention a los 7-14 días",
            "replicar el ganador en un segundo lote antes de fijar criterios",
            "gate humano Track-8 (≥60% preferencia) si hay oyentes disponibles",
        ],
        "notes": notes,
    }

    manifest_path = f"{prefix}.ab_manifest.json"
    Path(manifest_path).write_text(
        json.dumps(ab_manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return ab_manifest
