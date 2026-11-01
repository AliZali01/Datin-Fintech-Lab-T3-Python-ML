
import argparse
import json

from datetime import date, datetime
from pathlib import Path

from data_factory.config import load_config
from data_factory.aggregation import DataAggregator


ROOT = Path(__file__).resolve().parents[1]


def resolve_path(value):

    path = Path(value)

    return path if path.is_absolute() else ROOT / path


def generate_months(start_date, end_date):

    start = datetime.fromisoformat(start_date).date()
    end = datetime.fromisoformat(end_date).date()

    if end <= start:
        raise ValueError("End date must be after start date.")

    current = date(start.year, start.month, 1)

    months = []

    while current < end:

        months.append(current.strftime("%Y-%m"))

        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(
                current.year,
                current.month + 1,
                1,
            )

    return months


def main():

    parser = argparse.ArgumentParser(
        description="Aggregate NYC 311 enriched data."
    )

    parser.add_argument(
        "--run-dir",
        required=True,
        help="Raw collection run directory.",
    )

    args = parser.parse_args()

    config = load_config(ROOT / "config.json")

    run_dir = resolve_path(args.run_dir)

    output_dir = (
        resolve_path(config["paths"]["curated_dir"])
        / run_dir.name
    )

    cases_path = output_dir / "cases_enriched.csv"

    transformation_report_path = (
        output_dir / "transformation_report.json"
    )

    join_report_path = (
        output_dir / "population_join_report.json"
    )

    if not transformation_report_path.is_file():
        raise FileNotFoundError(
            "Transformation report not found."
        )

    if not join_report_path.is_file():
        raise FileNotFoundError(
            "Population join report not found."
        )

    transformation_report = json.loads(
        transformation_report_path.read_text(
            encoding="utf-8"
        )
    )

    join_report = json.loads(
        join_report_path.read_text(
            encoding="utf-8"
        )
    )

    expected_count = transformation_report[
        "records_transformed"
    ]

    if join_report["output_records"] != expected_count:
        raise ValueError(
            "Population join count does not match "
            "transformation count."
        )

    population_config = config["population"]
    borough_config = population_config["borough_reference"]

    population_path = resolve_path(
        borough_config["curated_path"]
    )

    months = generate_months(
        config["collection"]["start_date"],
        config["collection"]["end_date"],
    )

    aggregator = DataAggregator()

    report = aggregator.aggregate(
        cases_path=cases_path,
        population_path=population_path,
        output_path=output_dir / "monthly_summary_wide.csv",
        report_path=output_dir / "aggregation_report.json",
        months=months,
        expected_count=expected_count,
        expected_boroughs=borough_config[
            "county_to_borough"
        ].values(),
        population_year=population_config["dataset_year"],
    )

    print("\nDATA AGGREGATION COMPLETED")
    print("=" * 45)

    for key, value in report.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
