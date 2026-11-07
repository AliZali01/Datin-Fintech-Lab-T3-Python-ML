
"""Run the complete NYC 311 data pipeline."""

import argparse
import json
import subprocess
import sys
import time

from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def save_report(path, report):

    path.parent.mkdir(parents=True, exist_ok=True)

    temporary = path.with_suffix(".tmp")

    with temporary.open("w", encoding="utf-8") as file:
        json.dump(
            report,
            file,
            indent=2,
            ensure_ascii=False,
        )
        file.write("\n")
        file.flush()

    temporary.replace(path)


def verify_collection(run_dir):

    checkpoint_path = run_dir / "checkpoint.json"

    if not checkpoint_path.is_file():
        raise RuntimeError("Collection checkpoint not found.")

    checkpoint = json.loads(
        checkpoint_path.read_text(encoding="utf-8")
    )

    if checkpoint.get("completed") is not True:
        raise RuntimeError(
            "Collection is incomplete. Checkpoint not completed."
        )


def main():

    parser = argparse.ArgumentParser(
        description="Run the complete NYC 311 data pipeline."
    )

    parser.add_argument(
        "--run-dir",
        required=True,
        help="Raw data collection directory.",
    )

    parser.add_argument(
        "--skip-collection",
        action="store_true",
        help="Skip API collection and use existing completed data.",
    )

    args = parser.parse_args()

    run_dir = Path(args.run_dir)

    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir

    run_dir = run_dir.resolve()

    report_path = (
        ROOT
        / "reports"
        / "pipeline"
        / f"{run_dir.name}_pipeline_report.json"
    )

    report = {
        "run_id": run_dir.name,
        "started_at_utc": utc_now(),
        "finished_at_utc": None,
        "status": "running",
        "stages": [],
        "total_duration_seconds": None,
    }

    def execute_stage(name, command):

        print("\n" + "=" * 65)
        print(f"STAGE: {name}")
        print("=" * 65)

        started = time.perf_counter()

        result = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
        )

        duration = round(
            time.perf_counter() - started,
            2,
        )

        stage = {
            "name": name,
            "command": command,
            "status": (
                "success" if result.returncode == 0 else "failed"
            ),
            "return_code": result.returncode,
            "duration_seconds": duration,
        }

        report["stages"].append(stage)
        save_report(report_path, report)

        print(f"\n{name}: {stage['status'].upper()}")
        print(f"Duration: {duration} seconds")

        if result.returncode != 0:
            raise RuntimeError(
                f"Pipeline stopped at stage: {name}"
            )

    scripts = ROOT / "scripts"

    try:

        # 1. Data collection
        if not args.skip_collection:

            execute_stage(
                "data_collection",
                [
                    PYTHON,
                    str(scripts / "collect_data.py"),
                    "--all",
                ],
            )

        else:
            print("\nSkipping data collection.")

        verify_collection(run_dir)

        # 2. Raw data audit
        execute_stage(
            "raw_data_audit",
            [
                PYTHON,
                str(scripts / "audit_raw_data.py"),
                str(run_dir),
            ],
        )

        # 3. Data processing
        execute_stage(
            "data_processing",
            [
                PYTHON,
                str(scripts / "process_data.py"),
                "--run-dir",
                str(run_dir),
            ],
        )

        # 4. Data transformation
        execute_stage(
            "data_transformation",
            [
                PYTHON,
                str(scripts / "transform_data.py"),
                "--run-dir",
                str(run_dir),
            ],
        )

        # 5. ZIP population enrichment
        execute_stage(
            "population_enrichment",
            [
                PYTHON,
                str(scripts / "enrich_population.py"),
                "--run-dir",
                str(run_dir),
            ],
        )

        # 6. Borough population reference
        execute_stage(
            "borough_population_download",
            [
                PYTHON,
                str(scripts / "download_borough_population.py"),
            ],
        )

        # 7. Data aggregation
        execute_stage(
            "data_aggregation",
            [
                PYTHON,
                str(scripts / "aggregate_data.py"),
                "--run-dir",
                str(run_dir),
            ],
        )

        # 8. Geographic audit
        execute_stage(
            "geographic_audit",
            [
                PYTHON,
                str(scripts / "audit_geography.py"),
                "--run-dir",
                str(run_dir),
            ],
        )

        # 9. Reproducibility manifest
        execute_stage(
            "run_manifest",
            [
                PYTHON,
                str(scripts / "create_run_manifest.py"),
                "--run-dir",
                str(run_dir),
            ],
        )

        report["status"] = "success"

    except KeyboardInterrupt:

        report["status"] = "interrupted"
        print("\nPipeline interrupted by user.")

    except Exception as exc:

        report["status"] = "failed"
        report["error"] = str(exc)

        print(f"\nPIPELINE ERROR: {exc}")

    finally:

        report["finished_at_utc"] = utc_now()

        report["total_duration_seconds"] = round(
            sum(
                stage["duration_seconds"]
                for stage in report["stages"]
            ),
            2,
        )

        save_report(report_path, report)

        print("\n" + "=" * 65)
        print("PIPELINE SUMMARY")
        print("=" * 65)

        print("Status:", report["status"])
        print("Completed stages:", sum(
            s["status"] == "success"
            for s in report["stages"]
        ))
        print("Total stages:", len(report["stages"]))
        print(
            "Duration:",
            report["total_duration_seconds"],
            "seconds",
        )
        print("Report:", report_path)

    if report["status"] != "success":
        sys.exit(1)


if __name__ == "__main__":
    main()
