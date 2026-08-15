"""Unit tests del efecto "Pase Bajo" (audio lowpass): numpy/scipy, sin Premiere.

- Curva de easing: monotónica, bounded, curve=0 => lineal (misma convención
  que video zoom).
- Envolvente wet (rampas S en los bordes de la región): full/blip/on/off,
  regiones cortas, transition=0 (paso abrupto).
- Filtro Butterworth: atenuación real medida en la banda aguda (~12 dB/oct
  con order 2), paso bajo preservado, rechazo de nyquist.
- Plan --dry-run y validación de opciones.
- E2E: ruido blanco + región blip -> fuera de la región bit-exacto, dentro
  atenuado, y la envolvente de energía en la rampa sigue la curva S.
"""

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

import tests.synth as s
from voxera import audio_lowpass as al
from voxera.errors import EnhancementError

SR = 48000


class TestEase:
    def test_bounds_and_monotonic(self):
        ps = np.linspace(0, 1, 51)
        for easing in al.LP_EASINGS:
            vals = [al.ease(p, 62, easing) for p in ps]
            assert all(0.0 <= v <= 1.0 for v in vals)
            assert all(b >= a - 1e-12 for a, b in zip(vals, vals[1:]))

    def test_curve_zero_is_linear(self):
        for p in (0.1, 0.25, 0.5, 0.7, 0.9):
            assert al.ease(p, 0, "smooth") == pytest.approx(p, abs=1e-12)
            assert al.ease(p, 0, "out") == pytest.approx(p, abs=1e-12)

    def test_endpoints(self):
        assert al.ease(0.0) == 0.0
        assert al.ease(1.0) == 1.0

    def test_linear_passthrough(self):
        for p in (0.2, 0.6, 0.9):
            assert al.ease(p, 80, "linear") == pytest.approx(p)

    def test_ease_vectorized_matches_scalar(self):
        ps = np.linspace(0, 1, 101, dtype=np.float32)
        arr = al.ease(ps)
        assert arr.shape == ps.shape and arr.dtype == np.float32
        for i in range(0, 101, 10):
            assert arr[i] == pytest.approx(al.ease(float(ps[i])), abs=1e-6)

    def test_default_matches_tutorial_range(self):
        # curva 60-65: S marcada — al 25% de la rampa casi nada, al 75% casi todo
        assert al.ease(0.25, 62) < 0.05
        assert al.ease(0.75, 62) > 0.95


class TestOptions:
    def test_defaults(self):
        o = al.LowPassOptions()
        assert o.cutoff == 800.0
        assert o.transition == 1.0
        assert o.curve == 62.0
        assert o.easing == "smooth"
        assert o.order == 2
        assert o.resonance is None
        assert o.occlusion == 0.0
        assert o.shelf == 250.0

    def test_bad_cutoff(self):
        for c in (10, 25000):
            with pytest.raises(EnhancementError):
                al.LowPassOptions(cutoff=c).validate()

    def test_bad_transition(self):
        for t in (-0.5, 61):
            with pytest.raises(EnhancementError):
                al.LowPassOptions(transition=t).validate()

    def test_bad_curve(self):
        with pytest.raises(EnhancementError):
            al.LowPassOptions(curve=120).validate()

    def test_bad_easing(self):
        with pytest.raises(EnhancementError):
            al.LowPassOptions(easing="jump").validate()

    def test_bad_order(self):
        with pytest.raises(EnhancementError):
            al.LowPassOptions(order=3).validate()

    def test_bad_resonance(self):
        for r in (0.4, 2.5):
            with pytest.raises(EnhancementError):
                al.LowPassOptions(resonance=r).validate()

    def test_resonance_needs_order_2_or_4(self):
        with pytest.raises(EnhancementError):
            al.LowPassOptions(resonance=1.1, order=1).validate()

    def test_bad_occlusion(self):
        for db in (-1.0, 13.0):
            with pytest.raises(EnhancementError):
                al.LowPassOptions(occlusion=db).validate()

    def test_bad_shelf(self):
        for f in (30.0, 5000.0):
            with pytest.raises(EnhancementError):
                al.LowPassOptions(occlusion=3.0, shelf=f).validate()

    def test_bad_seg(self):
        with pytest.raises(EnhancementError):
            al.LowPassOptions(start=5.0, end=5.0).validate()
        with pytest.raises(EnhancementError):
            al.LowPassOptions(start=5.0, end=4.0).validate()
        with pytest.raises(EnhancementError):
            al.LowPassOptions(start=-1.0).validate()
        with pytest.raises(EnhancementError):
            al.LowPassOptions(end=0.0).validate()


