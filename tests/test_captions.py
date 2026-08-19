"""Unit tests del módulo de captions/subtítulos (voxera captions).

- build_ass: secciones ASS, timing karaoke (\k), static (sin \k), playful,
  highlight, márgenes desde safe_box.
- words_to_cues: packing por chars_per_sec, breaks por puntuación, sin cues vacías.
- _escape_ffmpeg_path: rutas Windows con backslashes y dos-puntos.
- No hay dependencia de red ni de faster_whisper en tests unitarios.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from voxera import captions as cap
from voxera.errors import EnhancementError


# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------

def _words_simple() -> list[dict]:
    """4 palabras de ejemplo con timings."""
    return [
        {"w": "Hola", "s": 0.50, "e": 0.83},
        {"w": "mundo", "s": 0.90, "e": 1.30},
        {"w": "esto", "s": 1.50, "e": 1.80},
        {"w": "funciona", "s": 1.90, "e": 2.40},
    ]


def _words_long() -> list[dict]:
    """Línea larga que debe partirse (>34 chars)."""
    return [
        {"w": "Una", "s": 0.0, "e": 0.30},
        {"w": "frase", "s": 0.35, "e": 0.70},
        {"w": "bastante", "s": 0.75, "e": 1.10},
        {"w": "larga", "s": 1.15, "e": 1.45},
        {"w": "para", "s": 1.50, "e": 1.75},
        {"w": "demostrar", "s": 1.80, "e": 2.20},
        {"w": "el", "s": 2.25, "e": 2.40},
        {"w": "particion", "s": 2.45, "e": 2.90},
    ]


def _words_punct() -> list[dict]:
    """Palabras con puntuación para probar breaks."""
    return [
        {"w": "Hola,", "s": 0.0, "e": 0.30},
        {"w": "buenos", "s": 0.35, "e": 0.65},
        {"w": "días.", "s": 0.70, "e": 1.00},
        {"w": "¿Cómo", "s": 1.20, "e": 1.50},
        {"w": "estás?", "s": 1.55, "e": 1.90},
    ]


def _words_two_line() -> list[dict]:
    """Frase que se parte tras puntuación en dos líneas de ≤25 chars:
    'Esto es bastante largo.' (20) + 'y aquí sigue la frase' (17)."""
    return [
        {"w": "Esto", "s": 0.00, "e": 0.30},
        {"w": "es", "s": 0.35, "e": 0.60},
        {"w": "bastante", "s": 0.65, "e": 1.00},
        {"w": "largo.", "s": 1.05, "e": 1.40},
        {"w": "y", "s": 1.45, "e": 1.60},
        {"w": "aquí", "s": 1.65, "e": 1.95},
        {"w": "sigue", "s": 2.00, "e": 2.30},
        {"w": "la", "s": 2.35, "e": 2.50},
        {"w": "frase", "s": 2.55, "e": 2.90},
    ]


def _words_empty() -> list[dict]:
    return []


# ---------------------------------------------------------------------------
# Tests: build_ass
# ---------------------------------------------------------------------------

class TestBuildAss:
    """Tests de generación de ASS."""

    def test_has_all_sections(self):
        """El ASS generado debe tener [Script Info], [V4+ Styles] y [Events]."""
        ass = cap.build_ass(_words_simple())
        assert "[Script Info]" in ass
        assert "[V4+ Styles]" in ass
        assert "[Events]" in ass
        assert "Dialogue:" in ass

    def test_script_info_header(self):
        """Script info contiene resolución 1080x1920 y WrapStyle 2."""
        ass = cap.build_ass(_words_simple())
        assert "PlayResX: 1080" in ass
        assert "PlayResY: 1920" in ass
        assert "WrapStyle: 2" in ass
        assert "ScaledBorderAndShadow: yes" in ass

    def test_karaoke_timing_math(self):
        """Palabra de 0.33s → \\k33 (centésimas)."""
        words = [{"w": "test", "s": 1.20, "e": 1.53}]
        ass = cap.build_ass(words, style="karaoke")
        # duración = 0.33s → 33 centésimas
        assert "\\k33" in ass

    def test_karaoke_minimum_one_cs(self):
        """Duración muy corta genera \\k1 como mínimo."""
        words = [{"w": "x", "s": 0.0, "e": 0.005}]
        ass = cap.build_ass(words, style="karaoke")
        assert "\\k1" in ass

    def test_static_no_karaoke_tag(self):
        """Estilo static no contiene \\k."""
        words = _words_simple()
        ass = cap.build_ass(words, style="static")
        assert "\\k" not in ass

    def test_static_has_fade(self):
        """Estilo static tiene \\fad(80,80)."""
        words = _words_simple()
        ass = cap.build_ass(words, style="static")
        assert "\\fad(80,80)" in ass

    def test_playful_lowercase(self):
        """text_style='playful' convierte todo a minúsculas."""
        words = [{"w": "HOLA", "s": 0.0, "e": 0.30}]
        ass = cap.build_ass(words, text_style="playful")
        assert "hola" in ass
        assert "HOLA" not in ass

    def test_playful_strip_punct(self):
        """playful elimina puntuación trailing (conservando ? y !)."""
        words = [
            {"w": "bien.", "s": 0.0, "e": 0.30},
            {"w": "¿qué?", "s": 0.40, "e": 0.70},
            {"w": "¡wow!", "s": 0.80, "e": 1.10},
        ]
        ass = cap.build_ass(words, text_style="playful")
        assert "bien" in ass
        # punto removido
        assert "bien." not in ass
        # ¿ y ? se conservan (forman parte de la palabra)
        assert "¿qué?" in ass
        assert "¡wow!" in ass

    def test_highlight_injection(self):
        """Palabra en highlight se envuelve en \\c&H0000D7FF&."""
        words = [{"w": "hook", "s": 0.0, "e": 0.30}]
        ass = cap.build_ass(words, highlight=("hook",))
        assert "\\c&H0000D7FF&" in ass
        assert "hook" in ass

    def test_highlight_case_insensitive(self):
        """Highlight es case-insensitive."""
        words = [{"w": "Hook", "s": 0.0, "e": 0.30}]
        ass = cap.build_ass(words, highlight=("hook",))
        assert "\\c&H0000D7FF&" in ass

    def test_margin_math_from_safe_box(self):
        """margin_l = margin_r = (1080 - 900) // 2 = 90."""
        ass = cap.build_ass(_words_simple())
        # ASS Style: ...,MarginL,MarginR,MarginV,Encoding
        # fields[19]=90, fields[20]=90, fields[21]=380
        style_line = [l for l in ass.split("\n") if l.startswith("Style: Karaoke")][0]
        fields = style_line.split(",")
        assert fields[19] == "90"  # MarginL
        assert fields[20] == "90"  # MarginR

    def test_custom_margin_v(self):
        """margin_v personalizado se refleja en el Style."""
        ass = cap.build_ass(_words_simple(), margin_v=500)
        style_line = [l for l in ass.split("\n") if l.startswith("Style: Karaoke")][0]
        fields = style_line.split(",")
        assert fields[21] == "500"  # MarginV

    def test_no_zero_length_events(self):
        """Ningún evento tiene start == end."""
        words = [{"w": "x", "s": 1.0, "e": 1.0}]
        ass = cap.build_ass(words)
        # start y end deben ser distintos — al menos 1 frame (0.033s)
        lines = [l for l in ass.split("\n") if l.startswith("Dialogue:")]
        assert len(lines) == 1
        parts = lines[0].split(",")
        start = parts[1]
        end = parts[2]
        assert start != end

    def test_invalid_style_raises(self):
        """Estilo no válido lanza EnhancementError."""
        with pytest.raises(EnhancementError, match="style"):
            cap.build_ass(_words_simple(), style="invalido")

    def test_invalid_text_style_raises(self):
        """text_style no válido lanza EnhancementError."""
        with pytest.raises(EnhancementError, match="text_style"):
            cap.build_ass(_words_simple(), text_style="invalido")

    def test_empty_words_raises(self):
        """Lista vacía de palabras → EnhancementError."""
        with pytest.raises(EnhancementError, match="sin cues"):
            cap.build_ass([])

    def test_outline_in_style(self):
        """El outline se refleja en la línea de estilo."""
        ass = cap.build_ass(_words_simple(), outline=5)
        # Outline es fields[16] (0-indexed) en la línea Style de ASS
        style_line = [l for l in ass.split("\n") if l.startswith("Style: Karaoke")][0]
        fields = style_line.split(",")
        assert fields[16] == "5"  # Outline


