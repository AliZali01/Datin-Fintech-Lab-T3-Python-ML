
"""Paginated NYC 311 data collection with checkpoint recovery."""

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from .exceptions import DataValidationError


class NYC311Collector:

    def __init__(self, config: dict[str, Any], client):
        self.config = config
        self.client = client

        self.endpoint = config["api"]["endpoint"]
        self.batch_size = config["api"]["batch_size"]
        self.collection = config["collection"]

        identity = {
            "endpoint": self.endpoint,
            "collection": self.collection,
            "batch_size": self.batch_size,
        }

        fingerprint = hashlib.sha256(
            json.dumps(identity, sort_keys=True).encode("utf-8")
        ).hexdigest()[:8]

        complaint = (
            self.collection["scope"].get("complaint_type") or "all"
        )
        slug = re.sub(r"[^a-z0-9]+", "_", complaint.lower()).strip("_")

        start = self.collection["start_date"][:10]
        end = self.collection["end_date"][:10]

        raw_dir = Path(config["paths"]["raw_dir"]).resolve()

        self.run_dir = raw_dir / (
            f"nyc311_{slug}_{start}_{end}_{fingerprint}"
        )

        self.batches_dir = self.run_dir / "batches"
        self.checkpoint_path = self.run_dir / "checkpoint.json"

    @staticmethod
    def _escape(value: str) -> str:
        """Escape single quotes in SoQL string values."""
        return value.replace("'", "''")

    def _build_where(self) -> str:
        collection = self.collection

        conditions = [
            f"created_date >= '{self._escape(collection['start_date'])}'",
            f"created_date < '{self._escape(collection['end_date'])}'",
        ]

        scope = collection.get("scope", {})

        for field in ("agency", "complaint_type", "borough"):
            value = scope.get(field)

            if value is not None and value != "":
                conditions.append(
                    f"{field} = '{self._escape(str(value))}'"
                )

        return " AND ".join(conditions)

    def _load_checkpoint(self) -> dict:
        default = {
            "next_offset": 0,
            "records_written": 0,
            "batches_written": 0,
            "completed": False,
        }

        if not self.checkpoint_path.exists():
            return default

        try:
            state = json.loads(
                self.checkpoint_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise DataValidationError(
                f"Invalid checkpoint: {exc}"
            ) from exc

        if not isinstance(state, dict):
            raise DataValidationError("Checkpoint must be a JSON object.")

        for key in ("next_offset", "records_written", "batches_written"):
            value = state.get(key)

            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise DataValidationError(
                    f"Invalid checkpoint field: {key}"
                )

        if not isinstance(state.get("completed"), bool):
            raise DataValidationError("Invalid checkpoint completed flag.")

        return state

    def _save_checkpoint(self, state: dict) -> None:
        temporary = self.checkpoint_path.with_name(
            "checkpoint.json.tmp"
        )

        temporary.write_text(
            json.dumps(state, indent=2),
            encoding="utf-8",
        )

        os.replace(temporary, self.checkpoint_path)

    def _read_batch(self, path: Path) -> list[dict]:
        try:
            with path.open("r", encoding="utf-8") as file:
                rows = [
                    json.loads(line)
                    for line in file
                    if line.strip()
                ]
        except (OSError, json.JSONDecodeError) as exc:
            raise DataValidationError(
                f"Cannot read batch file {path}: {exc}"
            ) from exc

        if not all(isinstance(row, dict) for row in rows):
            raise DataValidationError(
                f"Invalid record structure in {path}"
            )

        return rows

    def _write_batch(self, path: Path, rows: list[dict]) -> None:
        temporary = path.with_name(path.name + ".tmp")

        with temporary.open("w", encoding="utf-8") as file:
            for row in rows:
                file.write(
                    json.dumps(row, ensure_ascii=False) + "\n"
                )

            file.flush()
            os.fsync(file.fileno())

        os.replace(temporary, path)

    def collect(self, max_batches: int | None = None) -> dict:
        """Collect batches and resume from the saved checkpoint."""

        if max_batches is not None:
            if (
                isinstance(max_batches, bool)
                or not isinstance(max_batches, int)
                or max_batches <= 0
            ):
                raise ValueError("max_batches must be a positive integer.")

        self.batches_dir.mkdir(parents=True, exist_ok=True)

        state = self._load_checkpoint()

        if state["completed"]:
            return self._summary(state)

        batches_this_run = 0
        where = self._build_where()

        while max_batches is None or batches_this_run < max_batches:

            offset = state["next_offset"]

            batch_path = self.batches_dir / (
                f"batch_{offset:09d}.jsonl"
            )

            # Recover a batch saved before a possible interruption.
            if batch_path.exists():
                rows = self._read_batch(batch_path)

            else:
                params = {
                    "$where": where,
                    "$limit": self.batch_size,
                    "$offset": offset,
                    "$order": "created_date ASC, unique_key ASC",
                }

                rows = self.client.get(
                    self.endpoint,
                    params=params,
                )

                if not isinstance(rows, list):
                    raise DataValidationError(
                        "API response must be a list."
                    )

                if not rows:
                    state["completed"] = True
                    self._save_checkpoint(state)
                    break

                if len(rows) > self.batch_size:
                    raise DataValidationError(
                        "API returned more records than requested."
                    )

                if not all(isinstance(row, dict) for row in rows):
                    raise DataValidationError(
                        "API returned an invalid record."
                    )

                self._write_batch(batch_path, rows)

            state["next_offset"] = offset + len(rows)
            state["records_written"] += len(rows)
            state["batches_written"] += 1

            if len(rows) < self.batch_size:
                state["completed"] = True

            # Save progress only after the batch is safely written.
            self._save_checkpoint(state)

            batches_this_run += 1

            if state["completed"]:
                break

        return self._summary(state)

    def _summary(self, state: dict) -> dict:
        return {
            **state,
            "run_dir": str(self.run_dir),
            "batches_dir": str(self.batches_dir),
        }
