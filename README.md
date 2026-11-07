# Challenge 02 — Database Performance

A reproducible PostgreSQL and Python project for loading datasets, analyzing query execution plans, measuring index read/write trade-offs, and building reusable analytical database objects.

## Project scope

This challenge brings together two datasets:

- **Olist e-commerce data** — loaded into PostgreSQL for order, seller, product, review, and payment analysis.
- **NYC 311 service requests** — loaded into a dedicated schema, including a staging-to-target loading workflow.

The performance work focuses on:

- Baseline and optimized analytical SQL queries.
- `EXPLAIN (ANALYZE, BUFFERS)` plan inspection.
- Hash Join, Merge Join, Nested Loop, Scan, Sort, and Aggregate behavior.
- Index size and the impact of indexes on bulk inserts.
- Live views versus precomputed snapshots.
- PostgreSQL functions and stored procedures.
- Python integration through pandas, SQLAlchemy, and psycopg.

## Technology

- Python 3.11
- PostgreSQL 16 (Docker)
- pandas
- SQLAlchemy 2.x
- psycopg 3
- Jupyter Notebook

## Repository structure

```text
02_Challenge_Database_Performance/
├── compose.yaml
├── .env                         # Local credentials; do not commit
├── notebooks/
│   └── solution.ipynb           # Main analysis and demonstration notebook
├── scripts/
│   ├── load_nyc311.py
│   └── load_olist.py
├── sql/
│   ├── indexes/
│   ├── queries/
│   ├── routines/
│   ├── schema/
│   └── views/
├── reports/
│   ├── baseline_explain.txt
│   ├── optimized_explain.txt
│   ├── workmem_64mb_explain.txt
│   ├── index_size_audit.txt
│   ├── index_write_benchmark.txt
│   └── additional query-plan reports
├── tests/
│   └── test_database_objects.py
└── README.md
```

Local datasets, virtual environments, and database credentials are intentionally kept out of version control.

## 1. Configure the environment

Use the project virtual environment:

```powershell
.\DBPerformace-env\Scripts\Activate.ps1
```

Install the Python dependencies if needed:

```powershell
python -m pip install pandas SQLAlchemy "psycopg[binary]" python-dotenv jupyter
```

Create a local `.env` file in the project root. Set the values required by `compose.yaml` and the Python scripts:

```dotenv
POSTGRES_DB=your_database_name
POSTGRES_USER=your_database_user
POSTGRES_PASSWORD=your_local_password
DB_HOST=localhost
DB_PORT=5432
```

Use local credentials only. Never commit `.env` or place real passwords in notebooks or SQL files.

## 2. Start PostgreSQL

Make sure Docker Desktop is running, then execute:

```powershell
docker compose up -d
docker compose ps
```

The Compose service runs PostgreSQL 16 and exposes it on port `5432`.

## 3. Create the schemas and tables

Run these commands from the project root in PowerShell:

```powershell
function Invoke-SqlFile {
    param([string]$File)

    Get-Content $File -Raw |
        docker compose exec -T postgres sh -c 'psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'

    if ($LASTEXITCODE -ne 0) {
        throw "SQL execution failed: $File"
    }
}

Invoke-SqlFile ".\sql\schema\001_create_schemas.sql"
Invoke-SqlFile ".\sql\schema\002_create_olist_tables.sql"
Invoke-SqlFile ".\sql\schema\002_create_nyc311_cases.sql"
```

## 4. Load the datasets

Place the Olist source CSV files in:

```text
data/raw/olist/
```

Then run the loaders from the project root:

```powershell
python .\scripts\load_olist.py
python .\scripts\load_nyc311.py
```

The loaders require the local database credentials in `.env` and the corresponding source data files. The Olist loader resets and reloads the Olist tables as part of its loading workflow.

## 5. Create performance and analytical objects

After the schemas, tables, and source data are ready, apply the project's SQL definitions:

```powershell
Invoke-SqlFile ".\sql\indexes\001_performance_indexes.sql"
Invoke-SqlFile ".\sql\routines\001_analytics_objects.sql"
Invoke-SqlFile ".\sql\views\001_seller_performance_snapshot.sql"
Invoke-SqlFile ".\sql\views\002_required_views_and_monthly_procedure.sql"
```

The SQL files are kept in the repository so that database changes can be reviewed and reproduced. Run them against a disposable or backed-up database when testing destructive changes.

## 6. Run the analysis notebook

With the `DBPerformace-env` environment active:

```powershell
jupyter notebook .\notebooks\solution.ipynb
```

Run the notebook using **Restart Kernel and Run All**.

The notebook demonstrates:

- Database connectivity and object inspection.
- Execution of the five analytical queries.
- Repeated query timing.
- Extraction and comparison of execution-plan operators.
- Index-size and insert-cost evidence.
- Live-view and snapshot timing.
- Function and stored-procedure calls.
- Chunked reads and typed DataFrame writes through SQLAlchemy.
- Automated test execution.

The notebook reads database credentials from `.env` and uses the SQL and report files in this repository.

## 7. Run the tests

From the project root:

```powershell
python -m unittest discover -s tests -v
```

The database-object test suite currently contains seven tests covering:

- Category-sales function date filtering.
- Delivery-delay query behavior on controlled data.
- Monthly procedure idempotency.
- Rejection of a null month by the procedure.
- Payment-distribution function filtering.
- Top-seller function consistency with its snapshot.
- View consistency with source data.

Latest recorded result: **7 tests passed**.

## 8. Performance methodology

Query performance is evaluated using execution plans and measured execution times, rather than estimated cost alone.

The analysis considers:

- Actual versus estimated row counts.
- Join algorithm and number of join nodes.
- Rows entering and leaving joins and aggregates.
- Sequential and index scans.
- Sort methods and memory usage.
- Shared buffer hits and reads.
- Index storage overhead and insert-time impact.
- The freshness and refresh cost of snapshots.

The project uses **200 ms as a performance target**, not as a claim that every live analytical query meets the target. Expensive queries are documented with their measured plans and bottlenecks. Where appropriate, a precomputed snapshot is evaluated as an alternative to repeatedly calculating the same aggregation.

A faster query is not automatically a better overall design: read performance, write overhead, storage, refresh cost, and data freshness must be considered together.

## 9. Important operational notes

- Do not commit `.env`, passwords, virtual environments, or private source datasets.
- Keep SQL schema changes, queries, functions, procedures, and views in their respective `sql/` folders.
- Keep execution-plan and benchmark evidence in `reports/`.
- Re-run the relevant tests after changing database objects.
- Record benchmark conditions when comparing timings; cache state, JIT, `work_mem`, and concurrent activity can affect results.
- Do not compare timings from different conditions as if they were a controlled benchmark.

## Status

The main notebook has been executed successfully. The latest recorded database-object test run completed with **7/7 tests passing**.