# ---------------------------------------------------------------------------
# Tests: words_to_cues
# ---------------------------------------------------------------------------

class TestWordsToCues:
    """Tests de packing de palabras en cues."""

    def test_basic_packing(self):
        """4 palabras cortas → 1 cue."""
        cues = cap.words_to_cues(_words_simple())
        assert len(cues) >= 1
        total_words = sum(len(c) for c in cues)
        assert total_words == 4

    def test_long_line_splits(self):
        """Línea larga (>34 chars) se particiona."""
        cues = cap.words_to_cues(_words_long())
        # 8 palabras, total chars ~50 → al menos 2 cues
        assert len(cues) >= 2

    def test_punctuation_break(self):
        """Se prefiere romper tras puntuación cuando la línea es larga."""
        # Palabras lo suficientemente largas para forzar un break;
        # la coma después de "Hola" marca el punto de ruptura preferido.
        words = [
            {"w": "Hola,"  , "s": 0.00, "e": 0.30},
            {"w": "buenos" , "s": 0.35, "e": 0.65},
            {"w": "días."  , "s": 0.70, "e": 1.00},
            {"w": "¿Cómo"  , "s": 1.20, "e": 1.50},
            {"w": "estás?" , "s": 1.55, "e": 1.90},
            {"w": "todo"   , "s": 2.00, "e": 2.20},
            {"w": "bien"   , "s": 2.25, "e": 2.50},
        ]
        cues = cap.words_to_cues(words, chars_per_sec=10.0)
        # Con chars_per_sec bajo, la línea crece rápido y se rompe
        assert len(cues) >= 2

    def test_empty_words(self):
        """Lista vacía → lista vacía de cues."""
        assert cap.words_to_cues([]) == []

    def test_single_word(self):
        """Una sola palabra → un cue."""
        cues = cap.words_to_cues([{"w": "solo", "s": 0.0, "e": 0.30}])
        assert len(cues) == 1
        assert cues[0][0]["w"] == "solo"

    def test_chars_per_sec_limit(self):
        """Chars_per_sec bajo fuerza más cues."""
        words = [
            {"w": "largo", "s": 0.0, "e": 0.20},
            {"w": "texto", "s": 0.25, "e": 0.50},
        ]
        # chars_per_sec muy bajo → cada palabra en su propio cue
        cues = cap.words_to_cues(words, chars_per_sec=1.0)
        assert len(cues) >= 2


