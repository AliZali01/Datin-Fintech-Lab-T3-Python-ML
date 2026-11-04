import csv
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import (
    CHAR,
    DateTime,
    Float,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    URL,
    text,
)

from data_factory.database_destination import DatabaseDestination


ROOT = Path(__file__).resolve().parents[1]
DATA_FACTORY_ROOT = ROOT.parent / "01_Challenge_Data_Factory"

load_dotenv(ROOT / ".env")

DEFAULT_CSV_PATH = (
    DATA_FACTORY_ROOT
    / "data"
    / "curated"
    / "nyc311_noise_residential_2024-01-01_2025-07-01_4287f9b2"
    / "cases_enriched.csv"
)

CSV_PATH = Path(
    os.getenv("NYC311_CSV_PATH", str(DEFAULT_CSV_PATH))
)

SCHEMA = "nyc311"
TARGET_TABLE = "cases"
STAGING_TABLE = "cases_staging"

READ_CHUNKSIZE = 20000
WRITE_CHUNKSIZE = 2000


# CSV columns -> PostgreSQL types
SQL_TYPES = {
    "unique_key": String(20),
    "created_date": DateTime(),
    "closed_date": DateTime(),
    "agency": Text(),
    "agency_name": Text(),
    "complaint_type": Text(),
    "descriptor": Text(),
    "status": Text(),
    "resolution_action_updated_date": DateTime(),
    "community_board": Text(),
    "police_precinct": Text(),
    "borough": Text(),
    "open_data_channel_type": Text(),
    "park_facility_name": Text(),
    "park_borough": Text(),
    "location_type": Text(),
    "incident_address": Text(),
    "street_name": Text(),
    "address_type": Text(),
    "resolution_description": Text(),
    "incident_zip": String(10),
    "cross_street_2": Text(),
    "intersection_street_2": Text(),
    "cross_street_1": Text(),
    "intersection_street_1": Text(),
    "y_coordinate_state_plane": Float(precision=53),
    "x_coordinate_state_plane": Float(precision=53),
    "latitude": Float(precision=53),
    "longitude": Float(precision=53),
    "location": Text(),
    "council_district": SmallInteger(),
    "city": Text(),
    "landmark": Text(),
    "bbl": String(20),
    "resolution_time_hours": Numeric(14, 6),
    "created_year": SmallInteger(),
    "created_month": SmallInteger(),
    "created_year_month": CHAR(7),
    "population_estimate": Integer(),
    "population_match_status": Text(),
}


CSV_DTYPES = {
    "unique_key": "string",
    "incident_zip": "string",
    "bbl": "string",
    "created_year_month": "string",
    "council_district": "Int16",
    "created_year": "Int16",
    "created_month": "Int16",
    "population_estimate": "Int32",
}

DATE_COLUMNS = [
    "created_date",
    "closed_date",
    "resolution_action_updated_date",
]

COLUMNS = list(SQL_TYPES)


def validate_csv_header():

    if not CSV_PATH.is_file():
        raise FileNotFoundError(CSV_PATH)

    with CSV_PATH.open(
        encoding="utf-8-sig",
        newline="",
    ) as source:
        header = next(csv.reader(source), None)

    if not header:
        raise ValueError("CSV file has no header.")

    if len(header) != len(set(header)):
        raise ValueError("CSV contains duplicate column names.")

    missing = sorted(set(COLUMNS) - set(header))
    extra = sorted(set(header) - set(COLUMNS))

    if missing or extra:
        raise ValueError(
            f"CSV schema mismatch. Missing={missing}, Extra={extra}"
        )

    print(f"CSV schema validated: {len(header)} columns")


def create_staging_table(destination):

    with destination.transaction() as conn:

        conn.execute(
            text(
                "DROP TABLE IF EXISTS "
                "nyc311.cases_staging"
            )
        )

        conn.execute(
            text("""
                CREATE TABLE nyc311.cases_staging
                (LIKE nyc311.cases INCLUDING DEFAULTS)
            """)
        )

    print("Staging table prepared.")


def build_upsert_sql():

    quoted_columns = ", ".join(
        f'"{column}"' for column in COLUMNS
    )

    update_columns = [
        column
        for column in COLUMNS
        if column != "unique_key"
    ]

    assignments = ", ".join(
        f'"{column}" = EXCLUDED."{column}"'
        for column in update_columns
    )

    differences = " OR ".join(
        f'target_row."{column}" IS DISTINCT FROM '
        f'EXCLUDED."{column}"'
        for column in update_columns
    )

    return f"""
        INSERT INTO nyc311.cases AS target_row
            ({quoted_columns})

        SELECT {quoted_columns}
        FROM nyc311.cases_staging
        WHERE TRUE

        ON CONFLICT (unique_key)
        DO UPDATE SET
            {assignments}

        WHERE {differences}
    """


def main():

    start = time.perf_counter()

    validate_csv_header()

    required = [
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
    ]

    missing = [
        key for key in required
        if not os.getenv(key)
    ]

    if missing:
        raise RuntimeError(
            f"Missing database settings: {missing}"
        )

    database_url = URL.create(
        "postgresql+psycopg",
        username=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT") or "5432"),
        database=os.getenv("POSTGRES_DB"),
    )

    destination = DatabaseDestination(database_url)

    try:

        create_staging_table(destination)

        print("\nLoading NYC311 into staging...")

        with destination.transaction() as conn:

            conn.execute(
                text("TRUNCATE TABLE nyc311.cases_staging")
            )

            loaded_rows = destination.write_csv(
                file_path=CSV_PATH,
                table_name=STAGING_TABLE,
                schema=SCHEMA,
                dtype=SQL_TYPES,
                csv_dtype=CSV_DTYPES,
                parse_dates=DATE_COLUMNS,
                read_chunksize=READ_CHUNKSIZE,
                write_chunksize=WRITE_CHUNKSIZE,
                connection=conn,
            )

            staging_count = conn.execute(
                text(
                    "SELECT COUNT(*) "
                    "FROM nyc311.cases_staging"
                )
            ).scalar_one()

            if loaded_rows != staging_count:
                raise RuntimeError(
                    f"Row mismatch: read={loaded_rows}, "
                    f"staged={staging_count}"
                )

            duplicates = conn.execute(
                text("""
                    SELECT COUNT(*)
                    FROM (
                        SELECT unique_key
                        FROM nyc311.cases_staging
                        GROUP BY unique_key
                        HAVING COUNT(*) > 1
                    ) AS duplicate_keys
                """)
            ).scalar_one()

            if duplicates:
                raise RuntimeError(
                    f"Duplicate unique_key groups: {duplicates}"
                )

            print(f"Staged records: {staging_count:,}")
            print("Merging into target table...")

            result = conn.execute(
                text(build_upsert_sql())
            )

            affected_rows = result.rowcount

            target_count = conn.execute(
                text("SELECT COUNT(*) FROM nyc311.cases")
            ).scalar_one()

        elapsed = time.perf_counter() - start

        print("\n" + "=" * 55)
        print("NYC311 DATABASE LOADING COMPLETED")
        print("=" * 55)
        print(f"CSV records:       {loaded_rows:,}")
        print(f"Staging records:   {staging_count:,}")
        print(f"Inserted/updated:  {affected_rows:,}")
        print(f"Target total:      {target_count:,}")
        print(f"Duration:          {elapsed:.2f} seconds")
        print("=" * 55)

    finally:
        destination.close()


if __name__ == "__main__":
    main()
