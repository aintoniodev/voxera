"""Core enhance() contract tests: validation and backend routing."""

import wave
from pathlib import Path

import pytest

from improve_my_sound.backends import BACKENDS, get_backend, list_backends
from improve_my_sound.backends.base import Backend
from improve_my_sound.backends.dpdfnet import DpdfNetBackend
from improve_my_sound.enhance import EnhancementError, enhance


def write_wav(path: Path, frames: int = 8000, rate: int = 8000) -> Path:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\x00\x00" * frames)
    return path


def write_empty_wav(path: Path) -> Path:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"")
    return path


class RecordingBackend(Backend):
    name = "recorder"
    calls: list[tuple[Path, Path]] = []

    def enhance(self, input_path, output_path):
        RecordingBackend.calls.append((Path(input_path), Path(output_path)))
        output_path.write_bytes(b"enhanced")
        return output_path


@pytest.fixture()
def recording_backend(monkeypatch):
    RecordingBackend.calls = []
    monkeypatch.setitem(BACKENDS, "recorder", RecordingBackend)
    yield RecordingBackend
    monkeypatch.delitem(BACKENDS, "recorder")


class TestEnhanceValidation:
    def test_missing_input_raises(self, tmp_path):
        with pytest.raises(EnhancementError, match="no such file"):
            enhance(tmp_path / "nope.wav", tmp_path / "out.wav")

    def test_directory_input_raises(self, tmp_path):
        with pytest.raises(EnhancementError, match="directory"):
            enhance(tmp_path, tmp_path / "out.wav")

    def test_unsupported_extension_raises(self, tmp_path):
        audio = write_wav(tmp_path / "clip.mp3")
        with pytest.raises(EnhancementError, match="unsupported format"):
            enhance(audio, tmp_path / "out.wav")

    def test_empty_audio_raises(self, tmp_path):
        audio = write_empty_wav(tmp_path / "empty.wav")
        with pytest.raises(EnhancementError, match="empty audio"):
            enhance(audio, tmp_path / "out.wav")

    def test_zero_byte_file_raises(self, tmp_path):
        audio = tmp_path / "broken.wav"
        audio.write_bytes(b"")
        with pytest.raises(EnhancementError, match="invalid wav"):
            enhance(audio, tmp_path / "out.wav")

    def test_unknown_backend_raises(self, tmp_path):
        audio = write_wav(tmp_path / "in.wav")
        with pytest.raises(EnhancementError, match="unknown backend"):
            enhance(audio, tmp_path / "out.wav", backend="does-not-exist")

    def test_unknown_backend_lists_available(self, tmp_path):
        audio = write_wav(tmp_path / "in.wav")
        with pytest.raises(EnhancementError, match="dpdfnet"):
            enhance(audio, tmp_path / "out.wav", backend="does-not-exist")


class TestEnhanceRouting:
    def test_backend_called_with_resolved_paths(self, tmp_path, recording_backend):
        audio = write_wav(tmp_path / "in.wav")
        out = tmp_path / "out.wav"
        result = enhance(audio, out, backend="recorder")
        assert result == out
        assert RecordingBackend.calls == [(audio, out)]
        assert out.read_bytes() == b"enhanced"

    def test_missing_output_from_backend_raises(self, tmp_path, monkeypatch):
        class NoWriteBackend(Backend):
            name = "nowrite"

            def enhance(self, input_path, output_path):
                return output_path  # writes nothing

        monkeypatch.setitem(BACKENDS, "nowrite", NoWriteBackend)
        audio = write_wav(tmp_path / "in.wav")
        with pytest.raises(EnhancementError, match="did not produce output"):
            enhance(audio, tmp_path / "out.wav", backend="nowrite")

    def test_default_backend_is_dpdfnet(self):
        backend = get_backend("dpdfnet")
        assert isinstance(backend, DpdfNetBackend)
        assert backend.name == "dpdfnet"
        assert backend.model == "dpdfnet2"  # Pareto-informed real-time default
        assert backend.attn_limit_db == 24.0


class TestRegistry:
    def test_get_backend_returns_instance(self):
        backend = get_backend("dpdfnet")
        assert backend is not None
        assert backend.name == "dpdfnet"

    def test_get_backend_unknown_returns_none(self):
        assert get_backend("nope") is None

    def test_list_backends_sorted(self):
        assert list_backends() == sorted(list_backends())
        assert "dpdfnet" in list_backends()

    def test_dpdfnet_adapter_produces_output(self, tmp_path):
        audio = write_wav(tmp_path / "in.wav")
        out = enhance(audio, tmp_path / "out.wav", backend="dpdfnet")
        assert out.exists()
        assert out.stat().st_size > 0
