
import csv
import json
import math
import os

from collections import Counter
from datetime import datetime
from pathlib import Path

from .exceptions import DataValidationError


SOURCE_COLUMNS = [
    "unique_key",
    "created_date",
    "closed_date",
    "agency",
    "agency_name",
    "complaint_type",
    "descriptor",
    "status",
    "resolution_action_updated_date",
    "community_board",
    "police_precinct",
    "borough",
    "open_data_channel_type",
    "park_facility_name",
    "park_borough",
    "location_type",
    "incident_address",
    "street_name",
    "address_type",
    "resolution_description",
    "incident_zip",
    "cross_street_2",
    "intersection_street_2",
    "cross_street_1",
    "intersection_street_1",
    "y_coordinate_state_plane",
    "x_coordinate_state_plane",
    "latitude",
    "longitude",
    "location",
    "council_district",
    "city",
    "landmark",
    "bbl",
]

INTEGER_FIELDS = {
    "council_district",
}

FLOAT_FIELDS = {
    "y_coordinate_state_plane",
    "x_coordinate_state_plane",
    "latitude",
    "longitude",
}

DERIVED_COLUMNS = [
    "resolution_time_hours",
    "created_year",
    "created_month",
    "created_year_month",
]

OUTPUT_COLUMNS = SOURCE_COLUMNS + DERIVED_COLUMNS