class TestEnvelope:
    def test_full_mode_edge_ramps(self):
        env = al.build_envelope(int(SR * 6), SR, al.LowPassOptions(transition=1.0))
        t = np.arange(len(env)) / SR
        assert abs(env[0]) < 1e-6 and abs(env[-1]) < 1e-6
        assert env[int(0.5 * SR)] == pytest.approx(0.5, abs=1e-4)  # ease(0.5)=0.5
        assert env[int(3.0 * SR)] == 1.0
        assert env[int(5.5 * SR)] == pytest.approx(0.5, abs=1e-4)

    def test_blip_mode(self):
        env = al.build_envelope(
            int(SR * 6), SR, al.LowPassOptions(start=1.0, end=5.0, transition=1.0)
        )
        t = np.arange(len(env)) / SR
        assert env[int(0.5 * SR)] == 0.0
        assert env[int(1.5 * SR)] == pytest.approx(0.5, abs=1e-4)
        assert env[int(3.0 * SR)] == 1.0
        assert env[int(4.5 * SR)] == pytest.approx(0.5, abs=1e-4)
        assert env[int(5.5 * SR)] == 0.0
        # dentro de [a+τ, b-τ] siempre 1
        seg = env[(t >= 2.5) & (t <= 3.5)]
        assert (seg == 1.0).all()

    def test_on_mode(self):
        env = al.build_envelope(
            int(SR * 6), SR, al.LowPassOptions(start=2.0, transition=1.0)
        )
        t = np.arange(len(env)) / SR
        assert env[int(1.0 * SR)] == 0.0
        assert env[int(2.5 * SR)] == pytest.approx(0.5, abs=1e-4)
        assert env[int(4.0 * SR)] == 1.0
        # el filtro entra y se queda: sin rampa de salida en el borde del archivo
        assert env[-1] == 1.0

    def test_off_mode(self):
        env = al.build_envelope(
            int(SR * 6), SR, al.LowPassOptions(end=4.0, transition=1.0)
        )
        t = np.arange(len(env)) / SR
        # el clip empieza filtrado: sin rampa de entrada en t=0
        assert env[0] == 1.0
        assert env[int(1.0 * SR)] == 1.0
        assert env[int(3.5 * SR)] == pytest.approx(0.5, abs=1e-4)
        assert env[int(5.0 * SR)] == 0.0

    def test_short_region_peaks_below_one(self):
        # región más corta que 2*transition: las rampas se cruzan sin superar 1
        env = al.build_envelope(
            int(SR * 6), SR, al.LowPassOptions(start=2.0, end=3.0, transition=1.0)
        )
        assert env.max() < 1.0
        assert env.min() == 0.0
        assert 0.0 < env.max() <= 1.0

    def test_zero_transition_is_step(self):
        env = al.build_envelope(
            int(SR * 6), SR, al.LowPassOptions(start=2.0, end=4.0, transition=0.0)
        )
        t = np.arange(len(env)) / SR
        assert env[int(1.9 * SR)] == 0.0
        assert env[int(2.1 * SR)] == 1.0
        assert env[int(3.9 * SR)] == 1.0
        assert env[int(4.1 * SR)] == 0.0

    def test_linear_curve_ramps(self):
        env = al.build_envelope(
            int(SR * 6), SR, al.LowPassOptions(start=1.0, end=5.0, transition=1.0, curve=0.0)
        )
        # con curva 0 la rampa es lineal: al 25% de la rampa, 0.25
        assert env[int(1.25 * SR)] == pytest.approx(0.25, abs=1e-4)
        assert env[int(4.75 * SR)] == pytest.approx(0.25, abs=1e-4)

    def test_dtype_and_range(self):
        env = al.build_envelope(int(SR * 3), SR, al.LowPassOptions(transition=0.5))
        assert env.dtype == np.float32
        assert env.min() >= 0.0 and env.max() <= 1.0


