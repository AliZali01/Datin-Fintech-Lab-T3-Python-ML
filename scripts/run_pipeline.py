
from pathlib import Path
from datetime import datetime
import subprocess
import time
import re
import json


# =====================================================
# CONFIGURATION
# =====================================================

ROOT = Path(__file__).resolve().parents[1]

CONTAINER = "db-performance-postgres"

PYTHON = ROOT / "Capstone-env" / "Scripts" / "python.exe"

DATA_DIR = ROOT / "data" / "processed"
REPORT_DIR = ROOT / "reports"
MODEL_DIR = ROOT / "models"
OUTPUT_DIR = ROOT / "outputs"

MAX_DATABASE_MS = 500
MAX_PIPELINE_MINUTES = 45

# True: rebuild features from Olist source tables
# False: reuse existing order_features and history
REBUILD_FEATURES = True

SQL_FILES = [
    "sql/features/001_order_features.sql",
    "sql/features/002_fix_customer_history.sql",
    "sql/features/003_prepare_modeling_dataset.sql",
]


# =====================================================
# UTILITIES
# =====================================================

def run_command(command, input_text=None, capture=False):

    result = subprocess.run(
        command,
        cwd=ROOT,
        input=input_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=capture
    )

    if capture:
        if result.stdout:
            print(result.stdout)

        if result.stderr:
            print(result.stderr)

    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(map(str, command))}"
        )

    return result


def run_psql(sql, scalar=False):

    psql_command = (
        'psql -X '
        '-U "$POSTGRES_USER" '
        '-d "$POSTGRES_DB" '
        '-v ON_ERROR_STOP=1 '
        '-P pager=off'
    )

    if scalar:
        psql_command += " -At"

    command = [
        "docker",
        "exec",
        "-i",
        CONTAINER,
        "sh",
        "-c",
        psql_command
    ]

    result = run_command(
        command,
        input_text=sql,
        capture=True
    )

    return result.stdout.strip()


def run_sql_file(relative_path):

    path = ROOT / relative_path

    if not path.exists():
        raise FileNotFoundError(path)

    print(f"\n{'=' * 60}")
    print(f"EXECUTING SQL: {relative_path}")
    print("=" * 60)

    sql = path.read_text(encoding="utf-8-sig")

    return run_psql(sql)


def run_python_script(relative_path):

    path = ROOT / relative_path

    if not path.exists():
        raise FileNotFoundError(path)

    print(f"\n{'=' * 60}")
    print(f"EXECUTING PYTHON: {relative_path}")
    print("=" * 60)

    run_command([
        str(PYTHON),
        str(path)
    ])


# =====================================================
# 1. PREFLIGHT
# =====================================================

def preflight():

    print("\n===== PREFLIGHT =====")

    if not PYTHON.exists():
        raise FileNotFoundError(
            f"Python environment not found: {PYTHON}"
        )

    result = run_command([
        "docker",
        "inspect",
        "-f",
        "{{.State.Running}}",
        CONTAINER
    ], capture=True)

    if result.stdout.strip() != "true":
        raise RuntimeError(
            "PostgreSQL container is not running."
        )

    label_exists = run_psql(
        "SELECT to_regclass('capstone.order_labels') IS NOT NULL;",
        scalar=True
    )

    if label_exists.lower() not in ("t", "true"):
        raise RuntimeError(
            "Required table capstone.order_labels does not exist."
        )

    print("Docker: OK")
    print("PostgreSQL: OK")
    print("Order labels: OK")
    print("Python environment: OK")


# =====================================================
# 2. FEATURE ENGINEERING
# =====================================================

def build_features():

    print("\n===== FEATURE ENGINEERING =====")

    if REBUILD_FEATURES:

        for sql_file in SQL_FILES[:2]:
            run_sql_file(sql_file)

    else:
        print("Reusing existing feature table.")

    run_sql_file(SQL_FILES[2])


# =====================================================
# 3. DATASET EXPORT
# =====================================================

def export_dataset():

    print("\n===== DATASET EXPORT =====")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    export_sql = """
    COPY (
        SELECT *
        FROM capstone.modeling_dataset
        ORDER BY approved_at
    )
    TO '/tmp/modeling_dataset.csv'
    WITH (FORMAT CSV, HEADER TRUE);
    """

    run_psql(export_sql)

    destination = DATA_DIR / "modeling_dataset.csv"

    run_command([
        "docker",
        "cp",
        f"{CONTAINER}:/tmp/modeling_dataset.csv",
        str(destination)
    ])

    if not destination.exists():
        raise RuntimeError("Dataset export failed.")

    print(f"Dataset saved: {destination}")
    print(f"Dataset size: {destination.stat().st_size / 1e6:.2f} MB")


# =====================================================
# 4. DEPENDENCY VALIDATION
# =====================================================

def validate_dependencies():

    print("\n===== DEPENDENCY VALIDATION =====")

    run_command([
        str(PYTHON),
        "-m",
        "pip",
        "check"
    ])

    print("Dependencies: PASSED")


# =====================================================
# 5. MODEL TRAINING
# =====================================================

def train_model():

    print("\n===== MODEL TRAINING =====")

    run_python_script(
        "scripts/train_early_warning.py"
    )

    model_path = MODEL_DIR / "early_warning_model.joblib"

    if not model_path.exists():
        raise RuntimeError("Final model was not created.")

    print("Model training: PASSED")


