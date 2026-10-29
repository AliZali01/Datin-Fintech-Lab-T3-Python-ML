"""Load and validate Data Factory configuration."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .exceptions import ConfigurationError


def load_config(
    config_path: str | Path = "config.json",
) -> dict[str, Any]:
    """Load configuration from a JSON file and validate its values."""

    path = Path(config_path)

    if not path.is_file():
        raise ConfigurationError(
            f"Configuration file not found: {path}"
        )

    try:
        with path.open("r", encoding="utf-8") as file:
            config = json.load(file)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(
            f"Invalid JSON in configuration file: {exc}"
        ) from exc
    except OSError as exc:
        raise ConfigurationError(
            f"Cannot read configuration file: {exc}"
        ) from exc

    if not isinstance(config, dict):
        raise ConfigurationError(
            "Configuration must be a JSON object."
        )

    required_sections = ("api", "collection", "paths", "quality")

    for section in required_sections:
        if not isinstance(config.get(section), dict):
            raise ConfigurationError(
                f"Missing or invalid configuration section: {section}"
            )

    api = config["api"]
    collection = config["collection"]
    paths = config["paths"]
    quality = config["quality"]

    if not isinstance(api.get("endpoint"), str) or not api["endpoint"].strip():
        raise ConfigurationError("api.endpoint must be a non-empty string.")

    if api.get("method") not in ("GET", "POST"):
        raise ConfigurationError("api.method must be GET or POST.")

    timeout = api.get("timeout_seconds")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or timeout <= 0
    ):
        raise ConfigurationError(
            "api.timeout_seconds must be a positive number."
        )

    retries = api.get("max_retries")
    if (
        isinstance(retries, bool)
        or not isinstance(retries, int)
        or retries < 0
    ):
        raise ConfigurationError(
            "api.max_retries must be a non-negative integer."
        )

    batch_size = api.get("batch_size")
    if (
        isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or batch_size <= 0
    ):
        raise ConfigurationError(
            "api.batch_size must be a positive integer."
        )

    start_date = collection.get("start_date")
    end_date = collection.get("end_date")

    if not isinstance(start_date, str) or not isinstance(end_date, str):
        raise ConfigurationError(
            "Collection start_date and end_date must be strings."
        )

    try:
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
        if end <= start:
            raise ConfigurationError(
                "collection.end_date must be after start_date."
            )
    except ValueError as exc:
        raise ConfigurationError(
            "Collection dates must use valid ISO date-time values."
        ) from exc

    for name in ("raw_dir", "curated_dir"):
        value = paths.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ConfigurationError(
                f"paths.{name} must be a non-empty string."
            )
        if Path(value).is_absolute():
            raise ConfigurationError(
                f"paths.{name} must be a relative path."
            )

    ratio = quality.get("max_quarantine_ratio")
    if (
        isinstance(ratio, bool)
        or not isinstance(ratio, (int, float))
        or not 0 <= ratio <= 1
    ):
        raise ConfigurationError(
            "quality.max_quarantine_ratio must be between 0 and 1."
        )

    return config
