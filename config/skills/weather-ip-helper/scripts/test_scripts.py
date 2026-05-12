#!/usr/bin/env python3
"""Smoke tests for weather-ip-helper skill scripts.

Run from the skill root directory:
    python scripts/test_scripts.py

All tests make real network requests; requires internet access.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
PASS = "PASS"
FAIL = "FAIL"


def run(args: list[str]) -> tuple[bool, dict]:
    result = subprocess.run(
        [sys.executable, *args],
        capture_output=True,
        text=True,
        timeout=20,
    )
    output = result.stdout.strip() or result.stderr.strip()
    try:
        data = json.loads(output)
    except Exception:
        data = {"ok": False, "raw": output}
    return result.returncode == 0, data


def check(label: str, ok: bool, data: dict, required_keys: list[str] | None = None) -> bool:
    if not ok or not data.get("ok"):
        print(f"  {FAIL}  {label}: {data}")
        return False
    inner = data.get("data", {})
    missing = [k for k in (required_keys or []) if k not in inner]
    if missing:
        print(f"  {FAIL}  {label}: missing keys {missing} in {inner}")
        return False
    print(f"  {PASS}  {label}")
    return True


def main() -> int:
    print("=== weather-ip-helper smoke tests ===\n")
    results = []

    # 1. weather by city name
    ok, data = run([str(SCRIPTS_DIR / "weather_lookup.py"), "--city", "Shanghai"])
    results.append(
        check(
            "weather_lookup --city Shanghai",
            ok,
            data,
            required_keys=["latitude", "longitude", "timezone", "current", "location_name"],
        )
    )

    # 2. weather by coordinates
    ok, data = run([str(SCRIPTS_DIR / "weather_lookup.py"), "--lat", "31.2", "--lon", "121.5"])
    results.append(
        check(
            "weather_lookup --lat 31.2 --lon 121.5",
            ok,
            data,
            required_keys=["latitude", "longitude", "current"],
        )
    )

    # 3. weather by unknown city → expect error payload
    ok, data = run([str(SCRIPTS_DIR / "weather_lookup.py"), "--city", "__nonexistent_city_xyz__"])
    if not ok and not data.get("ok") and data.get("error"):
        print(f"  {PASS}  weather_lookup unknown city returns error payload")
        results.append(True)
    else:
        print(f"  {FAIL}  weather_lookup unknown city should have failed: {data}")
        results.append(False)

    # 4. ip lookup
    ok, data = run([str(SCRIPTS_DIR / "ip_lookup.py")])
    results.append(
        check(
            "ip_lookup",
            ok,
            data,
            required_keys=["ip", "country", "city"],
        )
    )

    print(f"\n{'=' * 38}")
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
