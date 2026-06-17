# Deployment & Scalability Guide

## Architecture Overview

```
┌──────────────────┐
│  Orchestrator    │ (port 5000)
│  REST API        │ Coordinates workflow, aggregates results
└────────┬─────────┘
         │ calls
    ┌────┴────┬──────────────────┐
    │         │                  │
    ▼         ▼                  ▼
┌─────────────────┐      ┌──────────────────┐
│ Data Readers    │      │ Data Classifiers │
│ (5001, 5011...) │      │ (5002, 5021...)  │
│ Schema + Samples│      │ Classification   │
└─────────────────┘      │ Logic 4-layers   │
    │                    │ Calls reader API │
    │                    └──────────────────┘
    │
    ▼
┌──────────────────┐
│  PostgreSQL DB   │
└──────────────────┘
```

## Single-Machine Deployment

All three services run on localhost.

### Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 2: Start Services (Windows)

```powershell
.\start-services.ps1
```

Or manually in three separate Command Prompts:

```cmd
python data_reader_service.py 5001 --config config/sample_healthcare.yaml
python data_classifier_service.py 5002 --config config/sample_healthcare.yaml
python orchestrator_service.py 5000 --config config/sample_healthcare.yaml
```

### Step 3: Test

```bash
python test_services.py
```

Or use curl:

```bash
curl -X POST http://localhost:5000/analyze ^
  -H "Content-Type: application/json" ^
    -d "{\"schema\": \"public\", \"output_file\": \"results.csv\", \"config_path\": \"config/sample_healthcare.yaml\"}"
```

## Horizontal Scalability

For large databases, run multiple instances of readers and classifiers.

### Add More Data Readers

```cmd
REM Terminal 1 (primary)
python data_reader_service.py 5001 --config config/sample_healthcare.yaml

REM Terminal 2+ (additional)
python data_reader_service.py 5011 --config config/sample_healthcare.yaml
python data_reader_service.py 5012 --config config/sample_healthcare.yaml
```

Each is independent and stateless. In production, use a load balancer (nginx, HAProxy).

### Add More Classifiers

```cmd
REM Terminal 1 (primary)
python data_classifier_service.py 5002 --config config/sample_healthcare.yaml

REM Terminal 2+ (additional - can run on different machines)
python data_classifier_service.py 5021 --config config/sample_healthcare.yaml
python data_classifier_service.py 5022 --config config/sample_healthcare.yaml
```

Then update `config/sample_healthcare.yaml`:

```yaml
services:
    data_reader_url: http://localhost:5001
    classifiers:
        - http://localhost:5002
        - http://localhost:5021
        - http://localhost:5022
```

The orchestrator uses the classifier list from the selected config file. For production, use a reverse proxy.

### Single Orchestrator

The orchestrator coordinates all readers and classifiers. It should be highly available:

```cmd
python orchestrator_service.py 5000 --config config/sample_healthcare.yaml
```

In production, run as:

- A single instance behind a reverse proxy
- Or in HA mode with health checks and failover

## Load Balancing (Production)

### Option A: Nginx (Recommended)

```nginx
# /etc/nginx/sites-available/classifiers
upstream classifiers {
    server localhost:5002;
    server localhost:5021;
    server localhost:5022;
}

server {
    listen 9002;
    location / {
        proxy_pass http://classifiers;
    }
}
```

Then update the YAML config to use the proxy endpoint:

```yaml
services:
    data_reader_url: http://localhost:5001
    classifiers:
        - http://localhost:9002
```

### Option B: HAProxy

```
frontend classifiers
    bind *:9002
    default_backend cf
    
backend cf
    server c1 localhost:5002
    server c2 localhost:5021
    server c3 localhost:5022
    balance roundrobin
```

## Database Connection Pooling

Each Data Reader instance has its own connection pool (min=1, max=5 in `database_reader.py`).

For heavy loads, consider:

1. Increase pool size in `database_reader.py`
2. Use PgBouncer connection pooler on database side
3. Distribute readers across multiple machines

## Monitoring

Each service logs to stdout as JSON records using `delphix_ps_utilities`.
You can redirect logs to files:

```cmd
python data_reader_service.py 5001 --config config/sample_healthcare.yaml > logs/data_reader.log 2>&1
python data_classifier_service.py 5002 --config config/sample_healthcare.yaml > logs/data_classifier.log 2>&1
python orchestrator_service.py 5000 --config config/sample_healthcare.yaml > logs/orchestrator.log 2>&1
```

Monitor logs in real-time:

```bash
tail -f logs/data_reader.log
tail -f logs/data_classifier.log
tail -f logs/orchestrator.log
```

### Logging Implementation

- Shared bootstrap: `logging_setup.py`
- Preferred logger creation path: `ConfigAndLogUtilities.create_logger(...)`
- Automatic fallback path: `log_manager.LogConfig` (also JSON) when optional dependencies for `ConfigAndLogUtilities` are unavailable
- Local wheel fallback: `packages/delphix_ps_utilities-3-py3-none-any.whl` is auto-added to `sys.path` if the package is not installed

## Performance Tuning

### 1. Increase Worker Threads

In `orchestrator_service.py`:

```python
with ThreadPoolExecutor(max_workers=8) as executor:  # was 4
```

### 2. Adjust Sample Size

In `config/sample_healthcare.yaml`:

```yaml
sample_size: 50  # was 20, higher = more accurate but slower
```

### 3. Confidence Thresholds

Lower threshold = more columns classified by early layers, faster:

```yaml
confidence_threshold: 0.7  # was 0.8, more lenient
```

### 4. LLM Timeout (Layer 2)

In config if using Ollama:

```yaml
layer_2_rules:
  timeout_seconds: 60  # was 30, for remote servers
```

## Failure Scenarios

### Data Reader Down

- Orchestrator logs error and skips that classification attempt
- Other classifiers continue working
- **Mitigation**: Run multiple readers, orchestrator tries next

### Classifier Down

- Orchestrator removes from load balancer queue (manually for now)
- Other classifiers absorb load
- **Mitigation**: Run multiple classifiers

### Database Down

- Data Reader sample endpoint returns `200` with an `error` field and empty samples for per-column sampling failures
- Classifier logs the sample error and returns `status=ERROR` for that column while continuing with remaining columns
- Orchestrator continues processing other columns and writes all results (including error rows)
- **Mitigation**: Ensure database HA (replication, clustering)

## Cost Optimization

1. **Run services on same machine initially** (no network overhead)
2. **Scale horizontally only if needed** (each service is lightweight)
3. **Use local Ollama** instead of OpenAI API (if Layer 2 enabled)
4. **Batch columns** by dividing work among multiple classifiers

## Docker (Optional Future Enhancement)

Each service can be containerized:

```dockerfile
FROM python:3.10-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
ENTRYPOINT ["python"]
```

Then:

```bash
docker build -t classifier:latest .
docker run -p 5001:5001 classifier:latest data_reader_service.py 5001
docker run -p 5002:5002 classifier:latest data_classifier_service.py 5002
docker run -p 5000:5000 classifier:latest orchestrator_service.py 5000
```

Deploy on Kubernetes for true auto-scaling.

---

**Scaling Summary:**

- **Throughput bottleneck**: Database reads → add more Data Readers
- **CPU bottleneck**: Classification logic → add more Data Classifiers
- **Coordination bottleneck**: Rare, single Orchestrator usually sufficient
- **IO bottleneck**: Network → co-locate services on same subnet