class DataTransformer:

    @staticmethod
    def parse_datetime(value, field_name):

        if value is None or value == "":
            return None

        if not isinstance(value, str):
            raise DataValidationError(
                f"{field_name} must be a datetime string."
            )

        try:
            normalized = value.strip()

            if normalized.endswith("Z"):
                normalized = normalized[:-1] + "+00:00"

            return datetime.fromisoformat(normalized)

        except ValueError as exc:
            raise DataValidationError(
                f"Invalid datetime in {field_name}: {value}"
            ) from exc

    @staticmethod
    def normalize_number(value, field_name, integer=False):

        if value is None or value == "":
            return None

        try:
            number = float(value)

            if not math.isfinite(number):
                raise ValueError("Non-finite number")

            if integer:
                if not number.is_integer():
                    raise ValueError("Expected integer")

                return int(number)

            return number

        except (ValueError, TypeError) as exc:
            raise DataValidationError(
                f"Invalid numeric value in {field_name}: {value}"
            ) from exc

    @staticmethod
    def serialize_value(value):

        if value is None:
            return ""

        if isinstance(value, (dict, list)):
            return json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )

        return value

    def transform_record(self, record):

        if not isinstance(record, dict):
            raise DataValidationError(
                "Input record must be a JSON object."
            )

        # Preserve all 34 source columns.
        result = {
            field: self.serialize_value(record.get(field))
            for field in SOURCE_COLUMNS
        }

        # Standardize date fields.
        created = self.parse_datetime(
            record.get("created_date"),
            "created_date",
        )

        if created is None:
            raise DataValidationError(
                "Accepted record has no created_date."
            )

        closed = self.parse_datetime(
            record.get("closed_date"),
            "closed_date",
        )

        result["created_date"] = created.isoformat()

        if closed is not None:
            result["closed_date"] = closed.isoformat()

            try:
                duration = (
                    closed - created
                ).total_seconds() / 3600

            except TypeError as exc:
                raise DataValidationError(
                    "Incompatible datetime timezones."
                ) from exc

            if duration < 0:
                raise DataValidationError(
                    "Accepted record has negative resolution time."
                )

            result["resolution_time_hours"] = round(
                duration, 6
            )

        else:
            result["closed_date"] = ""
            result["resolution_time_hours"] = ""

        # Convert numeric fields.
        for field in INTEGER_FIELDS:
            result[field] = self.normalize_number(
                record.get(field),
                field,
                integer=True,
            )

        for field in FLOAT_FIELDS:
            result[field] = self.normalize_number(
                record.get(field),
                field,
            )

        # Preserve ZIP as a string, including leading zeros.
        zip_value = record.get("incident_zip")

        if zip_value is not None:
            result["incident_zip"] = str(zip_value).strip()

        else:
            result["incident_zip"] = ""

        # Derived temporal features.
        result["created_year"] = created.year
        result["created_month"] = created.month
        result["created_year_month"] = created.strftime("%Y-%m")

        return result

    def transform(
        self,
        input_path,
        output_dir,
        expected_count=None,
    ):

        input_path = Path(input_path)
        output_dir = Path(output_dir)

        if not input_path.is_file():
            raise DataValidationError(
                f"Input file not found: {input_path}"
            )

        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / "cases.csv"
        report_path = output_dir / "transformation_report.json"

        output_tmp = output_dir / ".cases.csv.tmp"
        report_tmp = output_dir / ".transformation_report.json.tmp"

        rows_written = 0
        missing_zip = 0
        missing_coordinates = 0

        duration_count = 0
        duration_sum = 0.0
        duration_min = None
        duration_max = None

        transformer_stats = Counter()

        try:

            with (
                input_path.open("r", encoding="utf-8") as source,
                output_tmp.open(
                    "w",
                    encoding="utf-8-sig",
                    newline="",
                ) as destination,
            ):

                writer = csv.DictWriter(
                    destination,
                    fieldnames=OUTPUT_COLUMNS,
                    extrasaction="raise",
                    lineterminator="\n",
                )

                writer.writeheader()

                for line_number, line in enumerate(source, start=1):

                    if not line.strip():
                        raise DataValidationError(
                            f"Empty input line: {line_number}"
                        )

                    try:
                        record = json.loads(line)

                    except json.JSONDecodeError as exc:
                        raise DataValidationError(
                            f"Invalid JSON at line {line_number}."
                        ) from exc

                    try:
                        row = self.transform_record(record)

                    except DataValidationError as exc:
                        raise DataValidationError(
                            f"Transformation failed at line "
                            f"{line_number}: {exc}"
                        ) from exc

                    writer.writerow(row)
                    rows_written += 1

                    if row["incident_zip"] == "":
                        missing_zip += 1

                    if (
                        row["latitude"] in (None, "")
                        or row["longitude"] in (None, "")
                    ):
                        missing_coordinates += 1
                        
                    duration = row["resolution_time_hours"]

                    if duration != "":
                        duration = float(duration)

                        duration_count += 1
                        duration_sum += duration

                        duration_min = (
                            duration
                            if duration_min is None
                            else min(duration_min, duration)
                        )

                        duration_max = (
                            duration
                            if duration_max is None
                            else max(duration_max, duration)
                        )

            if (
                expected_count is not None
                and rows_written != expected_count
            ):
                raise DataValidationError(
                    f"Record count mismatch: expected "
                    f"{expected_count}, got {rows_written}."
                )

            report = {
                "records_transformed": rows_written,
                "source_columns": len(SOURCE_COLUMNS),
                "derived_columns": len(DERIVED_COLUMNS),
                "output_columns": len(OUTPUT_COLUMNS),
                "missing_zip": missing_zip,
                "missing_coordinate_pairs": missing_coordinates,
                "resolution_duration": {
                    "count": duration_count,
                    "mean_hours": (
                        round(duration_sum / duration_count, 6)
                        if duration_count else None
                    ),
                    "min_hours": duration_min,
                    "max_hours": duration_max,
                },
                "output_file": output_path.name,
            }

            with report_tmp.open(
                "w",
                encoding="utf-8",
                newline="\n",
            ) as report_file:

                json.dump(
                    report,
                    report_file,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                    allow_nan=False,
                )

                report_file.write("\n")
                report_file.flush()
                os.fsync(report_file.fileno())

            os.replace(output_tmp, output_path)
            os.replace(report_tmp, report_path)

            return report

        finally:
            output_tmp.unlink(missing_ok=True)
            report_tmp.unlink(missing_ok=True)
