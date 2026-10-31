
import json
import re
import sys
from pathlib import Path
from datetime import datetime


ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

BATCH_SIZE = CONFIG["api"]["batch_size"]
COLLECTION = CONFIG["collection"]

START = datetime.fromisoformat(COLLECTION["start_date"])
END = datetime.fromisoformat(COLLECTION["end_date"])
EXPECTED_TYPE = COLLECTION["scope"]["complaint_type"]


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            'Usage: python scripts/audit_raw_data.py "data/raw/run_folder"'
        )

    run_dir = Path(sys.argv[1])
    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir

    batches_dir = run_dir / "batches"
    checkpoint_path = run_dir / "checkpoint.json"

    checkpoint = json.loads(
        checkpoint_path.read_text(encoding="utf-8")
    )

    files = sorted(batches_dir.glob("batch_*.jsonl"))

    seen_keys = set()

    total = 0
    malformed = 0
    missing_ids = 0
    duplicates = 0
    wrong_type = 0
    invalid_dates = 0
    outside_window = 0
    invalid_records = 0
    short_batches = []

    offsets = []

    for file in files:
        match = re.fullmatch(r"batch_(\d+)\.jsonl", file.name)

        if not match:
            continue

        offset = int(match.group(1))
        offsets.append(offset)

        batch_count = 0

        with file.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    malformed += 1
                    continue

                if not isinstance(row, dict):
                    invalid_records += 1
                    continue

                total += 1
                batch_count += 1

                key = row.get("unique_key")

                if key is None or str(key).strip() == "":
                    missing_ids += 1
                elif str(key) in seen_keys:
                    duplicates += 1
                else:
                    seen_keys.add(str(key))

                if row.get("complaint_type") != EXPECTED_TYPE:
                    wrong_type += 1

                try:
                    created = datetime.fromisoformat(
                        row["created_date"].replace("Z", "+00:00")
                    ).replace(tzinfo=None)

                    if not START <= created < END:
                        outside_window += 1

                except (ValueError, TypeError, KeyError):
                    invalid_dates += 1

        if batch_count < BATCH_SIZE:
            short_batches.append((file.name, batch_count))

    expected_offsets = list(
        range(0, checkpoint["next_offset"], BATCH_SIZE)
    )

    checks = {
        "Checkpoint completed": checkpoint["completed"] is True,
        "Record count matches checkpoint":
            total == checkpoint["records_written"],
        "Batch count matches checkpoint":
            len(files) == checkpoint["batches_written"],
        "At least 300,000 records": total >= 300000,
        "Batch offsets are continuous":
            sorted(offsets) == expected_offsets,
        "No malformed JSON": malformed == 0,
        "No invalid records": invalid_records == 0,
        "No missing IDs": missing_ids == 0,
        "No duplicate IDs": duplicates == 0,
        "Correct complaint type": wrong_type == 0,
        "Valid dates": invalid_dates == 0,
        "Dates inside requested window": outside_window == 0,
        "Only final batch may be short": len(short_batches) <= 1,
    }

    print("\nRAW DATA AUDIT")
    print("=" * 45)

    print(f"Records: {total:,}")
    print(f"Batch files: {len(files)}")
    print(f"Checkpoint records: {checkpoint['records_written']:,}")
    print(f"Checkpoint completed: {checkpoint['completed']}")
    print(f"Malformed JSON: {malformed}")
    print(f"Invalid records: {invalid_records}")
    print(f"Missing IDs: {missing_ids}")
    print(f"Duplicate IDs: {duplicates}")
    print(f"Wrong complaint type: {wrong_type}")
    print(f"Invalid dates: {invalid_dates}")
    print(f"Outside date window: {outside_window}")

    if short_batches:
        print(f"Short batches: {short_batches}")

    print("\nCHECKS")
    print("=" * 45)

    for name, passed in checks.items():
        print(f"[{'PASS' if passed else 'FAIL'}] {name}")

    print("=" * 45)

    if all(checks.values()):
        print("RAW DATA AUDIT PASSED")
    else:
        print("RAW DATA AUDIT FAILED")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
