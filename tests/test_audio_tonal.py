"""Unit tests del módulo tonal (audio tonal): teoría, síntesis y mezcla.

Inventario:
- TestTheory        : note_to_midi/midi_to_freq/midi_to_name/scale_midi/triad,
                      SCALES con intervalos válidos, tabla MOODS (8 emociones).
- TestVoiceLeading  : best_voice_leading — mínimo movimiento Σ|Δ|, conserva
                      clase de altura, mismo largo; C→Am sin saltos > 3 st.
- TestSynth         : _osc (sine/triangle pico FFT en f0, saw/square con
                      anti-alias > 7 kHz, campana decae y exige t), _adsr
                      (attack 0 → sustain 1 → release 0, bounds), _normalize.
- TestTransition    : longitud dur·sr, pico FFT de la primera ventana cerca
                      de una voz del acorde A y de la última cerca del B,
                      determinismo bit-exacto, easings.
- TestRiser         : longitud (dur+tail)·sr, RMS por cuartiles PRE-HIT
                      monótono no-decreciente, estilo notes sube en general,
                      estilo glide > 2× (2 octavas), energía máxima justo
                      antes del hit (la cola decae), determinismo.
- TestMelody        : notas ∈ escala, primera y última == tónica, pregunta
                      (mitad) ≠ tónica, timing bars·4·60/bpm, campos de nota,
                      determinismo por seed, key/bpm override.
- TestMix           : mix_element — fuera de la región bit-exacto, ganancia
                      exacta con dry=0, duck -6 dB dentro pero NO en el borde
                      (fade 0.3 s), clip guard a [-1, 1].
- TestOptions       : validate() de Transition/Riser/MelodyOptions.
- TestPlan          : planes --dry-run con mood/key, riser hit=None resuelto
                      a la duración del archivo, colocación fuera → error.
- TestEndToEnd      : archivo 12 s PCM_16 → *_file: misma sr/duración, fuera
                      de la región ≈ input leído (cuantización), dentro difiere.
"""

import numpy as np
import pytest
import soundfile as sf

import tests.synth as s
from voxera import audio_tonal as at
from voxera.errors import EnhancementError

SR = 48000
SRQ = 24000  # sr de render rápido (los renders aceptan sr)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _rms(x):
    return float(np.sqrt(np.mean(np.asarray(x, dtype=np.float64) ** 2)))


def _fft_peak_hz(seg, sr, lo=60.0, hi=2000.0):
    """Frecuencia del máximo del espectro dentro de [lo, hi] Hz."""
    x = np.asarray(seg, dtype=np.float64)
    spec = np.abs(np.fft.rfft(x))
    f = np.fft.rfftfreq(len(x), 1.0 / sr)
    m = (f >= lo) & (f <= hi)
    return float(f[m][np.argmax(spec[m])])


def _sine(freq, n, sr, peak=0.5):
    t = np.arange(n, dtype=np.float64) / sr
    return (peak * np.sin(2.0 * np.pi * freq * t)).astype(np.float32)


# ---------------------------------------------------------------------------
# 1. Teoría musical
# ---------------------------------------------------------------------------


