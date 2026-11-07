
"""Run the NYC 311 data collector."""

import argparse

from data_factory.config import load_config
from data_factory.http_client import HttpClient
from data_factory.collector import NYC311Collector


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--max-batches",
        type=int,
        default=2,
        help="Maximum number of batches in this run.",
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Collect all remaining records.",
    )

    args = parser.parse_args()

    config = load_config()
    client = HttpClient.from_config(config)

    collector = NYC311Collector(config, client)

    result = collector.collect(
        max_batches=None if args.all else args.max_batches
    )

    print("\nCollection result")
    print("-----------------")
    print(f"Records written: {result['records_written']}")
    print(f"Batches written: {result['batches_written']}")
    print(f"Next offset: {result['next_offset']}")
    print(f"Completed: {result['completed']}")
    print(f"Data directory: {result['batches_dir']}")
    print(f"Checkpoint: {collector.checkpoint_path}")


if __name__ == "__main__":
    main()