def _band_rms(x, sr, lo, hi):
    from scipy.signal import stft

    f, t, Z = stft(x, fs=sr, nperseg=1024, noverlap=768, boundary=None)
    P = np.abs(Z) ** 2
    m = (f >= lo) & (f < hi)
    return np.sqrt(P[m, :].mean(axis=0))


class TestFilter:
    def test_cutoff_at_nyquist_raises(self):
        with pytest.raises(EnhancementError):
            al.apply_lowpass(np.zeros(100, np.float32), SR, al.LowPassOptions(cutoff=SR / 2))

    @staticmethod
    def _sine(freq, dur=5.0, peak=0.5):
        t = np.arange(int(SR * dur), dtype=np.float64) / SR
        return (peak * np.sin(2 * np.pi * freq * t)).astype(np.float32)

    @staticmethod
    def _steady_gain_db(x, y, tail=1.0):
        n = int(SR * tail)
        return 20 * np.log10(np.sqrt((y[-n:] ** 2).mean()) / (np.sqrt((x[-n:] ** 2).mean()) + 1e-12))

    def test_resonance_peaks_at_cutoff(self):
        # para el biquad RBJ, |H(f0)| == Q: Q>0.707 => ganancia > 0 dB en el cutoff
        x = self._sine(800.0)
        y = al.apply_lowpass(x, SR, al.LowPassOptions(transition=0.0, resonance=1.2))
        assert self._steady_gain_db(x, y) == pytest.approx(20 * np.log10(1.2), abs=0.4)

    def test_butterworth_gain_at_cutoff(self):
        # Butterworth (default): -3 dB exactos en el cutoff
        x = self._sine(800.0)
        y = al.apply_lowpass(x, SR, al.LowPassOptions(transition=0.0))
        assert self._steady_gain_db(x, y) == pytest.approx(-3.0, abs=0.4)

    def test_resonance_q_butterworth_matches_default(self):
        # Q=0.707 == Butterworth: misma respuesta (no bit-igual; el path None
        # es el legado bit-igual, este es el biquad RBJ numéricamente cercano)
        rng = np.random.default_rng(0)
        x = rng.standard_normal(int(SR * 3)).astype(np.float32)
        a = al.apply_lowpass(x, SR, al.LowPassOptions(transition=0.0))
        b = al.apply_lowpass(x, SR, al.LowPassOptions(transition=0.0, resonance=al.Q_BUTTERWORTH))
        assert np.allclose(a, b, atol=1e-3)

    def test_resonance_order4_cascades(self):
        # order 4 + resonance: pendiente ~24 dB/oct en la banda aguda
        rng = np.random.default_rng(1)
        x = rng.standard_normal(int(SR * 4)).astype(np.float32)
        out = al.apply_lowpass(x, SR, al.LowPassOptions(order=4, resonance=1.1, transition=0.0))
        hi_in = _band_rms(x, SR, 3000, 8000).mean()
        hi_out = _band_rms(out, SR, 3000, 8000).mean()
        drop = 20 * np.log10(hi_out / (hi_in + 1e-12))
        assert drop < -40, f"measured {drop:.1f} dB"

    def test_occlusion_shelf_boosts_lows_only(self):
        # shelf +6 dB @ 250 Hz (S=1): 100 Hz sube ~6 dB, 5 kHz se queda
        sos = al._rbj_lowshelf_sos(6.0, 250.0, SR)
        from scipy.signal import sosfilt

        x100 = self._sine(100.0)
        y100 = sosfilt(sos, x100)
        assert self._steady_gain_db(x100, y100) == pytest.approx(6.0, abs=0.4)
        x5k = self._sine(5000.0)
        y5k = sosfilt(sos, x5k)
        assert self._steady_gain_db(x5k, y5k) == pytest.approx(0.0, abs=0.4)

    def test_occlusion_zero_is_bit_identical(self):
        rng = np.random.default_rng(2)
        x = rng.standard_normal(int(SR * 3)).astype(np.float32)
        a = al.apply_lowpass(x, SR, al.LowPassOptions(transition=0.0))
        b = al.apply_lowpass(x, SR, al.LowPassOptions(transition=0.0, occlusion=0.0, shelf=250.0))
        assert np.array_equal(a, b)

    def test_occlusion_boosts_low_band_of_wet(self):
        # integración: con oclusión, la banda grave del húmedo sube vs sin oclusión
        rng = np.random.default_rng(3)
        x = rng.standard_normal(int(SR * 4)).astype(np.float32)
        base = al.apply_lowpass(x, SR, al.LowPassOptions(transition=0.0))
        occ = al.apply_lowpass(x, SR, al.LowPassOptions(transition=0.0, occlusion=6.0))
        lo_base = _band_rms(base, SR, 100, 400).mean()
        lo_occ = _band_rms(occ, SR, 100, 400).mean()
        assert 20 * np.log10(lo_occ / (lo_base + 1e-12)) > 3.0

    def test_occlusion_clip_guard(self):
        # material a full scale + oclusión fuerte: nunca sale de [-1, 1]
        x = self._sine(100.0, dur=2.0, peak=0.95)
        out = al.apply_lowpass(x, SR, al.LowPassOptions(transition=0.0, occlusion=12.0))
        assert np.abs(out).max() <= 1.0

    def test_region_outside_bit_exact_with_extras(self):
        # con resonance+occlusion, fuera de la región sigue siendo bit-exacto
        rng = np.random.default_rng(4)
        x = (0.5 * rng.standard_normal(int(SR * 6))).astype(np.float32)
        out = al.apply_lowpass(
            x, SR, al.LowPassOptions(start=2.0, end=4.0, resonance=1.2, occlusion=6.0)
        )
        assert np.array_equal(out[: int(2.0 * SR)], x[: int(2.0 * SR)])
        assert np.array_equal(out[int(4.0 * SR):], x[int(4.0 * SR):])

    @pytest.mark.parametrize("order,min_db", [(1, 12), (2, 26), (4, 50)])
    def test_high_band_attenuation(self, order, min_db):
        rng = np.random.default_rng(0)
        x = rng.standard_normal(int(SR * 4)).astype(np.float32)
        out = al.apply_lowpass(x, SR, al.LowPassOptions(order=order, transition=0.0))
        hi_in = _band_rms(x, SR, 3000, 8000).mean()
        hi_out = _band_rms(out, SR, 3000, 8000).mean()
        drop = 20 * np.log10(hi_out / (hi_in + 1e-12))
        assert drop < -min_db, f"order {order}: measured {drop:.1f} dB"

    def test_low_band_preserved(self):
        rng = np.random.default_rng(1)
        x = rng.standard_normal(int(SR * 4)).astype(np.float32)
        out = al.apply_lowpass(x, SR, al.LowPassOptions(transition=0.0))
        lo_in = _band_rms(x, SR, 100, 400).mean()
        lo_out = _band_rms(out, SR, 100, 400).mean()
        assert abs(20 * np.log10(lo_out / lo_in)) < 1.5


