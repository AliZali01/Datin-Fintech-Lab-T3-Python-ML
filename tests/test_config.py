"""Tests for Data Factory configuration loading."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from data_factory.config import load_config
from data_factory.exceptions import ConfigurationError


VALID_CONFIG = {
    "api": {
        "endpoint": "https://example.com/data.json",
        "method": "GET",
        "timeout_seconds": 30,
        "max_retries": 3,
        "batch_size": 5000,
    },
    "collection": {
        "start_date": "2024-01-01T00:00:00",
        "end_date": "2025-07-01T00:00:00",
        "scope": {
            "agency": None,
            "complaint_type": None,
            "borough": None,
        },
    },
    "paths": {
        "raw_dir": "data/raw",
        "curated_dir": "data/curated",
    },
    "quality": {
        "max_quarantine_ratio": 0.05,
    },
}


class TestLoadConfig(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.config_path = Path(self.temp_dir.name) / "config.json"
        self.config = copy.deepcopy(VALID_CONFIG)

    def write_config(self, config=None, raw_text=None):
        if raw_text is not None:
            self.config_path.write_text(raw_text, encoding="utf-8")
        else:
            data = self.config if config is None else config
            self.config_path.write_text(
                json.dumps(data),
                encoding="utf-8",
            )

        return self.config_path

    def test_loads_valid_configuration(self):
        path = self.write_config()

        result = load_config(path)

        self.assertEqual(result["api"]["batch_size"], 5000)
        self.assertEqual(result["api"]["method"], "GET")

    def test_missing_file_raises_configuration_error(self):
        missing_path = self.config_path.parent / "missing.json"

        with self.assertRaises(ConfigurationError):
            load_config(missing_path)

    def test_invalid_json_raises_configuration_error(self):
        path = self.write_config(raw_text="{invalid json")

        with self.assertRaises(ConfigurationError):
            load_config(path)

    def test_root_must_be_a_json_object(self):
        path = self.write_config(config=["not", "an", "object"])

        with self.assertRaises(ConfigurationError):
            load_config(path)

    def test_required_section_must_exist(self):
        del self.config["api"]
        path = self.write_config()

        with self.assertRaises(ConfigurationError):
            load_config(path)

    def test_endpoint_must_not_be_empty(self):
        self.config["api"]["endpoint"] = " "
        path = self.write_config()

        with self.assertRaises(ConfigurationError):
            load_config(path)

    def test_method_must_be_get_or_post(self):
        self.config["api"]["method"] = "PUT"
        path = self.write_config()

        with self.assertRaises(ConfigurationError):
            load_config(path)

    def test_timeout_must_be_positive(self):
        self.config["api"]["timeout_seconds"] = 0
        path = self.write_config()

        with self.assertRaises(ConfigurationError):
            load_config(path)

    def test_max_retries_must_be_non_negative(self):
        self.config["api"]["max_retries"] = -1
        path = self.write_config()

        with self.assertRaises(ConfigurationError):
            load_config(path)

    def test_batch_size_must_be_positive(self):
        self.config["api"]["batch_size"] = 0
        path = self.write_config()

        with self.assertRaises(ConfigurationError):
            load_config(path)

    def test_invalid_date_raises_configuration_error(self):
        self.config["collection"]["start_date"] = "not-a-date"
        path = self.write_config()

        with self.assertRaises(ConfigurationError):
            load_config(path)

    def test_end_date_must_be_after_start_date(self):
        self.config["collection"]["end_date"] = (
            self.config["collection"]["start_date"]
        )
        path = self.write_config()

        with self.assertRaises(ConfigurationError):
            load_config(path)

    def test_data_paths_must_be_relative(self):
        self.config["paths"]["raw_dir"] = str(
            Path(self.temp_dir.name).resolve()
        )
        path = self.write_config()

        with self.assertRaises(ConfigurationError):
            load_config(path)

    def test_quarantine_ratio_must_be_between_zero_and_one(self):
        self.config["quality"]["max_quarantine_ratio"] = 1.1
        path = self.write_config()

        with self.assertRaises(ConfigurationError):
            load_config(path)

    def test_curated_path_must_not_be_empty(self):
        self.config["paths"]["curated_dir"] = " "
        path = self.write_config()

        with self.assertRaises(ConfigurationError):
            load_config(path)


if __name__ == "__main__":
    unittest.main()