# ---------------------------------------------------------------------------
# Tests: segmentación sintáctica (Síntesis Theme 2)
# ---------------------------------------------------------------------------

class TestSegmentation:
    """Reglas negativas y cortes preferidos (BBC/Netflix)."""

    def test_bad_break_after_article(self):
        """Nunca partir artículo+nombre."""
        assert cap._bad_break({"w": "el"}, {"w": "gato"})
        assert cap._bad_break({"w": "una"}, {"w": "idea"})

    def test_bad_break_after_preposition(self):
        """Nunca dejar una preposición colgando al final de línea."""
        assert cap._bad_break({"w": "para"}, {"w": "ti"})
        assert cap._bad_break({"w": "con"}, {"w": "migo"})

    def test_bad_break_after_auxiliary(self):
        """Nunca separar auxiliar/negación del verbo."""
        assert cap._bad_break({"w": "no"}, {"w": "quiero"})
        assert cap._bad_break({"w": "he"}, {"w": "visto"})

    def test_bad_break_name_surname(self):
        """Nunca partir nombre+apellido (heurística de capitalizadas)."""
        assert cap._bad_break({"w": "Juan"}, {"w": "Pérez"})

    def test_good_break_after_punctuation(self):
        """Corte preferido tras puntuación."""
        assert cap._good_break({"w": "días."}, {"w": "Hoy"})

    def test_good_break_before_conjunction(self):
        """Corte preferido antes de conjunciones."""
        assert cap._good_break({"w": "pan"}, {"w": "y"})
        assert cap._good_break({"w": "vino"}, {"w": "pero"})

    def test_good_break_before_preposition(self):
        """Corte preferido antes de preposiciones."""
        assert cap._good_break({"w": "ir"}, {"w": "para"})

    def test_pause_over_half_second_breaks(self):
        """Una pausa real (≥0.5 s) separa cues aunque la línea no esté llena
        (BBC: hueco ≥1 s si hay pausa; Netflix: chaining solo 3–11 frames)."""
        words = [
            {"w": "Hola", "s": 0.0, "e": 0.30},
            {"w": "mundo", "s": 0.9, "e": 1.20},   # pausa 0.6 s
            {"w": "otra", "s": 1.25, "e": 1.50},
        ]
        cues = cap.words_to_cues(words, chars_per_sec=18.0)
        assert len(cues) == 2
        assert [w["w"] for w in cues[0]] == ["Hola"]
        assert [w["w"] for w in cues[1]] == ["mundo", "otra"]

    def test_small_gap_stays_joined(self):
        """Huecos pequeños (<0.5 s) no separan."""
        words = [
            {"w": "Hola", "s": 0.0, "e": 0.30},
            {"w": "mundo", "s": 0.35, "e": 0.70},
        ]
        cues = cap.words_to_cues(words, chars_per_sec=18.0)
        assert len(cues) == 1

    def test_backtrack_keeps_article_noun_together(self):
        """Si el corte caería tras un artículo, se retrocede al último buen
        punto (antes de la conjunción) y artículo+nombre quedan juntos."""
        words = [
            {"w": "Hola,", "s": 0.00, "e": 0.20},
            {"w": "y", "s": 0.25, "e": 0.30},
            {"w": "el", "s": 0.35, "e": 0.45},
            {"w": "gato", "s": 0.50, "e": 0.60},
            {"w": "duerme", "s": 0.65, "e": 1.00},
        ]
        cues = cap.words_to_cues(words, chars_per_sec=10.0)
        flat = [[w["w"] for w in line] for line in cues]
        # El artículo y su nombre nunca se separan
        for line in flat:
            assert not any(line[i] == "el" and line[i + 1] != "gato" for i in range(len(line) - 1))
        # El corte preferido cae antes de la conjunción "y"
        assert flat[0] == ["Hola,"]
        assert "y" in flat[1]


