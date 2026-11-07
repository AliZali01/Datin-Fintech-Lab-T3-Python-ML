
import csv
import tempfile
import unittest

from pathlib import Path
from unittest.mock import Mock

from data_factory.population import (
    PopulationClient,
    PopulationEnricher,
)

from data_factory.exceptions import (
    ConfigurationError,
    DataValidationError,
)


SAMPLE_RESPONSE = [
    ["NAME", "B01001_001E", "zip code tabulation area"],
    ["ZCTA5 10001", "25000", "10001"],
    ["ZCTA5 10002", "30000", "10002"],
    ["ZCTA5 02108", "12000", "02108"],
]


class TestPopulationClient(unittest.TestCase):

    def setUp(self):
        self.session = Mock()

        self.client = PopulationClient(
            endpoint="https://example.com/census",
            variable="B01001_001E",
            geography="zip code tabulation area:*",
            dataset_year=2024,
            session=self.session,
        )

        self.response = Mock()
        self.response.json.return_value = SAMPLE_RESPONSE
        self.session.get.return_value = self.response

    def test_fetch_population(self):

        payload, records = self.client.fetch("fake-key")

        self.assertEqual(len(records), 3)
        self.assertEqual(records[0]["zcta"], "02108")
        self.assertEqual(records[0]["population_estimate"], 12000)

        self.session.get.assert_called_once()

    def test_missing_api_key(self):

        with self.assertRaises(ConfigurationError):
            self.client.fetch(None)

    def test_duplicate_zcta_is_rejected(self):

        self.response.json.return_value = [
            SAMPLE_RESPONSE[0],
            SAMPLE_RESPONSE[1],
            SAMPLE_RESPONSE[1],
        ]

        with self.assertRaises(DataValidationError):
            self.client.fetch("fake-key")

    def test_invalid_population_is_rejected(self):

        self.response.json.return_value = [
            SAMPLE_RESPONSE[0],
            ["ZCTA5 10001", "invalid", "10001"],
        ]

        with self.assertRaises(DataValidationError):
            self.client.fetch("fake-key")

    def test_unexpected_schema_is_rejected(self):

        self.response.json.return_value = [
            ["NAME", "POPULATION", "ZCTA"],
            ["ZCTA5 10001", "25000", "10001"],
        ]

        with self.assertRaises(DataValidationError):
            self.client.fetch("fake-key")


class TestPopulationEnricher(unittest.TestCase):

    def setUp(self):

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name)

        self.cases_path = self.root / "cases.csv"
        self.reference_path = self.root / "population.csv"

        self.output_path = self.root / "enriched.csv"
        self.report_path = self.root / "report.json"

        self.enricher = PopulationEnricher()

        self.write_reference()

        self.write_cases([
            {"unique_key": "1", "incident_zip": "02108"},
            {"unique_key": "2", "incident_zip": "10001"},
            {"unique_key": "3", "incident_zip": ""},
            {"unique_key": "4", "incident_zip": "99999"},
        ])

    def write_reference(self):

        with self.reference_path.open(
            "w",
            encoding="utf-8",
            newline="",
        ) as file:

            writer = csv.DictWriter(
                file,
                fieldnames=[
                    "zcta",
                    "zcta_name",
                    "population_estimate",
                    "dataset_year",
                    "variable",
                ],
            )

            writer.writeheader()

            writer.writerows([
                {
                    "zcta": "02108",
                    "zcta_name": "ZCTA5 02108",
                    "population_estimate": 12000,
                    "dataset_year": 2024,
                    "variable": "B01001_001E",
                },
                {
                    "zcta": "10001",
                    "zcta_name": "ZCTA5 10001",
                    "population_estimate": 25000,
                    "dataset_year": 2024,
                    "variable": "B01001_001E",
                },
            ])

    def write_cases(self, records):

        with self.cases_path.open(
            "w",
            encoding="utf-8",
            newline="",
        ) as file:

            writer = csv.DictWriter(
                file,
                fieldnames=["unique_key", "incident_zip"],
            )

            writer.writeheader()
            writer.writerows(records)

    def test_left_join_preserves_all_records(self):

        report = self.enricher.enrich(
            self.cases_path,
            self.reference_path,
            self.output_path,
            self.report_path,
            expected_count=4,
        )

        self.assertEqual(report["input_records"], 4)
        self.assertEqual(report["output_records"], 4)
        self.assertEqual(report["matched_records"], 2)

        with self.output_path.open(
            encoding="utf-8-sig",
            newline="",
        ) as file:

            rows = list(csv.DictReader(file))

        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["population_estimate"], "12000")
        self.assertEqual(rows[0]["population_match_status"], "MATCHED")

        self.assertEqual(
            rows[2]["population_match_status"],
            "MISSING_ZIP",
        )

        self.assertEqual(
            rows[3]["population_match_status"],
            "NO_ZCTA_MATCH",
        )

    def test_count_mismatch_is_rejected(self):

        with self.assertRaises(DataValidationError):

            self.enricher.enrich(
                self.cases_path,
                self.reference_path,
                self.output_path,
                self.report_path,
                expected_count=10,
            )

    def test_duplicate_reference_is_rejected(self):

        with self.reference_path.open(
            "a",
            encoding="utf-8",
        ) as file:

            file.write(
                "02108,ZCTA5 02108,12000,2024,B01001_001E\n"
            )

        with self.assertRaises(DataValidationError):

            self.enricher.enrich(
                self.cases_path,
                self.reference_path,
                self.output_path,
                self.report_path,
            )


if __name__ == "__main__":
    unittest.main()