# =====================================================
# 6. MODEL SMOKE TEST
# =====================================================

def smoke_test():

    print("\n===== MODEL SMOKE TEST =====")

    run_python_script(
        "scripts/smoke_test_model.py"
    )

    queue_path = OUTPUT_DIR / "top_10pct_followup.csv"

    if not queue_path.exists():
        raise RuntimeError("Operational queue was not generated.")

    print("Smoke test: PASSED")


# =====================================================
# 7. DATABASE PERFORMANCE
# =====================================================

def benchmark_database():

    print("\n===== DATABASE PERFORMANCE =====")

    sql = """
    EXPLAIN (ANALYZE, BUFFERS)
    SELECT *
    FROM capstone.modeling_dataset;
    """

    result = run_psql(sql)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    report_path = (
        REPORT_DIR / "end_to_end_database_benchmark.txt"
    )

    report_path.write_text(
        result,
        encoding="utf-8"
    )

    match = re.search(
        r"Execution Time:\s*([\d.]+)\s*ms",
        result
    )

    if not match:
        raise RuntimeError(
            "Could not extract database execution time."
        )

    execution_ms = float(match.group(1))

    print(f"Database execution: {execution_ms:.3f} ms")
    print(f"Maximum allowed: {MAX_DATABASE_MS} ms")

    if execution_ms > MAX_DATABASE_MS:
        raise RuntimeError(
            "Database performance requirement failed."
        )

    print("Database performance: PASSED")

    return execution_ms


# =====================================================
# 8. DATASET VALIDATION
# =====================================================

def validate_dataset():

    sql = """
    SELECT
        COUNT(*),
        COUNT(DISTINCT order_id),
        COUNT(*) FILTER (WHERE target NOT IN (0,1))
    FROM capstone.modeling_dataset;
    """

    result = run_psql(sql, scalar=True)

    values = result.split("|")

    if len(values) != 3:
        raise RuntimeError("Invalid dataset validation result.")

    total, unique, invalid = map(int, values)

    if total == 0 or total != unique or invalid != 0:
        raise RuntimeError("Dataset integrity validation failed.")

    print(f"Dataset records: {total:,}")
    print(f"Unique orders: {unique:,}")
    print(f"Invalid targets: {invalid}")

    return total


# =====================================================
# 9. FINAL REPORT
# =====================================================

def create_final_report(
    started_at,
    elapsed_seconds,
    dataset_count,
    database_ms
):

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    report = {
        "status": "PASSED",
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now().isoformat(),
        "elapsed_seconds": round(elapsed_seconds, 2),
        "elapsed_minutes": round(elapsed_seconds / 60, 2),
        "dataset_records": dataset_count,
        "database_execution_ms": database_ms,
        "database_limit_ms": MAX_DATABASE_MS,
        "pipeline_limit_minutes": MAX_PIPELINE_MINUTES,
        "model": "Random Forest",
        "capacity": 0.10,
        "model_path": "models/early_warning_model.joblib",
        "operational_queue": "outputs/top_10pct_followup.csv"
    }

    json_path = REPORT_DIR / "end_to_end_run.json"

    json_path.write_text(
        json.dumps(report, indent=4),
        encoding="utf-8"
    )

    text_report = f"""
END-TO-END PIPELINE REPORT
================================

Status: PASSED

Started: {started_at}
Finished: {datetime.now()}

Elapsed: {elapsed_seconds:.2f} seconds
Elapsed minutes: {elapsed_seconds / 60:.2f}

Dataset records: {dataset_count:,}

Database execution: {database_ms:.3f} ms
Database limit: {MAX_DATABASE_MS} ms

Model: Random Forest
Capacity: 10%

Model artifact:
models/early_warning_model.joblib

Operational queue:
outputs/top_10pct_followup.csv

================================
PIPELINE COMPLETED SUCCESSFULLY
"""

    text_path = REPORT_DIR / "end_to_end_run.txt"

    text_path.write_text(
        text_report,
        encoding="utf-8"
    )

    print(text_report)


# =====================================================
# MAIN PIPELINE
# =====================================================

def main():

    started_at = datetime.now()
    timer = time.perf_counter()

    print("\n" + "=" * 60)
    print("DATIN FINTECH LAB - CAPSTONE PIPELINE")
    print("=" * 60)

    try:

        preflight()

        build_features()

        export_dataset()

        validate_dependencies()

        dataset_count = validate_dataset()

        train_model()

        smoke_test()

        database_ms = benchmark_database()

        elapsed = time.perf_counter() - timer

        if elapsed > MAX_PIPELINE_MINUTES * 60:
            raise RuntimeError(
                "Pipeline exceeded the 45-minute limit."
            )

        create_final_report(
            started_at,
            elapsed,
            dataset_count,
            database_ms
        )

        print("\nFINAL STATUS: PASSED")

    except Exception as error:

        elapsed = time.perf_counter() - timer

        print("\n" + "=" * 60)
        print("PIPELINE FAILED")
        print("=" * 60)

        print(f"Error: {error}")
        print(f"Elapsed: {elapsed / 60:.2f} minutes")

        raise


if __name__ == "__main__":
    main()