class TestTheory:
    def test_note_to_midi(self):
        assert at.note_to_midi("C", 4) == 60
        assert at.note_to_midi("A", 4) == 69
        assert at.note_to_midi("C#", 4) == 61
        assert at.note_to_midi("C#", 3) == 49
        assert at.note_to_midi("B", 0) == 23
        assert at.note_to_midi("C") == 60  # octava por defecto: 4

    def test_note_to_midi_invalid(self):
        for name in ("Db", "H", "c", ""):
            with pytest.raises(EnhancementError):
                at.note_to_midi(name, 4)
        for octave in (9, -1, 100):
            with pytest.raises(EnhancementError):
                at.note_to_midi("C", octave)

    def test_midi_to_freq(self):
        assert at.midi_to_freq(69) == pytest.approx(440.0, abs=1e-9)
        assert at.midi_to_freq(81) == pytest.approx(880.0, abs=1e-9)
        assert at.midi_to_freq(57) == pytest.approx(220.0, abs=1e-9)
        # temperamento igual: 1 octava arriba == 2x
        assert at.midi_to_freq(72) == pytest.approx(2.0 * at.midi_to_freq(60), rel=1e-12)

    def test_midi_to_name_roundtrip(self):
        assert at.midi_to_name(60) == "C4"
        assert at.midi_to_name(69) == "A4"
        assert at.midi_to_name(61) == "C#4"
        for m in range(36, 97):
            name = at.midi_to_name(m)
            note = name.rstrip("0123456789")
            octave = int(name[len(note):])
            assert at.note_to_midi(note, octave) == m

    def test_scale_midi_shape(self):
        major = at.scale_midi(60, "major", 2)
        assert len(major) == 2 * 7 + 1
        assert major[0] == 60 and major[-1] == 60 + 24
        assert np.all(np.diff(major) > 0)  # estrictamente ascendente
        assert major.dtype == np.dtype(int)
        penta = at.scale_midi(55, "pentatonic_minor", 3)
        assert len(penta) == 3 * 5 + 1 and penta[0] == 55
        with pytest.raises(EnhancementError):
            at.scale_midi(60, "gypsy")

    def test_scales_intervals_valid(self):
        for mode, intervals in at.SCALES.items():
            assert intervals[0] == 0
            assert all(b > a for a, b in zip(intervals, intervals[1:]))
            assert all(0 <= iv < 12 for iv in intervals)
            assert len(intervals) >= 5  # todas soportan triada (indices 0,2,4)

    def test_triad(self):
        assert at.triad_midi(60, "major") == (60, 64, 67)
        assert at.triad_midi(57, "minor") == (57, 60, 64)
        # pentatónica menor: "triada equivalente" cuartal 0-5-10
        assert at.triad_midi(60, "pentatonic_minor") == (60, 65, 70)

    def test_moods_table(self):
        assert len(at.MOODS) == 8
        assert set(at.MOODS) == {
            "hope", "tension", "melancholy", "triumph", "wonder", "calm", "mystery", "urgency"
        }
        contours = set()
        for name, spec in at.MOODS.items():
            assert spec.mode in at.SCALES, name
            assert spec.wave in at.TONAL_WAVES, name
            assert spec.contour in ("arch", "rise", "fall", "wave"), name
            assert 0.0 < spec.density <= 1.0, name
            assert spec.root in at.NOTE_NAMES, name
            assert 0 <= spec.octave <= 8, name
            assert 30 <= spec.bpm <= 300, name
            assert spec.detune_cents >= 0.0 and spec.vibrato_hz >= 0.0, name
            assert spec.attack >= 0.0 and spec.release >= 0.0, name
            assert isinstance(spec.doc, str) and spec.doc, name
            contours.add(spec.contour)
        assert contours == {"arch", "rise", "fall", "wave"}


# ---------------------------------------------------------------------------
# 2. Voice leading
# ---------------------------------------------------------------------------


class TestVoiceLeading:
    def test_c_major_to_a_minor_minimal_motion(self):
        a, b = (60, 64, 67), (57, 60, 64)  # C mayor → La menor
        v = at.best_voice_leading(a, b)
        moves = [abs(x - y) for x, y in zip(a, v)]
        assert sum(moves) == 2  # la mejor asignación: 2 semitonos en total
        assert max(moves) <= 3  # ninguna voz salta más de 3 semitonos
        # la suma es <= que cualquier rotación simple sin revozado
        naive = min(
            sum(abs(x - y) for x, y in zip(a, b[r:] + b[:r])) for r in range(3)
        )
        assert sum(moves) <= naive

    def test_shape_and_pitch_classes(self):
        cases = [
            ((60, 64, 67), (57, 60, 64)),
            ((62, 65, 69), (72, 76, 79)),
            ((60, 64, 67), (62, 66, 69)),
            ((55, 62, 66), (64, 68, 71)),
        ]
        for a, b in cases:
            v = at.best_voice_leading(a, b)
            assert isinstance(v, tuple) and len(v) == len(b) == len(a)
            # revozado: mismas clases de altura (mod 12), sin duplicar
            assert sorted(x % 12 for x in v) == sorted(x % 12 for x in b)

    def test_matches_brute_force_minimum(self):
        """La asignación devuelta alcanza el mínimo (Σ|Δ|, salto máximo) de
        todas las rotaciones × desplazamientos de octava — especificación."""
        import itertools

        cases = [
            ((60, 64, 67), (57, 60, 64)),
            ((62, 65, 69), (72, 76, 79)),
            ((64, 67, 71), (60, 63, 67)),
            ((48, 55, 60), (69, 72, 76)),
        ]
        for a, b in cases:
            v = at.best_voice_leading(a, b)
            got = (
                sum(abs(x - y) for x, y in zip(a, v)),
                max(abs(x - y) for x, y in zip(a, v)),
            )
            best = None
            for rot in range(len(b)):
                rotated = b[rot:] + b[:rot]
                for shifts in itertools.product((-12, 0, 12), repeat=len(b)):
                    voiced = tuple(ni + oi for ni, oi in zip(rotated, shifts))
                    key = (
                        sum(abs(x - y) for x, y in zip(a, voiced)),
                        max(abs(x - y) for x, y in zip(a, voiced)),
                    )
                    best = key if best is None else min(best, key)
            assert got == best


