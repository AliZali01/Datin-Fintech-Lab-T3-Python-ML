
from pathlib import Path
import json

import joblib
import numpy as np
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score, average_precision_score


ROOT = Path(__file__).resolve().parents[1]

DATA_PATH = ROOT / "data/processed/modeling_dataset.csv"
MODEL_PATH = ROOT / "models/early_warning_model.joblib"
REPORT_PATH = ROOT / "reports"

CAPACITY = 0.10
RANDOM_STATE = 42


def build_model(name, numeric_cols, categorical_cols):

    numeric_pipeline = Pipeline([
        ("imputer", SimpleImputer(
            strategy="median",
            add_indicator=True
        )),
        ("scaler", StandardScaler())
    ])

    categorical_pipeline = Pipeline([
        ("imputer", SimpleImputer(
            strategy="most_frequent"
        )),
        ("encoder", OneHotEncoder(
            handle_unknown="ignore",
            sparse_output=False
        ))
    ])

    preprocessing = ColumnTransformer([
        ("numeric", numeric_pipeline, numeric_cols),
        ("categorical", categorical_pipeline, categorical_cols)
    ])

    if name == "Logistic Regression":
        estimator = LogisticRegression(
            C=0.5,
            max_iter=2000,
            class_weight="balanced",
            random_state=RANDOM_STATE
        )

    else:
        estimator = RandomForestClassifier(
            n_estimators=250,
            max_depth=12,
            min_samples_leaf=25,
            max_features="sqrt",
            class_weight="balanced_subsample",
            n_jobs=-1,
            random_state=RANDOM_STATE
        )

    return Pipeline([
        ("preprocessing", preprocessing),
        ("model", estimator)
    ])


def evaluate(y_true, probabilities):

    y = np.asarray(y_true, dtype=int)

    selected_count = max(
        1,
        int(np.ceil(len(y) * CAPACITY))
    )

    ranked_indices = np.argsort(
        -probabilities,
        kind="mergesort"
    )[:selected_count]

    true_positives = int(y[ranked_indices].sum())

    precision = true_positives / selected_count
    recall = true_positives / max(1, int(y.sum()))

    return {
        "roc_auc": float(roc_auc_score(y, probabilities)),
        "pr_auc": float(average_precision_score(y, probabilities)),
        "precision_at_10pct": float(precision),
        "recall_at_10pct": float(recall),
        "lift_at_10pct": float(precision / y.mean()),
        "selected_orders": int(selected_count),
        "base_rate": float(y.mean())
    }


def main():

    print("Loading modeling dataset...")

    df = pd.read_csv(
        DATA_PATH,
        parse_dates=["approved_at"]
    )

    assert len(df) == 93079
    assert df["order_id"].is_unique
    assert df["target"].isin([0, 1]).all()

    print("Records:", len(df))

    # Metadata and target must never enter the model
    excluded = {
        "split",
        "order_id",
        "approved_at",
        "target"
    }

    feature_cols = [
        c for c in df.columns
        if c not in excluded
    ]

    X = df[feature_cols].copy()

    numeric_cols = [
        c for c in feature_cols
        if pd.api.types.is_numeric_dtype(X[c])
    ]

    categorical_cols = [
        c for c in feature_cols
        if c not in numeric_cols
    ]

    # Exclude columns entirely missing in training
    train_mask = df["split"] == "train"

    empty_cols = [
        c for c in feature_cols
        if X.loc[train_mask, c].notna().sum() == 0
    ]

    if empty_cols:
        print("Dropped empty training features:", empty_cols)
        X = X.drop(columns=empty_cols)

        feature_cols = list(X.columns)
        numeric_cols = [
            c for c in feature_cols
            if pd.api.types.is_numeric_dtype(X[c])
        ]
        categorical_cols = [
            c for c in feature_cols
            if c not in numeric_cols
        ]

    for col in numeric_cols:
        X[col] = pd.to_numeric(
            X[col], errors="coerce"
        ).replace([np.inf, -np.inf], np.nan)

    y = df["target"].astype(int)

    train_mask = df["split"] == "train"
    validation_mask = df["split"] == "validation"
    test_mask = df["split"] == "test"

    X_train, y_train = X.loc[train_mask], y.loc[train_mask]
    X_val, y_val = X.loc[validation_mask], y.loc[validation_mask]

    print("Features:", len(feature_cols))
    print("Numeric:", len(numeric_cols))
    print("Categorical:", len(categorical_cols))

    print("\nTraining models...")

    candidates = [
        "Logistic Regression",
        "Random Forest"
    ]

    models = {}
    validation_results = []

    for name in candidates:

        print(f"\nTraining {name}...")

        model = build_model(
            name,
            numeric_cols,
            categorical_cols
        )

        model.fit(X_train, y_train)

        probabilities = model.predict_proba(X_val)[:, 1]

        result = evaluate(y_val, probabilities)
        result["model"] = name

        models[name] = model
        validation_results.append(result)

        print(pd.Series(result).to_string())

    # Select using validation only
    comparison = pd.DataFrame(validation_results)

    comparison = comparison.sort_values(
        ["recall_at_10pct", "pr_auc"],
        ascending=False
    )

    REPORT_PATH.mkdir(exist_ok=True)

    comparison.to_csv(
        REPORT_PATH / "validation_model_comparison.csv",
        index=False
    )

    best_name = comparison.iloc[0]["model"]

    print("\nSelected model:", best_name)

    # Refit on train + validation
    train_validation_mask = df["split"].isin([
        "train",
        "validation"
    ])

    X_train_validation = X.loc[train_validation_mask]
    y_train_validation = y.loc[train_validation_mask]

    final_model = models[best_name]

    print("\nRefitting selected model on Train + Validation...")

    final_model.fit(
        X_train_validation,
        y_train_validation
    )

    # Test is used only once for final evaluation
    X_test = X.loc[test_mask]
    y_test = y.loc[test_mask]

    test_probabilities = final_model.predict_proba(
        X_test
    )[:, 1]

    test_result = evaluate(
        y_test,
        test_probabilities
    )

    test_result["model"] = best_name

    pd.DataFrame([test_result]).to_csv(
        REPORT_PATH / "final_test_evaluation.csv",
        index=False
    )

    bundle = {
        "pipeline": final_model,
        "model_name": best_name,
        "feature_columns": feature_cols,
        "numeric_columns": numeric_cols,
        "categorical_columns": categorical_cols,
        "capacity": CAPACITY,
        "validation_results": validation_results,
        "test_results": test_result
    }

    joblib.dump(bundle, MODEL_PATH)

    with open(
        REPORT_PATH / "model_metadata.json",
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            {
                "model": best_name,
                "features": feature_cols,
                "capacity": CAPACITY,
                "test_metrics": test_result
            },
            f,
            indent=2
        )

    print("\n" + "=" * 55)
    print("FINAL TEST RESULTS")
    print("=" * 55)

    print(pd.Series(test_result).to_string())

    print("\nModel saved:", MODEL_PATH)
    print("TRAINING COMPLETED SUCCESSFULLY")


if __name__ == "__main__":
    main()
