
import csv
import json
import math
import os
import re

from pathlib import Path

import requests

from .exceptions import ConfigurationError, NetworkError, DataValidationError


ZIP_PATTERN = re.compile(r"^\d{5}$")

REFERENCE_COLUMNS = [
    "zcta",
    "zcta_name",
    "population_estimate",
    "dataset_year",
    "variable",
]

ENRICHMENT_COLUMNS = [
    "population_estimate",
    "population_match_status",
]


class PopulationClient:

    def __init__(
        self,
        endpoint,
        variable,
        geography,
        dataset_year,
        timeout_seconds=60,
        session=None,
    ):
        self.endpoint = endpoint
        self.variable = variable
        self.geography = geography
        self.dataset_year = dataset_year
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

    def fetch(self, api_key):

        if not api_key:
            raise ConfigurationError(
                "CENSUS_API_KEY environment variable is missing."
            )

        params = {
            "get": f"NAME,{self.variable}",
            "for": self.geography,
            "key": api_key,
        }

        try:
            response = self.session.get(
                self.endpoint,
                params=params,
                timeout=self.timeout_seconds,
            )

            response.raise_for_status()

        except requests.RequestException as exc:
            raise NetworkError(
                f"Census API request failed: {exc}"
            ) from exc

        try:
            payload = response.json()

        except ValueError as exc:
            raise DataValidationError(
                "Census API returned invalid JSON."
            ) from exc

        if not isinstance(payload, list) or len(payload) < 2:
            raise DataValidationError(
                "Census API returned an empty or invalid response."
            )

        header = payload[0]

        required_headers = {
            "NAME",
            self.variable,
            "zip code tabulation area",
        }

        if (
            not isinstance(header, list)
            or not required_headers.issubset(set(header))
        ):
            raise DataValidationError(
                f"Unexpected Census API schema: {header}"
            )

        name_index = header.index("NAME")
        population_index = header.index(self.variable)
        zcta_index = header.index("zip code tabulation area")

        records = []
        seen_zctas = set()

        for line_number, values in enumerate(payload[1:], start=2):

            if not isinstance(values, list) or len(values) != len(header):
                raise DataValidationError(
                    f"Malformed Census row: {line_number}"
                )

            zcta = str(values[zcta_index]).strip()
            name = str(values[name_index]).strip()
            population_value = values[population_index]

            if not ZIP_PATTERN.fullmatch(zcta):
                raise DataValidationError(
                    f"Invalid ZCTA at row {line_number}: {zcta}"
                )

            if zcta in seen_zctas:
                raise DataValidationError(
                    f"Duplicate ZCTA found: {zcta}"
                )

            if population_value in (None, "", "-", "null"):
                raise DataValidationError(
                    f"Missing population for ZCTA {zcta}"
                )

            try:
                population_float = float(population_value)

                if (
                    not math.isfinite(population_float)
                    or not population_float.is_integer()
                    or population_float < 0
                ):
                    raise ValueError("Invalid population")

                population = int(population_float)

            except (ValueError, TypeError) as exc:
                raise DataValidationError(
                    f"Invalid population for ZCTA {zcta}: "
                    f"{population_value}"
                ) from exc

            seen_zctas.add(zcta)

            records.append({
                "zcta": zcta,
                "zcta_name": name,
                "population_estimate": population,
                "dataset_year": self.dataset_year,
                "variable": self.variable,
            })

        if not records:
            raise DataValidationError(
                "Census API returned no population records."
            )

        return payload, sorted(records, key=lambda x: x["zcta"])

    @staticmethod
    def _atomic_write_json(path, payload):

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        temp_path = path.with_name("." + path.name + ".tmp")

        try:
            with temp_path.open(
                "w",
                encoding="utf-8",
                newline="\n",
            ) as file:

                json.dump(
                    payload,
                    file,
                    ensure_ascii=False,
                    indent=2,
                )

                file.write("\n")
                file.flush()
                os.fsync(file.fileno())

            os.replace(temp_path, path)

        finally:
            temp_path.unlink(missing_ok=True)

    @staticmethod
    def _atomic_write_csv(path, records):

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        temp_path = path.with_name("." + path.name + ".tmp")

        try:
            with temp_path.open(
                "w",
                encoding="utf-8-sig",
                newline="",
            ) as file:

                writer = csv.DictWriter(
                    file,
                    fieldnames=REFERENCE_COLUMNS,
                    lineterminator="\n",
                )

                writer.writeheader()
                writer.writerows(records)

                file.flush()
                os.fsync(file.fileno())

            os.replace(temp_path, path)

        finally:
            temp_path.unlink(missing_ok=True)

    def download(self, api_key, raw_path, curated_path):

        raw_payload, records = self.fetch(api_key)

        # Validate completely before replacing existing files.
        self._atomic_write_json(raw_path, raw_payload)
        self._atomic_write_csv(curated_path, records)

        return {
            "source_records": len(records),
            "raw_file": str(raw_path),
            "curated_file": str(curated_path),
            "dataset_year": self.dataset_year,
            "variable": self.variable,
        }


