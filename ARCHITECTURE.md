# Architecture Document

## Overview

The solution is a three-service Python system for automated PostgreSQL data classification.
Each service is independently deployable, stateless, and communicates over HTTP REST.

```
┌─────────────────────────────────────────────────────────┐
│  User / Test Script                                     │
└─────────────────────────┬───────────────────────────────┘
                          │ POST /analyze
                          ▼
┌─────────────────────────────────────────────────────────┐
│  Orchestrator Service  (port 5000)                      │
│  orchestrator_service.py                                │
│  – Fetches schema from Data Reader                      │
│  – Fans out classify calls across Data Classifiers      │
│  – Aggregates results → CSV + pretty-print              │
└──────────┬──────────────────────────────┬───────────────┘
           │ GET /schema/{schema}         │ POST /classify
           │                             ▼
           │              ┌──────────────────────────────┐
           │              │  Data Classifier  (port 5002) │
           │              │  data_classifier_service.py   │
           │              │  – Resolves config            │
           │              │  – Calls Data Reader          │
           │              │    for sample values          │
           │              │  – Runs LayerRouter           │
           │              └──────────┬───────────────────┘
           │                         │ GET /sample/...
           └────────────►────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  Data Reader Service  (port 5001)                       │
│  data_reader_service.py                                 │
│  – Reads information_schema.columns                     │
│  – Samples column values via SQL                        │
│  – Returns 200 with error field on DB failures          │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
                   PostgreSQL Database
```

---

## Services

### Data Reader  (`data_reader_service.py`, port 5001)

Owns all database access. No classification logic.

**Startup:**
```
python data_reader_service.py 5001 --config config/sample_healthcare.yaml
```

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness check |
| GET | `/schema/{schema}` | All columns in schema from `information_schema` |
| GET | `/sample/{schema}/{table}/{column}?limit=N` | Up to N sample values for a column |

Both read endpoints accept an optional `config_path` query parameter to select which
database config to use. The startup `--config` value is used when not present in the request.

**Sample-read error contract:**
When a database error occurs (e.g. column does not exist), the endpoint returns HTTP 200 with:
```json
{"samples": [], "error": "Failed to sample schema.table.column: <detail>"}
```
This allows callers to log the error and continue without aborting the full run.

**Internal modules:**
`DatabaseReader` (`database_reader.py`) – uses `psycopg2` with a per-request connection.
`ConfigLoader` (`config_loader.py`) – loads YAML and builds `DatabaseConfig`.

---

### Data Classifier  (`data_classifier_service.py`, port 5002)

Owns classification logic. No direct database access.

**Startup:**
```
python data_classifier_service.py 5002 --config config/sample_healthcare.yaml
```

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness check |
| POST | `/classify` | Classify a single column |

**Request body:**
```json
{
  "schema_name": "public",
  "table_name": "customers",
  "column_name": "email_address",
  "data_type": "character varying",
  "config_path": "config/sample_healthcare.yaml"
}
```

`config_path` is optional. The startup `--config` value is the fallback.

**Normal response:**
```json
{
  "schema_name": "public",
  "table_name": "customers",
  "column_name": "email_address",
  "data_type": "character varying",
  "status": "CLASSIFIED",
  "category": "EMAIL",
  "confidence": 0.92,
  "sensitive": true,
  "masking_method": "EMAIL_UNIQUE",
  "decided_by": "Layer 1 - Regex Rules",
  "notes": "Best match: ..., score=0.9200",
  "reasoning": "",
  "error": ""
}
```

**Sample-read error response:**
```json
{
  "status": "ERROR",
  "category": "UNKNOWN",
  "confidence": 0.0,
  "sensitive": false,
  "masking_method": "",
  "decided_by": "Data Reader - Sample Retrieval",
  "notes": "Column classification skipped due to sample retrieval error.",
  "error": "Failed to sample public.customers.email: column does not exist"
}
```

**Internal modules:**
`LayerRouter` (`layer_router.py`) – runs the classification pipeline.
`ConfigLoader` (`config_loader.py`) – per-request config resolution with in-process caching by path.

---

### Orchestrator  (`orchestrator_service.py`, port 5000)

Coordinates the end-to-end classification workflow. No direct database or classification logic.

**Startup:**
```
python orchestrator_service.py 5000 --config config/sample_healthcare.yaml
```

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness check |
| POST | `/analyze` | Full schema classification |

**Request body:**
```json
{
  "schema": "public",
  "output_file": "results.csv",
  "config_path": "config/sample_healthcare.yaml"
}
```

**Response:**
```json
{
  "total_columns": 9,
  "classified": 9,
  "output_file": "results.csv",
  "config_path": "config/sample_healthcare.yaml",
  "data_reader_url": "http://localhost:5001",
  "classifiers": ["http://localhost:5002"],
  "results_preview": "schema_name | table_name | ..."
}
```

