
import tempfile
import unittest
import json

from pathlib import Path

from data_factory.collector import NYC311Collector
from data_factory.exceptions import DataValidationError


class FakeClient:

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None):
        self.calls.append({
            "url": url,
            "params": params,
        })

        return self.responses.pop(0)


class TestNYC311Collector(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.config = {
            "api": {
                "endpoint": "https://example.com/data.json",
                "batch_size": 2,
            },
            "collection": {
                "start_date": "2024-01-01T00:00:00",
                "end_date": "2025-07-01T00:00:00",
                "scope": {
                    "agency": None,
                    "complaint_type": "Noise - Residential",
                    "borough": None,
                },
            },
            "paths": {
                "raw_dir": str(Path(self.temp_dir.name) / "raw"),
                "curated_dir": str(Path(self.temp_dir.name) / "curated"),
            },
        }

    def test_pagination_and_jsonl_storage(self):
        client = FakeClient([
            [{"unique_key": "1"}, {"unique_key": "2"}],
            [{"unique_key": "3"}],
        ])

        collector = NYC311Collector(self.config, client)
        result = collector.collect()

        self.assertEqual(result["records_written"], 3)
        self.assertEqual(result["batches_written"], 2)
        self.assertTrue(result["completed"])

        self.assertEqual(
            client.calls[0]["params"]["$offset"], 0
        )
        self.assertEqual(
            client.calls[1]["params"]["$offset"], 2
        )

        self.assertEqual(
            len(list(collector.batches_dir.glob("*.jsonl"))), 2
        )

    def test_resume_from_checkpoint(self):
        first_client = FakeClient([
            [{"unique_key": "1"}, {"unique_key": "2"}]
        ])

        collector = NYC311Collector(self.config, first_client)
        first_result = collector.collect(max_batches=1)

        self.assertFalse(first_result["completed"])
        self.assertEqual(first_result["next_offset"], 2)

        second_client = FakeClient([
            [{"unique_key": "3"}]
        ])

        resumed = NYC311Collector(self.config, second_client)
        second_result = resumed.collect()

        self.assertEqual(
            second_client.calls[0]["params"]["$offset"], 2
        )
        self.assertEqual(second_result["records_written"], 3)
        self.assertTrue(second_result["completed"])

    def test_invalid_api_response_is_rejected(self):
        client = FakeClient([
            {"error": "invalid response"}
        ])

        collector = NYC311Collector(self.config, client)

        with self.assertRaises(DataValidationError):
            collector.collect()

    def test_empty_response_completes_collection(self):
        client = FakeClient([[]])

        collector = NYC311Collector(self.config, client)
        result = collector.collect()

        self.assertTrue(result["completed"])
        self.assertEqual(result["records_written"], 0)


if __name__ == "__main__":
    unittest.main()
