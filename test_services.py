"""Test script to validate three-service architecture."""

import argparse
import time

import requests

READER_URL = "http://localhost:5001"
CLASSIFIER_URL = "http://localhost:5002"
ORCHESTRATOR_URL = "http://localhost:5000"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test the classification microservices.")
    parser.add_argument(
        "--config",
        dest="config_path",
        default="",
        help="Optional config path passed through to service requests.",
    )
    return parser.parse_args()


def test_health():
    """Test service health checks."""
    print("\n=== HEALTH CHECKS ===")
    services = [
        ("Data Reader", READER_URL),
        ("Data Classifier", CLASSIFIER_URL),
        ("Orchestrator", ORCHESTRATOR_URL),
    ]
    
    for name, url in services:
        try:
            resp = requests.get(f"{url}/health", timeout=5)
            status = "OK" if resp.status_code == 200 else f"ERROR ({resp.status_code})"
            print(f"✓ {name}: {status}")
        except Exception as e:
            print(f"✗ {name}: {e}")

def test_data_reader(config_path: str):
    """Test data reader endpoints."""
    print("\n=== DATA READER TESTS ===")
    
    # Test schema fetch
    try:
        resp = requests.get(
            f"{READER_URL}/schema/public",
            params={"config_path": config_path} if config_path else None,
            timeout=10,
        )
        resp.raise_for_status()
        columns = resp.json().get("columns", [])
        print(f"✓ Schema fetch: Retrieved {len(columns)} columns")
        
        if columns:
            col = columns[0]
            print(f"  Sample: {col['table_name']}.{col['column_name']} ({col['data_type']})")
            
            # Test sample fetch
            try:
                resp = requests.get(
                    f"{READER_URL}/sample/public/{col['table_name']}/{col['column_name']}",
                    params={
                        "limit": 5,
                        **({"config_path": config_path} if config_path else {}),
                    },
                    timeout=10
                )
                resp.raise_for_status()
                samples = resp.json().get("samples", [])
                print(f"✓ Sample fetch: Retrieved {len(samples)} values")
            except Exception as e:
                print(f"✗ Sample fetch: {e}")
    except Exception as e:
        print(f"✗ Schema fetch: {e}")


def test_reader_to_classifier_integration(config_path: str):
    """Integration test: chain Data Reader output into Data Classifier input."""
    print("\n=== READER -> CLASSIFIER INTEGRATION TEST ===")

    try:
        reader_resp = requests.get(
            f"{READER_URL}/schema/public",
            params={"config_path": config_path} if config_path else None,
            timeout=10,
        )
        reader_resp.raise_for_status()
        columns = reader_resp.json().get("columns", [])

        if not columns:
            print("✗ Integration test: Data Reader returned no columns")
            return

        # Use one of the returned columns directly as classifier payload.
        col = columns[0]
        payload = {
            "schema_name": col.get("schema_name", "public"),
            "table_name": col.get("table_name"),
            "column_name": col.get("column_name"),
            "data_type": col.get("data_type", "unknown"),
        }
        if config_path:
            payload["config_path"] = config_path

        classifier_resp = requests.post(
            f"{CLASSIFIER_URL}/classify",
            json=payload,
            timeout=30,
        )
        classifier_resp.raise_for_status()
        result = classifier_resp.json()

        print(
            "✓ Integration: %s.%s.%s -> %s (status=%s, confidence=%.4f)"
            % (
                payload["schema_name"],
                payload["table_name"],
                payload["column_name"],
                result.get("category"),
                result.get("status"),
                float(result.get("confidence", 0.0)),
            )
        )

        if result.get("error"):
            print(f"  Reader/Classifer reported error: {result.get('error')}")

    except Exception as e:
        print(f"✗ Reader -> Classifier integration test failed: {e}")


def test_classifier(config_path: str):
    """Test classifier endpoint."""
    print("\n=== DATA CLASSIFIER TESTS ===")
    
    payload = {
        "schema_name": "public",
        "table_name": "customers",
        "column_name": "email_address",
        "data_type": "text",
    }
    if config_path:
        payload["config_path"] = config_path
    
    try:
        resp = requests.post(
            f"{CLASSIFIER_URL}/classify",
            json=payload,
            timeout=30
        )
        resp.raise_for_status()
        result = resp.json()
        print(f"✓ Classification: {result.get('column_name')} → {result.get('category')} (confidence={result.get('confidence'):.4f})")
    except Exception as e:
        print(f"✗ Classification: {e}")

def test_orchestrator(config_path: str):
    """Test orchestrator endpoint."""
    print("\n=== ORCHESTRATOR TESTS ===")
    
    payload = {
        "schema": "public",
        "output_file": "test_results.csv",
    }
    if config_path:
        payload["config_path"] = config_path
    
    try:
        print("Starting end-to-end analysis (this may take a minute)...")
        resp = requests.post(
            f"{ORCHESTRATOR_URL}/analyze",
            json=payload,
            timeout=120
        )
        resp.raise_for_status()
        result = resp.json()
        
        print(f"✓ Analysis complete:")
        print(f"  Total columns: {result.get('total_columns')}")
        print(f"  Classified: {result.get('classified')}")
        print(f"  Output file: {result.get('output_file')}")
        
        if result.get('results_preview'):
            print(f"\nResults Preview:")
            print(result.get('results_preview'))
    except Exception as e:
        print(f"✗ Analysis: {e}")

def main():
    args = parse_args()
    print("="*60)
    print("MICROSERVICE ARCHITECTURE TEST SUITE")
    print("="*60)
    
    # Check if services are up
    # test_health()
    # time.sleep(1)
    
    # Run component tests
    # test_data_reader(args.config_path)
    # test_reader_to_classifier_integration(args.config_path)
    # test_classifier(args.config_path)
    test_orchestrator(args.config_path)
    
    print("\n" + "="*60)
    print("TEST COMPLETE")
    print("="*60)

if __name__ == "__main__":
    main()