# ---------------------------------------------------------------------------
# Tests: agrupación a 2 líneas (Síntesis Theme 2 — Li 2026)
# ---------------------------------------------------------------------------

class TestTwoLines:
    """Dos líneas = punto dulce de atención en vertical."""

    def test_group_merges_medium_cues(self):
        """Dos cues medianos (≤25 chars c/u, corte tras puntuación) se
        agrupan en un evento de 2 líneas."""
        words = _words_two_line()
        events = cap._build_events(words, max_lines=3, chars_per_sec=18.0, two_lines=True)
        # ['Esto es bastante largo.' (20) + 'y aquí sigue la frase' (17)]
        assert len(events) == 1
        assert len(events[0]) == 2  # dos líneas en un evento
        assert events[0][0][-1]["w"] == "largo."
        assert events[0][1][0]["w"] == "y"

    def test_renders_newline_separator(self):
        """El evento de 2 líneas usa \\N en el texto ASS."""
        ass = cap.build_ass(_words_two_line())
        dialogue = [l for l in ass.split("\n") if l.startswith("Dialogue:")]
        assert len(dialogue) == 1
        assert "\\N" in dialogue[0]

    def test_disabled_with_max_lines_1(self):
        """max_lines=1 desactiva la agrupación."""
        ass = cap.build_ass(_words_two_line(), max_lines=1)
        dialogue = [l for l in ass.split("\n") if l.startswith("Dialogue:")]
        assert len(dialogue) == 2

    def test_no_group_across_bad_break(self):
        """No se agrupan cues cuya frontera rompería artículo+nombre."""
        words = [
            {"w": "Hola", "s": 0.00, "e": 0.30},
            {"w": "el", "s": 0.35, "e": 0.50},
            {"w": "gato", "s": 0.55, "e": 0.90},
        ]
        events = cap._build_events(words, max_lines=3, chars_per_sec=2.0, two_lines=True)
        # Con cps bajo cada palabra va a su propia línea; ninguna frontera
        # (el|gato) es sintácticamente buena → no hay eventos de 2 líneas.
        assert all(len(ev) == 1 for ev in events)
        assert [w["w"] for ev in events for w in ev[0]] == ["Hola", "el", "gato"]


# ---------------------------------------------------------------------------
# Tests: hooks de texto arriba (Síntesis Theme 5)
# ---------------------------------------------------------------------------

