import json
import tempfile
import unittest

from pathlib import Path

from data_factory.manifest import create_run_manifest
from data_factory.exceptions import DataValidationError


class TestRunManifest(unittest.TestCase):

    def setUp(self):

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name)

        self.run_dir = self.root / "raw" / "test_run"
        self.curated = self.root / "curated" / "test_run"

        batches = self.run_dir / "batches"
        batches.mkdir(parents=True)
        self.curated.mkdir(parents=True)

        (self.root / "config.json").write_text(
            json.dumps({
                "collection": {
                    "complaint_type": "Noise - Residential"
                },
                "quality": {
                    "max_quarantine_ratio": 0.05
                },
            }),
            encoding="utf-8",
        )

        (self.run_dir / "checkpoint.json").write_text(
            '{"completed": true}',
            encoding="utf-8",
        )

        (batches / "batch_000000000.jsonl").write_text(
            '{"unique_key":"1"}\n',
            encoding="utf-8",
        )

        files = {
            "cases.csv": "unique_key\n1\n",
            "cases_enriched.csv": "unique_key\n1\n",
            "monthly_summary_wide.csv": "borough\nBRONX\n",
            "geographic_mismatches.csv": "unique_key\n",
        }

        for name, content in files.items():
            (self.curated / name).write_text(
                content,
                encoding="utf-8",
            )

        reports = {
            "transformation_report.json": {
                "records_transformed": 2
            },
            "population_join_report.json": {
                "input_records": 2,
                "output_records": 2
            },
            "aggregation_report.json": {
                "input_records": 2,
                "aggregated_records": 2
            },
            "geographic_quality_report.json": {
                "total_records": 2,
                "match_rate_percent": 99.0,
                "mismatching_records": 0,
                "missing_coordinate_pairs": 0,
                "unspecified_source_borough": 0
            },
        }

        for name, data in reports.items():
            (self.curated / name).write_text(
                json.dumps(data),
                encoding="utf-8",
            )

    def create_manifest(self):

        return create_run_manifest(
            project_root=self.root,
            run_dir=self.run_dir,
            curated_dir=self.curated,
        )

    def test_manifest_is_created(self):

        manifest = self.create_manifest()

        output = self.curated / "run_manifest.json"

        self.assertTrue(output.exists())
        self.assertEqual(
            manifest["dataset"]["processed_records"],
            2,
        )
        self.assertTrue(
            manifest["dataset"]["record_conservation"]
        )

    def test_artifacts_have_sha256(self):

        manifest = self.create_manifest()

        for artifact in manifest["artifacts"]:
            self.assertEqual(
                len(artifact["sha256"]),
                64,
            )

    def test_record_mismatch_is_rejected(self):

        path = self.curated / "geographic_quality_report.json"

        path.write_text(
            json.dumps({"total_records": 3}),
            encoding="utf-8",
        )

        with self.assertRaises(DataValidationError):
            self.create_manifest()

    def test_missing_output_is_rejected(self):

        (self.curated / "cases.csv").unlink()

        with self.assertRaises(DataValidationError):
            self.create_manifest()


if __name__ == "__main__":
    unittest.main()
