
import argparse
import sys
from pathlib import Path

from data_factory.geographic_audit import (
    download_boundary_file,
    run_geographic_audit,
)

from data_factory.exceptions import DataValidationError


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--run-dir",
        required=True,
    )

    args = parser.parse_args()

    root = Path.cwd()

    raw_dir = Path(args.run_dir)

    if not raw_dir.is_absolute():
        raw_dir = root / raw_dir

    if not raw_dir.is_dir():
        raise DataValidationError(
            f"Raw run directory not found: {raw_dir}"
        )

    curated_dir = (
        root / "data" / "curated" / raw_dir.name
    )

    cases_path = curated_dir / "cases_enriched.csv"

    if not cases_path.exists():
        raise DataValidationError(
            f"Input file not found: {cases_path}"
        )

    boundary_path = (
        root
        / "data"
        / "raw"
        / "reference"
        / "nyc_borough_boundaries.geojson"
    )

    download_boundary_file(boundary_path)

    report_path = (
        curated_dir / "geographic_quality_report.json"
    )

    mismatch_path = (
        curated_dir / "geographic_mismatches.csv"
    )

    report = run_geographic_audit(
        cases_path=cases_path,
        boundary_path=boundary_path,
        output_path=mismatch_path,
        report_path=report_path,
    )

    print("\nGEOGRAPHIC AUDIT COMPLETED")
    print("=" * 45)

    for key, value in report.items():
        print(f"{key}: {value}")

    print("\nOutput files:")
    print(report_path)
    print(mismatch_path)


if __name__ == "__main__":

    try:
        main()

    except DataValidationError as exc:
        print(f"ERROR: {exc}")
        sys.exit(exc.exit_code)
