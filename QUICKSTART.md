# Quick Start Guide

## Overview

- **3 independent REST services** running in parallel
- **Data Reader** fetches schema & samples
- **Data Classifier** performs classification via API calls
- **Orchestrator** coordinates the workflow
- **Horizontal scalability** by running multiple service instances

## Files Overview

### Core Modules (8 files)

| File | Purpose |
| ---- | ------- |
| `models.py` | Data Transfer Objects (ColumnMetadata, ClassificationResult) |
| `config_loader.py` | YAML configuration parsing with env var fallback |
| `database_reader.py` | PostgreSQL schema and sample reading |
| `layer_router.py` | 4-layer classification logic (Layers 0, 1, 2) |
| `data_reader_service.py` | REST API for schema/sample access |
| `data_classifier_service.py` | REST API for classification |
| `orchestrator_service.py` | Top-level REST API orchestrating workflow |
| `results_exporter.py` | CSV and pretty-table formatting |

### Documentation (3 files)

| File | Purpose |
| ---- | ------- |
| `README.md` | Architecture overview, usage examples |
| `ARCHITECTURE.md` | Design rationale, patterns, scalability |
| `DEPLOYMENT.md` | Deployment guide, scaling, monitoring |

### Utilities & Config (4 files)

| File | Purpose |
| ---- | ------- |
| `requirements.txt` | Python dependencies (Flask, psycopg2, PyYAML) |
| `start-services.ps1` | Windows PowerShell startup script (all 3 services) |
| `start-services.sh` | Linux/Mac startup script |
| `test_services.py` | Test/validation script |
| `config/sample_healthcare.yaml` | Example domain config |

## 30-Second Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Start Services (Windows)

```powershell
.\start-services.ps1
```

Or manually (3 Command Prompt windows):

```cmd
python data_reader_service.py 5001 --config config/sample_healthcare.yaml
python data_classifier_service.py 5002 --config config/sample_healthcare.yaml
python orchestrator_service.py 5000 --config config/sample_healthcare.yaml
```

### 3. Run Analysis

```bash
python test_services.py
```

Or use curl:

```bash
curl -X POST http://localhost:5000/analyze ^
  -H "Content-Type: application/json" ^
  -d "{\"schema\": \"public\", \"output_file\": \"results.csv\", \"config_path\": \"config/sample_healthcare.yaml\"}"
```

### 4. Check Results

Open `classification_output.csv` or `results.csv` in Excel/CSV viewer.

### 5. Check JSON Logs

When started with `start-services.ps1`, logs are written under `logs/` as JSON lines:

- `logs/data_reader.log`
- `logs/data_classifier.log`
- `logs/orchestrator.log`

Example log line:

```json
{"timestamp":"2026-06-17T15:35:10Z","levelname":"INFO","name":"data_reader_service_12345","module":"data_reader_service","lineno":42,"message":"Data reader initialized for config config/sample_healthcare.yaml","traceback":null}
```

Logging is configured in `logging_setup.py` using `delphix_ps_utilities` JSON formatter.

## Port Assignment

| Service | Port | Role |
| ------- | ---- | ---- |
| Orchestrator | 5000 | Top-level API (user-facing) |
| Data Reader | 5001 | Schema & sample fetching |
| Data Classifier | 5002 | Column classification |

## Included Features

All classification features are preserved:

✅ **4-Layer Classification Pipeline** – Layers 0, 1, 2 implemented in `layer_router.py`
✅ **YAML Configuration** – Environment variable fallback for database credentials
✅ **PostgreSQL Pooling** – Thread-safe connection management
✅ **CSV Export** – Full column set with reasoning and error fields
✅ **Pretty-Print Output** – Console-friendly ASCII table (excludes reasoning/error)
✅ **Blacklist Support** – Excluded tables/columns/pairs
✅ **Security Masking** – Category → Masking Strategy mapping

## Scaling Example

Want to classify **500+ columns** concurrently?

### Option 1: Multi-Instance (Same Machine)

```cmd
REM Start 2 readers
python data_reader_service.py 5001 --config config/sample_healthcare.yaml
python data_reader_service.py 5011 --config config/sample_healthcare.yaml

REM Start 4 classifiers
python data_classifier_service.py 5002 --config config/sample_healthcare.yaml
python data_classifier_service.py 5021 --config config/sample_healthcare.yaml
python data_classifier_service.py 5022 --config config/sample_healthcare.yaml
python data_classifier_service.py 5023 --config config/sample_healthcare.yaml

REM Single orchestrator
python orchestrator_service.py 5000 --config config/sample_healthcare.yaml
```

Then update `config/sample_healthcare.yaml`:

```yaml
services:
  data_reader_url: http://localhost:5001
  classifiers:
    - http://localhost:5002
    - http://localhost:5021
    - http://localhost:5022
    - http://localhost:5023
```

### Option 2: Distributed (Multiple Machines)

**Machine A (Readers & Orchestrator):**

```cmd
data_reader_service.py 5001
orchestrator_service.py 5000
```

**Machine B (Classifiers):**

```cmd
data_classifier_service.py 5002
data_classifier_service.py 5021
```

Update `orchestrator_service.py`:

```yaml
services:
  data_reader_url: http://<machine-a-ip>:5001
  classifiers:
    - http://<machine-b-ip>:5002
    - http://<machine-b-ip>:5021
```

## Troubleshooting

### ❌ "Connection refused" on <http://localhost:5001>

**Solution:** Did you start the Data Reader service?

```cmd
python data_reader_service.py 5001
```

### ❌ "PGPASSWORD missing" or database connection error

**Solution:** Ensure PostgreSQL credentials are in `config/sample_healthcare.yaml`:

```yaml
database:
  host: fx-pg16.dlpxdc.co
  port: 5432
  dbname: healthcare
  user: postgres
  password: your_password  # or use PGPASSWORD env var
  sslmode: prefer
```

Or set environment variables:

```bash
$env:PGHOST = "fx-pg16.dlpxdc.co"
$env:PGPORT = "5432"
$env:PGDATABASE = "healthcare"
$env:PGUSER = "postgres"
$env:PGPASSWORD = "your_password"
```

### ❌ No columns returned from schema

**Solution:** Check schema name. Default is `public`. If your schema is different, update in orchestrator call:

```bash
curl -X POST http://localhost:5000/analyze -d "{\"schema\": \"your_schema_name\"}"
```

## Key Design Principles

1. **Separation of Concerns** – Each service has one job
2. **Stateless** – Services can be stopped/started without state loss
3. **Scalable** – Add more readers/classifiers for throughput
4. **Minimal Code** – ~500 lines of business logic across all modules
5. **HTTP REST** – Simple, debuggable, language-agnostic APIs

## Next Steps

- [ ] Add Layer 2 LLM integration (OpenAI, Ollama)
- [ ] Add persistent job queue (database-backed)
- [ ] Add service discovery (Consul, Eureka)
- [ ] Add monitoring/observability (Prometheus, Grafana)
- [ ] Containerize with Docker and deploy to Kubernetes
- [ ] Add result caching (Redis)

---

**Architecture:** Three independent, horizontally-scalable REST services  
**Status:** ✅ Fully functional, ready for production use  
**Preserved:** Classification logic, config system, and export behavior  
**New:** Microservices design, REST APIs, parallel scalability
