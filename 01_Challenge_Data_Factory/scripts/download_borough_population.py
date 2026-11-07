
import os
from pathlib import Path

from dotenv import load_dotenv

from data_factory.config import load_config
from data_factory.borough_population import BoroughPopulationClient


ROOT = Path(__file__).resolve().parents[1]


def resolve_path(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main():

    load_dotenv(ROOT / ".env", override=True)

    config = load_config(ROOT / "config.json")

    population = config["population"]
    borough_config = population["borough_reference"]

    client = BoroughPopulationClient(
        endpoint=population["endpoint"],
        variable=population["variable"],
        dataset_year=population["dataset_year"],
        state_fips=borough_config["state_fips"],
        county_to_borough=borough_config["county_to_borough"],
        timeout_seconds=population["timeout_seconds"],
    )

    report = client.download(
        api_key=os.getenv("CENSUS_API_KEY"),
        raw_path=resolve_path(borough_config["raw_path"]),
        curated_path=resolve_path(borough_config["curated_path"]),
    )

    print("\nBOROUGH POPULATION DOWNLOAD COMPLETED")
    print("=" * 45)

    for record in report["population_records"]:
        print(
            f"{record['borough']}: "
            f"{record['population_estimate']:,}"
        )

    print("\nCurated file:", report["curated_file"])


if __name__ == "__main__":
    main()
