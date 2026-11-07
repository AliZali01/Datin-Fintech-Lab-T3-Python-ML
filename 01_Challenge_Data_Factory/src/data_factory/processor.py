
import json
import os
from pathlib import Path

from .exceptions import DataValidationError
from .quarantine import QuarantineManager


class DataProcessor:

    def __init__(
        self,
        expected_complaint_type,
        max_quarantine_ratio,
    ):
        if (
            isinstance(max_quarantine_ratio, bool)
            or not isinstance(max_quarantine_ratio, (int, float))
            or not 0 <= max_quarantine_ratio <= 1
        ):
            raise ValueError("Invalid quarantine threshold.")

        self.expected_complaint_type = expected_complaint_type
        self.max_quarantine_ratio = max_quarantine_ratio

    @staticmethod
    def _write_jsonl(file, record):
        file.write(
            json.dumps(
                record,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ) + "\n"
        )

    def process(
        self,
        batches_dir,
        output_dir,
        expected_raw_count=None,
    ):

        batches_dir = Path(batches_dir)
        output_dir = Path(output_dir)

        batch_files = sorted(
            batches_dir.glob("batch_*.jsonl")
        )

        if not batch_files:
            raise DataValidationError("No raw batch files found.")

        output_dir.mkdir(parents=True, exist_ok=True)

        accepted_path = output_dir / "accepted.jsonl"
        quarantine_path = output_dir / "quarantine.jsonl"
        report_path = output_dir / "quality_report.json"

        accepted_tmp = output_dir / ".accepted.jsonl.tmp"
        quarantine_tmp = output_dir / ".quarantine.jsonl.tmp"
        report_tmp = output_dir / ".quality_report.json.tmp"

        manager = QuarantineManager(
            expected_complaint_type=self.expected_complaint_type
        )

        total_records = 0

        try:
            with (
                accepted_tmp.open("w", encoding="utf-8") as accepted_file,
                quarantine_tmp.open("w", encoding="utf-8") as quarantine_file,
            ):

                for batch_path in batch_files:

                    with batch_path.open(
                        "r",
                        encoding="utf-8",
                    ) as source:

                        for line in source:

                            total_records += 1

                            try:
                                record = json.loads(line)

                            except json.JSONDecodeError:
                                result = manager.quarantine(
                                    {"raw_line": line.rstrip("\r\n")},
                                    ["MALFORMED_JSON"],
                                )

                                self._write_jsonl(
                                    quarantine_file,
                                    result,
                                )
                                continue

                            accepted, rejected = manager.process_record(
                                record
                            )

                            if accepted is not None:
                                self._write_jsonl(
                                    accepted_file,
                                    accepted,
                                )

                            else:
                                self._write_jsonl(
                                    quarantine_file,
                                    rejected,
                                )

                accepted_file.flush()
                os.fsync(accepted_file.fileno())

                quarantine_file.flush()
                os.fsync(quarantine_file.fileno())

            if (
                expected_raw_count is not None
                and total_records != expected_raw_count
            ):
                raise DataValidationError(
                    f"Raw count mismatch: expected "
                    f"{expected_raw_count}, got {total_records}"
                )

            ratio = (
                manager.quarantined_count / total_records
                if total_records else 0
            )

            report = {
                "total_raw_records": total_records,
                "accepted_records": manager.accepted_count,
                "quarantined_records": manager.quarantined_count,
                "quarantine_ratio": ratio,
                "max_quarantine_ratio": self.max_quarantine_ratio,
                "duplicate_records": manager.duplicate_count,
                "accepted_records_with_missing_zip":
                    manager.missing_zip_count,
                "batch_files_processed": len(batch_files),
                "quarantine_by_reason": dict(
                    sorted(manager.reason_counts.items())
                ),
            }

            report_tmp.write_text(
                json.dumps(
                    report,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ) + "\n",
                encoding="utf-8",
            )

            # Preserve diagnostic outputs even if the threshold is exceeded.
            os.replace(quarantine_tmp, quarantine_path)
            os.replace(report_tmp, report_path)

            if ratio > self.max_quarantine_ratio:
                accepted_tmp.unlink(missing_ok=True)
                accepted_path.unlink(missing_ok=True)

                raise DataValidationError(
                    f"Quarantine ratio {ratio:.4%} exceeds "
                    f"the configured threshold "
                    f"{self.max_quarantine_ratio:.2%}."
                )

            os.replace(accepted_tmp, accepted_path)

            return report

        finally:
            for temporary in (
                accepted_tmp,
                quarantine_tmp,
                report_tmp,
            ):
                temporary.unlink(missing_ok=True)
