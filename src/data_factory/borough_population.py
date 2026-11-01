
import csv
import json
import os

from pathlib import Path

import requests

from .exceptions import (
    ConfigurationError,
    NetworkError,
    DataValidationError,
)


BOROUGH_COLUMNS = [
    "borough",
    "county_fips",
    "county_name",
    "population_estimate",
    "dataset_year",
    "variable",
]


class BoroughPopulationClient:

    def __init__(
        self,
        endpoint,
        variable,
        dataset_year,
        state_fips,
        county_to_borough,
        timeout_seconds=60,
        session=None,
    ):
        self.endpoint = endpoint
        self.variable = variable
        self.dataset_year = dataset_year
        self.state_fips = state_fips
        self.county_to_borough = county_to_borough
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

    def fetch(self, api_key):

        if not api_key:
            raise ConfigurationError(
                "CENSUS_API_KEY is missing."
            )

        params = {
            "get": f"NAME,{self.variable}",
            "for": "county:*",
            "in": f"state:{self.state_fips}",
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
                f"Census county request failed: {exc}"
            ) from exc

        try:
            payload = response.json()

        except ValueError as exc:
            raise DataValidationError(
                "Invalid Census county JSON response."
            ) from exc

        if not isinstance(payload, list) or len(payload) < 2:
            raise DataValidationError(
                "Empty Census county response."
            )

        header = payload[0]

        required = {
            "NAME",
            self.variable,
            "state",
            "county",
        }

        if not required.issubset(set(header)):
            raise DataValidationError(
                f"Unexpected county schema: {header}"
            )

        name_i = header.index("NAME")
        population_i = header.index(self.variable)
        state_i = header.index("state")
        county_i = header.index("county")

        records = {}
        
        for values in payload[1:]:

            if len(values) != len(header):
                raise DataValidationError(
                    "Malformed Census county row."
                )

            state = str(values[state_i]).zfill(2)
            county = str(values[county_i]).zfill(3)

            if state != self.state_fips:
                continue

            if county not in self.county_to_borough:
                continue

            if county in records:
                raise DataValidationError(
                    f"Duplicate county: {county}"
                )

            try:
                population = int(values[population_i])

                if population < 0:
                    raise ValueError

            except (ValueError, TypeError) as exc:
                raise DataValidationError(
                    f"Invalid population for county {county}"
                ) from exc

            records[county] = {
                "borough": self.county_to_borough[county],
                "county_fips": state + county,
                "county_name": values[name_i],
                "population_estimate": population,
                "dataset_year": self.dataset_year,
                "variable": self.variable,
            }

        missing = set(self.county_to_borough) - set(records)

        if missing:
            raise DataValidationError(
                f"Missing NYC counties: {sorted(missing)}"
            )

        return payload, sorted(
            records.values(),
            key=lambda x: x["borough"],
        )

    def download(self, api_key, raw_path, curated_path):

        raw_path = Path(raw_path)
        curated_path = Path(curated_path)

        raw_path.parent.mkdir(parents=True, exist_ok=True)
        curated_path.parent.mkdir(parents=True, exist_ok=True)

        payload, records = self.fetch(api_key)

        raw_tmp = raw_path.with_name("." + raw_path.name + ".tmp")
        csv_tmp = curated_path.with_name(
            "." + curated_path.name + ".tmp"
        )

        try:

            with raw_tmp.open(
                "w",
                encoding="utf-8",
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

            with csv_tmp.open(
                "w",
                encoding="utf-8-sig",
                newline="",
            ) as file:

                writer = csv.DictWriter(
                    file,
                    fieldnames=BOROUGH_COLUMNS,
                    lineterminator="\n",
                )

                writer.writeheader()
                writer.writerows(records)

                file.flush()
                os.fsync(file.fileno())

            os.replace(raw_tmp, raw_path)
            os.replace(csv_tmp, curated_path)

        finally:
            raw_tmp.unlink(missing_ok=True)
            csv_tmp.unlink(missing_ok=True)

        return {
            "boroughs": len(records),
            "population_records": records,
            "raw_file": str(raw_path),
            "curated_file": str(curated_path),
        }
