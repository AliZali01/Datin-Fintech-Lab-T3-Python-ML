
import csv
import tempfile
import unittest

from pathlib import Path

from data_factory.aggregation import DataAggregator
from data_factory.exceptions import DataValidationError


class TestDataAggregator(unittest.TestCase):

    def setUp(self):

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name)

        self.cases_path = self.root / "cases.csv"
        self.population_path = self.root / "population.csv"
        self.output_path = self.root / "summary.csv"
        self.report_path = self.root / "report.json"

        self.months = ["2024-01", "2024-02"]

        self.aggregator = DataAggregator()

        self.write_population()

        self.rows = [
            self.make_row("1", "BRONX", "2024-01", 1),
            self.make_row("2", "BRONX", "2024-01", 3),
            self.make_row("3", "BROOKLYN", "2024-02", 2),
            self.make_row("4", "UNSPECIFIED", "2024-02", 4),
        ]

        self.write_cases(self.rows)

    @staticmethod
    def make_row(key, borough, month, duration):

        return {
            "unique_key": key,
            "created_date": f"{month}-15T12:00:00",
            "created_year_month": month,
            "borough": borough,
            "complaint_type": "Noise - Residential",
            "resolution_time_hours": str(duration),
        }

    def write_population(self, duplicate=False):

        with self.population_path.open(
            "w",
            encoding="utf-8",
            newline="",
        ) as file:

            fields = [
                "borough",
                "population_estimate",
            ]

            writer = csv.DictWriter(
                file,
                fieldnames=fields,
            )

            writer.writeheader()

            writer.writerows([
                {
                    "borough": "BRONX",
                    "population_estimate": 1000,
                },
                {
                    "borough": "BROOKLYN",
                    "population_estimate": 2000,
                },
            ])

            if duplicate:
                writer.writerow({
                    "borough": "BRONX",
                    "population_estimate": 1000,
                })

    def write_cases(self, rows):

        with self.cases_path.open(
            "w",
            encoding="utf-8",
            newline="",
        ) as file:

            writer = csv.DictWriter(
                file,
                fieldnames=list(rows[0].keys()),
            )

            writer.writeheader()
            writer.writerows(rows)

    def run_aggregation(self, expected_count=4):

        return self.aggregator.aggregate(
            cases_path=self.cases_path,
            population_path=self.population_path,
            output_path=self.output_path,
            report_path=self.report_path,
            months=self.months,
            expected_count=expected_count,
            expected_boroughs=["BRONX", "BROOKLYN"],
            population_year=2024,
        )

    def read_output(self):

        with self.output_path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as file:

            return list(csv.DictReader(file))

    def test_wide_aggregation_preserves_all_records(self):

        report = self.run_aggregation()

        self.assertEqual(report["input_records"], 4)
        self.assertEqual(report["aggregated_records"], 4)
        self.assertEqual(report["wide_output_rows"], 3)

    def test_monthly_complaint_counts(self):

        self.run_aggregation()

        rows = {
            row["borough"]: row
            for row in self.read_output()
        }

        self.assertEqual(
            rows["BRONX"]["2024-01_complaints"],
            "2",
        )

        self.assertEqual(
            rows["BROOKLYN"]["2024-02_complaints"],
            "1",
        )

    def test_population_rate_is_correct(self):

        self.run_aggregation()

        rows = {
            row["borough"]: row
            for row in self.read_output()
        }

        self.assertEqual(
            rows["BRONX"][
                "2024-01_rate_per_1000_residents"
            ],
            "2.000000",
        )

        self.assertEqual(
            rows["BROOKLYN"][
                "2024-02_rate_per_1000_residents"
            ],
            "0.500000",
        )

    def test_mean_and_median_are_correct(self):

        self.run_aggregation()

        rows = {
            row["borough"]: row
            for row in self.read_output()
        }

        self.assertEqual(
            rows["BRONX"][
                "2024-01_mean_resolution_hours"
            ],
            "2.000000",
        )

        self.assertEqual(
            rows["BRONX"][
                "2024-01_median_resolution_hours"
            ],
            "2.000000",
        )

    def test_unspecified_borough_is_preserved(self):

        self.run_aggregation()

        rows = {
            row["borough"]: row
            for row in self.read_output()
        }

        self.assertEqual(
            rows["UNSPECIFIED"]["total_complaints"],
            "1",
        )

        self.assertEqual(
            rows["UNSPECIFIED"][
                "2024-02_rate_per_1000_residents"
            ],
            "",
        )

    def test_input_count_mismatch_is_rejected(self):

        with self.assertRaises(DataValidationError):
            self.run_aggregation(expected_count=100)

    def test_unknown_borough_is_rejected(self):

        self.write_cases([
            self.make_row("1", "UNKNOWN", "2024-01", 1)
        ])

        with self.assertRaises(DataValidationError):
            self.run_aggregation(expected_count=1)

    def test_invalid_duration_is_rejected(self):

        self.write_cases([
            self.make_row("1", "BRONX", "2024-01", -1)
        ])

        with self.assertRaises(DataValidationError):
            self.run_aggregation(expected_count=1)

    def test_outside_month_range_is_rejected(self):

        self.write_cases([
            self.make_row("1", "BRONX", "2024-03", 1)
        ])

        with self.assertRaises(DataValidationError):
            self.run_aggregation(expected_count=1)

    def test_duplicate_population_borough_is_rejected(self):

        self.write_population(duplicate=True)

        with self.assertRaises(DataValidationError):
            self.run_aggregation()


if __name__ == "__main__":
    unittest.main()
