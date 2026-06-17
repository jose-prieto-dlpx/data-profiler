#!/usr/bin/env bash
# Start all three services in background

set -e

PYTHON="D:/Python/Python3104/python.exe"
LOG_DIR="./logs"
mkdir -p "$LOG_DIR"

echo "Starting Distributed Data Classification Pipeline..."

# Start Data Reader Service
echo "Starting Data Reader Service (port 5001)..."
$PYTHON data_reader_service.py 5001 > "$LOG_DIR/data_reader.log" 2>&1 &
READER_PID=$!
echo "Data Reader PID: $READER_PID"

# Start Data Classifier Service
echo "Starting Data Classifier Service (port 5002)..."
$PYTHON data_classifier_service.py 5002 > "$LOG_DIR/data_classifier.log" 2>&1 &
CLASSIFIER_PID=$!
echo "Data Classifier PID: $CLASSIFIER_PID"

# Start Orchestrator Service
echo "Starting Orchestrator Service (port 5000)..."
$PYTHON orchestrator_service.py 5000 > "$LOG_DIR/orchestrator.log" 2>&1 &
ORCHESTRATOR_PID=$!
echo "Orchestrator PID: $ORCHESTRATOR_PID"

echo ""
echo "All services started. PIDs: Reader=$READER_PID, Classifier=$CLASSIFIER_PID, Orchestrator=$ORCHESTRATOR_PID"
echo "Logs available in: $LOG_DIR/"
echo ""
echo "Test with:"
echo '  curl -X POST http://localhost:5000/analyze -H "Content-Type: application/json" -d '"'"'{"schema": "public"}'"'"
echo ""
echo "To stop services, run: kill $READER_PID $CLASSIFIER_PID $ORCHESTRATOR_PID"
