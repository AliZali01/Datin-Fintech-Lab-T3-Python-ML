
import argparse
import sys

from pathlib import Path

from data_factory.manifest import create_run_manifest
from data_factory.exceptions import DataValidationError


def main():

    root = Path(__file__).resolve().parents[1]

    parser = argparse.ArgumentParser(
        description="Create reproducibility manifest."
    )

    parser.add_argument(
        "--run-dir",
        required=True,
    )

    args = parser.parse_args()

    run_dir = Path(args.run_dir)

    if not run_dir.is_absolute():
        run_dir = root / run_dir

    curated_dir = (
        root / "data" / "curated" / run_dir.name
    )

    report = create_run_manifest(
        project_root=root,
        run_dir=run_dir,
        curated_dir=curated_dir,
    )

    print("\nRUN MANIFEST CREATED")
    print("=" * 45)

    print("Run ID:", report["run_id"])
    print(
        "Raw batches:",
        report["dataset"]["raw_batch_count"],
    )
    print(
        "Processed records:",
        report["dataset"]["processed_records"],
    )
    print(
        "Artifact count:",
        report["artifact_count"],
    )
    print(
        "Record conservation:",
        report["dataset"]["record_conservation"],
    )
    print(
        "Git branch:",
        report["git"]["branch"],
    )
    print(
        "Git commit:",
        report["git"]["commit"],
    )
    print(
        "Working tree dirty:",
        report["git"]["working_tree_dirty"],
    )

    print(
        "\nManifest:",
        curated_dir / "run_manifest.json",
    )


if __name__ == "__main__":

    try:
        main()

    except DataValidationError as exc:
        print(f"ERROR: {exc}")
        sys.exit(exc.exit_code)
