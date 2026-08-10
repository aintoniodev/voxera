"""Track 5: restore — declip, deplosive, dehum."""

import numpy as np
import pytest

import tests.synth as s
from voxera.errors import EnhancementError
from voxera.restore import declip, deplosive, restore_file
from voxera.vad import speech_mask

SR = 48000


def clipped_light():
    return np.clip(s.speech_like(2.0) * 3.0, -0.95, 0.95).astype(np.float32)


def write_fixture(tmp_path, x, name="in.wav"):
    import soundfile as sf

    p = tmp_path / name
    sf.write(str(p), x, SR, subtype="PCM_16")
    return str(p)


class TestDeclip:
    def test_clean_audio_untouched(self):
        x = s.speech_like(2.0)
        assert np.array_equal(declip(x, SR), x)

    def test_flat_tops_reconstructed(self):
        x = clipped_light()
        y = declip(x, SR)
        plateau_in = float(np.mean(np.abs(np.abs(x) - 0.95) < 1e-6))
        plateau_out = float(np.mean(np.abs(np.abs(y) - 0.95) < 1e-6))
        assert plateau_out < plateau_in * 0.1

    def test_keeps_duration_and_level(self):
        x = clipped_light()
        y = declip(x, SR)
        assert len(y) == len(x)
        assert np.abs(y).max() <= 1.0


class TestDeplosive:
    def test_reduces_lf_burst_at_onset(self):
        x = s.with_plosive()
        mask = speech_mask(x, SR)
        y = deplosive(x, SR, mask)
        # the LF burst region loses energy
        from voxera.analyze import plosive_regions

        regions = plosive_regions(x, SR, mask)
        assert regions
        s0, s1 = regions[0]
        a, b = int(s0 * SR), int(s1 * SR)

        def lf_energy(z):
            spec = np.abs(np.fft.rfft(z[a:b].astype(np.float64))) ** 2
            f = np.fft.rfftfreq(b - a, 1 / SR)
            return 10 * np.log10(spec[(f >= 20) & (f < 150)].sum() + 1e-30)

        assert lf_energy(y) < lf_energy(x) - 1.0

    def test_clean_speech_mostly_untouched(self):
        x = s.speech_like(2.0)
        mask = speech_mask(x, SR)
        y = deplosive(x, SR, mask)
        # sin onsets plosivos, la energia total cambia poco
        assert 10 * np.log10((y**2).mean() + 1e-12) > 10 * np.log10((x**2).mean() + 1e-12) - 0.5


class TestRestoreFile:
    def test_declip_flow(self, tmp_path):
        result = restore_file(
            write_fixture(tmp_path, clipped_light(), "c.wav"),
            tmp_path / "out.wav",
            do_declip=True,
        )
        assert result["stages"] == ["declip"]
        assert result["clipping_ratio_out"] <= result["clipping_ratio_in"]
        import soundfile as sf

        info = sf.info(str(tmp_path / "out.wav"))
        assert info.samplerate == 48000 and info.subtype == "PCM_24"

    def test_no_op_raises(self, tmp_path):
        with pytest.raises(EnhancementError, match="at least one of"):
            restore_file(
                write_fixture(tmp_path, s.speech_like(1.0), "s.wav"), tmp_path / "o.wav"
            )

    def test_restore_plus_preset(self, tmp_path):
        result = restore_file(
            write_fixture(tmp_path, clipped_light(), "c.wav"),
            tmp_path / "out.wav",
            do_declip=True,
            preset="youtube",
        )
        assert "declip" in result["stages"]
        assert any("Loudness" in st for st in result["stages"])
        import pyloudnorm as pyln

        import soundfile as sf

        y, _ = sf.read(str(tmp_path / "out.wav"), dtype="float32")
        lufs = pyln.Meter(SR).integrated_loudness(y)
        assert abs(lufs - (-14.0)) <= 1.0

    def test_dehum_notch(self, tmp_path):
        x = s.speech_like(2.0) + 0.3 * s.tone(50.0, 2.0, 0.3)
        result = restore_file(
            write_fixture(tmp_path, x, "h.wav"), tmp_path / "out.wav", dehum_hz=50
        )
        assert "dehum 50 Hz" in result["stages"]
        import soundfile as sf

        y, _ = sf.read(str(tmp_path / "out.wav"), dtype="float32")
        spec_in = np.abs(np.fft.rfft(x.astype(np.float64))) ** 2
        spec_out = np.abs(np.fft.rfft(y.astype(np.float64))) ** 2
        f = np.fft.rfftfreq(len(x), 1 / SR)
        band = (f >= 48) & (f <= 52)
        assert 10 * np.log10(spec_out[band].sum() + 1e-30) < 10 * np.log10(spec_in[band].sum() + 1e-30) - 15
