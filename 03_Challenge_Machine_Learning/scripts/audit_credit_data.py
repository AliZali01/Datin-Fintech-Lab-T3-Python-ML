from pathlib import Path
import os

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, text

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

url = URL.create(
    "postgresql+psycopg",
    username=os.getenv("POSTGRES_USER"),
    password=os.getenv("POSTGRES_PASSWORD"),
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", "5432")),
    database=os.getenv("POSTGRES_DB"),
)

engine = create_engine(url)

queries = {
    "OVERVIEW": """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE age = 0) AS zero_age,
            COUNT(*) FILTER (
                WHERE "RevolvingUtilizationOfUnsecuredLines" > 1
            ) AS utilization_above_one,
            COUNT(*) FILTER (
                WHERE "RevolvingUtilizationOfUnsecuredLines" > 10
            ) AS utilization_above_ten,
            COUNT(*) FILTER (
                WHERE "DebtRatio" > 100
            ) AS debt_ratio_above_100
        FROM credit_risk.raw_training
    """,

    "DELINQUENCY_96_98": """
        SELECT
            column_name,
            suspicious_value,
            COUNT(*) AS records,
            SUM(target) AS defaults,
            ROUND(100.0 * SUM(target) / COUNT(*), 2) AS default_pct
        FROM (
            SELECT '30_59' AS column_name,
                   "NumberOfTime30-59DaysPastDueNotWorse" AS suspicious_value,
                   "SeriousDlqin2yrs" AS target
            FROM credit_risk.raw_training

            UNION ALL

            SELECT '60_89',
                   "NumberOfTime60-89DaysPastDueNotWorse",
                   "SeriousDlqin2yrs"
            FROM credit_risk.raw_training

            UNION ALL

            SELECT '90_plus',
                   "NumberOfTimes90DaysLate",
                   "SeriousDlqin2yrs"
            FROM credit_risk.raw_training
        ) x
        WHERE suspicious_value IN (96, 98)
        GROUP BY column_name, suspicious_value
        ORDER BY column_name, suspicious_value
    """,

    "SENTINEL_OVERLAP": """
        SELECT
            COUNT(*) FILTER (
                WHERE "NumberOfTime30-59DaysPastDueNotWorse" IN (96,98)
            ) AS d30_59,
            COUNT(*) FILTER (
                WHERE "NumberOfTime60-89DaysPastDueNotWorse" IN (96,98)
            ) AS d60_89,
            COUNT(*) FILTER (
                WHERE "NumberOfTimes90DaysLate" IN (96,98)
            ) AS d90_plus,
            COUNT(*) FILTER (
                WHERE "NumberOfTime30-59DaysPastDueNotWorse" IN (96,98)
                AND "NumberOfTime60-89DaysPastDueNotWorse" IN (96,98)
                AND "NumberOfTimes90DaysLate" IN (96,98)
            ) AS all_three
        FROM credit_risk.raw_training
    """,

    "EXTREME_RECORDS": """
        SELECT
            "Unnamed: 0" AS source_id,
            "SeriousDlqin2yrs" AS target,
            age,
            "RevolvingUtilizationOfUnsecuredLines" AS utilization,
            "DebtRatio" AS debt_ratio,
            "MonthlyIncome" AS income
        FROM credit_risk.raw_training
        WHERE age = 0
           OR "RevolvingUtilizationOfUnsecuredLines" > 10
           OR "DebtRatio" > 10000
        ORDER BY "RevolvingUtilizationOfUnsecuredLines" DESC
        LIMIT 15
    """
}

report = []

with engine.connect() as conn:
    for title, query in queries.items():
        report.append(f"\n{'=' * 60}\n{title}\n{'=' * 60}")

        result = conn.execute(text(query))
        rows = result.mappings().all()

        report.append(str([dict(row) for row in rows]))

engine.dispose()

output = "\n".join(report)

(ROOT / "reports").mkdir(exist_ok=True)
(ROOT / "reports" / "data_quality_audit.txt").write_text(
    output, encoding="utf-8"
)

print(output)
print("\nAudit saved successfully.")