from pathlib import Path
import os

import numpy as np
import pandas as pd

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

print("Reading data from PostgreSQL...")

df = pd.read_sql(
    "SELECT * FROM credit_risk.training_data",
    engine
)

features = pd.DataFrame({
    "source_id": df["source_id"],
    "target": df["target"],
})

# Missing value indicators
features["income_missing_flag"] = (
    df["monthly_income"].isna().astype("int8")
)

features["dependents_missing_flag"] = (
    df["dependents"].isna().astype("int8")
)

# Invalid age
features["age_invalid_flag"] = (
    (df["age"] <= 0).astype("int8")
)

features["age"] = df["age"].mask(df["age"] <= 0)

# Delinquency special codes
delinquency_cols = [
    "delinquency_30_59",
    "delinquency_60_89",
    "delinquency_90_plus",
]

features["delinquency_code_96_flag"] = (
    df[delinquency_cols].eq(96).any(axis=1).astype("int8")
)

features["delinquency_code_98_flag"] = (
    df[delinquency_cols].eq(98).any(axis=1).astype("int8")
)

# Preserve raw values in PostgreSQL.
# Special codes are excluded from numerical count features.
clean_counts = df[delinquency_cols].mask(
    df[delinquency_cols].isin([96, 98])
)

for col in delinquency_cols:
    features[f"{col}_clean"] = clean_counts[col]

features["total_delinquency_count"] = (
    clean_counts.sum(axis=1, min_count=1)
)

features["any_delinquency_flag"] = (
    features["total_delinquency_count"].gt(0)
    .fillna(False).astype("int8")
)

# Credit utilization
features["revolving_utilization"] = df["revolving_utilization"]

features["revolving_utilization_over_limit"] = (
    (df["revolving_utilization"] > 1).astype("int8")
)

features["revolving_utilization_extreme_flag"] = (
    (df["revolving_utilization"] > 10).astype("int8")
)

features["revolving_utilization_log1p"] = np.log1p(
    df["revolving_utilization"].clip(lower=0)
)

# Debt ratio
features["debt_ratio"] = df["debt_ratio"]

features["debt_ratio_extreme_flag"] = (
    (df["debt_ratio"] > 100).astype("int8")
)

features["debt_ratio_log1p"] = np.log1p(
    df["debt_ratio"].clip(lower=0)
)

# Income
features["monthly_income"] = df["monthly_income"]

features["monthly_income_log1p"] = np.log1p(
    df["monthly_income"].clip(lower=0)
)

# Financial capacity
features["income_per_dependent"] = (
    df["monthly_income"] / (df["dependents"] + 1)
)

features["credit_lines_per_dependent"] = (
    df["open_credit_lines"] / (df["dependents"] + 1)
)

# Credit structure
features["open_credit_lines"] = df["open_credit_lines"]

features["real_estate_loans"] = df["real_estate_loans"]

features["open_unsecured_lines"] = (
    df["open_credit_lines"] - df["real_estate_loans"]
).clip(lower=0)

features["dependents"] = df["dependents"]

# Save to PostgreSQL
with engine.begin() as conn:
    conn.execute(text("""
        DROP TABLE IF EXISTS credit_risk.modeling_dataset
    """))

features.to_sql(
    "modeling_dataset",
    engine,
    schema="credit_risk",
    if_exists="replace",
    index=False,
    chunksize=2000,
)

with engine.connect() as conn:
    count = conn.execute(text("""
        SELECT COUNT(*)
        FROM credit_risk.modeling_dataset
    """)).scalar_one()

print("\nFEATURE ENGINEERING COMPLETED")
print("Rows:", count)
print("Total columns:", len(features.columns))
print("New features:", len(features.columns) - 2)
print("\nMissing values:")
print(features.isna().sum()[features.isna().sum() > 0])

print("\nFeature table created successfully.")

engine.dispose()