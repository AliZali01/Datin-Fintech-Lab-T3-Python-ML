
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"

CATEGORY_FIELDS = [
    "status",
    "borough",
    "agency",
    "complaint_type",
    "open_data_channel_type",
]

files = sorted(RAW_DIR.glob("**/batches/*.jsonl"))

categories = {field: Counter() for field in CATEGORY_FIELDS}

zip_stats = Counter()
invalid_zip_examples = Counter()

date_stats = Counter()
duration_stats = {
    "count": 0,
    "sum_hours": 0.0,
    "min_hours": float("inf"),
    "max_hours": float("-inf"),
}

coordinate_stats = Counter()
coordinate_ranges = {
    "latitude_min": float("inf"),
    "latitude_max": float("-inf"),
    "longitude_min": float("inf"),
    "longitude_max": float("-inf"),
}

total = 0


def parse_date(value):
    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )


for path in files:
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            total += 1

            # Categorical distributions
            for field in CATEGORY_FIELDS:
                categories[field][str(row.get(field))] += 1

            # ZIP quality
            raw_zip = row.get("incident_zip")

            if raw_zip is None or str(raw_zip).strip() == "":
                zip_stats["missing"] += 1
            else:
                value = str(raw_zip)
                normalized = value.strip()

                if value != normalized:
                    zip_stats["surrounding_whitespace"] += 1

                if normalized == "00000":
                    zip_stats["placeholder_00000"] += 1
                elif re.fullmatch(r"\d{5}", normalized):
                    zip_stats["valid_format"] += 1
                else:
                    zip_stats["invalid_format"] += 1
                    invalid_zip_examples[normalized] += 1

            # Date and resolution time quality
            try:
                created = parse_date(row["created_date"])
                closed = parse_date(row["closed_date"])

                date_stats["valid_date_pairs"] += 1

                if closed < created:
                    date_stats["closed_before_created"] += 1

                else:
                    hours = (closed - created).total_seconds() / 3600

                    if hours == 0:
                        date_stats["zero_duration"] += 1

                    duration_stats["count"] += 1
                    duration_stats["sum_hours"] += hours

                    duration_stats["min_hours"] = min(
                        duration_stats["min_hours"], hours
                    )

                    duration_stats["max_hours"] = max(
                        duration_stats["max_hours"], hours
                    )

                hours = (closed - created).total_seconds() / 3600

                if hours == 0:
                    date_stats["zero_duration"] += 1

                duration_stats["count"] += 1
                duration_stats["sum_hours"] += hours
                duration_stats["min_hours"] = min(
                    duration_stats["min_hours"], hours
                )
                duration_stats["max_hours"] = max(
                    duration_stats["max_hours"], hours
                )

            except (ValueError, TypeError, KeyError):
                date_stats["invalid_date_pairs"] += 1

            # Coordinate quality
            lat = row.get("latitude")
            lon = row.get("longitude")

            if lat is None and lon is None:
                coordinate_stats["both_missing"] += 1
                continue

            if lat is None or lon is None:
                coordinate_stats["partial_coordinates"] += 1
                continue

            try:
                lat = float(lat)
                lon = float(lon)

                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    coordinate_stats["out_of_range"] += 1
                    continue

                coordinate_stats["valid_pairs"] += 1

                coordinate_ranges["latitude_min"] = min(
                    coordinate_ranges["latitude_min"], lat
                )
                coordinate_ranges["latitude_max"] = max(
                    coordinate_ranges["latitude_max"], lat
                )
                coordinate_ranges["longitude_min"] = min(
                    coordinate_ranges["longitude_min"], lon
                )
                coordinate_ranges["longitude_max"] = max(
                    coordinate_ranges["longitude_max"], lon
                )

            except (ValueError, TypeError):
                coordinate_stats["invalid_numeric"] += 1


print("\nDATA QUALITY PROFILE")
print("=" * 55)
print(f"Total records: {total:,}")

print("\nCATEGORY DISTRIBUTIONS")
print("-" * 55)

for field, counts in categories.items():
    print(f"\n{field}")
    for value, count in counts.most_common(20):
        print(f"  {value}: {count:,}")

print("\nZIP QUALITY")
print("-" * 55)

for key, value in zip_stats.items():
    print(f"{key}: {value:,}")

print("\nInvalid ZIP examples:")
for value, count in invalid_zip_examples.most_common(15):
    print(f"  {value}: {count:,}")

print("\nDATE QUALITY")
print("-" * 55)

for key, value in date_stats.items():
    print(f"{key}: {value:,}")

if duration_stats["count"]:
    print(f"Mean resolution hours: "
          f"{duration_stats['sum_hours'] / duration_stats['count']:.2f}")

    print(f"Minimum resolution hours: "
          f"{duration_stats['min_hours']:.2f}")

    print(f"Maximum resolution hours: "
          f"{duration_stats['max_hours']:.2f}")

print("\nCOORDINATE QUALITY")
print("-" * 55)

for key, value in coordinate_stats.items():
    print(f"{key}: {value:,}")

print("\nCoordinate ranges:")
for key, value in coordinate_ranges.items():
    print(f"{key}: {value}")