class PopulationEnricher:

    def load_reference(self, reference_path):

        reference = {}

        with Path(reference_path).open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as file:

            reader = csv.DictReader(file)

            if not set(REFERENCE_COLUMNS).issubset(
                set(reader.fieldnames or [])
            ):
                raise DataValidationError(
                    "Population reference schema is invalid."
                )

            for row in reader:

                zcta = row["zcta"]

                if not ZIP_PATTERN.fullmatch(zcta):
                    raise DataValidationError(
                        f"Invalid reference ZCTA: {zcta}"
                    )

                if zcta in reference:
                    raise DataValidationError(
                        f"Duplicate reference ZCTA: {zcta}"
                    )

                try:
                    population = int(row["population_estimate"])

                    if population < 0:
                        raise ValueError

                except (ValueError, TypeError) as exc:
                    raise DataValidationError(
                        f"Invalid population for {zcta}"
                    ) from exc

                reference[zcta] = population

        if not reference:
            raise DataValidationError(
                "Population reference is empty."
            )

        return reference

    def enrich(
        self,
        cases_path,
        reference_path,
        output_path,
        report_path,
        expected_count=None,
    ):

        cases_path = Path(cases_path)
        output_path = Path(output_path)
        report_path = Path(report_path)

        if not cases_path.is_file():
            raise DataValidationError("Cases CSV not found.")

        reference = self.load_reference(reference_path)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.parent.mkdir(parents=True, exist_ok=True)

        output_tmp = output_path.with_name(
            "." + output_path.name + ".tmp"
        )

        report_tmp = report_path.with_name(
            "." + report_path.name + ".tmp"
        )

        total = 0
        matched = 0
        missing_zip = 0
        unmatched_zip = 0

        try:

            with (
                cases_path.open(
                    "r",
                    encoding="utf-8-sig",
                    newline="",
                ) as source,
                output_tmp.open(
                    "w",
                    encoding="utf-8-sig",
                    newline="",
                ) as destination,
            ):

                reader = csv.DictReader(source)

                if not reader.fieldnames or (
                    "incident_zip" not in reader.fieldnames
                ):
                    raise DataValidationError(
                        "Cases CSV has no incident_zip column."
                    )

                if set(ENRICHMENT_COLUMNS).intersection(
                    reader.fieldnames
                ):
                    raise DataValidationError(
                        "Cases CSV is already enriched."
                    )

                output_fields = (
                    reader.fieldnames + ENRICHMENT_COLUMNS
                )

                writer = csv.DictWriter(
                    destination,
                    fieldnames=output_fields,
                    lineterminator="\n",
                )

                writer.writeheader()

                for row in reader:

                    total += 1

                    zip_code = (row.get("incident_zip") or "").strip()

                    if not zip_code:
                        population = None
                        status = "MISSING_ZIP"
                        missing_zip += 1

                    elif zip_code in reference:
                        population = reference[zip_code]
                        status = "MATCHED"
                        matched += 1

                    else:
                        population = None
                        status = "NO_ZCTA_MATCH"
                        unmatched_zip += 1

                    row["population_estimate"] = (
                        population if population is not None else ""
                    )

                    row["population_match_status"] = status

                    writer.writerow(row)

                destination.flush()
                os.fsync(destination.fileno())

            if (
                expected_count is not None
                and total != expected_count
            ):
                raise DataValidationError(
                    f"Join count mismatch: expected "
                    f"{expected_count}, got {total}"
                )

            report = {
                "input_records": total,
                "output_records": total,
                "matched_records": matched,
                "missing_zip_records": missing_zip,
                "unmatched_zip_records": unmatched_zip,
                "distinct_population_zctas": len(reference),
                "join_type": "left",
                "join_key": "incident_zip = zcta",
            }

            with report_tmp.open(
                "w",
                encoding="utf-8",
                newline="\n",
            ) as file:

                json.dump(
                    report,
                    file,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )

                file.write("\n")
                file.flush()
                os.fsync(file.fileno())

            os.replace(output_tmp, output_path)
            os.replace(report_tmp, report_path)

            return report

        finally:
            output_tmp.unlink(missing_ok=True)
            report_tmp.unlink(missing_ok=True)
