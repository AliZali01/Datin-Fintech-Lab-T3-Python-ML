
import argparse
import json
from pathlib import Path

from data_factory.config import load_config
from data_factory.processor import DataProcessor
from data_factory.exceptions import DataValidationError


ROOT = Path(__file__).resolve().parents[1]


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--run-dir",
        required=True,
        help="Path to completed raw data run directory.",
    )

    args = parser.parse_args()

    config = load_config()

    run_dir = Path(args.run_dir)

    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir

    checkpoint_path = run_dir / "checkpoint.json"

    if not checkpoint_path.exists():
        raise DataValidationError("Checkpoint not found.")

    checkpoint = json.loads(
        checkpoint_path.read_text(encoding="utf-8")
    )

    if checkpoint.get("completed") is not True:
        raise DataValidationError(
            "Raw data collection is not completed."
        )

    batches_dir = run_dir / "batches"

    curated_root = Path(config["paths"]["curated_dir"])

    if not curated_root.is_absolute():
        curated_root = ROOT / curated_root

    output_dir = curated_root / run_dir.name

    processor = DataProcessor(
        expected_complaint_type=config["collection"]["scope"][
            "complaint_type"
        ],
        max_quarantine_ratio=config["quality"][
            "max_quarantine_ratio"
        ],
    )

    report = processor.process(
        batches_dir=batches_dir,
        output_dir=output_dir,
        expected_raw_count=checkpoint["records_written"],
    )

    print("\nDATA PROCESSING COMPLETED")
    print("=" * 45)

    for key, value in report.items():
        print(f"{key}: {value}")

    print(f"\nOutput directory: {output_dir}")


if __name__ == "__main__":
    main()
