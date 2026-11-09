
# Credit Risk Prediction — Challenge 03

Part of Datin Fintech Lab — Term 3 Python & Machine Learning.

## Project Overview

A machine learning project for predicting whether a borrower will experience serious financial delinquency within two years.

Dataset: Give Me Some Credit (Kaggle)

## Dataset

- Original records: 150,000
- Original features: 11
- Target: SeriousDlqin2yrs
- Default rate: 6.68%
- Missing values handled through ML pipelines.
- Raw data is excluded from Git.

## Architecture

1. Data Profiling
2. PostgreSQL Data Storage
3. Data Quality Auditing
4. Feature Engineering
5. Model Training
6. Cost-sensitive Evaluation
7. Final Model Packaging

## Technology Stack

- Python
- PostgreSQL 16
- SQLAlchemy
- Pandas / NumPy
- Scikit-learn
- Joblib
- Docker

## Models

- Logistic Regression
- Random Forest

## Final Model

Random Forest

Experimental FN-to-FP cost ratio: 5:1

Decision threshold: 0.70

### Test Performance

| Metric | Result |
|---|---:|
| ROC-AUC | 0.864546 |
| PR-AUC | 0.403554 |
| Precision | 36.41% |
| Recall | 52.97% |
| F1 | 0.431532 |
| False Positives | 1,855 |
| False Negatives | 943 |
| Relative Cost | 6,570 |

The 5:1 cost ratio is an experimental assumption, not an actual bank policy.

## Project Structure

```text
03_Challenge_Machine_Learning/
├── data/
│   ├── raw/
│   └── processed/
├── models/
├── reports/
├── scripts/
├── sql/
│   └── schema/
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Execution Order

1. profile_data.py
2. load_credit_data.py
3. audit_credit_data.py
4. build_features.py
5. train_models.py
6. cost_analysis.py
7. finalize_model.py

## Final Artifact

`models/credit_risk_final.joblib`

The packaged model includes the estimator, feature definitions, experimental threshold, and evaluation metadata.

## Reproducibility

Python dependencies are listed in requirements.txt.

PostgreSQL credentials must be configured locally through `.env`.

Raw datasets and credentials must not be committed to Git.
