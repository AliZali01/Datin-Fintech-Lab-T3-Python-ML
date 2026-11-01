
import csv
import json
import tempfile
import unittest

from pathlib import Path
from shapely.geometry import box, mapping

from data_factory.geographic_audit import run_geographic_audit


class TestGeographicAudit(unittest.TestCase):

    def setUp(self):

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name)

        self.cases = self.root / "cases.csv"
        self.boundaries = self.root / "boundaries.geojson"
        self.output = self.root / "mismatches.csv"
        self.report = self.root / "report.json"

        polygons = {
            "BRONX": box(-73.95, 40.85, -73.90, 40.90),
            "BROOKLYN": box(-74.00, 40.60, -73.90, 40.70),
            "MANHATTAN": box(-74.00, 40.75, -73.95, 40.82),
            "QUEENS": box(-73.85, 40.70, -73.75, 40.80),
            "STATEN ISLAND": box(-74.20, 40.50, -74.10, 40.60),
        }

        features = []

        for name, polygon in polygons.items():

            features.append({
                "type": "Feature",
                "properties": {
                    "BoroName": name,
                },
                "geometry": mapping(polygon),
            })

        self.boundaries.write_text(
            json.dumps({
                "type": "FeatureCollection",
                "features": features,
            }),
            encoding="utf-8",
        )

        rows = [
            ["1", "2024-01-01", "10468", "BRONX", 40.87, -73.92],
            ["2", "2024-01-02", "10468", "BROOKLYN", 40.87, -73.92],
            ["3", "2024-01-03", "10468", "UNSPECIFIED", 40.87, -73.92],
            ["4", "2024-01-04", "11375", "QUEENS", 40.70, -73.70],
        ]

        with self.cases.open(
            "w",
            encoding="utf-8",
            newline="",
        ) as file:

            writer = csv.writer(file)

            writer.writerow([
                "unique_key",
                "created_date",
                "incident_zip",
                "borough",
                "latitude",
                "longitude",
            ])

            writer.writerows(rows)

    def test_geographic_comparison(self):

        report = run_geographic_audit(
            cases_path=self.cases,
            boundary_path=self.boundaries,
            output_path=self.output,
            report_path=self.report,
            chunk_size=2,
        )

        self.assertEqual(report["total_records"], 4)
        self.assertEqual(report["matching_records"], 1)
        self.assertEqual(report["mismatching_records"], 2)
        self.assertEqual(
            report["unspecified_source_borough"], 1
        )
        self.assertEqual(
            report["unspecified_with_inferable_location"], 1
        )
        self.assertEqual(
            report["outside_boundary_records"], 1
        )

        with self.output.open(
            encoding="utf-8-sig",
            newline="",
        ) as file:
            mismatches = list(csv.DictReader(file))

        self.assertEqual(len(mismatches), 2)


if __name__ == "__main__":
    unittest.main()
