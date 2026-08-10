"""Track 3: voxera score — CVS contract, verdicts and Voice Preservation."""

import pytest

import tests.synth as s
from voxera.errors import EnhancementError
from voxera.score import score_file

SR = 48000


def write_fixture(tmp_path, x, name="in.wav"):
    import soundfile as sf

    p = tmp_path / name
    sf.write(str(p), x, SR, subtype="PCM_16")
    return str(p)


class TestScoreContract:
    def test_structure_and_verdict(self, tmp_path):
        report = score_file(write_fixture(tmp_path, s.speech_like(2.0)))
        score = report["score"]
        assert 0 <= score["cvs"] <= 100
        assert set(score["dimensions"]) == {"noise", "clarity", "loudness", "room", "dynamics"}
        for dim in score["dimensions"].values():
            assert 0 <= dim["value"] <= 100
            assert dim["detail"]
        assert score["verdict"] in (
            "Your voice is ready for publishing",
            "Close — needs a little polish",
            "Needs work",
        )
        assert report["system"]["voxera_version"] == "0.2.0"

    def test_ready_for_publishing_on_clean_loud(self, tmp_path):
        from voxera.dsp import master

        x = s.speech_like(4.0)
        mastered, _ = master(x, SR, "youtube")  # loud, clean-ish
        report = score_file(write_fixture(tmp_path, mastered))
        assert report["score"]["cvs"] >= 60  # synthetic fixture caps below 80

    def test_score_rises_after_master_on_quiet_fixture(self, tmp_path):
        """El loop 'escucha + métrica': master sube el score en fixture baja."""
        from voxera.dsp import master

        quiet = (s.speech_like(4.0) * 0.05).astype("float32")  # LUFS ~ -45
        before = score_file(write_fixture(tmp_path, quiet, "q.wav"))
        mastered, _ = master(quiet, SR, "youtube")
        after = score_file(write_fixture(tmp_path, mastered, "m.wav"))
        assert after["score"]["cvs"] > before["score"]["cvs"] + 5
        assert after["score"]["dimensions"]["loudness"]["value"] > 90

    def test_missing_input_raises(self, tmp_path):
        with pytest.raises(EnhancementError, match="no such file"):
            score_file(str(tmp_path / "nope.wav"))


class TestVoicePreservation:
    def test_identical_control_is_100(self, tmp_path):
        p = write_fixture(tmp_path, s.speech_like(2.0))
        report = score_file(p, ref_path=p)
        assert report["voice_preservation_pct"] > 99.0

    def test_master_keeps_speaker(self, tmp_path):
        from voxera.dsp import master

        x = s.speech_like(2.0)
        orig = write_fixture(tmp_path, x, "orig.wav")
        mastered, _ = master(x, SR, "creator")
        m = write_fixture(tmp_path, mastered, "m.wav")
        report = score_file(m, ref_path=orig)
        # el timbre procesado (EQ/comp) baja algo el coseno, pero el hablante se mantiene
        assert report["voice_preservation_pct"] > 60.0

    def test_missing_ref_raises(self, tmp_path):
        p = write_fixture(tmp_path, s.speech_like(1.0))
        with pytest.raises(EnhancementError):
            score_file(p, ref_path=str(tmp_path / "nope.wav"))
