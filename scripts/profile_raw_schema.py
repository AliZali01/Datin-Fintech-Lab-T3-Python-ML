
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"

TARGET_FIELDS = [
    "unique_key",
    "created_date",
    "closed_date",
    "agency",
    "complaint_type",
    "descriptor",
    "incident_zip",
    "borough",
    "status",
    "city",
    "community_board",
    "latitude",
    "longitude",
]

files = sorted(RAW_DIR.glob("**/batches/*.jsonl"))

present = Counter()
nulls = Counter()
blanks = Counter()
examples = defaultdict(list)

total = 0

for path in files:
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            total += 1

            for field in row:
                present[field] += 1

                value = row[field]

                if value is None:
                    nulls[field] += 1
                elif isinstance(value, str) and not value.strip():
                    blanks[field] += 1
                elif field in TARGET_FIELDS and len(examples[field]) < 3:
                    examples[field].append(value)

print(f"Total records: {total:,}")
print(f"Batch files: {len(files)}")
print(f"Total source columns: {len(present)}")

print("\nALL SOURCE COLUMNS")
print("-" * 65)

for field, count in present.most_common():
    print(f"{field:45} {count:>10,}")

print("\nIMPORTANT FIELD PROFILE")
print("-" * 65)

for field in TARGET_FIELDS:
    count = present[field]

    print(f"\n{field}")
    print(f"Present: {count:,}")
    print(f"Missing/null: {total - count + nulls[field]:,}")
    print(f"Blank strings: {blanks[field]:,}")
    print(f"Examples: {examples[field]}")