class TestPlan:
    def test_plan_contract(self, tmp_path):
        wav = tmp_path / "in.wav"
        sf.write(wav, s.sibilant(1.0), SR)
        plan = al.build_plan(wav, al.LowPassOptions(start=0.2, end=0.8))
        assert plan.startswith("VOXERA PLAN (audio lowpass)")
        assert "800" in plan and "blip" in plan
        assert "0.20s .. 0.80s" in plan
        assert "oclusión: off" in plan

    def test_plan_shows_extras(self, tmp_path):
        wav = tmp_path / "in.wav"
        sf.write(wav, s.sibilant(1.0), SR)
        plan = al.build_plan(
            wav, al.LowPassOptions(resonance=1.2, occlusion=6.0)
        )
        assert "Q=1.2" in plan
        assert "+6 dB @ 250 Hz" in plan

    def test_plan_bad_opts_raises(self, tmp_path):
        wav = tmp_path / "in.wav"
        sf.write(wav, s.sibilant(1.0), SR)
        with pytest.raises(EnhancementError):
            al.build_plan(wav, al.LowPassOptions(cutoff=99999))


class TestEndToEnd:
    def _write(self, tmp_path, x, name="in.wav"):
        p = tmp_path / name
        sf.write(p, x, SR)
        return p

    @staticmethod
    def _noise(n, seed):
        rng = np.random.default_rng(seed)
        x = rng.standard_normal(n).astype(np.float32)
        return (0.8 * x / (np.abs(x).max() + 1e-12)).astype(np.float32)

    def test_region_bit_exact_outside_and_attenuated_inside(self, tmp_path):
        x = self._noise(int(SR * 6), 2)
        inp = self._write(tmp_path, x)
        out = al.lowpass_file(inp, tmp_path / "out.wav", al.LowPassOptions(start=2.0, end=4.0))
        y, sr = sf.read(out, dtype="float32")
        assert sr == SR and len(y) == len(x)
        # a nivel de módulo, fuera de la región la salida es bit-exacta
        y_mod = al.apply_lowpass(x, SR, al.LowPassOptions(start=2.0, end=4.0))
        assert np.array_equal(y_mod[: int(2.0 * SR)], x[: int(2.0 * SR)])
        assert np.array_equal(y_mod[int(4.0 * SR):], x[int(4.0 * SR):])
        # a nivel de archivo: misma cuantización que la entrada leída (~1e-7)
        x_in, _ = sf.read(inp, dtype="float32")
        assert np.allclose(y[: int(2.0 * SR)], x_in[: int(2.0 * SR)], atol=1e-6)
        assert np.allclose(y[int(4.0 * SR):], x_in[int(4.0 * SR):], atol=1e-6)
        # dentro: la banda aguda cae
        hi_in = _band_rms(x[int(2.5 * SR): int(3.5 * SR)], SR, 3000, 8000).mean()
        hi_out = _band_rms(y[int(2.5 * SR): int(3.5 * SR)], SR, 3000, 8000).mean()
        assert 20 * np.log10(hi_out / (hi_in + 1e-12)) < -20

    def test_region_beyond_file_raises(self, tmp_path):
        wav = tmp_path / "in.wav"
        sf.write(wav, s.sibilant(1.0), SR)
        with pytest.raises(EnhancementError):
            al.build_plan(wav, al.LowPassOptions(start=5.0))
        with pytest.raises(EnhancementError):
            al.lowpass_file(wav, tmp_path / "o.wav", al.LowPassOptions(end=5.0))

    def test_ramp_follows_s_curve(self, tmp_path):
        x = self._noise(int(SR * 4), 3)
        inp = self._write(tmp_path, x)
        out = al.lowpass_file(inp, tmp_path / "out.wav", al.LowPassOptions(start=1.0, end=3.0))
        y, _ = sf.read(out, dtype="float32")
        # envolvente de energía 4-8 kHz en la rampa de entrada (1.0-2.0 s),
        # normalizada, debe seguir ease() (S-curva, curva 62)
        f, t, Z = __import__("scipy.signal", fromlist=["stft"]).stft(
            y, fs=SR, nperseg=512, noverlap=384, boundary=None
        )
        P = np.abs(Z) ** 2
        m = (f >= 4000) & (f < 8000)
        env = np.sqrt(P[m, :].mean(axis=0))
        win = (t >= 1.0) & (t <= 2.0)
        seg = env[win]
        seg = (seg.max() - seg) / (seg.max() - seg.min() + 1e-12)  # la energía cae al entrar el filtro
        ts = (t[win] - 1.0) / 1.0
        expected = np.array([al.ease(p) for p in ts])
        corr = np.corrcoef(seg, expected)[0, 1]
        assert corr > 0.9, f"ramp correlation {corr:.3f}"

    def test_cli_dry_run(self, tmp_path):
        import subprocess
        import sys

        inp = self._write(tmp_path, s.sibilant(1.0))
        env = dict(__import__("os").environ)
        root = Path(__file__).resolve().parent.parent
        env["PYTHONPATH"] = str(root / "src")
        proc = subprocess.run(
            [sys.executable, "-m", "voxera.cli", "audio", "lowpass", str(inp),
             "-o", str(tmp_path / "out.wav"), "--dry-run"],
            capture_output=True, text=True, env=env,
        )
        assert proc.returncode == 0, proc.stderr
        assert "VOXERA PLAN (audio lowpass)" in proc.stdout
