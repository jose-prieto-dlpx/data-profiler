# Automated Data Classification and Masking Pipeline

A robust, modular Python system for analyzing PostgreSQL database schemas, classifying columns by data sensitivity using multi-layer heuristics and LLM fallback, and generating actionable masking recommendations.

## Features

- **4-Layer Routing-by-Confidence Architecture**: Progressive classification from fast schema rules → local regex patterns → LLM intelligence with graceful fallback
- **Blacklist Filter**: Skip explicitly excluded tables/columns immediately
- **Empty Column Detection**: Identify and skip columns with 100% NULL/empty values before expensive processing
- **PostgreSQL Integration**: Safe schema introspection with connection pooling and exception resilience
- **LLM Abstraction**: Provider-agnostic layer supporting OpenAI, Ollama, or local-only mode
- **YAML Domain Configuration**: Centralized, domain-specific rules (healthcare, finance, etc.) with default fallbacks
- **Security Masking Mapping**: Link classified categories to concrete masking strategies (HASH, REDACT, PSEUDONYMIZE, etc.)
- **CSV Export**: Tabular output with confidence scores, decided-by layer attribution, and error tracking
- **Debug Logging**: Comprehensive structured logging across all layers

## Architecture

### Module Breakdown

| Module | Purpose |
|--------|---------|
| `models.py` | Typed dataclasses for metadata, decisions, and pipeline results |
| `database_generic.py` | Abstract database interface (connect, schema introspection, sampling) |
| `database_postgres.py` | PostgreSQL concrete implementation with pooling and safe SQL composition |
| `config_manager.py` | YAML parsing, validation, and rule matching for all layers |
| `local_classifier.py` | Layer 1: regex-based pattern matching for fast local classification |
| `llm_clients.py` | Layer 2: LLM provider abstraction (OpenAI, Ollama, NoOp) with JSON parsing |
| `classification_pipeline.py` | Core orchestrator: filter 0 → layers 0–3 with confidence routing |
| `export_manager.py` | CSV formatter and writer |
| `main.py` | CLI entrypoint with DSN/env fallback and lifecycle management |

### Processing Flow (Per Column)

```
Column Input
    ↓
[Filter 0: Blacklist Check]
    ↓ (if excluded → EXCLUDED)
    ↓ (if not excluded → continue)
[Layer 0: Metadata/Schema Match]
    ↓ (confidence ≥ threshold → CLASSIFIED + Layer 3)
    ↓ (else → continue)
[Empty Column Check]
    ↓ (100% NULL/empty → EMPTY_COLUMN)
    ↓ (else → continue)
[Layer 1: Local Regex Classifier]
    ↓ (confidence ≥ threshold → CLASSIFIED + Layer 3)
    ↓ (else → continue)
[Layer 2: LLM Fallback]
    ↓ (returns category + confidence, validated against closed label set)
[Layer 3: Security Masking Lookup]
    ↓
CSV Row Output
```

## Installation

### Prerequisites

- Python 3.10 or higher
- PostgreSQL 12+ (with network access)

### Setup

1. **Clone/download the project** and navigate to the directory:
   ```bash
   cd Profiler-demo
   ```

2. **Create a virtual environment** (optional but recommended):
   ```bash
   D:/Python/Python3104/python.exe -m venv venv
   venv/Scripts/activate  # On Windows
   # or: source venv/bin/activate  # On macOS/Linux
   ```

3. **Install dependencies**:
   ```bash
   D:/Python/Python3104/python.exe -m pip install -r requirements.txt
   ```

## Configuration

### YAML Schema

Create or edit a YAML config file (e.g., `config/sample_healthcare.yaml`):

```yaml
domain: healthcare                          # Domain identifier for LLM prompts
confidence_threshold: 0.8                   # Minimum confidence to stop early
sample_size: 20                             # Rows sampled per column for analysis

blacklist:
  tables:                                   # Skip entire tables
    - migration_audit
  columns:                                  # Skip columns by name
    - created_at
    - updated_at
  table_columns:                            # Skip specific table-column pairs
    - table: users
      column: password_hash

layer_0_rules:                              # Schema/metadata exact/regex matches
  - table_name: patients
    column_name: first_name
    category: NAME
    confidence: 0.98
  - table_regex: ".*patient.*"              # Regex pattern on table name
    column_regex: ".*ssn.*"                 # Regex pattern on column name
    category: SSN
    confidence: 0.95

layer_1_rules:                              # Local regex patterns on sample values
  - category: EMAIL
    regex: "^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$"
    confidence: 0.92
  - category: SSN
    regex: "^\\d{3}-\\d{2}-\\d{4}$"
    confidence: 0.97

layer_2_rules:                              # LLM configuration
  provider: none                            # "none", "openai", or "ollama"
  model: ""                                 # e.g., "gpt-4-turbo" or "llama2"
  temperature: 0.0                          # LLM temperature
  timeout_seconds: 30
  max_tokens: 256
  system_prompt_template: |
    You are a strict data-classification model for the {domain} domain.
    Classify using only: {valid_labels}
    Return JSON: {"category": "<LABEL>", "confidence": <0_to_1>}
  valid_labels:                             # Closed set of allowed labels
    - NAME
    - EMAIL
    - PHONE
    - SSN
    - DATE_OF_BIRTH
    - UNKNOWN

security_masking:                           # Category → masking strategy
  NAME: PSEUDONYMIZE
  EMAIL: PARTIAL_MASK
  SSN: HASH
  DATE_OF_BIRTH: REDACT
```

