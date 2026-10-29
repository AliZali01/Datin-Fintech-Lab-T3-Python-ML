"""Project-specific exceptions and exit codes."""


class DataFactoryError(Exception):
    """Base exception for expected project failures."""

    exit_code = 1


class ConfigurationError(DataFactoryError):
    """Raised when project configuration is missing or invalid."""

    exit_code = 2


class NetworkError(DataFactoryError):
    """Raised when a network request fails."""

    exit_code = 3


class DataValidationError(DataFactoryError):
    """Raised when data violates the expected contract."""

    exit_code = 4
