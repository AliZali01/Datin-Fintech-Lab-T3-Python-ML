
# Credit Risk Model Selection

## Dataset
- Records: 150,000
- Features: 23
- Target: SeriousDlqin2yrs
- Default rate: 6.68%

## Models
- Logistic Regression
- Random Forest

## Evaluation
- Stratified train/validation/test split
- ROC-AUC
- PR-AUC
- Precision
- Recall
- F1-score
- Cost-sensitive threshold optimization

## Selected Model
Random Forest

## Primary Experimental Scenario
FN-to-FP cost ratio: 5:1
Threshold: 0.70

## Test Results
- ROC-AUC: 0.864546
- PR-AUC: 0.403554
- Precision: 0.364073
- Recall: 0.529676
- F1: 0.431532
- False Positives: 1855
- False Negatives: 943
- Relative Cost: 6570

## Conclusion
Random Forest achieved the lowest test cost
across all four evaluated cost scenarios.

The 5:1 ratio is an experimental assumption,
not an actual bank-approved cost policy.

## Reproducibility
- scripts/profile_data.py
- scripts/audit_credit_data.py
- scripts/load_credit_data.py
- scripts/build_features.py
- scripts/train_models.py
- scripts/cost_analysis.py

Database: PostgreSQL 16
Python environment: ML-env
