"""Track 2: voxera silence — gap trimming, breath protection, declick."""

import numpy as np
import pytest

import tests.synth as s
from voxera.errors import EnhancementError
from voxera.silence import SR, LEVELS, silence_file, trim_gaps
from voxera.vad import speech_mask, speech_ratio


def write_fixture(tmp_path, x, name="in.wav"):
    import soundfile as sf

    p = tmp_path / name
    sf.write(str(p), x, SR, subtype="PCM_16")
    return str(p)


class TestLevels:
    def test_levels_table_frozen(self):
        assert LEVELS == {
            "light": (1.5, 0.8),
            "medium": (0.8, 0.5),
            "aggressive": (0.4, 0.25),
        }

    def test_invalid_level_raises(self):
        with pytest.raises(EnhancementError, match="invalid silence level"):
            trim_gaps(s.speech_like(1.0), speech_mask(s.speech_like(1.0), SR), "extreme")


class TestTrimming:
    @pytest.mark.parametrize("level,min_saved", [
        ("light", 0.5),
        ("medium", 0.9),
        ("aggressive", 1.5),
    ])
    def test_gap_trimming_reduces_duration(self, tmp_path, level, min_saved):
        """Más agresivo => más silencio recortado; la voz siempre se conserva."""
        x = s.long_gaps()
        result = silence_file(write_fixture(tmp_path, x, "g.wav"), tmp_path / "out.wav", level=level)
        saved = result["duration_in_s"] - result["duration_out_s"]
        assert saved >= min_saved
        assert result["speech_ratio_out"] > result["speech_ratio_in"]

    def test_speech_intact_after_trim(self, tmp_path):
        x = s.long_gaps()
        result = silence_file(write_fixture(tmp_path, x, "g.wav"), tmp_path / "out.wav", level="medium")
        out, _ = read(result["output"])
        # speech ratio must rise (silence removed, speech kept)
        assert result["speech_ratio_out"] > result["speech_ratio_in"]
        # each 1 s speech block survives: energy is preserved within tolerance
        assert out.std() > 0.05

    def test_short_gaps_untouched(self, tmp_path):
        x = s.speech_like(2.0, gap_frac=0.15)  # 0.36 s gaps < 0.4 trigger
        result = silence_file(write_fixture(tmp_path, x, "s.wav"), tmp_path / "out.wav", level="aggressive")
        assert abs(result["duration_in_s"] - result["duration_out_s"]) < 0.05

    def test_output_policy_24bit_48k(self, tmp_path):
        x = s.long_gaps()
        silence_file(write_fixture(tmp_path, x, "g.wav"), tmp_path / "out.wav", level="medium")
        import soundfile as sf

        info = sf.info(str(tmp_path / "out.wav"))
        assert info.samplerate == 48000 and info.subtype == "PCM_24"


class TestBreaths:
    def test_preserve_is_byte_identical_when_no_trims(self, tmp_path):
        """Fixture con breaths y sin gaps largos: preserve => byte-iguales.

        Se compara contra el input leído (ambos cuantizados: input PCM_16,
        output PCM_24 del mismo float) para evitar ruido de cuantización.
        """
        import soundfile as sf

        p = write_fixture(tmp_path, s.with_breaths(), "b.wav")
        silence_file(p, tmp_path / "out.wav", level="medium")
        orig, _ = sf.read(p, dtype="float32")
        out, _ = sf.read(str(tmp_path / "out.wav"), dtype="float32")
        np.testing.assert_array_equal(orig, out)

    def test_attenuate_lowers_breath_energy(self, tmp_path):
        from voxera.analyze import breath_regions

        x = s.with_breaths()
        result = silence_file(
            write_fixture(tmp_path, x, "b.wav"), tmp_path / "out.wav", level="medium", breaths="attenuate"
        )
        out, _ = read(result["output"])
        regions = breath_regions(x, SR)
        assert regions
        s0, s1 = regions[0]
        a, b = int(s0 * SR), int(s1 * SR)
        e_before = 10 * np.log10((x[a:b] ** 2).mean() + 1e-12)
        e_after = 10 * np.log10((out[a:b] ** 2).mean() + 1e-12)
        assert e_after <= e_before - 3.0

    def test_invalid_breaths_raises(self, tmp_path):
        with pytest.raises(EnhancementError, match="invalid --breaths"):
            silence_file(write_fixture(tmp_path, s.speech_like(1.0), "s.wav"), tmp_path / "o.wav", breaths="nuke")


class TestDeclick:
    def test_click_regions_attenuated(self, tmp_path):
        from voxera.analyze import click_regions

        x = s.with_clicks()
        result = silence_file(write_fixture(tmp_path, x, "c.wav"), tmp_path / "out.wav", level="medium", declick=True)
        out, _ = read(result["output"])
        regions = click_regions(x, SR)
        assert len(regions) >= 2
        s0, s1 = regions[0]
        a, b = int(s0 * SR), int(s1 * SR)
        e_before = 10 * np.log10((x[a:b] ** 2).mean() + 1e-12)
        e_after = 10 * np.log10((out[a:b] ** 2).mean() + 1e-12)
        assert e_after <= e_before - 2.0


def read(path):
    import soundfile as sf

    return sf.read(str(path), dtype="float32")
