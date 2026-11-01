
import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from data_factory.config import load_config
from data_factory.population import (
    PopulationClient,
    PopulationEnricher,
)
from data_factory.exceptions import DataValidationError


ROOT = Path(__file__).resolve().parents[1]


def resolve_path(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main():

    parser = argparse.ArgumentParser(
        description="Download Census population data and enrich NYC 311."
    )

    parser.add_argument(
        "--run-dir",
        required=True,
        help="Completed raw data run directory.",
    )

    args = parser.parse_args()

    load_dotenv(ROOT / ".env")

    config = load_config(ROOT / "config.json")

    population_config = config["population"]

    run_dir = resolve_path(args.run_dir)
    output_dir = (
        resolve_path(config["paths"]["curated_dir"]) / run_dir.name
    )

    cases_path = output_dir / "cases.csv"
    transformation_report_path = (
        output_dir / "transformation_report.json"
    )

    if not transformation_report_path.is_file():
        raise DataValidationError(
            "Transformation report not found. "
            "Run transform_data.py first."
        )

    transformation_report = json.loads(
        transformation_report_path.read_text(encoding="utf-8")
    )

    expected_count = transformation_report.get(
        "records_transformed"
    )

    client = PopulationClient(
        endpoint=population_config["endpoint"],
        variable=population_config["variable"],
        geography=population_config["geography"],
        dataset_year=population_config["dataset_year"],
        timeout_seconds=population_config["timeout_seconds"],
    )

    raw_path = resolve_path(population_config["raw_path"])
    reference_path = resolve_path(
        population_config["curated_path"]
    )

    print("Downloading Census population reference...")

    download_report = client.download(
        api_key=os.getenv("CENSUS_API_KEY"),
        raw_path=raw_path,
        curated_path=reference_path,
    )

    print(f"Population records: {download_report['source_records']}")

    enricher = PopulationEnricher()

    report = enricher.enrich(
        cases_path=cases_path,
        reference_path=reference_path,
        output_path=output_dir / "cases_enriched.csv",
        report_path=output_dir / "population_join_report.json",
        expected_count=expected_count,
    )

    print("\nPOPULATION ENRICHMENT COMPLETED")
    print("=" * 45)

    print("Source:", download_report)
    print("Join report:")

    for key, value in report.items():
        print(f"{key}: {value}")

    print(f"\nOutput directory: {output_dir}")


if __name__ == "__main__":
    main()
