
import csv
import json
import math
import os

from .exceptions import DataValidationError
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median


class DataAggregator:

    REQUIRED_CASE_COLUMNS = {
        "created_date",
        "created_year_month",
        "borough",
        "complaint_type",
        "resolution_time_hours",
    }

    REQUIRED_POPULATION_COLUMNS = {
        "borough",
        "population_estimate",
    }

    def load_population(self, path, expected_boroughs=None):

        population = {}

        with Path(path).open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as file:

            reader = csv.DictReader(file)

            if not self.REQUIRED_POPULATION_COLUMNS.issubset(
                set(reader.fieldnames or [])
            ):
                raise DataValidationError(
                    "Invalid borough population schema."
                )

            for row in reader:

                borough = (row["borough"] or "").strip().upper()

                if not borough:
                    raise DataValidationError("Empty borough in population data.")

                if borough in population:
                    raise DataValidationError(
                        f"Duplicate borough: {borough}"
                    )

                try:
                    value = int(row["population_estimate"])

                    if value <= 0:
                        raise DataValidationError

                except (ValueError, TypeError) as exc:
                    raise DataValidationError(
                        f"Invalid population for {borough}"
                    ) from exc

                population[borough] = value

        if not population:
            raise DataValidationError("Population reference is empty.")

        if expected_boroughs is not None:

            expected = {
                value.strip().upper()
                for value in expected_boroughs
            }

            if set(population) != expected:
                raise DataValidationError(
                    "Population reference does not contain "
                    "exactly the expected boroughs."
                )

        return population

    @staticmethod
    def _write_json(path, payload):

        path = Path(path)
        temp = path.with_name("." + path.name + ".tmp")

        try:
            with temp.open(
                "w",
                encoding="utf-8",
                newline="\n",
            ) as file:

                json.dump(
                    payload,
                    file,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )

                file.write("\n")
                file.flush()
                os.fsync(file.fileno())

            os.replace(temp, path)

        finally:
            temp.unlink(missing_ok=True)

    def aggregate(
        self,
        cases_path,
        population_path,
        output_path,
        report_path,
        months,
        expected_count=None,
        expected_boroughs=None,
        population_year=2024,
    ):

        months = list(months)

        if (
            not months
            or len(set(months)) != len(months)
            or sorted(months) != months
        ):
            raise DataValidationError("Invalid aggregation month sequence.")

        for month in months:
            datetime.strptime(month, "%Y-%m")

        population = self.load_population(
            population_path,
            expected_boroughs=expected_boroughs,
        )

        cases_path = Path(cases_path)
        output_path = Path(output_path)
        report_path = Path(report_path)

        if not cases_path.is_file():
            raise DataValidationError("Enriched cases file not found.")

        aggregates = defaultdict(
            lambda: {
                "count": 0,
                "duration_sum": 0.0,
                "durations": [],
            }
        )

        groups = set()
        records_by_borough = defaultdict(int)
        records_by_complaint = defaultdict(int)

        total_records = 0
        month_set = set(months)

        with cases_path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as file:

            reader = csv.DictReader(file)

            if not self.REQUIRED_CASE_COLUMNS.issubset(
                set(reader.fieldnames or [])
            ):
                raise DataValidationError(
                    "Enriched cases schema is invalid."
                )

            for line_number, row in enumerate(reader, start=2):

                total_records += 1

                borough = (
                    row.get("borough") or ""
                ).strip().upper()

                if not borough or borough == "UNSPECIFIED":
                    borough = "UNSPECIFIED"

                elif borough not in population:
                    raise DataValidationError(
                        f"Unknown borough at line {line_number}: "
                        f"{borough}"
                    )

                complaint = (
                    row.get("complaint_type") or ""
                ).strip()

                if not complaint:
                    raise DataValidationError(
                        f"Missing complaint type at line {line_number}"
                    )

                month = (
                    row.get("created_year_month") or ""
                ).strip()

                if month not in month_set:
                    raise DataValidationError(
                        f"Unexpected month at line {line_number}: "
                        f"{month}"
                    )

                try:
                    created = datetime.fromisoformat(
                        row["created_date"]
                    )

                    if created.strftime("%Y-%m") != month:
                        raise DataValidationError

                except (ValueError, TypeError) as exc:
                    raise DataValidationError(
                        f"Invalid or inconsistent date at line "
                        f"{line_number}"
                    ) from exc

                try:
                    duration = float(row["resolution_time_hours"])

                    if not math.isfinite(duration) or duration < 0:
                        raise ValueError("Duration must be finite and non-negative")

                except (ValueError, TypeError) as exc:
                    raise DataValidationError(
                        f"Invalid resolution duration at line {line_number}"
                    ) from exc

                key = (borough, complaint, month)

                item = aggregates[key]

                item["count"] += 1
                item["duration_sum"] += duration
                item["durations"].append(duration)

                groups.add((borough, complaint))

                records_by_borough[borough] += 1
                records_by_complaint[complaint] += 1

        if total_records == 0:
            raise DataValidationError("No records found for aggregation.")

        if (
            expected_count is not None
            and total_records != expected_count
        ):
            raise DataValidationError(
                f"Input count mismatch: expected {expected_count}, "
                f"received {total_records}"
            )

        aggregated_count = sum(
            item["count"]
            for item in aggregates.values()
        )

        if aggregated_count != total_records:
            raise DataValidationError(
                "Aggregation record conservation failed."
            )

        fields = [
            "borough",
            "complaint_type",
            f"population_estimate_{population_year}",
            "total_complaints",
        ]

        for month in months:
            fields.extend([
                f"{month}_complaints",
                f"{month}_rate_per_1000_residents",
                f"{month}_mean_resolution_hours",
                f"{month}_median_resolution_hours",
            ])

        output_rows = []

        for borough, complaint in sorted(groups):

            borough_population = population.get(borough)

            row = {
                "borough": borough,
                "complaint_type": complaint,
                f"population_estimate_{population_year}": (
                    borough_population
                    if borough_population is not None
                    else ""
                ),
                "total_complaints": 0,
            }

            for month in months:

                item = aggregates.get(
                    (borough, complaint, month)
                )

                if item is None:
                    count = 0
                    mean = ""
                    med = ""

                else:
                    count = item["count"]

                    mean = (
                        f"{item['duration_sum'] / count:.6f}"
                    )

                    med = f"{median(item['durations']):.6f}"

                row["total_complaints"] += count

                row[f"{month}_complaints"] = count

                if borough_population is None:
                    rate = ""
                else:
                    rate = (
                        f"{count / borough_population * 1000:.6f}"
                    )

                row[
                    f"{month}_rate_per_1000_residents"
                ] = rate

                row[
                    f"{month}_mean_resolution_hours"
                ] = mean

                row[
                    f"{month}_median_resolution_hours"
                ] = med

            output_rows.append(row)

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_tmp = output_path.with_name(
            "." + output_path.name + ".tmp"
        )

        try:

            with output_tmp.open(
                "w",
                encoding="utf-8-sig",
                newline="",
            ) as file:

                writer = csv.DictWriter(
                    file,
                    fieldnames=fields,
                    lineterminator="\n",
                )

                writer.writeheader()
                writer.writerows(output_rows)

                file.flush()
                os.fsync(file.fileno())

            report = {
                "input_file": cases_path.name,
                "input_records": total_records,
                "aggregated_records": aggregated_count,
                "wide_output_rows": len(output_rows),
                "wide_output_columns": len(fields),
                "months": months,
                "month_count": len(months),
                "population_year": population_year,
                "population_source": Path(
                    population_path
                ).name,
                "population_boroughs": sorted(population),
                "records_by_borough": dict(
                    sorted(records_by_borough.items())
                ),
                "records_by_complaint_type": dict(
                    sorted(records_by_complaint.items())
                ),
                "unspecified_borough_records": (
                    records_by_borough.get("UNSPECIFIED", 0)
                ),
                "rate_definition": (
                    "Monthly complaint count / 2024 ACS "
                    "borough population * 1000; not annualized."
                ),
                "population_denominator_note": (
                    "Borough population is counted once per borough, "
                    "not summed from case-level ZIP population."
                ),
            }

            os.replace(output_tmp, output_path)

            self._write_json(
                report_path,
                report,
            )

            report["output_file"] = str(output_path)
            report["report_file"] = str(report_path)

            return report

        finally:
            output_tmp.unlink(missing_ok=True)