**Workflow:**
1. Loads config to resolve `data_reader_url` and `classifiers`.
2. Calls `GET /schema/{schema}` on Data Reader.
3. Dispatches one `POST /classify` per column to a classifier, selected by hash-based distribution across the configured classifier list.
4. Uses `ThreadPoolExecutor(max_workers=4)` for concurrency.
5. Converts each classifier JSON response to a `ClassificationResult` object.
6. Writes CSV via `ResultsExporter` and returns a pretty-printed summary.

---

## Classification Pipeline  (`layer_router.py`)

`LayerRouter.classify()` processes one column through a sequential decision chain.
Each step either produces a final result or falls through to the next.

```
Column + Samples
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│ Filter 0 – Blacklist                                     │
│ Is table, column, or (table, column) pair blacklisted?   │
│ decided_by: "Filter 0 - Blacklist"                       │
│ → status: EXCLUDED                                       │
└──────────────────────────┬───────────────────────────────┘
                           │ not blacklisted
                           ▼
┌──────────────────────────────────────────────────────────┐
│ Layer 0 – Schema Rules                                   │
│ Matches table/column name against configured rules       │
│ (exact match or regex on table + column names)           │
│ Passes if confidence ≥ threshold                         │
│ decided_by: "Layer 0 - Schema Rules"                     │
│ → status: CLASSIFIED → _apply_masking()                  │
└──────────────────────────┬───────────────────────────────┘
                           │ no rule matched
                           ▼
┌──────────────────────────────────────────────────────────┐
│ Empty Check                                              │
│ Are all sampled values null or blank?                    │
│ decided_by: "Empty Check - No Sample Values"             │
│ → status: EMPTY_COLUMN                                   │
└──────────────────────────┬───────────────────────────────┘
                           │ samples available
                           ▼
┌──────────────────────────────────────────────────────────┐
│ Layer 1 – Regex Rules                                    │
│ Applies each configured regex to sample values           │
│ score = rule.confidence × (matching / total samples)     │
│ Best-scoring rule wins if score ≥ threshold              │
│ decided_by: "Layer 1 - Regex Rules"                      │
│ → status: CLASSIFIED → _apply_masking()                  │
└──────────────────────────┬───────────────────────────────┘
                           │ no rule above threshold
                           ▼
┌──────────────────────────────────────────────────────────┐
│ Layer 2 – LLM Fallback  (reserved)                       │
│ decided_by: "Layer 2 - LLM Fallback"                     │
│ → status: UNCLASSIFIED                                   │
└──────────────────────────────────────────────────────────┘
```

### Masking Enforcement (`_apply_masking`)

All `CLASSIFIED` results pass through this method regardless of which layer decided them.

- `sensitive` is set to `True`.
- `masking_method` is set from the `security_masking` config map (category → strategy).
- If the category has no configured masking method:
  - `masking_method` is set to `REVIEW_REQUIRED`.
  - A `WARNING` is logged identifying the column and category.

### Classification Statuses

| Status | Meaning |
|--------|---------|
| `CLASSIFIED` | Category identified; sensitive=True, masking_method set |
| `EXCLUDED` | Column is blacklisted; skipped |
| `EMPTY_COLUMN` | No non-null, non-blank sample values found |
| `UNCLASSIFIED` | No layer reached the confidence threshold |
| `ERROR` | Data Reader failed to retrieve samples for this column |

### `decided_by` Values

| Value | Source |
|-------|--------|
| `Filter 0 - Blacklist` | Matched blacklist rule |
| `Layer 0 - Schema Rules` | Matched schema/name rule |
| `Empty Check - No Sample Values` | All samples null or blank |
| `Layer 1 - Regex Rules` | Matched regex pattern on values |
| `Layer 2 - LLM Fallback` | Fell through all layers (LLM not yet integrated) |
| `Data Reader - Sample Retrieval` | Sample fetch failed; classification skipped |

---

## Configuration  (`config_loader.py`)

Each service loads a YAML file at startup. Config path can also be overridden per request.

**Config structure:**