class TestHooks:
    """Primitivo hook: ≤4 palabras, 0.8–2.0 s, ancla al transcript."""

    def test_resolve_anchor_after(self):
        """El hook arranca 0.1 s tras el final de la palabra ancla."""
        words = _words_simple()  # 'mundo' s=0.90 e=1.30
        hooks = cap.resolve_hooks(words, [{"text": "Espera", "anchor": "mundo"}])
        assert len(hooks) == 1
        assert abs(hooks[0]["start"] - 1.40) < 1e-9
        assert abs(hooks[0]["end"] - (1.40 + cap.HOOK_DEFAULT_DUR)) < 1e-9

    def test_duration_clamped(self):
        """Duración fuera de [0.8, 2.0] se clampa."""
        words = _words_simple()
        long = cap.resolve_hooks(words, [{"text": "X", "anchor": "mundo", "dur": 5.0}])
        short = cap.resolve_hooks(words, [{"text": "X", "anchor": "mundo", "dur": 0.1}])
        assert long[0]["end"] - long[0]["start"] <= cap.HOOK_MAX_DUR
        assert short[0]["end"] - short[0]["start"] >= cap.HOOK_MIN_DUR

    def test_text_too_long_raises(self):
        """Más de 4 palabras → EnhancementError."""
        with pytest.raises(EnhancementError, match="4 palabras"):
            cap.resolve_hooks(_words_simple(), [{"text": "uno dos tres cuatro cinco", "anchor": "mundo"}])

    def test_missing_anchor_raises(self):
        """Palabra ancla ausente → EnhancementError."""
        with pytest.raises(EnhancementError, match="ancla"):
            cap.resolve_hooks(_words_simple(), [{"text": "Ojo", "anchor": "inexistente"}])

    def test_renders_hook_style_and_caps(self):
        """El hook usa estilo Hook, \\an8 (arriba-centro) y MAYÚSCULAS."""
        words = _words_simple()
        ass = cap.build_ass(words, hooks=[{"text": "Ojo", "anchor": "mundo"}])
        assert "Style: Hook" in ass
        assert "\\an8" in ass
        assert "OJO" in ass
        assert "Dialogue: 2," in ass

    def test_hook_dropped_over_wide_cue(self):
        """Hook que solapa un evento de 2 líneas se descarta con nota."""
        notes: list = []
        # _words_two_line se agrupa en un evento de 2 líneas (37 chars) que
        # abarca 0..2.9; el hook anclado a 'largo' (e=1.40) lo solapa.
        ass = cap.build_ass(_words_two_line(), hooks=[{"text": "Ojo", "anchor": "largo"}], notes=notes)
        assert any("descartado" in n for n in notes)
        assert "OJO" not in ass

    def test_hook_dropped_over_hook(self):
        """Dos hooks simultáneos → el segundo se descarta."""
        notes: list = []
        hooks = [
            {"text": "Uno", "anchor": "mundo", "dur": 2.0},
            {"text": "Dos", "anchor": "mundo", "dur": 2.0},
        ]
        cap.build_ass(_words_simple(), hooks=hooks, notes=notes)
        assert any("descartado" in n for n in notes)


# ---------------------------------------------------------------------------
# Tests: variante de español (Síntesis Theme 6 — Netflix ES)
# ---------------------------------------------------------------------------

class TestEsVariant:
    """Ajustes regionales es-ES / es-LATAM."""

    def test_es_es_decimal_comma(self):
        """es-ES: decimales con coma (3.5 → 3,5)."""
        words = [{"w": "3.5", "s": 0.0, "e": 0.40}]
        ass = cap.build_ass(words, es_variant="es-ES")
        assert "3,5" in ass
        assert "3.5" not in ass

    def test_es_latam_decimal_point(self):
        """es-LATAM: decimales con punto (3,5 → 3.5)."""
        words = [{"w": "3,5", "s": 0.0, "e": 0.40}]
        ass = cap.build_ass(words, es_variant="es-LATAM")
        assert "3.5" in ass

    def test_es_latam_time_ampm(self):
        """es-LATAM: hora 24h → a. m./p. m."""
        words = [{"w": "14:00", "s": 0.0, "e": 0.40}, {"w": "9:30", "s": 0.5, "e": 0.9}]
        ass = cap.build_ass(words, es_variant="es-LATAM")
        assert "2:00 p. m." in ass
        assert "9:30 a. m." in ass

    def test_invalid_variant_raises(self):
        """Variante inválida → EnhancementError."""
        with pytest.raises(EnhancementError, match="es_variant"):
            cap.build_ass(_words_simple(), es_variant="es-MX")

    def test_playful_keeps_inverted_marks(self):
        """playful + es nunca elimina ¿/¡ (obligatorios en español)."""
        words = [
            {"w": "¿Qué", "s": 0.0, "e": 0.30},
            {"w": "pasa?", "s": 0.4, "e": 0.70},
        ]
        ass = cap.build_ass(words, text_style="playful", es_variant="es-ES")
        assert "¿qué" in ass
        assert "pasa?" in ass


