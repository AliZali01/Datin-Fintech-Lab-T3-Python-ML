# NYC 311 Data Factory

A reproducible, modular, and quality-controlled data engineering pipeline for collecting, validating, transforming, enriching, and analyzing NYC 311 service requests.

## 1. Project Overview

This project implements an end-to-end data factory using the NYC 311 Open Data API.

The pipeline collects residential noise complaints from New York City, processes raw JSON records, performs data quality checks, enriches records with Census population data, aggregates monthly statistics, and validates geographic consistency using official NYC borough boundaries.

**Dataset scope:**
- Source: NYC 311 Open Data
- Complaint type: Noise - Residential
- Start date: 2024-01-01
- End date: 2025-07-01 (exclusive)
- Actual collection period: January 2024 – June 2025
- Raw records collected: 596,592
- Accepted records: 596,547
- Quarantined records: 45
- Raw batch files: 120

## 2. Technology Stack

- Python 3.11
- Requests – HTTP communication
- Shapely 2.x – Geographic point-in-polygon analysis
- Python-dotenv – Environment configuration
- JSON / JSONL / CSV – Data storage
- unittest – Automated testing
- Git – Version control

## 3. Project Architecture

```text
01_Challenge_Data_Factory/
│
├── config.json
├── .env
├── .gitignore
├── pyproject.toml
├── requirements.txt
├── README.md
│
├── data/
│   ├── raw/
│   │   ├── NYC 311 batches/
│   │   └── reference/
│   │
│   └── curated/
│       ├── processed records/
│       ├── enriched records/
│       ├── aggregated datasets/
│       └── reference/
│
├── src/
│   └── data_factory/
│       ├── config.py
│       ├── exceptions.py
│       ├── http_client.py
│       ├── collector.py
│       ├── processor.py
│       ├── transformer.py
│       ├── population.py
│       ├── borough_population.py
│       ├── aggregation.py
│       ├── geographic_audit.py
│       └── manifest.py
│
├── scripts/
│   ├── collect_data.py
│   ├── audit_raw_data.py
│   ├── process_data.py
│   ├── transform_data.py
│   ├── enrich_population.py
│   ├── download_borough_population.py
│   ├── aggregate_data.py
│   ├── audit_geography.py
│   ├── create_run_manifest.py
│   └── run_pipeline.py
│
├── tests/
│
└── reports/
    └── pipeline/
```

## 4. Installation

Python 3.11 is recommended.

Clone the repository and navigate to the project directory.

Create a virtual environment:

**Windows PowerShell:**

```powershell
python -m venv datafactory-env
.\datafactory-env\Scripts\Activate.ps1
```

**Linux / Ubuntu:**

```bash
python3 -m venv datafactory-env
source datafactory-env/bin/activate
```

