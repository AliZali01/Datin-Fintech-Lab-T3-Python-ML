
from pathlib import Path
import json
import math

import joblib
import numpy as np
import pandas as pd

from sklearn.metrics import (
    roc_auc_score,
    average_precision_score
)

ROOT = Path(__file__).resolve().parents[1]

DATA_PATH = ROOT / "data/processed/modeling_dataset.csv"
MODEL_PATH = ROOT / "models/early_warning_model.joblib"

OUTPUT_DIR = ROOT / "outputs"
REPORT_DIR = ROOT / "reports"

CAPACITY = 0.10


def main():

    print("Loading final model...")

    bundle = joblib.load(MODEL_PATH)
    model = bundle["pipeline"]
    features = bundle["feature_columns"]

    df = pd.read_csv(
        DATA_PATH,
        parse_dates=["approved_at"]
    )

    test = df[df["split"] == "test"].copy()

    assert len(test) > 0
    assert test["order_id"].is_unique

    missing_features = set(features) - set(test.columns)
    assert not missing_features, missing_features

    X_test = test[features]

    print("Scoring test records...")

    probabilities = model.predict_proba(X_test)[:, 1]

    assert len(probabilities) == len(test)
    assert np.isfinite(probabilities).all()
    assert ((probabilities >= 0) & (probabilities <= 1)).all()

    # Rank orders by predicted risk
    ranked_indices = np.argsort(
        -probabilities,
        kind="mergesort"
    )

    top_n = math.ceil(len(test) * CAPACITY)
    selected_indices = ranked_indices[:top_n]

    # Operational queue: no actual labels exposed
    queue = test.iloc[selected_indices][
        ["order_id", "approved_at"]
    ].copy()

    queue["risk_score"] = probabilities[selected_indices]
    queue["priority_rank"] = np.arange(1, top_n + 1)

    queue = queue.sort_values("priority_rank")

    OUTPUT_DIR.mkdir(exist_ok=True)
    REPORT_DIR.mkdir(exist_ok=True)

    queue.to_csv(
        OUTPUT_DIR / "top_10pct_followup.csv",
        index=False
    )

    # Evaluation only; target is excluded from the operational queue
    y_test = test["target"].to_numpy()

    tp = int(y_test[selected_indices].sum())
    positives = int(y_test.sum())

    metrics = {
        "model": bundle["model_name"],
        "test_records": len(test),
        "selected_orders": top_n,
        "capacity": CAPACITY,
        "risk_score_cutoff": float(
            probabilities[selected_indices[-1]]
        ),
        "roc_auc": float(
            roc_auc_score(y_test, probabilities)
        ),
        "pr_auc": float(
            average_precision_score(y_test, probabilities)
        ),
        "precision_at_10pct": tp / top_n,
        "recall_at_10pct": tp / positives,
        "lift_at_10pct": (
            (tp / top_n) / y_test.mean()
        ),
        "true_positives_in_queue": tp,
        "total_positive_orders": positives
    }

    with open(
        REPORT_DIR / "smoke_test_report.json",
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(metrics, f, indent=2)

    # Final assertions
    assert len(queue) == top_n
    assert queue["order_id"].is_unique
    assert "target" not in queue.columns
    assert queue["risk_score"].is_monotonic_decreasing

    print("\nFINAL MODEL SMOKE TEST")
    print("=" * 45)

    for key, value in metrics.items():
        print(f"{key}: {value}")

    print("\nQueue:", OUTPUT_DIR / "top_10pct_followup.csv")
    print("Status: PASSED")


if __name__ == "__main__":
    main()
