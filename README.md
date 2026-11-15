# Early Warning System

Datin Fintech Lab — Term 3 Capstone

Predicting orders at risk of receiving negative customer reviews
at the order approval timestamp.

## Architecture

Data Factory -> PostgreSQL -> Feature Engineering -> ML -> Top 10% Follow-up

## Constraints

- Point-in-time features only
- Temporal train/test split
- Database feature query under 500 ms
- End-to-end execution under 45 minutes
- Capacity-based evaluation
