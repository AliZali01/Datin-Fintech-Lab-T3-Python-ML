import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import (
    URL, text, BigInteger, SmallInteger, Integer, Float
)

from data_factory.database_destination import DatabaseDestination

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "raw" / "cs-training.csv"

load_dotenv(ROOT / ".env")

required = ["POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"]

if not all(os.getenv(key) for key in required):
    raise RuntimeError("Database credentials missing from .env")

url = URL.create(
    "postgresql+psycopg",
    username=os.getenv("POSTGRES_USER"),
    password=os.getenv("POSTGRES_PASSWORD"),
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", "5432")),
    database=os.getenv("POSTGRES_DB"),
)

destination = DatabaseDestination(url)

with destination.engine.connect() as conn:
    existing = conn.execute(
        text("SELECT COUNT(*) FROM credit_risk.raw_training")
    ).scalar_one()

if existing:
    raise RuntimeError(
        f"Target already contains {existing} records. Refusing duplicate load."
    )

sql_types = {
    "Unnamed: 0": BigInteger(),
    "SeriousDlqin2yrs": SmallInteger(),
    "RevolvingUtilizationOfUnsecuredLines": Float(),
    "age": Integer(),
    "NumberOfTime30-59DaysPastDueNotWorse": Integer(),
    "DebtRatio": Float(),
    "MonthlyIncome": Float(),
    "NumberOfOpenCreditLinesAndLoans": Integer(),
    "NumberOfTimes90DaysLate": Integer(),
    "NumberRealEstateLoansOrLines": Integer(),
    "NumberOfTime60-89DaysPastDueNotWorse": Integer(),
    "NumberOfDependents": Float(),
}

csv_types = {
    "Unnamed: 0": "int64",
    "SeriousDlqin2yrs": "int64",
    "RevolvingUtilizationOfUnsecuredLines": "float64",
    "age": "int64",
    "NumberOfTime30-59DaysPastDueNotWorse": "int64",
    "DebtRatio": "float64",
    "MonthlyIncome": "float64",
    "NumberOfOpenCreditLinesAndLoans": "int64",
    "NumberOfTimes90DaysLate": "int64",
    "NumberRealEstateLoansOrLines": "int64",
    "NumberOfTime60-89DaysPastDueNotWorse": "int64",
    "NumberOfDependents": "float64",
}

written = destination.write_csv(
    file_path=DATA,
    table_name="raw_training",
    schema="credit_risk",
    dtype=sql_types,
    csv_dtype=csv_types,
    read_chunksize=20000,
    write_chunksize=2000,
)

with destination.engine.connect() as conn:
    result = conn.execute(text("""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (
                WHERE "SeriousDlqin2yrs" = 1
            ) AS defaults,
            COUNT(*) FILTER (
                WHERE "MonthlyIncome" IS NULL
            ) AS missing_income,
            COUNT(*) FILTER (
                WHERE "NumberOfDependents" IS NULL
            ) AS missing_dependents
        FROM credit_risk.raw_training
    """)).one()

print("\nCREDIT RISK LOADING COMPLETED")
print("Written:", written)
print("Total:", result.total)
print("Defaults:", result.defaults)
print("Missing income:", result.missing_income)
print("Missing dependents:", result.missing_dependents)

destination.engine.dispose()
