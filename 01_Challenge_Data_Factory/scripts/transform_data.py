
import argparse
import json
from pathlib import Path

from data_factory.config import load_config
from data_factory.transformer import DataTransformer
from data_factory.exceptions import DataValidationError


ROOT = Path(__file__).resolve().parents[1]


def main():

    parser = argparse.ArgumentParser(
        description="Transform accepted NYC 311 records into CSV."
    )

    parser.add_argument(
        "--run-dir",
        required=True,
        help="Completed raw data run directory.",
    )

    args = parser.parse_args()

    config = load_config()

    run_dir = Path(args.run_dir)

    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir

    curated_root = Path(config["paths"]["curated_dir"])

    if not curated_root.is_absolute():
        curated_root = ROOT / curated_root

    output_dir = curated_root / run_dir.name

    accepted_path = output_dir / "accepted.jsonl"
    quality_report_path = output_dir / "quality_report.json"

    if not quality_report_path.is_file():
        raise DataValidationError(
            "Quality report not found. Run processing first."
        )

    quality_report = json.loads(
        quality_report_path.read_text(encoding="utf-8")
    )

    expected_count = quality_report.get("accepted_records")

    if (
        isinstance(expected_count, bool)
        or not isinstance(expected_count, int)
        or expected_count < 0
    ):
        raise DataValidationError(
            "Invalid accepted_records in quality report."
        )

    transformer = DataTransformer()

    report = transformer.transform(
        input_path=accepted_path,
        output_dir=output_dir,
        expected_count=expected_count,
    )

    print("\nDATA TRANSFORMATION COMPLETED")
    print("=" * 45)

    for key, value in report.items():
        print(f"{key}: {value}")

    print(f"\nOutput directory: {output_dir}")


if __name__ == "__main__":
    main()
