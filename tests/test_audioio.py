"""Track 1A: audio I/O + frozen format policy tests."""

import numpy as np
import pytest
import soundfile as sf

import tests.synth as s
from voxera import audioio
from voxera.errors import EnhancementError


def write(path, samples, sr=48000, subtype="PCM_16", channels=None):
    if channels == 2:
        sf.write(str(path), np.stack([samples, samples], axis=1), sr, subtype=subtype)
    else:
        sf.write(str(path), samples, sr, subtype=subtype)
    return path


class TestFormatPolicy:
    def test_supported_rates_load(self, tmp_path):
        for rate in (16000, 22050, 44100, 48000):
            p = write(tmp_path / f"r{rate}.wav", s.speech_like(0.5), sr=rate)
            data = audioio.load_audio(p)
            assert data.samples.dtype == np.float32
            assert data.source_sample_rate == rate

    def test_unsupported_rate_rejected_with_value(self, tmp_path):
        p = write(tmp_path / "r8k.wav", s.speech_like(0.5), sr=8000)
        with pytest.raises(EnhancementError, match="8000"):
            audioio.load_audio(p)

    def test_unsupported_rate_rejected_odd_value(self, tmp_path):
        p = write(tmp_path / "r96k.wav", s.speech_like(0.5), sr=96000)
        with pytest.raises(EnhancementError, match="96000"):
            audioio.load_audio(p)

    def test_three_channels_rejected(self, tmp_path):
        x = s.speech_like(0.5)
        p = tmp_path / "3ch.wav"
        sf.write(str(p), np.stack([x, x, x], axis=1), 48000)
        with pytest.raises(EnhancementError, match="channel"):
            audioio.load_audio(p)

    def test_empty_file_rejected(self, tmp_path):
        p = tmp_path / "empty.wav"
        sf.write(str(p), np.zeros(0, np.float32), 48000)
        with pytest.raises(EnhancementError, match="empty"):
            audioio.load_audio(p)

    def test_missing_file_rejected(self, tmp_path):
        with pytest.raises(EnhancementError, match="no such file"):
            audioio.load_audio(tmp_path / "nope.wav")

    def test_unsupported_extension_rejected(self, tmp_path):
        p = tmp_path / "clip.xyz"
        p.write_bytes(b"x")
        with pytest.raises(EnhancementError, match="unsupported format"):
            audioio.load_audio(p)

    def test_mp3_decoded_via_ffmpeg(self, tmp_path):
        """Los .mp3 se decodifican con ffmpeg a 48k mono (Track 4 machinery)."""
        import shutil

        if not shutil.which("ffmpeg") and not Path("C:/ffmpeg/bin/ffmpeg.exe").exists():
            pytest.skip("ffmpeg required")
        import subprocess

        wav = tmp_path / "s.wav"
        import soundfile as sf

        sf.write(str(wav), s.speech_like(1.0), 48000)
        mp3 = tmp_path / "s.mp3"
        subprocess.run(
            [shutil.which("ffmpeg") or "C:/ffmpeg/bin/ffmpeg.exe", "-y", "-v", "error",
             "-i", str(wav), "-b:a", "128k", str(mp3)],
            check=True, capture_output=True,
        )
        data = audioio.load_audio(mp3)
        assert data.samples.ndim == 1
        assert abs(len(data.samples) / 48000 - 1.0) < 0.05


class TestStereoDownmix:
    def test_energy_preserving_halves_sum(self, tmp_path):
        """mono = 0.5*(L+R): a hard-panned pair sums to the average, no clip."""
        x = s.speech_like(1.0)
        p = write(tmp_path / "st.wav", x, channels=2)
        data = audioio.load_audio(p)
        np.testing.assert_allclose(data.samples, x, atol=1e-4)
        assert np.abs(data.samples).max() <= 1.0

    def test_stereo_44k1_resampled_to_48k_mono(self, tmp_path):
        x = s.speech_like(1.0)
        p = write(tmp_path / "st441.wav", x, sr=44100, channels=2)
        data = audioio.load_audio(p)
        assert data.samples.ndim == 1
        # 48000 source samples written at 44100 Hz -> 1.088 s, resampled back to 48k
        assert abs(len(data.samples) / 48000 - 48000 / 44100) < 0.05
        assert data.source_sample_rate == 44100
        assert data.source_channels == 2


class TestOutputPolicy:
    def test_writes_pcm24_48k(self, tmp_path):
        p = audioio.write_wav(tmp_path / "out.wav", s.speech_like(1.0))
        info = sf.info(str(p))
        assert info.samplerate == 48000
        assert info.subtype == "PCM_24"
        assert info.channels == 1

    def test_roundtrip_values_preserved(self, tmp_path):
        x = s.speech_like(1.0)
        p = audioio.write_wav(tmp_path / "out.wav", x)
        y, _ = sf.read(str(p), dtype="float32")
        np.testing.assert_allclose(y, x, atol=2e-5)