## Usage

### Basic Invocation

```bash
D:/Python/Python3104/python.exe main.py \
  --config config/sample_healthcare.yaml \
  --schema public \
  --host localhost \
  --port 5432 \
  --dbname mydb \
  --user myuser \
  --password mypassword \
  --output classification_output.csv
```

### Using DSN String

```bash
D:/Python/Python3104/python.exe main.py \
  --config config/sample_healthcare.yaml \
  --schema public \
  --dsn "host=localhost port=5432 dbname=mydb user=myuser password=mypassword sslmode=prefer" \
  --output classification_output.csv
```

### With Environment Variables

```bash
export PGHOST=localhost
export PGPORT=5432
export PGDATABASE=mydb
export PGUSER=myuser
export PGPASSWORD=mypassword

D:/Python/Python3104/python.exe main.py \
  --config config/sample_healthcare.yaml \
  --schema public \
  --output classification_output.csv
```

### Debug Mode

```bash
D:/Python/Python3104/python.exe main.py \
  --config config/sample_healthcare.yaml \
  --schema public \
  --host localhost \
  --dbname mydb \
  --user myuser \
  --password mypassword \
  --output classification_output.csv \
  --debug
```

Debug mode enables INFO-level logging with timestamps, logger names, and detailed layer-by-layer traces.

## Output Format

The CSV contains one row per discovered column:

| Column | Description |
|--------|-------------|
| `schema_name` | Schema (e.g., "public") |
| `table_name` | Table name |
| `column_name` | Column name |
| `data_type` | PostgreSQL data type (e.g., "varchar", "integer") |
| `status` | One of: CLASSIFIED, UNCLASSIFIED, EXCLUDED, EMPTY_COLUMN, ERROR |
| `category` | Assigned category (e.g., "NAME", "EMAIL", "UNKNOWN") |
| `confidence` | Float in [0.0, 1.0], to 4 decimal places |
| `sensitive` | "TRUE" or "FALSE" |
| `masking_method` | Masking strategy (e.g., "HASH", "REDACT") or empty if not sensitive |
| `decided_by` | Layer that made the decision: filter_0, layer_0, empty_check, layer_1, layer_2, or pipeline |
| `notes` | Human-readable rationale or error details |
| `error` | Exception message if status=ERROR, else empty |

### Example Output

```csv
schema_name,table_name,column_name,data_type,status,category,confidence,sensitive,masking_method,decided_by,notes,error
public,patients,id,integer,CLASSIFIED,UNKNOWN,0.0000,FALSE,,layer_1,Best regex rule matched with score=0.0000.,
public,patients,first_name,varchar,CLASSIFIED,NAME,0.9800,TRUE,PSEUDONYMIZE,layer_0,Matched schema metadata rule.,
public,patients,email,varchar,CLASSIFIED,EMAIL,0.9200,TRUE,PARTIAL_MASK,layer_1,Best regex rule '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]' score=0.9200.,
public,patients,created_at,timestamp,EXCLUDED,EXCLUDED,1.0000,FALSE,,filter_0,Column matched blacklist rules.,
public,patients,last_modified,timestamp,EMPTY_COLUMN,EMPTY_COLUMN,1.0000,FALSE,,empty_check,Sample values are 100% empty or NULL.,
```

## Error Handling

- **Database Connectivity Failures**: Logged and reported; pipeline continues if schema introspection succeeds for at least one column.
- **Blacklist/Rule Parsing Errors**: Configuration errors are caught early; if a rule is malformed, it is skipped with a warning.
- **LLM Timeout/API Errors**: Layer 2 failures degrade gracefully; the pipeline retains the best Layer 1 classification (if any).
- **Invalid JSON from LLM**: Unparseable responses are caught; JSON extraction via regex fallback is attempted.
- **Per-Column Exceptions**: Any unhandled error during a column's processing is caught, logged, and marked as ERROR in the output row; the pipeline continues.

