
import csv
import json
import tempfile
import unittest

from pathlib import Path

from data_factory.transformer import (
    DataTransformer,
    SOURCE_COLUMNS,
    OUTPUT_COLUMNS,
)
from data_factory.exceptions import DataValidationError


def make_record():

    record = {
        field: None
        for field in SOURCE_COLUMNS
    }

    record.update({
        "unique_key": "59889016",
        "created_date": "2024-01-01T00:00:00.000",
        "closed_date": "2024-01-01T01:30:00.000",
        "agency": "NYPD",
        "complaint_type": "Noise - Residential",
        "status": "Closed",
        "borough": "BRONX",
        "incident_zip": "02108",
        "latitude": "40.8624",
        "longitude": "-73.9110",
        "police_precinct": "Precinct 7",
        "council_district": "12",
        "x_coordinate_state_plane": "1000000.5",
        "y_coordinate_state_plane": "2000000.5",
        "location": {
            "latitude": "40.8624",
            "longitude": "-73.9110",
        },
        "bbl": "0012345678",
    })

    return record


class TestDataTransformer(unittest.TestCase):

    def setUp(self):

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name)

        self.input_path = self.root / "accepted.jsonl"
        self.output_dir = self.root / "output"

        self.transformer = DataTransformer()

    def write_records(self, records):

        with self.input_path.open(
            "w",
            encoding="utf-8",
        ) as file:

            for record in records:
                file.write(
                    json.dumps(record, ensure_ascii=False) + "\n"
                )

    def run_transform(self, expected_count=None):

        return self.transformer.transform(
            self.input_path,
            self.output_dir,
            expected_count=expected_count,
        )

    def read_csv(self):

        with self.output_dir.joinpath("cases.csv").open(
            encoding="utf-8-sig",
            newline="",
        ) as file:

            return list(csv.DictReader(file))

    def test_transforms_valid_record(self):

        self.write_records([make_record()])

        report = self.run_transform(1)

        rows = self.read_csv()
        row = rows[0]

        self.assertEqual(report["records_transformed"], 1)

        self.assertEqual(
            row["resolution_time_hours"],
            "1.5",
        )

        self.assertEqual(row["created_year"], "2024")
        self.assertEqual(row["created_month"], "1")
        self.assertEqual(row["created_year_month"], "2024-01")

        self.assertEqual(row["incident_zip"], "02108")
        self.assertEqual(row["police_precinct"], "Precinct 7")

        self.assertEqual(
            len(row),
            len(OUTPUT_COLUMNS),
        )

    def test_preserves_nested_location(self):

        self.write_records([make_record()])

        self.run_transform(1)

        row = self.read_csv()[0]

        location = json.loads(row["location"])

        self.assertEqual(
            location["latitude"],
            "40.8624",
        )

    def test_missing_closed_date(self):

        record = make_record()
        record["closed_date"] = None

        self.write_records([record])

        self.run_transform(1)

        row = self.read_csv()[0]

        self.assertEqual(
            row["resolution_time_hours"],
            "",
        )

    def test_missing_zip_is_preserved(self):

        record = make_record()
        record["incident_zip"] = None

        self.write_records([record])

        report = self.run_transform(1)

        row = self.read_csv()[0]

        self.assertEqual(row["incident_zip"], "")
        self.assertEqual(report["missing_zip"], 1)

    def test_negative_duration_is_rejected(self):

        record = make_record()
        record["closed_date"] = "2023-12-31T23:00:00"

        self.write_records([record])

        with self.assertRaises(DataValidationError):
            self.run_transform(1)

        self.assertFalse(
            (self.output_dir / "cases.csv").exists()
        )

    def test_invalid_numeric_value_is_rejected(self):

        record = make_record()
        record["latitude"] = "ABC"

        self.write_records([record])

        with self.assertRaises(DataValidationError):
            self.run_transform(1)

    def test_invalid_json_is_rejected(self):

        self.input_path.write_text(
            "{invalid json\n",
            encoding="utf-8",
        )

        with self.assertRaises(DataValidationError):
            self.run_transform(1)

    def test_record_count_mismatch(self):

        self.write_records([make_record()])

        with self.assertRaises(DataValidationError):
            self.run_transform(2)

    def test_repeated_execution_is_deterministic(self):

        self.write_records([
            make_record(),
            make_record(),
        ])

        self.run_transform(2)

        first_csv = (
            self.output_dir / "cases.csv"
        ).read_bytes()

        first_report = (
            self.output_dir / "transformation_report.json"
        ).read_bytes()

        self.run_transform(2)

        second_csv = (
            self.output_dir / "cases.csv"
        ).read_bytes()

        second_report = (
            self.output_dir / "transformation_report.json"
        ).read_bytes()

        self.assertEqual(first_csv, second_csv)
        self.assertEqual(first_report, second_report)


if __name__ == "__main__":
    unittest.main()