# ---------------------------------------------------------------------------
# Tests: QA de lectura (Síntesis §7 CAMBIO 1)
# ---------------------------------------------------------------------------

class TestAuditCues:
    """Auditoría cps por cue y duración mínima."""

    def _events(self, words):
        return cap._build_events(words, max_lines=3, chars_per_sec=18.0, two_lines=True)

    def test_fast_cue_fails(self):
        """Cue muy rápido (>20 cps) → severidad fail."""
        words = [
            {"w": "palabra", "s": 0.0, "e": 0.20},
            {"w": "larguísima", "s": 0.22, "e": 0.45},
        ]
        issues = cap.audit_cues(self._events(words))
        assert any(i["severity"] == "fail" for i in issues)

    def test_slow_cue_clean(self):
        """Cue a ritmo natural → sin issues."""
        words = [
            {"w": "Hola", "s": 0.5, "e": 0.83},
            {"w": "mundo", "s": 0.9, "e": 1.35},
        ]
        assert cap.audit_cues(self._events(words)) == []

    def test_short_cue_warns(self):
        """Cue < 0.83 s → warn de duración mínima."""
        words = [{"w": "hola", "s": 0.0, "e": 0.30}]
        issues = cap.audit_cues(self._events(words))
        assert any(i["severity"] == "warn" and "0.83" in i["message"] for i in issues)

    def test_warn_below_fail(self):
        """Cue entre 18 y 20 cps → warn, no fail."""
        words = [
            {"w": "texto", "s": 0.0, "e": 0.18},
            {"w": "rápido", "s": 0.20, "e": 0.40},
        ]
        # chars=11, dur=0.4 → 27.5 cps → fail; ajustamos a un caso warn:
        words = [
            {"w": "texto", "s": 0.0, "e": 0.30},
            {"w": "rápido", "s": 0.32, "e": 0.62},
        ]
        issues = cap.audit_cues(self._events(words))
        sevs = {i["severity"] for i in issues}
        assert "warn" in sevs
        assert "fail" not in sevs


# ---------------------------------------------------------------------------
# Tests: _escape_ffmpeg_path
# ---------------------------------------------------------------------------

class TestEscapeFfmpegPath:
    """Tests de escape de rutas para el filtro subtitles= de ffmpeg."""

    def test_unix_path(self):
        """Ruta Unix sin cambios extraños."""
        result = cap._escape_ffmpeg_path("/tmp/test.ass")
        assert result == "'/tmp/test.ass'"

    def test_windows_backslash(self):
        """Backslashes se convierten a forward slashes."""
        result = cap._escape_ffmpeg_path("C:\\Users\\test\\file.ass")
        assert "\\\\" not in result
        assert "/" in result
        assert result.startswith("'")
        assert result.endswith("'")

    def test_windows_colon(self):
        """Dos-puntos se escapa como \\:."""
        result = cap._escape_ffmpeg_path("C:\\file.ass")
        assert "\\:" in result

    def test_single_quote(self):
        """Comilla simple se escapa como \\'.\""""
        result = cap._escape_ffmpeg_path("C:\\my file's.ass")
        assert "\\'" in result

    def test_full_windows_path(self):
        """Ruta Windows completa completa."""
        path = "C:\\Users\\otero\\test\\subtitle file.ass"
        result = cap._escape_ffmpeg_path(path)
        # Debe empezar y terminar con comillas simples
        assert result.startswith("'") and result.endswith("'")
        # No debe tener backslashes sin escapar (excepto los de escape)
        inner = result[1:-1]
        # Los \\: y \\' están bien, pero \\ normal no
        # Simplemente verificar que C: → C\:
        assert "C\\:" in inner