## Logging

All modules emit structured logs to `stdout` with timestamps:

```
2026-06-16 12:34:56,789 | DEBUG | classification_pipeline | Processing column: public.patients.first_name
2026-06-16 12:34:57,123 | INFO | main | Discovered 42 columns in schema 'public'.
2026-06-16 12:34:58,456 | INFO | main | Classification finished. CSV written to 'classification_output.csv'.
```

Enable debug logging with the `--debug` flag to see layer-by-layer decisions and LLM payloads.

## Advanced Configuration

### Using OpenAI

1. Set the `OPENAI_API_KEY` environment variable:
   ```bash
   export OPENAI_API_KEY=sk-...
   ```

2. Update your YAML config:
   ```yaml
   layer_2_rules:
     provider: openai
     model: gpt-4-turbo
     temperature: 0.0
     timeout_seconds: 30
     max_tokens: 256
   ```

3. Run the pipeline as normal.

### Using Ollama

1. Start a local Ollama service (e.g., on `http://localhost:11434`):
   ```bash
   ollama pull llama2
   ollama serve
   ```

2. Update your YAML config:
   ```yaml
   layer_2_rules:
     provider: ollama
     model: llama2
     temperature: 0.0
     timeout_seconds: 60
   ```

3. Run the pipeline.

### Custom Domain Config

Create a new YAML file for your domain (e.g., `config/sample_finance.yaml`) with domain-specific rules:

```yaml
domain: finance
layer_0_rules:
  - table_name: accounts
    column_name: account_number
    category: ACCOUNT_NUMBER
    confidence: 0.99
  - table_name: transactions
    column_regex: ".*amount.*"
    category: FINANCIAL_AMOUNT
    confidence: 0.85

security_masking:
  ACCOUNT_NUMBER: HASH
  FINANCIAL_AMOUNT: REDACT
```

## Testing

### Quick Sanity Check

```bash
D:/Python/Python3104/python.exe -m compileall .
```

This compiles all modules to check for syntax errors.

### Unit Testing (Optional)

Create a `test_*.py` file to verify individual components:

```python
from config_manager import ConfigManager
from models import ColumnMetadata

# Test config loading
cfg = ConfigManager.load_from_file("config/sample_healthcare.yaml")
assert cfg.config.domain == "healthcare"

# Test blacklist matching
assert cfg.is_blacklisted("migration_audit", "any_column") == True
assert cfg.is_blacklisted("users", "password_hash") == True
assert cfg.is_blacklisted("users", "name") == False

print("All tests passed!")
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ImportError: No module named 'psycopg2'` | Run `pip install psycopg2-binary` |
| `ImportError: No module named 'yaml'` | Run `pip install pyyaml` |
| `psycopg2.OperationalError: could not connect to server` | Verify PostgreSQL is running and DSN/credentials are correct |
| `FileNotFoundError: Configuration file not found` | Ensure `--config` path is absolute or relative to the current working directory |
| `OpenAI API error` | Verify `OPENAI_API_KEY` is set and has billing enabled |
| `Ollama connection refused` | Ensure Ollama is running (`ollama serve`) on `localhost:11434` |
| CSV output is empty | Check `--schema` argument matches the target schema name (e.g., "public") |

## Dependencies

- **pyyaml** ≥ 6.0 – YAML parsing
- **psycopg2-binary** ≥ 2.9 – PostgreSQL adapter
- **openai** ≥ 1.0 – OpenAI API client (optional, only if using provider=openai)

Optional:
- **spacy** – For advanced NLP (future Layer 1 enhancement)

## Performance Notes

- **Schema Introspection**: O(n) where n = number of columns in schema. Typically < 1s for schemas with < 1000 columns.
- **Sampling**: 20 rows per column by default; configurable via `sample_size` in YAML.
- **Layer 1 (Regex)**: Very fast; O(sample_size × number_of_rules).
- **Layer 2 (LLM)**: Dependent on LLM latency; typically 1–5s per column. Skipped if Layer 1 meets confidence threshold.
- **Typical End-to-End**: 50–100 columns = 30–120 seconds (without LLM) or 5–15 minutes (with LLM).

## Contributing

To extend the pipeline:

1. Add new LLM providers by subclassing `LLMClient` in `llm_clients.py`.
2. Add new Layer 1 classifiers in `local_classifier.py` (e.g., spaCy NER).
3. Extend the YAML schema in `config_manager.py` for domain-specific rules.
4. Add new masking strategies to the `security_masking` section in your YAML.

## License

MIT or your preferred license. Update as needed.

## Contact

For questions or issues, open a GitHub issue or contact the project maintainers.

---

**Built with Python 3.10+, PostgreSQL, and modular architecture for production-ready data governance.**
