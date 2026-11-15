# Final Challenge – Early Warning System

**Datin Fintech Lab | Term 3 – Python & Machine Learning**

## 1. Project Overview

This project develops an Early Warning System to identify e-commerce orders at risk of receiving negative customer reviews.

The system predicts the probability of a negative customer outcome at the order approval timestamp and prioritizes the highest-risk 10% of orders for operational follow-up.

The solution combines PostgreSQL, temporal feature engineering, machine learning, and capacity-based evaluation.

## 2. Business Objective

The primary objective is to help an e-commerce business proactively identify potentially problematic orders before their final customer feedback becomes available.

Key objectives:

- Identify high-risk orders early.
- Prevent target leakage through point-in-time feature selection.
- Prioritize follow-up using a fixed operational capacity of 10%.
- Evaluate model performance using business-oriented metrics.
- Build a reproducible end-to-end pipeline.

## 3. Data & Preparation

**Source:** Brazilian E-Commerce Public Dataset by Olist.

The data is stored and processed in PostgreSQL.

The preparation workflow includes:

- Review-based target construction.
- Point-in-time feature availability audit.
- Customer and seller history engineering.
- Product, payment, order, and geographical features.
- Missing-value and data-quality handling.
- Temporal train, validation, and test splitting.

Final modeling dataset:

| Split | Records |
|---|---:|
| Train | 65,991 |
| Validation | 12,314 |
| Test | 14,774 |
| **Total** | **93,079** |

The final dataset contains 39 features: 38 numeric and 1 categorical.

## 4. Data Leakage Prevention

The prediction timestamp is the order approval timestamp.

Only features available at or before this decision point are used.

Post-decision information, including delivery outcomes and future reviews, is excluded from model predictors.

Temporal validation is used instead of random splitting to preserve chronological ordering.

## 5. Machine Learning

Two models were evaluated:

- Logistic Regression
- Random Forest

Random Forest was selected based on validation performance at the 10% operational capacity.

### Validation comparison

| Metric | Logistic Regression | Random Forest |
|---|---:|---:|
| ROC-AUC | 0.6440 | 0.6505 |
| PR-AUC | 0.2406 | 0.2550 |
| Precision@10% | 0.2873 | 0.2906 |
| Recall@10% | 0.2440 | 0.2467 |
| Lift@10% | 2.4385 | 2.4661 |

## 6. Final Test Results

**Selected Model: Random Forest**

| Metric | Final Test |
|---|---:|
| ROC-AUC | 0.6035 |
| PR-AUC | 0.2026 |
| Precision@10% | 22.94% |
| Recall@10% | 21.46% |
| Lift@10% | 2.14x |
| Test Records | 14,774 |
| Selected Orders | 1,478 |
| True Positives in Queue | 339 |

The model identifies approximately 2.14 times as many negative-review outcomes per selected order as random selection at the same capacity.

The operational queue contains the highest-risk 10% of test orders.

## 7. Database Performance

The modeling dataset is stored in PostgreSQL.

Final full-table query benchmark:

| Metric | Result |
|---|---:|
| Execution Time | 13.671 ms |
| Maximum Allowed | 500 ms |
| Status | PASSED |

## 8. End-to-End Pipeline

The complete workflow is orchestrated using Python.

Execution:

```bash
python scripts/run_pipeline.py
```

Pipeline stages:

1. Infrastructure validation
2. Feature engineering
3. Modeling dataset preparation
4. Dataset export
5. Dependency validation
6. Model training
7. Model smoke testing
8. Database performance benchmarking
9. Final execution reporting

### Pipeline Results

| Metric | Result |
|---|---:|
| Total Execution Time | 53.15 seconds |
| Maximum Allowed | 45 minutes |
| Database Query | 13.671 ms |
| Dataset Records | 93,079 |
| Pipeline Status | PASSED |

## 9. Project Structure

```text
04_Final_Challenge_Capstone/
│
├── data/
│   ├── raw/
│   └── processed/
│
├── models/
│   └── early_warning_model.joblib
│
├── notebooks/
│
├── outputs/
│   └── top_10pct_followup.csv
│
├── reports/
│   ├── validation_model_comparison.csv
│   ├── final_test_evaluation.csv
│   ├── model_metadata.json
│   ├── smoke_test_report.json
│   ├── end_to_end_run.json
│   ├── end_to_end_run.txt
│   └── end_to_end_database_benchmark.txt
│
├── scripts/
│   ├── train_early_warning.py
│   ├── smoke_test_model.py
│   └── run_pipeline.py
│
├── sql/
│   ├── audit/
│   ├── features/
│   └── schema/
│
├── src/
├── tests/
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## 10. Technologies

- Python
- PostgreSQL
- SQL
- Pandas
- Scikit-learn
- Random Forest
- SQLAlchemy
- Docker
- Git & GitHub

## 11. Reproducibility

The pipeline requires:

- A configured PostgreSQL database.
- The Olist source tables.
- The previously constructed `capstone.order_labels` table.
- A configured Python virtual environment.
- Dependencies installed from `requirements.txt`.

Activate the environment and execute:

```powershell
.\Capstone-env\Scripts\Activate.ps1

python -m pip install -r requirements.txt

python scripts/run_pipeline.py
```

## 12. Conclusion

The project delivers a complete temporal early warning workflow, from database-level feature engineering to model training and operational risk prioritization.

The final Random Forest model achieves a 2.14x lift at 10% operational capacity, while the complete pipeline executes in approximately 53 seconds.

**Final Status: Successfully Completed.**