"""User-facing error taxonomy for GOLEM.

Every exception that the application can surface to the user has a class
here with a ``user_message`` attribute. Catch ``GolemError`` to handle
all of them. Catch a more specific subclass to handle a specific class
of failure (e.g. a stale API key).

These classes are also useful for tests: a test can assert that a
function raises ``GolemError`` instead of catching ``Exception`` and
missing real bugs.
"""

from __future__ import annotations


class GolemError(Exception):
    """Base class for user-facing errors.

    Subclasses set ``user_message`` to a one-line, end-user-friendly
    explanation. The application surfaces this to the user in a message
    box; developers can read the original exception for details.
    """

    user_message: str = "Something went wrong."

    def __init__(self, message: str = "", *args: object) -> None:
        if message:
            super().__init__(message)
        else:
            super().__init__(self.user_message, *args)


class ConfigurationError(GolemError):
    user_message = "GOLEM is not configured correctly. Open Settings to review."


class TermsNotAcceptedError(ConfigurationError):
    user_message = "You must accept the Terms of Service to continue."


class VaultUnreachableError(GolemError):
    user_message = (
        "GOLEM cannot write to the Obsidian vault. Check that the path exists "
        "and that you have permission to create files in it."
    )


class WatchedFolderMissingError(GolemError):
    user_message = "The watched folder no longer exists. Open Settings to choose a new one."


class ProviderAuthError(GolemError):
    user_message = "The API key was rejected by the provider. Open Settings to update it."


class ProviderRateLimitError(GolemError):
    user_message = "The provider is rate-limiting requests. GOLEM will retry automatically."


class ProviderTimeoutError(GolemError):
    user_message = "The provider did not respond in time. The file will be retried later."


class FileLockedError(GolemError):
    user_message = "A file is locked by another process. Try again later."


class PayloadTamperedError(GolemError):
    user_message = (
        "The installer payload is corrupted. Re-download the installer from the official source."
    )


class IndexCorruptedError(GolemError):
    user_message = (
        "The local index database is corrupted. Use 'Reset all settings' from the tray menu "
        "to rebuild it from scratch."
    )
