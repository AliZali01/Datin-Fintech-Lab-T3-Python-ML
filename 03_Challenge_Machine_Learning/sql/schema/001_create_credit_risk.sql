CREATE SCHEMA IF NOT EXISTS credit_risk;

CREATE TABLE IF NOT EXISTS credit_risk.raw_training (
    "Unnamed: 0" BIGINT PRIMARY KEY,
    "SeriousDlqin2yrs" SMALLINT NOT NULL
        CHECK ("SeriousDlqin2yrs" IN (0,1)),
    "RevolvingUtilizationOfUnsecuredLines" DOUBLE PRECISION,
    "age" INTEGER,
    "NumberOfTime30-59DaysPastDueNotWorse" INTEGER,
    "DebtRatio" DOUBLE PRECISION,
    "MonthlyIncome" DOUBLE PRECISION,
    "NumberOfOpenCreditLinesAndLoans" INTEGER,
    "NumberOfTimes90DaysLate" INTEGER,
    "NumberRealEstateLoansOrLines" INTEGER,
    "NumberOfTime60-89DaysPastDueNotWorse" INTEGER,
    "NumberOfDependents" DOUBLE PRECISION
);

CREATE OR REPLACE VIEW credit_risk.training_data AS
SELECT
    "Unnamed: 0" AS source_id,
    "SeriousDlqin2yrs" AS target,
    "RevolvingUtilizationOfUnsecuredLines" AS revolving_utilization,
    age,
    "NumberOfTime30-59DaysPastDueNotWorse" AS delinquency_30_59,
    "DebtRatio" AS debt_ratio,
    "MonthlyIncome" AS monthly_income,
    "NumberOfOpenCreditLinesAndLoans" AS open_credit_lines,
    "NumberOfTimes90DaysLate" AS delinquency_90_plus,
    "NumberRealEstateLoansOrLines" AS real_estate_loans,
    "NumberOfTime60-89DaysPastDueNotWorse" AS delinquency_60_89,
    "NumberOfDependents" AS dependents
FROM credit_risk.raw_training;
