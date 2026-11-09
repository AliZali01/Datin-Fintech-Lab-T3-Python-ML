from pathlib import Path
import os

import joblib
import numpy as np
import pandas as pd

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine

from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import RobustScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier

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

print("Loading modeling dataset...")

df = pd.read_sql(
    "SELECT * FROM credit_risk.modeling_dataset",
    engine
)

y = df["target"].astype(int)

X = df.drop(columns=[
    "source_id",
    "target",
    "revolving_utilization",
    "debt_ratio",
    "monthly_income",
])

# Log-transform skewed ratio features
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

print("Features:", X.shape[1])
print("Records:", len(X))

# 65% Train / 15% Validation / 20% Test
X_train, X_test, y_train, y_test = train_test_split(
    X, y,
    test_size=0.20,
    stratify=y,
    random_state=42
)

X_train, X_val, y_train, y_val = train_test_split(
    X_train, y_train,
    test_size=0.1875,
    stratify=y_train,
    random_state=42
)

print("Train:", len(X_train))
print("Validation:", len(X_val))
print("Test:", len(X_test))

models = {
    "Logistic Regression": Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", RobustScaler()),
        ("model", LogisticRegression(
            max_iter=300,
            class_weight="balanced",
            random_state=42
        ))
    ]),

    "Random Forest": Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("model", RandomForestClassifier(
            n_estimators=100,
            max_depth=12,
            min_samples_leaf=25,
            max_features="sqrt",
            class_weight="balanced_subsample",
            n_jobs=-1,
            random_state=42
        ))
    ])
}

(ROOT / "models").mkdir(exist_ok=True)
(ROOT / "reports").mkdir(exist_ok=True)

results = []

for name, model in models.items():

    print(f"\nTraining {name}...")

    model.fit(X_train, y_train)

    # Threshold selection on validation data only
    val_prob = model.predict_proba(X_val)[:, 1]

    thresholds = np.arange(0.05, 0.96, 0.01)

    scores = [
        f1_score(
            y_val,
            (val_prob >= threshold).astype(int),
            zero_division=0
        )
        for threshold in thresholds
    ]

    best_threshold = float(thresholds[np.argmax(scores)])

    # Final evaluation on untouched test data
    test_prob = model.predict_proba(X_test)[:, 1]

    predictions = (test_prob >= best_threshold).astype(int)

    tn, fp, fn, tp = confusion_matrix(
        y_test,
        predictions,
        labels=[0, 1]
    ).ravel()

    result = {
        "model": name,
        "roc_auc": roc_auc_score(y_test, test_prob),
        "pr_auc": average_precision_score(y_test, test_prob),
        "threshold": best_threshold,
        "precision": precision_score(
            y_test, predictions, zero_division=0
        ),
        "recall": recall_score(
            y_test, predictions, zero_division=0
        ),
        "f1": f1_score(
            y_test, predictions, zero_division=0
        ),
        "true_negative": tn,
        "false_positive": fp,
        "false_negative": fn,
        "true_positive": tp,
    }

    results.append(result)

    filename = (
        "logistic_regression.joblib"
        if name == "Logistic Regression"
        else "random_forest.joblib"
    )

    joblib.dump(model, ROOT / "models" / filename)

    print(pd.Series(result).to_string())

# Save comparison
comparison = pd.DataFrame(results)

comparison.to_csv(
    ROOT / "reports" / "model_comparison.csv",
    index=False
)

print("\n" + "=" * 55)
print("FINAL MODEL COMPARISON")
print("=" * 55)

print(comparison.to_string(index=False))

engine.dispose()

print("\nMODEL TRAINING COMPLETED")