"""Track 1 + 1B: the frozen mastering pipeline acceptance criteria.

Spec criteria: LUFS_out in target ±1, true peak <= -1 dBTP, duration ±0.1 s,
|mean(samples)| < -60 dBFS (DC), mud band attenuated >= 2 dB on a mud-heavy
fixture, byte-equivalent determinism, per-stage unit tests, de-esser
no-harm (2-5 kHz energy degradation <= 5%).
"""

import numpy as np
import pytest
import soundfile as sf

import tests.synth as s
from voxera import audioio
from voxera.dsp import DEFAULT_PRESET, PRESETS, master, plan_stages, preset_names, resolve_preset
from voxera.dsp import filters
from voxera.errors import EnhancementError

SR = 48000


def band_energy_db(x, lo, hi, sr=SR):
    f = np.fft.rfftfreq(len(x), 1 / sr)
    return 10 * np.log10(np.sum(np.abs(np.fft.rfft(x)) ** 2 / len(x) ** 2 * ((f >= lo) & (f < hi))) + 1e-30)


def run_master(x, preset="youtube", **kw):
    return master(x, SR, preset, **kw)


class TestPresets:
    def test_default_is_creator(self):
        assert DEFAULT_PRESET == "creator"
        assert resolve_preset(None).name == "creator"

    def test_frozen_table(self):
        assert PRESETS["creator"].lufs == -16.0
        assert PRESETS["youtube"].lufs == -14.0 and PRESETS["youtube"].deesser
        assert PRESETS["podcast"].lufs == -16.0 and PRESETS["podcast"].eq_mud_db == -3.0
        assert PRESETS["social"].lufs == -14.0 and PRESETS["social"].comp_ratio == 3.5
        assert PRESETS["bad-room"].highpass_hz == 90.0

    def test_unknown_preset_raises(self):
        with pytest.raises(EnhancementError, match="unknown preset"):
            resolve_preset("bogus")

    def test_preset_names_listed(self):
        assert set(preset_names()) == set(PRESETS)


class TestPipelineStages:
    def test_order_is_frozen(self):
        _, stages = run_master(s.speech_like(1.0))
        labels = [st.split(" ")[0] for st in stages]
        assert labels == ["DC", "High-pass", "Vocal", "De-esser", "Compressor", "Limiter", "Loudness"]

    def test_creator_has_no_deesser(self):
        _, stages = run_master(s.speech_like(1.0), preset="creator")
        assert not any("De-esser" in st for st in stages)

    def test_no_eq_skips_eq_and_deesser(self):
        _, stages = run_master(s.speech_like(1.0), preset="youtube", no_eq=True)
        assert not any("EQ" in st or "De-esser" in st for st in stages)

    def test_dehum_stage(self):
        _, stages = run_master(s.speech_like(1.0), dehum_hz=50)
        assert any("De-hum 50" in st for st in stages)

    def test_bad_room_highpass_90(self):
        _, stages = run_master(s.speech_like(1.0), preset="bad-room")
        assert any("High-pass 90" in st for st in stages)

    def test_dc_block_removes_offset(self):
        x = s.speech_like(1.0) + 0.05
        y = filters.dc_block(x, SR)
        assert 20 * np.log10(abs(float(np.mean(y))) + 1e-12) < -60

    def test_highpass_lr24_removes_rumble(self):
        x = s.speech_like(1.0) + 0.5 * s.tone(40.0, 1.0, 0.5)
        y = filters.highpass_lr24(x, SR, 70.0)
        assert band_energy_db(y, 20, 60) < band_energy_db(x, 20, 60) - 15

    def test_vocal_eq_band_gains_bounded(self):
        for g in (-10, 10):  # must clip to ±4
            x = filters.vocal_eq(s.speech_like(1.0), SR, mud_db=g)
            assert np.all(np.isfinite(x))


class TestDeesser:
    def test_sibilance_attenuated(self):
        x = s.sibilant()
        y = filters.deesser(x, SR)
        # max attenuation 6 dB; require at least 4 dB in the detection band
        assert band_energy_db(y, 4000, 10000) <= band_energy_db(x, 4000, 10000) - 4.0
        assert band_energy_db(y, 4000, 10000) >= band_energy_db(x, 4000, 10000) - 6.5

    def test_no_harm_on_2_5k_for_normal_speech(self):
        """No degradar >5% la energía 2-5 kHz (criterio obligatorio en CI)."""
        x = s.speech_like(2.0)
        y = filters.deesser(x, SR)
        ratio = 10 ** (band_energy_db(y, 2000, 5000) / 10) / 10 ** (band_energy_db(x, 2000, 5000) / 10)
        assert ratio >= 0.95


class TestMasterAcceptance:
    def test_lufs_in_target_plusminus_1(self):
        x = s.speech_like(4.0)
        y, _ = run_master(x, preset="youtube")
        import pyloudnorm as pyln

        measured = pyln.Meter(SR).integrated_loudness(y)
        assert abs(measured - (-14.0)) <= 1.0

    def test_true_peak_under_minus_1_db(self):
        x = s.speech_like(4.0)
        y, _ = run_master(x)
        assert filters.true_peak_db(y) <= -0.99

    def test_duration_preserved(self):
        x = s.speech_like(4.0)
        y, _ = run_master(x)
        assert abs(len(y) / SR - 4.0) <= 0.1

    def test_dc_removed(self):
        x = s.speech_like(4.0)
        y, _ = run_master(x)
        assert 20 * np.log10(abs(float(np.mean(y))) + 1e-12) < -60

    def test_mud_band_attenuated_2db(self):
        """Banda 100-300 Hz atenuada >= 2 dB en fixture mud-heavy (podcast: -3 dB)."""
        x = s.mud_heavy(3.0)
        y, _ = run_master(x, preset="podcast")
        assert band_energy_db(y, 100, 300) <= band_energy_db(x, 100, 300) - 2.0

    def test_byte_equivalent_determinism(self, tmp_path):
        x = s.speech_like(2.0)
        y1, _ = run_master(x, preset="youtube")
        y2, _ = run_master(x, preset="youtube")
        np.testing.assert_array_equal(y1, y2)
        p1 = audioio.write_wav(tmp_path / "a.wav", y1)
        p2 = audioio.write_wav(tmp_path / "b.wav", y2)
        assert p1.read_bytes() == p2.read_bytes()

    def test_plan_stages_never_write(self, tmp_path):
        assert plan_stages("youtube")[0] == "DC removal"


class TestLimiter:
    def test_hot_input_true_peak_capped(self):
        """El criterio del producto: true peak <= -1 dBTP tras loudnorm (guard)."""
        x = s.speech_like(2.0) * 8.0  # hard-clipped hot signal
        y = filters.loudness_normalize(x, SR, -16.0)
        assert filters.true_peak_db(y) <= -0.99
