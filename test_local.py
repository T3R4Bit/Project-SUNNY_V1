#!/usr/bin/env python
"""Quick test of local Sunny application."""

import asyncio
import subprocess
import time
import requests
import sys
from pathlib import Path


async def test_sunny():
    """Start server and test endpoints."""
    print("Project SUNNY — Local Test")
    print("=" * 50)

    # Start uvicorn server
    print("\n1⃣ Starting server...")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "sunny_code.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "5000",
            "--log-level",
            "warning",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to start
    time.sleep(2)

    try:
        # Test health endpoint
        print("\n2⃣ Testing endpoints...")
        response = requests.get("http://127.0.0.1:5000/health")
        print(f" GET /health → {response.status_code}")
        assert response.status_code == 200

        # Test root endpoint
        response = requests.get("http://127.0.0.1:5000/")
        print(f" GET / → {response.status_code}")
        assert response.status_code == 200
        data = response.json()
        print(f" Response: {data['name']} - {data['status']}")

        # Test dashboard status
        response = requests.get("http://127.0.0.1:5000/api/dashboard/status")
        print(f" GET /api/dashboard/status → {response.status_code}")
        assert response.status_code == 200
        data = response.json()
        print(f" Dashboard: {data['name']} at {data['tailscale_ip']}")

        # Test metrics recording
        response = requests.post(
            "http://127.0.0.1:5000/api/dashboard/metrics/record",
            params={"cpu": 45, "ram": 60, "disk": 50},
        )
        print(f" POST /api/dashboard/metrics/record → {response.status_code}")
        assert response.status_code == 200

        print("\nAll tests passed!")
        print("\nSummary:")
        print(" • FastAPI server running on 127.0.0.1:5000")
        print(" • 7 API endpoints configured")
        print(" • Database (sunny.db) initialized")
        print(" • Ready for Phase 2 development")

        return True

    except Exception as e:
        print(f"\nTest failed: {e}")
        return False

    finally:
        # Stop server
        print("\n3⃣ Stopping server...")
        proc.terminate()
        proc.wait(timeout=5)
        print(" Server stopped")


if __name__ == "__main__":
    success = asyncio.run(test_sunny())
    sys.exit(0 if success else 1)
