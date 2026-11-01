
import csv
import hashlib
import json
import os
import platform
import subprocess
import sys

from datetime import datetime, timezone
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path

from .exceptions import DataValidationError


REQUIRED_CURATED_FILES = [
    "cases.csv",
    "cases_enriched.csv",
    "monthly_summary_wide.csv",
    "transformation_report.json",
    "population_join_report.json",
    "aggregation_report.json",
    "geographic_quality_report.json",
    "geographic_mismatches.csv",
]


def sha256_file(path):

    digest = hashlib.sha256()

    with Path(path).open("rb") as file:
        for chunk in iter(
            lambda: file.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def read_json(path):

    try:
        return json.loads(
            Path(path).read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        raise DataValidationError(
            f"Cannot read JSON report: {path}"
        ) from exc


def get_git_info(root):

    def run_git(command):

        try:
            result = subprocess.run(
                ["git", "-C", str(root), *command],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

            if result.returncode == 0:
                return result.stdout.strip()

        except (OSError, subprocess.TimeoutExpired):
            pass

        return None

    status = run_git(["status", "--porcelain"])

    return {
        "branch": run_git(["branch", "--show-current"]),
        "commit": run_git(["rev-parse", "HEAD"]),
        "working_tree_dirty": (
            bool(status) if status is not None else None
        ),
    }


def get_package_versions():

    packages = [
        "requests",
        "shapely",
        "numpy",
        "pandas",
        "python-dotenv",
    ]

    result = {}

    for package in packages:

        try:
            result[package] = version(package)
        except PackageNotFoundError:
            result[package] = None

    return result


def describe_file(path, root):

    path = Path(path)

    return {
        "path": path.relative_to(root).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def create_run_manifest(
    project_root,
    run_dir,
    curated_dir,
):

    root = Path(project_root).resolve()
    run_dir = Path(run_dir).resolve()
    curated_dir = Path(curated_dir).resolve()

    config_path = root / "config.json"
    checkpoint_path = run_dir / "checkpoint.json"
    batches_dir = run_dir / "batches"

    if not config_path.is_file():
        raise DataValidationError("config.json not found.")

    if not checkpoint_path.is_file():
        raise DataValidationError("checkpoint.json not found.")

    if not batches_dir.is_dir():
        raise DataValidationError("Raw batches directory not found.")

    if not curated_dir.is_dir():
        raise DataValidationError("Curated directory not found.")

    required_paths = [
        curated_dir / name
        for name in REQUIRED_CURATED_FILES
    ]

    for path in required_paths:
        if not path.is_file():
            raise DataValidationError(
                f"Required output is missing: {path.name}"
            )

    batches = sorted(
        batches_dir.glob("batch_*.jsonl")
    )

    if not batches:
        raise DataValidationError("No raw batch files found.")

    # Load stage reports
    transformation = read_json(
        curated_dir / "transformation_report.json"
    )

    population = read_json(
        curated_dir / "population_join_report.json"
    )

    aggregation = read_json(
        curated_dir / "aggregation_report.json"
    )

    geography = read_json(
        curated_dir / "geographic_quality_report.json"
    )

    # Validate record conservation across stages
    stage_counts = {
        "transformation": transformation.get(
            "records_transformed"
        ),
        "population_join": population.get(
            "output_records"
        ),
        "aggregation_input": aggregation.get(
            "input_records"
        ),
        "aggregation_output": aggregation.get(
            "aggregated_records"
        ),
        "geographic_audit": geography.get(
            "total_records"
        ),
    }

    if any(value is None for value in stage_counts.values()):
        raise DataValidationError(
            "One or more stage reports lack record counts."
        )

    if len(set(stage_counts.values())) != 1:
        raise DataValidationError(
            f"Record conservation failed: {stage_counts}"
        )

    # Collect files to fingerprint
    artifact_paths = [
        config_path,
        checkpoint_path,
        *batches,
    ]

    for filename in ["pyproject.toml", "requirements.txt"]:
        path = root / filename
        if path.is_file():
            artifact_paths.append(path)

    artifact_paths.extend(required_paths)

    # Include reference datasets
    for folder in [
        root / "data" / "raw" / "reference",
        root / "data" / "curated" / "reference",
    ]:
        if folder.is_dir():
            artifact_paths.extend(
                path for path in folder.rglob("*")
                if path.is_file()
            )

    # Include other curated outputs
    artifact_paths.extend(
        path for path in curated_dir.rglob("*")
        if (
            path.is_file()
            and path.name != "run_manifest.json"
            and not path.name.endswith(".tmp")
        )
    )

    # Remove duplicates and sort
    artifact_paths = sorted(
        set(path.resolve() for path in artifact_paths),
        key=str,
    )

    for path in artifact_paths:
        if not path.is_relative_to(root):
            raise DataValidationError(
                f"Artifact outside project root: {path}"
            )

    print(
        f"Calculating SHA-256 for {len(artifact_paths)} files..."
    )

    artifacts = []

    for index, path in enumerate(artifact_paths, start=1):

        artifacts.append(
            describe_file(path, root)
        )

        if index % 25 == 0:
            print(f"Hashed {index}/{len(artifact_paths)} files")

    config = read_json(config_path)

    manifest = {
        "manifest_version": "1.0",
        "created_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),

        "run_id": run_dir.name,

        "configuration": {
            "config_file": "config.json",
            "collection": config.get("collection", {}),
            "quality": config.get("quality", {}),
        },

        "dataset": {
            "raw_batch_count": len(batches),
            "processed_records": stage_counts[
                "transformation"
            ],
            "record_conservation": True,
        },

        "stage_counts": stage_counts,

        "geographic_quality": {
            "match_rate_percent": geography.get(
                "match_rate_percent"
            ),
            "mismatching_records": geography.get(
                "mismatching_records"
            ),
            "missing_coordinate_pairs": geography.get(
                "missing_coordinate_pairs"
            ),
            "unspecified_borough_records": geography.get(
                "unspecified_source_borough"
            ),
        },

        "environment": {
            "python_version": sys.version,
            "platform": platform.platform(),
            "packages": get_package_versions(),
        },

        "git": get_git_info(root),

        "artifact_count": len(artifacts),
        "artifacts": artifacts,
    }

    output_path = curated_dir / "run_manifest.json"
    temp_path = output_path.with_name(
        ".run_manifest.json.tmp"
    )

    try:
        with temp_path.open(
            "w",
            encoding="utf-8",
            newline="\n",
        ) as file:

            json.dump(
                manifest,
                file,
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )

            file.write("\n")
            file.flush()
            os.fsync(file.fileno())

        os.replace(temp_path, output_path)

    finally:
        temp_path.unlink(missing_ok=True)

    return manifest
