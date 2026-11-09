from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "raw" / "cs-training.csv"
REPORT = ROOT / "reports" / "data_profile.txt"

df = pd.read_csv(DATA)

target = "SeriousDlqin2yrs"
id_col = "Unnamed: 0"

lines = []

def section(title):
    lines.extend(["\n" + "=" * 65, title, "=" * 65])

section("DATASET OVERVIEW")
lines.append(f"Rows: {len(df):,}")
lines.append(f"Columns: {len(df.columns)}")
lines.append(f"Duplicate rows: {df.duplicated().sum():,}")
lines.append(f"Duplicate IDs: {df[id_col].duplicated().sum():,}")

section("DATA TYPES")
lines.append(df.dtypes.to_string())

section("MISSING VALUES")
missing = df.isna().sum()
lines.append(missing[missing > 0].to_string() if missing.any() else "No missing values")

section("TARGET DISTRIBUTION")
counts = df[target].value_counts(dropna=False)
lines.append(counts.to_string())
lines.append("\nPercentages:")
lines.append((df[target].value_counts(normalize=True) * 100).round(2).to_string())

section("NUMERIC SUMMARY")
lines.append(
    df.drop(columns=[id_col])
    .describe(percentiles=[.01, .25, .5, .75, .95, .99])
    .round(3).T.to_string()
)

section("DATA QUALITY CHECKS")
checks = {
    "Invalid target values": (~df[target].isin([0, 1])).sum(),
    "Non-positive ages": (df["age"] <= 0).sum(),
    "Negative monthly income": (df["MonthlyIncome"] < 0).sum(),
    "Negative dependents": (df["NumberOfDependents"] < 0).sum(),
}

for name, value in checks.items():
    lines.append(f"{name}: {value:,}")

section("DELINQUENCY FREQUENCIES")

for col in [
    "NumberOfTime30-59DaysPastDueNotWorse",
    "NumberOfTimes90DaysLate",
    "NumberOfTime60-89DaysPastDueNotWorse"
]:
    lines.append(f"\n{col}")
    lines.append(df[col].value_counts().sort_index().tail(15).to_string())

section("PROFILE COMPLETED")

REPORT.write_text("\n".join(lines), encoding="utf-8")

print("\n".join(lines))
print(f"\nReport saved: {REPORT}")
