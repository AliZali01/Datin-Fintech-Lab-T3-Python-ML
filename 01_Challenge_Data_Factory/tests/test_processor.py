
import json
import tempfile
import unittest

from pathlib import Path

from data_factory.processor import DataProcessor
from data_factory.exceptions import DataValidationError


def make_record(key="1001", closed="2024-01-01T01:00:00"):
    return {
        "unique_key": key,
        "created_date": "2024-01-01T00:00:00",
        "closed_date": closed,
        "complaint_type": "Noise - Residential",
        "agency": "NYPD",
        "status": "Closed",
        "borough": "BRONX",
        "incident_zip": "10468",
        "latitude": "40.86",
        "longitude": "-73.91",
        "open_data_channel_type": "ONLINE",
    }


class TestDataProcessor(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name)
        self.batches = self.root / "batches"
        self.output = self.root / "output"

        self.batches.mkdir()

        self.processor = DataProcessor(
            expected_complaint_type="Noise - Residential",
            max_quarantine_ratio=1.0,
        )

    def write_batch(self, records):
        path = self.batches / "batch_000000000.jsonl"

        with path.open("w", encoding="utf-8") as file:
            for record in records:
                if isinstance(record, str):
                    file.write(record + "\n")
                else:
                    file.write(json.dumps(record) + "\n")

    def run_processor(self, count):
        return self.processor.process(
            self.batches,
            self.output,
            expected_raw_count=count,
        )

    def read_jsonl(self, path):
        with path.open(encoding="utf-8") as file:
            return [json.loads(line) for line in file]

    def test_valid_and_invalid_records_are_separated(self):
        valid = make_record()
        invalid = make_record(
            key="1002",
            closed="2023-12-31T23:00:00",
        )
        missing_zip = make_record(key="1003")
        missing_zip["incident_zip"] = None

        self.write_batch([valid, invalid, missing_zip])

        report = self.run_processor(3)

        self.assertEqual(report["accepted_records"], 2)
        self.assertEqual(report["quarantined_records"], 1)

        accepted = self.read_jsonl(
            self.output / "accepted.jsonl"
        )

        rejected = self.read_jsonl(
            self.output / "quarantine.jsonl"
        )

        self.assertIsNone(accepted[1]["incident_zip"])

        self.assertIn(
            "CLOSED_BEFORE_CREATED",
            rejected[0]["reasons"],
        )

    def test_duplicate_unique_key_is_quarantined(self):
        self.write_batch([
            make_record("1001"),
            make_record("1001"),
        ])

        report = self.run_processor(2)

        self.assertEqual(report["accepted_records"], 1)
        self.assertEqual(report["duplicate_records"], 1)
        self.assertEqual(report["quarantined_records"], 1)

    def test_invalid_first_record_does_not_block_valid_record(self):
        invalid = make_record(
            "1001",
            closed="2023-12-31T23:00:00",
        )
        valid = make_record("1001")

        self.write_batch([invalid, valid])

        report = self.run_processor(2)

        self.assertEqual(report["accepted_records"], 1)
        self.assertEqual(report["duplicate_records"], 0)

    def test_quarantine_threshold_stops_processing(self):
        invalid = make_record(
            "1001",
            closed="2023-12-31T23:00:00",
        )

        self.write_batch([invalid])

        strict_processor = DataProcessor(
            expected_complaint_type="Noise - Residential",
            max_quarantine_ratio=0.05,
        )

        with self.assertRaises(DataValidationError):
            strict_processor.process(
                self.batches,
                self.output,
                expected_raw_count=1,
            )

        self.assertTrue(
            (self.output / "quarantine.jsonl").exists()
        )

        self.assertTrue(
            (self.output / "quality_report.json").exists()
        )

        self.assertFalse(
            (self.output / "accepted.jsonl").exists()
        )
    
    def test_malformed_json_is_quarantined(self):
        self.write_batch(["{invalid json"])

        report = self.run_processor(1)

        self.assertEqual(report["quarantined_records"], 1)

        rejected = self.read_jsonl(
            self.output / "quarantine.jsonl"
        )

        self.assertIn(
            "MALFORMED_JSON",
            rejected[0]["reasons"],
        )

    def test_missing_zip_is_preserved_as_null(self):
        record = make_record()
        record["incident_zip"] = None

        self.write_batch([record])

        report = self.run_processor(1)

        accepted = self.read_jsonl(
            self.output / "accepted.jsonl"
        )

        self.assertEqual(report["accepted_records"], 1)
        self.assertIsNone(accepted[0]["incident_zip"])

    def test_repeated_execution_is_deterministic(self):
        self.write_batch([
            make_record("1001"),
            make_record(
                "1002",
                closed="2023-12-31T23:00:00",
            ),
        ])

        self.run_processor(2)

        first_outputs = {
            name: (self.output / name).read_bytes()
            for name in (
                "accepted.jsonl",
                "quarantine.jsonl",
                "quality_report.json",
            )
        }

        self.run_processor(2)

        second_outputs = {
            name: (self.output / name).read_bytes()
            for name in first_outputs
        }

        self.assertEqual(first_outputs, second_outputs)

    def test_raw_count_mismatch_is_rejected(self):
        self.write_batch([make_record()])

        with self.assertRaises(DataValidationError):
            self.run_processor(2)


if __name__ == "__main__":
    unittest.main()