# ---------------------------------------------------------------------------
# 3. Síntesis (primitivas privadas)
# ---------------------------------------------------------------------------


class TestSynth:
    def test_sine_and_triangle_fft_peak(self):
        t = np.arange(SRQ, dtype=np.float64) / SRQ  # 1 s → resolución 1 Hz
        for wave in ("sine", "triangle"):
            x = at._osc(wave, 440.0, SRQ, t)
            assert _fft_peak_hz(x, SRQ, 20.0, 5000.0) == pytest.approx(440.0, abs=2.0)

    @pytest.mark.parametrize("wave", ["saw", "square"])
    def test_naive_waves_attenuated_above_7k(self, wave):
        # f0 bajo (220 Hz): más energía bajo 7 kHz que en la banda 8-16 kHz
        t = np.arange(SRQ, dtype=np.float64) / SRQ
        x = at._osc(wave, 220.0, SRQ, t).astype(np.float64)
        spec = np.abs(np.fft.rfft(x)) ** 2
        f = np.fft.rfftfreq(len(x), 1.0 / SRQ)
        lo = np.sqrt(spec[(f >= 100.0) & (f < 7000.0)].mean())
        hi = np.sqrt(spec[(f >= 8000.0) & (f < 11000.0)].mean())
        assert hi < 0.5 * lo, f"{wave}: hi={hi:.4f} lo={lo:.4f}"

    def test_bell_requires_t_and_decays(self):
        with pytest.raises(EnhancementError):
            at._osc("bell", 440.0, SRQ, None)
        n = 2 * SRQ  # 2 s: exp(-2.5t) deja la cola casi a cero
        t = np.arange(n, dtype=np.float64) / SRQ
        x = at._osc("bell", 440.0, SRQ, t)
        q = n // 4
        assert _rms(x[:q]) > 5.0 * _rms(x[-q:])  # el decay ES la envolvente

    def test_bad_wave_raises(self):
        t = np.arange(100, dtype=np.float64) / SRQ
        with pytest.raises(EnhancementError):
            at._osc("noise", 440.0, SRQ, t)

    def test_adsr_shape(self):
        n = int(1.0 * SRQ)
        env = at._adsr(n, SRQ, attack=0.05, release=0.3)
        assert len(env) == n and env.dtype == np.float32
        assert env.max() == pytest.approx(1.0, abs=1e-6)   # sustain == 1
        assert abs(env[0]) < 1e-6                          # attack arranca en 0
        assert abs(env[-1]) < 1e-3                         # release acaba en ~0
        assert env.min() >= 0.0 and env.max() <= 1.0
        mid = env[n // 2]
        assert mid == pytest.approx(1.0, abs=1e-6)
        # clamp: attack+release > n no explota y respeta bounds
        tiny = at._adsr(50, SRQ, attack=5.0, release=5.0)
        assert len(tiny) == 50 and tiny.min() >= 0.0 and tiny.max() <= 1.0

    def test_normalize(self):
        x = _sine(300.0, SRQ, SRQ, peak=0.137)
        y = at._normalize(x)
        assert np.max(np.abs(y)) == pytest.approx(0.5, abs=1e-6)
        y2 = at._normalize(x, peak=0.31)
        assert np.max(np.abs(y2)) == pytest.approx(0.31, abs=1e-6)
        z = at._normalize(np.zeros(64, np.float32))
        assert z.shape == (64,) and not z.any()


# ---------------------------------------------------------------------------
# 4. render_transition
# ---------------------------------------------------------------------------


class TestTransition:
    OPTS = at.TransitionOptions(dur=3.0)  # calm (D dorian) → hope (C lydian)

    def test_length_dtype_and_peak(self):
        el = at.render_transition(SRQ, self.OPTS)
        assert abs(len(el) - round(self.OPTS.dur * SRQ)) <= 1
        assert el.dtype == np.float32
        assert np.max(np.abs(el)) == pytest.approx(0.5, abs=1e-6)  # normalizado

    def test_first_window_near_chord_a(self):
        el = at.render_transition(SRQ, self.OPTS)
        _ma, _mb, _ra, _rb, chord_a, _bv = at._transition_chords(self.OPTS)
        seg = el[: int(0.2 * len(el))]  # primera ventana (≥ 0.5 s)
        peak = _fft_peak_hz(seg, SRQ, 60.0, 2000.0)
        voices = [at.midi_to_freq(float(m)) for m in chord_a]
        best = min(abs(peak - v) / v for v in voices)
        assert best <= 0.03, f"peak {peak:.1f} Hz lejos de {voices}"

    def test_last_window_near_chord_b(self):
        el = at.render_transition(SRQ, self.OPTS)
        _ma, _mb, _ra, _rb, _ca, b_voiced = at._transition_chords(self.OPTS)
        seg = el[-int(0.2 * len(el)):]
        peak = _fft_peak_hz(seg, SRQ, 60.0, 2000.0)
        voices = [at.midi_to_freq(float(m)) for m in b_voiced]
        best = min(abs(peak - v) / v for v in voices)
        assert best <= 0.03, f"peak {peak:.1f} Hz lejos de {voices}"

    def test_deterministic(self):
        a = at.render_transition(SRQ, self.OPTS)
        b = at.render_transition(SRQ, self.OPTS)
        assert np.array_equal(a, b)

    def test_easings_render(self):
        outs = {}
        for easing in at.TONAL_EASINGS:
            o = at.TransitionOptions(dur=3.0, easing=easing)
            el = at.render_transition(SRQ, o)
            assert abs(len(el) - 3 * SRQ) <= 1
            outs[easing] = el
        assert not np.array_equal(outs["smooth"], outs["linear"])


# ---------------------------------------------------------------------------
# 5. render_riser
# ---------------------------------------------------------------------------


class TestRiser:
    def test_length(self):
        o = at.RiserOptions(mood="tension", dur=2.0, tail=0.3)
        el = at.render_riser(SRQ, o)
        assert abs(len(el) - round((o.dur + o.tail) * SRQ)) <= 1
        # tail=0: el elemento acaba justo en el hit
        o0 = at.RiserOptions(mood="tension", dur=2.0, tail=0.0)
        assert abs(len(at.render_riser(SRQ, o0)) - round(o0.dur * SRQ)) <= 1

    @pytest.mark.parametrize("style", ["notes", "glide"])
    def test_quartile_rms_rises_to_hit(self, style):
        o = at.RiserOptions(mood="tension", dur=2.0, tail=0.3, style=style)
        el = at.render_riser(SRQ, o).astype(np.float64)
        n_hit = round(o.dur * SRQ)
        qs = [_rms(q) for q in np.array_split(el[:n_hit], 4)]
        assert all(b >= a - 1e-4 for a, b in zip(qs, qs[1:])), qs

    def test_notes_windows_rise_in_general(self):
        o = at.RiserOptions(mood="tension", dur=2.0, tail=0.3, style="notes")
        el = at.render_riser(SRQ, o)
        n_hit = round(o.dur * SRQ)
        w = int(0.28 * SRQ)
        peaks = [
            _fft_peak_hz(el[i * w:(i + 1) * w], SRQ, 60.0, 4000.0)
            for i in range(n_hit // w)
        ]
        rising = sum(1 for a, b in zip(peaks, peaks[1:]) if b > a)
        assert peaks[-1] > peaks[0], peaks          # sube de la 1ª a la última
        assert rising >= (len(peaks) - 1) // 2      # sube "en general"

    def test_glide_two_octaves(self):
        o = at.RiserOptions(mood="tension", dur=2.0, tail=0.3, style="glide")
        el = at.render_riser(SRQ, o)
        n_hit = round(o.dur * SRQ)
        w = int(0.2 * SRQ)
        first = _fft_peak_hz(el[:w], SRQ, 60.0, 4000.0)
        last = _fft_peak_hz(el[n_hit - w:n_hit], SRQ, 60.0, 4000.0)
        assert last > 2.0 * first, (first, last)

    @pytest.mark.parametrize("style", ["notes", "glide"])
    def test_energy_peaks_just_before_hit(self, style):
        o = at.RiserOptions(mood="tension", dur=2.0, tail=0.3, style=style)
        el = at.render_riser(SRQ, o).astype(np.float64)
        n_hit = round(o.dur * SRQ)
        pre = _rms(el[n_hit - int(0.3 * SRQ):n_hit])
        post = _rms(el[n_hit:])  # la cola decae tras el hit
        assert post < pre

    def test_deterministic(self):
        for style in ("notes", "glide"):
            o = at.RiserOptions(mood="tension", dur=2.0, tail=0.3, style=style)
            assert np.array_equal(at.render_riser(SRQ, o), at.render_riser(SRQ, o))


# ---------------------------------------------------------------------------
# 6. render_melody
# ---------------------------------------------------------------------------


class TestMelody:
    def test_scale_tonic_edges_and_question(self):
        o = at.MelodyOptions(mood="wonder", bars=4, seed=0)  # G5 pentatónica mayor
        el, notas = at.render_melody(SRQ, o)
        root = at.note_to_midi("G", 5)
        scale = set(at.scale_midi(root, "pentatonic_major", 2).tolist())
        assert all(nn["midi"] in scale for nn in notas)
        assert notas[0]["midi"] == root               # arranca en la tónica
        assert notas[-1]["midi"] in (root, root + 12)  # respuesta: tónica
        # pregunta: la última nota de la primera mitad NO es la tónica
        total_s = len(el) / SRQ
        q = max(
            (nn for nn in notas if nn["t_on"] < total_s / 2.0),
            key=lambda nn: nn["t_on"],
        )
        assert q["midi"] % 12 != root % 12

    def test_timing_and_note_fields(self):
        o = at.MelodyOptions(mood="wonder", bars=4, seed=0)
        el, notas = at.render_melody(SRQ, o)
        beat = 60.0 / 75.0  # bpm del mood wonder
        assert abs(len(el) / SRQ - 4 * 4 * beat) < beat  # ± 1 beat
        assert len(notas) >= 3
        t_ons = [nn["t_on"] for nn in notas]
        assert all(b > a for a, b in zip(t_ons, t_ons[1:]))  # estrictamente ascendente
        assert all(nn["dur"] > 0.0 for nn in notas)
        for nn in notas:
            assert nn["freq"] == pytest.approx(at.midi_to_freq(nn["midi"]), rel=1e-9)
            assert isinstance(nn["midi"], int) and isinstance(nn["degree"], int)

    def test_determinism(self):
        for mood, bars in (("wonder", 2), ("urgency", 4)):
            a, _ = at.render_melody(SRQ, at.MelodyOptions(mood=mood, bars=bars, seed=0))
            b, _ = at.render_melody(SRQ, at.MelodyOptions(mood=mood, bars=bars, seed=0))
            c, _ = at.render_melody(SRQ, at.MelodyOptions(mood=mood, bars=bars, seed=1))
            assert np.array_equal(a, b)       # mismo seed: bit-idéntico
            assert not np.array_equal(a, c)   # seed distinto: distinto

    def test_key_override(self):
        o = at.MelodyOptions(mood="wonder", key="A", bars=2, seed=0)
        _el, notas = at.render_melody(SRQ, o)
        root = at.note_to_midi("A", 5)  # octava del mood (5)
        assert notas[0]["midi"] == root
        scale = set(at.scale_midi(root, "pentatonic_major", 2).tolist())
        assert all(nn["midi"] in scale for nn in notas)

    def test_output_normalized(self):
        el, _n = at.render_melody(SRQ, at.MelodyOptions(mood="wonder", bars=2, seed=0))
        assert el.dtype == np.float32
        assert np.max(np.abs(el)) == pytest.approx(0.5, abs=1e-6)

    def test_bpm_override_changes_length(self):
        o = at.MelodyOptions(mood="wonder", bars=2, bpm=120.0, seed=0)
        el, _n = at.render_melody(SRQ, o)
        assert abs(len(el) / SRQ - 2 * 4 * 0.5) < 0.5  # 2 bars @ 120 bpm = 4 s


# ---------------------------------------------------------------------------
# 7. mix_element
# ---------------------------------------------------------------------------


class TestMix:
    def test_outside_region_bit_exact(self):
        sr = SRQ
        dry = _sine(300.0, int(4 * sr), sr)
        elem = _sine(500.0, int(1.5 * sr), sr)
        out = at.mix_element(dry, sr, elem, 1.0, -6.0)
        i0, i1 = round(1.0 * sr), round(1.0 * sr) + len(elem)
        assert np.array_equal(out[:i0], dry[:i0])
        assert np.array_equal(out[i1:], dry[i1:])
        assert len(out) == len(dry)

    def test_inside_gain_with_silent_dry(self):
        sr = SRQ
        dry = np.zeros(int(3 * sr), np.float32)
        elem = _sine(500.0, int(1.5 * sr), sr)  # pico exactamente 0.5
        for gain_db in (0.0, -6.0, -18.0):
            out = at.mix_element(dry, sr, elem, 1.0, gain_db)
            g = 10.0 ** (gain_db / 20.0)
            i0 = round(1.0 * sr)
            region = out[i0:i0 + len(elem)]
            assert np.max(np.abs(region)) == pytest.approx(0.5 * g, abs=1e-3)
            expect = (elem * g).astype(np.float32)
            assert np.allclose(region, expect, atol=1e-6)

    def test_duck_attenuates_inside_not_edges(self):
        sr = SRQ
        dry = _sine(271.0, int(5 * sr), sr)          # 271 Hz: borde nunca en cruce por 0
        elem = _sine(500.0, int(3 * sr), sr)
        at_s = 0.9
        plain = at.mix_element(dry, sr, elem, at_s, 0.0)
        ducked = at.mix_element(dry, sr, elem, at_s, 0.0, duck_db=6.0)
        assert np.array_equal(plain, at.mix_element(dry, sr, elem, at_s, 0.0, duck_db=0.0))
        i0 = round(at_s * sr)
        # borde: la primera muestra NO está ducked (fade 0.3 s) y elem[0]==0
        assert abs(float(ducked[i0]) - float(dry[i0])) <= 1e-6
        # centro de la región: el seco queda ~6 dB por debajo
        mid = slice(i0 + int(0.5 * sr), i0 + int(2.0 * sr))
        dry_only = ducked[mid].astype(np.float64) - elem[mid].astype(np.float64)
        db = 20.0 * np.log10(_rms(dry_only) / (_rms(dry[mid]) + 1e-12))
        assert db == pytest.approx(-6.0, abs=0.5), db

    def test_clip_guard(self):
        sr = SRQ
        dry = np.full(int(2 * sr), 0.9, np.float32)
        elem = np.full(int(1 * sr), 0.8, np.float32)  # 0.9 + 0.8·1.0 > 1
        out = at.mix_element(dry, sr, elem, 0.5, 0.0)
        assert np.max(np.abs(out)) <= 1.0
        i0 = round(0.5 * sr)
        assert np.array_equal(out[:i0], dry[:i0])  # fuera intacto
        assert np.all(out[i0:i0 + len(elem)] == 1.0)  # clipeado exacto a +1

    def test_at_negative_and_empty_element(self):
        with pytest.raises(EnhancementError):
            at.mix_element(np.zeros(100, np.float32), SRQ, np.zeros(10, np.float32), -1.0, 0.0)
        dry = _sine(300.0, 1000, SRQ)
        out = at.mix_element(dry, SRQ, np.zeros(0, np.float32), 0.5, -6.0)
        assert np.array_equal(out, dry)  # elemento vacío: passthrough


# ---------------------------------------------------------------------------
# 8. Options.validate()
# ---------------------------------------------------------------------------


class TestOptions:
    def test_transition_bad_moods(self):
        with pytest.raises(EnhancementError):
            at.TransitionOptions(from_mood="nope").validate()
        with pytest.raises(EnhancementError):
            at.TransitionOptions(to_mood="nope").validate()

    def test_transition_bad_keys(self):
        with pytest.raises(EnhancementError):
            at.TransitionOptions(from_key="Db").validate()
        with pytest.raises(EnhancementError):
            at.TransitionOptions(to_key="H").validate()

    def test_transition_bad_dur_at_gain_curve_easing(self):
        for dur in (0.2, 31.0):
            with pytest.raises(EnhancementError):
                at.TransitionOptions(dur=dur).validate()
        with pytest.raises(EnhancementError):
            at.TransitionOptions(at=-1.0).validate()
        with pytest.raises(EnhancementError):
            at.TransitionOptions(gain_db=3.0).validate()
        with pytest.raises(EnhancementError):
            at.TransitionOptions(curve=101.0).validate()
        with pytest.raises(EnhancementError):
            at.TransitionOptions(easing="snap").validate()

    def test_riser_bad_options(self):
        with pytest.raises(EnhancementError):  # hit < dur
            at.RiserOptions(hit=1.0, dur=2.0).validate()
        for kwargs in (
            dict(style="fuga"),
            dict(tail=-1.0),
            dict(tail=6.0),
            dict(mood="nope"),
            dict(dur=0.2),
            dict(gain_db=1.0),
        ):
            with pytest.raises(EnhancementError):
                at.RiserOptions(**kwargs).validate()

    def test_melody_bad_bars_bpm_start(self):
        for bars in (0, 99):
            with pytest.raises(EnhancementError):
                at.MelodyOptions(bars=bars).validate()
        for bpm in (10.0, 999.0):
            with pytest.raises(EnhancementError):
                at.MelodyOptions(bpm=bpm).validate()
        with pytest.raises(EnhancementError):
            at.MelodyOptions(start=-1.0).validate()

    def test_melody_bad_duck_and_gain_and_seed_ok(self):
        with pytest.raises(EnhancementError):
            at.MelodyOptions(duck_db=-1.0).validate()
        with pytest.raises(EnhancementError):
            at.MelodyOptions(duck_db=30.0).validate()
        with pytest.raises(EnhancementError):
            at.MelodyOptions(gain_db=3.0).validate()
        for seed in (-12345, 0, 7, 999999):  # cualquier int es válido
            at.MelodyOptions(seed=seed).validate()


# ---------------------------------------------------------------------------
# 9. Planes --dry-run
# ---------------------------------------------------------------------------


class TestPlan:
    @pytest.fixture()
    def wav(self, tmp_path):
        p = tmp_path / "in.wav"
        sf.write(p, s.speech_like(4.0), SR, subtype="PCM_16")
        return p

    def test_transition_plan_contract(self, wav):
        plan = at.build_transition_plan(wav, at.TransitionOptions(dur=1.0, at=0.2))
        assert plan.startswith("VOXERA PLAN (audio transition)")
        assert "calm" in plan and "hope" in plan
        assert "dorian" in plan and "lydian" in plan
        assert "movimiento mínimo" in plan

    def test_riser_plan_resolves_hit_none(self, wav):
        # hit=None → hit = duración - tail: no explota y lo muestra
        plan = at.build_riser_plan(wav, at.RiserOptions(dur=1.0, tail=0.2))
        assert plan.startswith("VOXERA PLAN (audio riser)")
        assert "tension" in plan and "phrygian" in plan
        assert "t=3.80 s" in plan  # 4.0 s de archivo - 0.2 de cola

    def test_melody_plan_contract(self, wav):
        plan = at.build_melody_plan(wav, at.MelodyOptions(bars=1, seed=0))
        assert plan.startswith("VOXERA PLAN (audio melody)")
        assert "wonder" in plan and "G" in plan
        assert "notas" in plan

    def test_plan_placement_out_of_file_raises(self, wav):
        # (build_riser_plan no valida la colocación: solo informativo)
        with pytest.raises(EnhancementError):
            at.build_transition_plan(wav, at.TransitionOptions(at=999.0))
        with pytest.raises(EnhancementError):
            at.build_melody_plan(wav, at.MelodyOptions(start=999.0, bpm=300.0))


# ---------------------------------------------------------------------------
# 10. E2E a archivo
# ---------------------------------------------------------------------------


class TestEndToEnd:
    @pytest.fixture()
    def inp(self, tmp_path):
        p = tmp_path / "in.wav"
        sf.write(p, s.speech_like(12.0), SR, subtype="PCM_16")
        return p

    @staticmethod
    def _read(path):
        y, sr = sf.read(path, dtype="float32")
        return y, sr

    def test_transition_file(self, tmp_path, inp):
        opts = at.TransitionOptions(at=1.0, dur=3.0, gain_db=-18.0)
        out = tmp_path / "out.wav"
        at.transition_file(inp, out, opts)
        assert out.exists()
        y, sr = self._read(out)
        x, xsr = self._read(inp)
        assert sr == xsr == SR and len(y) == len(x)
        # fuera de la región: idéntico al input LEÍDO (tolerancia PCM_16)
        a0, a1 = round(1.0 * SR), round(4.0 * SR)
        assert np.allclose(y[: a0 - 100], x[: a0 - 100], atol=1e-4)
        assert np.allclose(y[a1 + 100:], x[a1 + 100:], atol=1e-4)
        # dentro: el elemento está presente
        assert np.max(np.abs(y[a0 + 100 : a1 - 100] - x[a0 + 100 : a1 - 100])) > 1e-3

    def test_riser_file(self, tmp_path, inp):
        opts = at.RiserOptions(dur=2.0, tail=0.3, hit=5.0, gain_db=-16.0)
        out = tmp_path / "out.wav"
        at.riser_file(inp, out, opts)
        y, sr = self._read(out)
        x, _xsr = self._read(inp)
        assert sr == SR and len(y) == len(x)
        t0, t1 = round(3.0 * SR), round(5.3 * SR)  # región [hit-dur, hit+tail]
        assert np.allclose(y[: t0 - 100], x[: t0 - 100], atol=1e-4)
        assert np.allclose(y[t1 + 100:], x[t1 + 100:], atol=1e-4)
        assert np.max(np.abs(y[t0 + 100 : t1 - 100] - x[t0 + 100 : t1 - 100])) > 1e-3
        # hit=None: resuelto al final del archivo (t0 = 12 - 0.3 - 2.0 = 9.7)
        out2 = tmp_path / "out2.wav"
        at.riser_file(inp, out2, at.RiserOptions(dur=2.0, tail=0.3, gain_db=-16.0))
        y2, sr2 = self._read(out2)
        assert out2.exists() and sr2 == SR and len(y2) == len(x)
        assert np.allclose(y2[: round(9.7 * SR) - 100], x[: round(9.7 * SR) - 100], atol=1e-4)

    def test_melody_file(self, tmp_path, inp):
        opts = at.MelodyOptions(start=1.0, bars=2, seed=3, gain_db=-20.0)  # 8 s @ 75 bpm
        out = tmp_path / "out.wav"
        at.melody_file(inp, out, opts)
        y, sr = self._read(out)
        x, _xsr = self._read(inp)
        assert sr == SR and len(y) == len(x)
        a0, a1 = round(1.0 * SR), round(9.0 * SR)
        assert np.allclose(y[: a0 - 100], x[: a0 - 100], atol=1e-4)
        assert np.allclose(y[a1 + 100:], x[a1 + 100:], atol=1e-4)
        assert np.max(np.abs(y[a0 + 100 : a1 - 100] - x[a0 + 100 : a1 - 100])) > 1e-3

    def test_placement_beyond_file_raises(self, tmp_path, inp):
        out = tmp_path / "nope.wav"
        with pytest.raises(EnhancementError):
            at.transition_file(inp, out, at.TransitionOptions(at=999.0))
        with pytest.raises(EnhancementError):
            at.riser_file(inp, out, at.RiserOptions(dur=1.0, hit=999.0))
        with pytest.raises(EnhancementError):
            at.melody_file(inp, out, at.MelodyOptions(start=999.0, bpm=300.0))
