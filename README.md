# Distributed Data Classification Pipeline

A scalable, three-service architecture for automated PostgreSQL data classification.

## Architecture

Three independent, horizontally scalable REST services:

### 1. Data Reader Service (port 5001)

- Reads database schema metadata and sample values
- Uses `--config` at startup and optional `config_path` query parameter per request
- Endpoints:
  - `GET /health` – Service health check
  - `GET /schema/{schema_name}` – Returns all columns in schema
  - `GET /sample/{schema}/{table}/{column}?limit=20` – Returns sample values

### 2. Data Classifier Service (port 5002)

- Performs 4-layer classification pipeline
- Calls Data Reader to fetch samples
- Uses `--config` at startup and optional `config_path` in the request body
- Endpoints:
  - `GET /health` – Service health check
  - `POST /classify` – Classifies a single column (JSON payload)

### 3. Orchestrator Service (port 5000)

- Top-level API for end-to-end analysis
- Coordinates readers and classifiers in parallel
- Exports results to CSV and pretty-printed table
- Uses `--config` at startup and optional `config_path` in the request body
- Endpoints:
  - `GET /health` – Service health check
  - `POST /analyze` – Triggers full analysis on a schema

## Modules

| Module | Purpose |
| ------ | ------- |
| `models.py` | DTOs for API communication (ColumnMetadata, ClassificationResult) |
| `config_loader.py` | YAML config parsing with defaults and fallbacks |
| `database_reader.py` | PostgreSQL metadata and sample fetcher |
| `layer_router.py` | 4-layer classification logic (filter, layer 0-1) |
| `data_reader_service.py` | REST service for schema/sample access |
| `data_classifier_service.py` | REST service for classification |
| `orchestrator_service.py` | Top-level REST API coordinating workflow |
| `results_exporter.py` | CSV and pretty-table formatters |

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

Edit `config/sample_healthcare.yaml` (or create new domain-specific config):

```yaml
domain: healthcare
confidence_threshold: 0.8
sample_size: 20

services:
  data_reader_url: http://localhost:5001
  classifiers:
    - http://localhost:5002

database:
  host: fx-pg16.dlpxdc.co
  port: 5432
  dbname: healthcare
  user: postgres
  # password: ""  # use PGPASSWORD env var for security
  sslmode: prefer

# ... rest of classification rules (layer_0, layer_1, layer_2, etc.)
```

## Running the Services

### Option 1: Manual (3 terminal windows)

**Terminal 1 – Data Reader:**

```bash
python data_reader_service.py 5001 --config config/sample_healthcare.yaml
```

**Terminal 2 – Data Classifier:**

```bash
python data_classifier_service.py 5002 --config config/sample_healthcare.yaml
```

**Terminal 3 – Orchestrator:**

```bash
python orchestrator_service.py 5000 --config config/sample_healthcare.yaml
```

### Option 2: Startup Script

Windows (PowerShell):

```powershell
.\start-services.ps1
```

Linux/Mac:

```bash
./start-services.sh
```

## Usage

### Trigger Analysis

```bash
curl -X POST http://localhost:5000/analyze \
  -H "Content-Type: application/json" \
  -d '{"schema": "public", "output_file": "results.csv", "config_path": "config/sample_healthcare.yaml"}'
```

### Response

```json
{
  "total_columns": 42,
  "classified": 42,
  "output_file": "results.csv",
  "config_path": "config/sample_healthcare.yaml",
  "data_reader_url": "http://localhost:5001",
  "classifiers": ["http://localhost:5002"],
  "results_preview": "schema_name | table_name | column_name | status | category | ..."
}
```

## Scalability

To handle large databases:

1. **Multiple Data Readers**: Start additional reader instances on different ports

   ```bash
   python data_reader_service.py 5011
   python data_reader_service.py 5012
   ```

2. **Multiple Classifiers**: Start additional classifier instances

   ```bash
   python data_classifier_service.py 5021
   python data_classifier_service.py 5022
   ```

3. **Update the YAML config**: Add classifier URLs to load-balance

   ```yaml
   services:
     data_reader_url: http://localhost:5001
     classifiers:
       - http://localhost:5002
       - http://localhost:5021
       - http://localhost:5022
   ```

## API Contract

### Data Reader

- **GET /schema/{schema}** → `{"columns": [{"schema_name", "table_name", "column_name", "data_type"}]}`
- **GET /sample/{schema}/{table}/{column}** → `{"samples": [value1, value2, null, ...]}`
- **GET /sample/{schema}/{table}/{column}** (sample read error) → `{"samples": [], "error": "Failed to sample schema.table.column: ..."}`
- Optional query parameter on both endpoints: `config_path=config/sample_healthcare.yaml`

### Data Classifier

- **POST /classify** ← `{"schema_name", "table_name", "column_name", "data_type", "config_path"}`
- **POST /classify** → `{"schema_name", "table_name", "column_name", ..., "category", "confidence", "sensitive", "masking_method", ...}`
- **POST /classify** (reader sample error) → `{"schema_name", "table_name", "column_name", "status": "ERROR", "category": "UNKNOWN", "confidence": 0.0, "decided_by": "Data Reader - Sample Retrieval", "error": "..."}`

### Orchestrator

- **POST /analyze** ← `{"schema": "public", "output_file": "results.csv", "config_path"}`
- **POST /analyze** → `{"total_columns": N, "classified": N, "output_file": "...", "config_path": "...", "data_reader_url": "...", "classifiers": [...], "results_preview": "..."}`

## Environment Variables

```bash
export PGHOST=localhost
export PGPORT=5432
export PGDATABASE=healthcare
export PGUSER=postgres
export PGPASSWORD=your_password
export PGSSLMODE=prefer
```

All are optional; YAML config takes precedence.

## Output

CSV file with columns:

- `schema_name`, `table_name`, `column_name`, `data_type`
- `status`, `category`, `confidence`
- `sensitive`, `masking_method`
- `decided_by`, `notes`, `reasoning`, `error`

Console output shows a pretty-printed summary (without `reasoning` and `error` fields).

## Logging

- Services now emit **JSON-formatted logs** through `delphix_ps_utilities`.
- Logger bootstrap lives in `logging_setup.py` and is shared by all services.
- Preferred path uses `ConfigAndLogUtilities.create_logger(...)` with `log_mode=console` and `format_type=json`.
- If `ConfigAndLogUtilities` cannot load due to optional package dependencies, startup automatically falls back to `log_manager.LogConfig` (still JSON).
- If `delphix_ps_utilities` is not globally installed, `logging_setup.py` loads the local wheel from `packages/delphix_ps_utilities-3-py3-none-any.whl`.
- `start-services.ps1` redirects stdout/stderr to files under `logs/`, so each line in those files is a JSON log record.

---

**Architecture principles:**

- **Separation of concerns**: Each service has one responsibility
- **Stateless**: Services can be replicated and load-balanced
- **JSON API**: Simple HTTP REST for inter-service communication
- **Minimal dependencies**: Flask, psycopg2, PyYAML only
