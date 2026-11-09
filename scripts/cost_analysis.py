
from pathlib import Path
import os
import joblib
import numpy as np
import pandas as pd

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    roc_auc_score,
    average_precision_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
)

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

df = pd.read_sql(
    "SELECT * FROM credit_risk.modeling_dataset",
    engine
)

y = df["target"].astype(int)

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

# Reproduce the exact original split
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.20,
    stratify=y, random_state=42
)

X_train, X_val, y_train, y_val = train_test_split(
    X_train, y_train,
    test_size=0.1875,
    stratify=y_train, random_state=42
)

models = {
    "Logistic Regression": "logistic_regression.joblib",
    "Random Forest": "random_forest.joblib",
}

thresholds = np.linspace(0.01, 0.99, 99)
cost_ratios = [1, 2, 5, 10]

results = []

for name, filename in models.items():

    model = joblib.load(ROOT / "models" / filename)

    val_prob = model.predict_proba(X_val)[:, 1]
    test_prob = model.predict_proba(X_test)[:, 1]

    val_matrix = (
        val_prob[:, None] >= thresholds[None, :]
    )

    yv = y_val.to_numpy()
    yt = y_test.to_numpy()

    fp_val = ((val_matrix) & (yv[:, None] == 0)).sum(axis=0)
    fn_val = ((~val_matrix) & (yv[:, None] == 1)).sum(axis=0)

    for ratio in cost_ratios:

        # Optimize threshold using validation only
        validation_cost = fp_val + ratio * fn_val
        best_idx = np.argmin(validation_cost)

        threshold = float(thresholds[best_idx])

        # Evaluate once on untouched test set
        pred = (test_prob >= threshold).astype(int)

        tn, fp, fn, tp = confusion_matrix(
            yt, pred, labels=[0, 1]
        ).ravel()

        results.append({
            "model": name,
            "FN_to_FP_cost_ratio": ratio,
            "threshold": threshold,
            "validation_cost": int(validation_cost[best_idx]),
            "test_cost": int(fp + ratio * fn),
            "cost_per_1000": round(
                (fp + ratio * fn) / len(yt) * 1000, 2
            ),
            "ROC_AUC": roc_auc_score(yt, test_prob),
            "PR_AUC": average_precision_score(yt, test_prob),
            "precision": precision_score(yt, pred, zero_division=0),
            "recall": recall_score(yt, pred, zero_division=0),
            "F1": f1_score(yt, pred, zero_division=0),
            "FP": fp,
            "FN": fn,
            "TN": tn,
            "TP": tp,
        })

        print(
            f"{name} | FN:FP={ratio}:1 | "
            f"Threshold={threshold:.2f} | "
            f"Test Cost={fp + ratio * fn}"
        )

result_df = pd.DataFrame(results)

result_df.to_csv(
    ROOT / "reports" / "cost_sensitivity_analysis.csv",
    index=False
)

print("\nFINAL COST SENSITIVITY ANALYSIS")
print(
    result_df.sort_values(
        ["FN_to_FP_cost_ratio", "test_cost"]
    ).to_string(index=False)
)

engine.dispose()

print("\nCOST ANALYSIS COMPLETED")
