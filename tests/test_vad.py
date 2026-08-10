"""Track 1A/1: VAD contract — speech ratios and the VOXERA_NO_SPEECH gate."""

import pytest

import tests.synth as s
from voxera.errors import NoSpeechError
from voxera.vad import require_speech, speech_ratio

SR = 48000


class TestSpeechRatio:
    def test_speech_like_high_ratio(self):
        assert speech_ratio(s.speech_like(), SR) > 0.5

    def test_silence_zero(self):
        assert speech_ratio(s.silence(), SR) == 0.0

    def test_pure_tone_below_threshold(self):
        # A pure 200 Hz tone is not speech: webrtcvad rejects it.
        assert speech_ratio(s.tone(200.0), SR) < 0.05


class TestRequireSpeech:
    def test_speech_passes(self):
        assert require_speech(s.speech_like(), SR) > 0.5

    def test_silence_raises_no_speech(self):
        with pytest.raises(NoSpeechError, match="no speech detected"):
            require_speech(s.silence(), SR)

    def test_tone_raises_no_speech(self):
        with pytest.raises(NoSpeechError):
            require_speech(s.tone(200.0), SR)