Install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install -r requirements.txt
```

## 5. Configuration

Project settings are stored in `config.json`.

Main configuration sections:

- `api`: Endpoint, HTTP method, timeout, retry policy, and batch size.
- `collection`: Date range and complaint scope.
- `paths`: Raw and curated data directories.
- `quality`: Data quality and quarantine thresholds.
- `population`: Census API and population reference configuration.

Sensitive credentials must be stored in `.env`, not directly in source code or configuration files.

Example:

```env
CENSUS_API_KEY=your_census_api_key
```

The `.env` file is excluded from Git.

## 6. Pipeline Execution

The complete pipeline can be executed using one command:

```powershell
python scripts/run_pipeline.py --run-dir "data/raw/nyc311_noise_residential_2024-01-01_2025-07-01_4287f9b2"
```

For an existing completed collection, skip downloading the raw dataset:

```powershell
python scripts/run_pipeline.py --run-dir "data/raw/nyc311_noise_residential_2024-01-01_2025-07-01_4287f9b2" --skip-collection
```

The pipeline executes the following stages:

1. Data Collection
2. Raw Data Audit
3. Data Processing and Validation
4. Data Transformation
5. ZIP Code Population Enrichment
6. Borough Population Download
7. Data Aggregation
8. Geographic Audit
9. Run Manifest Generation

The runner stops when a stage fails and records execution details in a JSON report.

## 7. Data Quality and Processing

The processing stage separates accepted records from quarantined records.

Observed results:

| Metric | Result |
|---|---:|
| Raw records | 596,592 |
| Accepted records | 596,547 |
| Quarantined records | 45 |
| Quarantine ratio | 0.00754% |
| Duplicate records | 0 |
| Missing ZIP records | 44 |

All 45 quarantined records were associated with `CLOSED_BEFORE_CREATED`.

The transformation stage produces 38 columns, including four derived temporal and duration fields.

## 8. Population Enrichment

The project uses the 2024 American Community Survey (ACS) 5-Year Estimates.

Population data is joined using:

`incident_zip = zcta`

Observed join results:

- Input records: 596,547
- Output records: 596,547
- Matched records: 596,483
- Missing ZIP records: 44
- Unmatched ZIP records: 20

A separate borough-level population reference is used for normalized borough comparisons.

## 9. Data Aggregation

The aggregation stage produces monthly complaint statistics for five NYC boroughs.

Analysis period: 18 months (January 2024 – June 2025).

Output:

- 596,547 input records
- 596,547 aggregated records
- 6 wide-format rows
- 76 output columns

Population-normalized complaint rate:

`Monthly complaint count / 2024 ACS borough population * 1000`

The rate is monthly and is not annualized.

The borough population denominator is counted once per borough, rather than summed from case-level ZIP population estimates.

## 10. Geographic Audit

Geographic consistency is evaluated using official NYC borough boundary polygons and Shapely point-in-polygon operations.

Observed results:

| Metric | Result |
|---|---:|
| Valid coordinate pairs | 595,511 |
| Missing coordinate pairs | 1,036 |
| Compared records | 595,499 |
| Matching records | 594,246 |
| Mismatching records | 1,253 |
| Match rate | 99.7896% |

The largest discrepancy category was:

`BRONX → MANHATTAN: 1,242 records`

Geographic discrepancies are reported separately. Original borough assignments are not automatically overwritten.

## 11. Reproducibility and Provenance

The project generates a `run_manifest.json` containing:

- Dataset and collection configuration
- Python and dependency versions
- Git branch and commit
- SHA-256 fingerprints of project artifacts
- Record counts across processing stages
- Geographic quality metrics

Record conservation is checked across the main pipeline stages.

The pipeline also supports checkpoint-based collection recovery and batch-level storage.

## 12. Automated Testing

Run the complete test suite:

```powershell
python -m unittest discover -s tests -v
```

Tests cover:

- Configuration validation
- HTTP client behavior and retry policies
- Data collection and checkpoint recovery
- Schema validation
- Data processing and quarantine
- Transformation
- Population enrichment
- Borough population reference
- Aggregation
- Geographic audit
- Run manifest generation

The current project test suite has passed.

## 13. Generated Outputs

Important outputs include:

| File | Description |
|---|---|
| `accepted.jsonl` | Validated records |
| `quarantine.jsonl` | Rejected records |
| `cases.csv` | Transformed dataset |
| `cases_enriched.csv` | Population-enriched dataset |
| `monthly_summary_wide.csv` | Monthly aggregated statistics |
| `geographic_mismatches.csv` | Geographic discrepancy records |
| `geographic_quality_report.json` | Geographic quality results |
| `aggregation_report.json` | Aggregation statistics |
| `run_manifest.json` | Reproducibility metadata |
| `pipeline_report.json` | Pipeline execution report |

## 14. Current Project Status

The end-to-end pipeline has been successfully executed on the collected NYC 311 dataset.

**Verified execution results:**

- 596,592 raw records collected
- 596,547 accepted records
- 120 raw batch files
- 18 months of aggregated data
- 99.7896% geographic match rate
- All automated tests passing
- Git working tree clean at the last committed release

---

**Project:** NYC 311 Data Factory  
**Language:** Python 3.11  
**Architecture:** Modular, reproducible data pipeline  
**Status:** End-to-end pipeline implemented and tested.
