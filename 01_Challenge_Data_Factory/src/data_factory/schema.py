
import re
import math
from datetime import datetime
from collections.abc import Mapping


REQUIRED_STRING_FIELDS = (
    "unique_key",
    "created_date",
    "complaint_type",
    "agency",
)

ZIP_PATTERN = re.compile(r"^\d{5}$")

ZIP_MISSING_VALUES = {
    "",
    "N/A",
    "NA",
    "NULL",
    "NONE",
    "00000",
}


def normalize_zip(value):
    """Normalize ZIP codes and convert missing placeholders to None."""

    if value is None:
        return None

    normalized = str(value).strip()

    if normalized.upper() in ZIP_MISSING_VALUES:
        return None

    return normalized


def get_zip_error(value):
    """Return ZIP validation error code or None."""

    normalized = normalize_zip(value)

    if normalized is None:
        return None

    if ZIP_PATTERN.fullmatch(normalized) is None:
        return "INVALID_ZIP_FORMAT"

    return None


def validate_zip(value):
    """Return True when ZIP is valid or legitimately missing."""

    return get_zip_error(value) is None


def _is_missing(value):
    return value is None or (
        isinstance(value, str) and not value.strip()
    )


def _parse_datetime(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Invalid datetime value")

    value = value.strip().replace("Z", "+00:00")

    return datetime.fromisoformat(value)


def validate_record(
    record,
    expected_complaint_type=None,
):
    """Validate one source record and return error codes."""

    if not isinstance(record, Mapping):
        return ["RECORD_NOT_OBJECT"]

    errors = []

    # 1. Required fields
    for field in REQUIRED_STRING_FIELDS:

        value = record.get(field)

        if _is_missing(value):
            errors.append(f"MISSING_{field.upper()}")

        elif not isinstance(value, str):
            errors.append(f"INVALID_{field.upper()}_TYPE")

    # 2. Created date
    created = None
    created_value = record.get("created_date")

    if isinstance(created_value, str) and created_value.strip():

        try:
            created = _parse_datetime(created_value)

        except (ValueError, TypeError):
            errors.append("INVALID_CREATED_DATE")

    # 3. Closed date
    closed_value = record.get("closed_date")
    closed = None

    if not _is_missing(closed_value):

        try:
            closed = _parse_datetime(closed_value)

        except (ValueError, TypeError):
            errors.append("INVALID_CLOSED_DATE")

    # 4. Logical date validation
    if created is not None and closed is not None:

        try:
            if closed < created:
                errors.append("CLOSED_BEFORE_CREATED")

        except TypeError:
            errors.append("INCOMPATIBLE_DATETIME_TIMEZONES")

    # 5. ZIP validation
    zip_error = get_zip_error(record.get("incident_zip"))

    if zip_error is not None:
        errors.append(zip_error)

    # 6. Coordinate validation
    lat = record.get("latitude")
    lon = record.get("longitude")

    lat_missing = _is_missing(lat)
    lon_missing = _is_missing(lon)

    if lat_missing != lon_missing:
        errors.append("PARTIAL_COORDINATES")

    elif not lat_missing:

        try:
            lat = float(lat)
            lon = float(lon)

            if not math.isfinite(lat) or not math.isfinite(lon):
                errors.append("INVALID_COORDINATES")

            elif not (-90 <= lat <= 90 and -180 <= lon <= 180):
                errors.append("COORDINATES_OUT_OF_RANGE")

        except (ValueError, TypeError):
            errors.append("INVALID_COORDINATES")

    # 7. Optional categorical fields must be strings
    for field in (
        "status",
        "borough",
        "open_data_channel_type",
    ):

        value = record.get(field)

        if value is not None and not isinstance(value, str):
            errors.append(f"INVALID_{field.upper()}_TYPE")

    # 8. Collection scope
    if (
        expected_complaint_type is not None
        and isinstance(record.get("complaint_type"), str)
        and record["complaint_type"] != expected_complaint_type
    ):
        errors.append("UNEXPECTED_COMPLAINT_TYPE")

    return errors
