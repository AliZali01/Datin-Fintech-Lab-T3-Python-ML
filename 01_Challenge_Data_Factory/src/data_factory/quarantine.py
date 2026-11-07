
from collections import Counter

from .schema import validate_record, normalize_zip


class QuarantineManager:

    def __init__(self, expected_complaint_type=None):
        self.expected_complaint_type = expected_complaint_type

        self.seen_keys = set()
        self.reason_counts = Counter()

        self.accepted_count = 0
        self.quarantined_count = 0
        self.duplicate_count = 0
        self.missing_zip_count = 0

    def quarantine(self, record, reasons):
        reasons = sorted(set(reasons))

        self.quarantined_count += 1
        self.reason_counts.update(reasons)

        if "DUPLICATE_UNIQUE_KEY" in reasons:
            self.duplicate_count += 1

        return {
            "record": record,
            "reasons": reasons,
        }

    def process_record(self, record):

        errors = validate_record(
            record,
            expected_complaint_type=self.expected_complaint_type,
        )

        if errors:
            return None, self.quarantine(record, errors)

        # Deduplication based on unique_key
        key = record["unique_key"].strip()

        if key in self.seen_keys:
            return None, self.quarantine(
                record,
                ["DUPLICATE_UNIQUE_KEY"],
            )

        self.seen_keys.add(key)

        # Normalize accepted record
        accepted = dict(record)

        accepted["unique_key"] = key
        accepted["incident_zip"] = normalize_zip(
            record.get("incident_zip")
        )

        if accepted["incident_zip"] is None:
            self.missing_zip_count += 1

        self.accepted_count += 1

        return accepted, None
