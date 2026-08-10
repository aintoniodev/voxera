"""Shared error type for the voxera core.

Defined in its own module so the backend adapters can raise it without
creating an import cycle between ``enhance`` (which routes backends) and the
backend implementations.
"""


class EnhancementError(Exception):
    """A user-facing enhancement failure (bad path, format, backend, ...)."""


class UnknownBackendError(EnhancementError):
    """Raised when the requested backend is not registered."""


class NoSpeechError(EnhancementError):
    """VAD speech ratio < 5%: the file contains no detectable voice.

    Maps to the reserved exit code ``VOXERA_NO_SPEECH`` (20). ``analyze`` and
    ``inspect`` keep working on such files (analysis-only); ``enhance`` and
    ``master`` abort rather than masterize noise as a voice.
    """


NO_SPEECH_EXIT_CODE = 20