# ---------------------------------------------------------------------------
# Tests: _fmt_ass_time
# ---------------------------------------------------------------------------

class TestFmtAssTime:
    """Tests de formateo de tiempo ASS."""

    def test_zero(self):
        assert cap._fmt_ass_time(0.0) == "0:00:00.00"

    def test_one_second(self):
        assert cap._fmt_ass_time(1.0) == "0:00:01.00"

    def test_minutes(self):
        assert cap._fmt_ass_time(65.5) == "0:01:05.50"

    def test_hours(self):
        assert cap._fmt_ass_time(3661.25) == "1:01:01.25"

    def test_negative_clamped(self):
        assert cap._fmt_ass_time(-1.0) == "0:00:00.00"


# ---------------------------------------------------------------------------
# Tests: _quantize_frame
# ---------------------------------------------------------------------------

class TestQuantizeFrame:
    """Tests de cuantización a rejilla de frames."""

    def test_exact_frame(self):
        """1.0 a 30fps → 1.0 (exacto)."""
        assert cap._quantize_frame(1.0, 30.0) == 1.0

    def test_mid_frame(self):
        """0.5/30 = 0.01666... → round(0.5)/30 = 0.01666..."""
        result = cap._quantize_frame(0.5 / 30.0 + 0.001, 30.0)
        expected = round((0.5 / 30.0 + 0.001) * 30) / 30
        assert abs(result - expected) < 1e-9

    def test_roundtrip(self):
        """round(t*30)/30 produce múltiplos exactos de 1/30."""
        for t in [0.1, 0.5, 1.23, 3.456, 10.0]:
            qt = cap._quantize_frame(t, 30.0)
            residual = qt * 30 - round(qt * 30)
            assert abs(residual) < 1e-9


# ---------------------------------------------------------------------------
# Tests: build_plan
# ---------------------------------------------------------------------------

class TestBuildPlan:
    """Tests del plan de dry-run."""

    @pytest.fixture(autouse=True)
    def _require_ffmpeg(self):
        if shutil.which("ffmpeg") is None:
            pytest.skip("ffmpeg no encontrado en PATH")

    def _make_dummy_video(self, tmp: Path) -> Path:
        vid = tmp / "dummy.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "testsrc2=size=1080x1920:rate=30:duration=1",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                "-c:v", "libx264", "-crf", "28", "-preset", "ultrafast",
                "-c:a", "aac", "-shortest",
                str(vid),
            ],
            capture_output=True, timeout=30,
        )
        return vid

    def test_plan_contains_voxera(self, tmp_path: Path):
        """El plan contiene VOXERA PLAN."""
        vid = self._make_dummy_video(tmp_path)
        plan = cap.build_plan(str(vid))
        assert "VOXERA PLAN (video captions)" in plan
        assert "karaoke" in plan


# ---------------------------------------------------------------------------
# Tests: transcribe_words (unit mock — no network)
# ---------------------------------------------------------------------------

class TestTranscribeWords:
    """Tests de transcribe_words sin faster_whisper."""

    def test_missing_package_raises(self):
        """Si faster_whisper no está instalado, lanza EnhancementError."""
        # Este test solo tiene sentido si el paquete NO está instalado
        # en el entorno de test. Si está instalado, lo saltamos.
        try:
            from faster_whisper import WhisperModel  # noqa: F401
            pytest.skip("faster-whisper instalado — test de paquete faltante no aplica")
        except ImportError:
            with pytest.raises(EnhancementError, match="faster-whisper no instalado"):
                cap.transcribe_words("nonexistent.wav")


# ---------------------------------------------------------------------------
# Tests: integration (ffmpeg — no network)
# ---------------------------------------------------------------------------

