"""Shared error type for the voxera core.

Defined in its own module so the backend adapters can raise it without
creating an import cycle between ``enhance`` (which routes backends) and the
backend implementations.
"""


class EnhancementError(Exception):
    """A user-facing enhancement failure (bad path, format, backend, ...)."""


class UnknownBackendError(EnhancementError):
    """Raised when the requested backend is not registered."""
