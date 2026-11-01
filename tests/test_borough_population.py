
import unittest
from unittest.mock import Mock

from data_factory.borough_population import BoroughPopulationClient
from data_factory.exceptions import (
    ConfigurationError,
    DataValidationError,
)


MAPPING = {
    "005": "BRONX",
    "047": "BROOKLYN",
    "061": "MANHATTAN",
    "081": "QUEENS",
    "085": "STATEN ISLAND",
}

SAMPLE = [
    ["NAME", "B01001_001E", "state", "county"],
    ["Bronx County, New York", "1400000", "36", "005"],
    ["Kings County, New York", "2700000", "36", "047"],
    ["New York County, New York", "1600000", "36", "061"],
    ["Queens County, New York", "2300000", "36", "081"],
    ["Richmond County, New York", "500000", "36", "085"],
    ["Albany County, New York", "310000", "36", "001"],
]


class TestBoroughPopulationClient(unittest.TestCase):

    def setUp(self):

        self.session = Mock()
        self.response = Mock()

        self.response.json.return_value = SAMPLE
        self.session.get.return_value = self.response

        self.client = BoroughPopulationClient(
            endpoint="https://example.com/census",
            variable="B01001_001E",
            dataset_year=2024,
            state_fips="36",
            county_to_borough=MAPPING,
            session=self.session,
        )

    def test_fetches_exactly_five_boroughs(self):

        _, records = self.client.fetch("fake-key")

        self.assertEqual(len(records), 5)

        self.assertEqual(
            records[0]["borough"],
            "BRONX",
        )

        self.assertEqual(
            records[0]["population_estimate"],
            1400000,
        )

    def test_missing_api_key(self):

        with self.assertRaises(ConfigurationError):
            self.client.fetch(None)

    def test_missing_county_is_rejected(self):

        self.response.json.return_value = SAMPLE[:-2]

        with self.assertRaises(DataValidationError):
            self.client.fetch("fake-key")

    def test_invalid_population_is_rejected(self):

        invalid = [row[:] for row in SAMPLE]
        invalid[1][1] = "invalid"

        self.response.json.return_value = invalid

        with self.assertRaises(DataValidationError):
            self.client.fetch("fake-key")


if __name__ == "__main__":
    unittest.main()