class TestIntegration:
    """Tests de integración: words.json → ASS → burn-in con ffmpeg."""

    @pytest.fixture(autouse=True)
    def _require_ffmpeg(self):
        if shutil.which("ffmpeg") is None:
            pytest.skip("ffmpeg no encontrado en PATH")

    def _make_test_video(self, tmp: Path, duration: float = 2.0) -> Path:
        """Genera un vídeo de prueba con testsrc2."""
        vid = tmp / "test.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", f"testsrc2=size=1080x1920:rate=30:duration={duration}",
                "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
                "-c:v", "libx264", "-crf", "28", "-preset", "ultrafast",
                "-c:a", "aac", "-shortest",
                str(vid),
            ],
            capture_output=True, timeout=30,
        )
        assert vid.exists(), "No se pudo generar testsrc2"
        return vid

    def _make_words_json(self, tmp: Path, duration: float = 2.0) -> Path:
        """Crea un words.json de prueba."""
        words = [
            {"w": "Hola", "s": 0.20, "e": 0.60},
            {"w": "mundo", "s": 0.80, "e": 1.30},
            {"w": "prueba", "s": 1.50, "e": 2.00},
        ]
        # Ajustar para no exceder duration
        words = [w for w in words if w["e"] <= duration]
        wp = tmp / "words.json"
        wp.write_text(json.dumps({"words": words}), encoding="utf-8")
        return wp

    def test_burn_in_preserves_duration(self, tmp_path: Path):
        """Burn-in: duración ± 1 frame."""
        vid = self._make_test_video(tmp_path)
        words_json = self._make_words_json(tmp_path)
        out = tmp_path / "out.mp4"
        result = cap.captions_video(
            str(vid), str(out), words_json=str(words_json),
        )
        assert Path(result).exists()
        # Verificar duración con ffprobe
        from voxera import video_enhance as ve_mod
        probe_in = ve_mod.probe_video(vid)
        probe_out = ve_mod.probe_video(out)
        fps = probe_in["fps"] or 30.0
        frame_dur = 1.0 / fps
        assert abs(probe_out["duration_s"] - probe_in["duration_s"]) <= frame_dur * 1.5

    def test_ass_only_returns_file(self, tmp_path: Path):
        """ass_only devuelve el fichero ASS sin burn-in."""
        vid = self._make_test_video(tmp_path)
        words_json = self._make_words_json(tmp_path)
        ass_out = tmp_path / "subtitles.ass"
        result = cap.captions_video(
            str(vid), str(tmp_path / "unused.mp4"),
            words_json=str(words_json),
            ass_only=str(ass_out),
        )
        assert Path(result) == ass_out
        assert ass_out.exists()
        content = ass_out.read_text(encoding="utf-8")
        assert "[Script Info]" in content
        assert "Dialogue:" in content

    def test_karaoke_vs_static_output(self, tmp_path: Path):
        """karaoke tiene \\k, static no."""
        vid = self._make_test_video(tmp_path)
        words_json = self._make_words_json(tmp_path)

        out_k = tmp_path / "k.mp4"
        cap.captions_video(
            str(vid), str(out_k),
            words_json=str(words_json), style="karaoke",
            ass_only=str(tmp_path / "k.ass"),
        )
        ass_k = (tmp_path / "k.ass").read_text(encoding="utf-8")
        assert "\\k" in ass_k

        out_s = tmp_path / "s.mp4"
        cap.captions_video(
            str(vid), str(out_s),
            words_json=str(words_json), style="static",
            ass_only=str(tmp_path / "s.ass"),
        )
        ass_s = (tmp_path / "s.ass").read_text(encoding="utf-8")
        assert "\\k" not in ass_s
        assert "\\fad(80,80)" in ass_s

    def test_hooks_in_pipeline(self, tmp_path: Path):
        """La pipeline acepta hooks y los refleja en el ASS."""
        vid = self._make_test_video(tmp_path)
        words_json = self._make_words_json(tmp_path)
        ass_out = tmp_path / "hooks.ass"
        cap.captions_video(
            str(vid), str(tmp_path / "unused.mp4"),
            words_json=str(words_json),
            hooks=[{"text": "Ojo", "anchor": "mundo"}],
            ass_only=str(ass_out),
        )
        content = ass_out.read_text(encoding="utf-8")
        assert "Style: Hook" in content
        assert "OJO" in content

    def test_strict_qa_aborts(self, tmp_path: Path):
        """strict_qa aborta si algún cue supera el límite de lectura."""
        vid = self._make_test_video(tmp_path)
        wp = tmp_path / "fast.json"
        wp.write_text(json.dumps({"words": [
            {"w": "palabra", "s": 0.10, "e": 0.20},
            {"w": "larguísima", "s": 0.22, "e": 0.35},
        ]}), encoding="utf-8")
        with pytest.raises(EnhancementError, match="QA estricto"):
            cap.captions_video(
                str(vid), str(tmp_path / "out.mp4"),
                words_json=str(wp), strict_qa=True,
            )