```yaml
domain: healthcare          # Used in LLM prompt context
confidence_threshold: 0.8   # Minimum score for a rule to decide
sample_size: 20             # Rows fetched per column

services:
  data_reader_url: http://localhost:5001
  classifiers:
    - http://localhost:5002  # One or more classifier instances

database:
  host: ...
  port: 5432
  dbname: ...
  user: ...
  # password via PGPASSWORD env var
  sslmode: prefer

blacklist:
  tables: [...]             # Entire tables excluded
  columns: [...]            # Column names excluded globally
  table_columns:            # Specific (table, column) pairs excluded
    - table: ...
      column: ...

layer_0_rules:
  - table_name: customers   # Exact name match
    column_name: first_name
    category: NAME
    confidence: 0.98
  - table_regex: ".*billing.*"   # Regex match
    column_regex: ".*email.*"
    category: EMAIL
    confidence: 0.90

layer_1_rules:
  - category: EMAIL
    regex: "^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$"
    confidence: 0.92

layer_2_rules:              # LLM configuration (not yet active)
  provider: ollama
  model: phi4-mini
  url: http://...
  valid_labels: [NAME, EMAIL, PHONE, ...]

security_masking:
  EMAIL: EMAIL_UNIQUE
  NAME: FULL_NAME_ALGORITHM
  SSN: HASH
  ...
```

**Precedence for database credentials:**
YAML value → environment variable (PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD, PGSSLMODE) → default.

---

## Data Models  (`models.py`)

### `ColumnMetadata`
Returned by Data Reader schema endpoint. Fields: `schema_name`, `table_name`, `column_name`, `data_type`.

### `ClassificationResult`
Produced by the Classifier and aggregated by the Orchestrator.

| Field | Type | Description |
|-------|------|-------------|
| `schema_name` | str | Schema of the column |
| `table_name` | str | Table of the column |
| `column_name` | str | Column name |
| `data_type` | str | PostgreSQL data type |
| `status` | str | CLASSIFIED / EXCLUDED / EMPTY_COLUMN / UNCLASSIFIED / ERROR |
| `category` | str | Sensitivity category (NAME, EMAIL, SSN, …) |
| `confidence` | float | 0.0–1.0 confidence score |
| `sensitive` | bool | True for all CLASSIFIED results |
| `masking_method` | str | Masking strategy from config; REVIEW_REQUIRED if none configured |
| `decided_by` | str | Human-readable label for the deciding layer |
| `notes` | str | Rule details or diagnostic message |
| `reasoning` | str | LLM reasoning text (empty until Layer 2 active) |
| `error` | str | Error message for ERROR status rows |

---

## Output  (`results_exporter.py`)

**CSV:** All 13 fields including `reasoning` and `error`. Written to the path specified in `/analyze`.

**Pretty-print:** Console-friendly ASCII table with 9 display columns, omitting `reasoning` and `error`:
`schema_name`, `table_name`, `column_name`, `status`, `category`, `confidence`, `sensitive`, `masking_method`, `decided_by`.

---

## Logging Architecture

All three services use a shared logger bootstrap in `logging_setup.py`.

### Goals

- Structured logs for machine parsing and centralized ingestion
- Consistent fields across services
- Minimal startup friction in local environments

### Runtime Behavior

1. `create_json_logger(service_name)` ensures the local wheel path is available if needed.
2. It tries `ConfigAndLogUtilities` first for logger creation (`log_mode=console`, `format_type=json`).
3. If that import path is unavailable due to optional dependencies, it falls back to `log_manager.LogConfig`.
4. Both paths emit JSON logs to stdout via `StreamHandler`.
5. `start-services.ps1` redirects stdout/stderr to:
  - `logs/data_reader.log`
  - `logs/data_classifier.log`
  - `logs/orchestrator.log`

### JSON Fields

Configured output includes:

- `timestamp`
- `levelname`
- `name`
- `module`
- `lineno`
- `message`
- `traceback`

This keeps existing log statements unchanged while standardizing output format.

---

## Scalability

The `services` config section controls how the Orchestrator routes work.

**Multiple classifiers (same machine):**
```yaml
services:
  data_reader_url: http://localhost:5001
  classifiers:
    - http://localhost:5002
    - http://localhost:5021
    - http://localhost:5022
```
The Orchestrator distributes columns across the list using hash-based selection
(`hash((table_name, column_name)) % len(classifiers)`), ensuring each column always
routes to the same instance. Each classifier calls the Data Reader independently.

**Distributed deployment:**
```yaml
services:
  data_reader_url: http://<reader-host>:5001
  classifiers:
    - http://<classifier-a>:5002
    - http://<classifier-b>:5002
```

For production, put classifiers behind a load balancer and point `classifiers` at the proxy.

---

## Limitations and Future Work

| Area | Current State | Next Step |
|------|--------------|-----------|
| Layer 2 – LLM | Stub; returns UNCLASSIFIED | Integrate Ollama/OpenAI via `layer_2_rules` config |
| Service discovery | Static URLs in YAML | Add Consul or environment-variable-driven registry |
| Request tracing | No correlation IDs | Add trace ID propagated from Orchestrator through all calls |
| Connection pooling | One connection per DB request | Switch to `psycopg2.pool.ThreadedConnectionPool` |
| Config hot-reload | Restart required | Add file-watch and cache invalidation |
| Log aggregation | Per-service log files | Centralise with ELK or similar |
