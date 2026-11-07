
import unittest

from data_factory.schema import (
    normalize_zip,
    validate_zip,
    get_zip_error,
    validate_record,
)


VALID_RECORD = {
    "unique_key": "59889016",
    "created_date": "2024-01-01T00:00:20.000",
    "closed_date": "2024-01-01T01:00:00.000",
    "complaint_type": "Noise - Residential",
    "agency": "NYPD",
    "status": "Closed",
    "borough": "BRONX",
    "incident_zip": "10468",
    "latitude": "40.8624",
    "longitude": "-73.9110",
    "open_data_channel_type": "ONLINE",
}


class TestZipValidation(unittest.TestCase):

    def test_normalize_whitespace(self):
        self.assertEqual(normalize_zip(" 10468 "), "10468")

    def test_missing_zip(self):
        self.assertIsNone(normalize_zip(None))

    def test_na_zip(self):
        self.assertIsNone(normalize_zip("N/A"))

    def test_placeholder_zip(self):
        self.assertIsNone(normalize_zip("00000"))

    def test_valid_zip(self):
        self.assertTrue(validate_zip("10468"))

    def test_invalid_zip(self):
        self.assertFalse(validate_zip("12ABC"))

    def test_invalid_zip_error(self):
        self.assertEqual(
            get_zip_error("1234"),
            "INVALID_ZIP_FORMAT",
        )

    def test_missing_zip_is_accepted(self):
        self.assertTrue(validate_zip(None))


class TestRecordValidation(unittest.TestCase):

    def test_valid_record(self):
        self.assertEqual(validate_record(VALID_RECORD), [])

    def test_missing_unique_key(self):
        record = VALID_RECORD.copy()
        record["unique_key"] = None

        self.assertIn(
            "MISSING_UNIQUE_KEY",
            validate_record(record),
        )

    def test_invalid_created_date(self):
        record = VALID_RECORD.copy()
        record["created_date"] = "invalid"

        self.assertIn(
            "INVALID_CREATED_DATE",
            validate_record(record),
        )

    def test_closed_before_created(self):
        record = VALID_RECORD.copy()
        record["closed_date"] = "2023-12-31T23:00:00"

        self.assertIn(
            "CLOSED_BEFORE_CREATED",
            validate_record(record),
        )

    def test_missing_closed_date_is_allowed(self):
        record = VALID_RECORD.copy()
        record["closed_date"] = None

        self.assertEqual(validate_record(record), [])

    def test_partial_coordinates(self):
        record = VALID_RECORD.copy()
        record["latitude"] = None

        self.assertIn(
            "PARTIAL_COORDINATES",
            validate_record(record),
        )

    def test_invalid_coordinates(self):
        record = VALID_RECORD.copy()
        record["latitude"] = "ABC"

        self.assertIn(
            "INVALID_COORDINATES",
            validate_record(record),
        )

    def test_wrong_complaint_type(self):
        self.assertIn(
            "UNEXPECTED_COMPLAINT_TYPE",
            validate_record(
                VALID_RECORD,
                expected_complaint_type="Illegal Parking",
            ),
        )

    def test_non_object_record(self):
        self.assertIn(
            "RECORD_NOT_OBJECT",
            validate_record(None),
        )


if __name__ == "__main__":
    unittest.main()
