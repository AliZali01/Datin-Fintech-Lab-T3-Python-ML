
from pathlib import Path
import os
import joblib
import numpy as np
import pandas as pd

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine

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

print("Loading data...")

df = pd.read_sql(
    "SELECT * FROM credit_risk.modeling_dataset",
    engine
)

X = df.drop(columns=[
    "source_id", "target",
    "revolving_utilization",
    "debt_ratio",
    "monthly_income",
])

X["income_per_dependent_log1p"] = np.log1p(
    X["income_per_dependent"].clip(lower=0)
)
X["credit_lines_per_dependent_log1p"] = np.log1p(
    X["credit_lines_per_dependent"].clip(lower=0)
)

X = X.drop(columns=[
    "income_per_dependent",
    "credit_lines_per_dependent"
])

model = joblib.load(ROOT / "models" / "random_forest.joblib")

feature_columns = list(model.feature_names_in_)

if set(X.columns) != set(feature_columns):
    raise ValueError("Model feature mismatch!")

X = X[feature_columns]

# Final experimental configuration
threshold = 0.70

# Smoke test on 1,000 records
sample = X.head(1000)
probabilities = model.predict_proba(sample)[:, 1]

if not np.isfinite(probabilities).all():
    raise ValueError("Invalid prediction probabilities!")

predictions = (probabilities >= threshold).astype(int)

package = {
    "model": model,
    "model_name": "Random Forest",
    "threshold": threshold,
    "cost_ratio_fn_to_fp": 5,
    "feature_columns": feature_columns,
    "test_metrics": {
        "roc_auc": 0.864546,
        "pr_auc": 0.403554,
        "precision": 0.364073,
        "recall": 0.529676,
        "f1": 0.431532,
        "false_positives": 1855,
        "false_negatives": 943,
        "relative_cost": 6570,
    }
}

(ROOT / "models").mkdir(exist_ok=True)
(ROOT / "reports").mkdir(exist_ok=True)

model_path = ROOT / "models" / "credit_risk_final.joblib"

joblib.dump(package, model_path)

report = f"""
FINAL MODEL SMOKE TEST
======================

Model: Random Forest
Threshold: {threshold}
Cost ratio FN:FP = 5:1

Features: {len(feature_columns)}
Test records: 1000
Valid probabilities: {len(probabilities)}
Predicted defaults: {predictions.sum()}
Predicted non-defaults: {(predictions == 0).sum()}

Probability minimum: {probabilities.min():.6f}
Probability maximum: {probabilities.max():.6f}
Probability mean: {probabilities.mean():.6f}

Model package: {model_path.name}
Status: PASSED
"""

(ROOT / "reports" / "final_model_smoke_test.txt").write_text(
    report, encoding="utf-8"
)

print(report)
print("FINAL MODEL SAVED SUCCESSFULLY")

engine.dispose()
