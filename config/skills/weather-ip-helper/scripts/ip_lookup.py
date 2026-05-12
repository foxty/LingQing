#!/usr/bin/env python3
"""Fetch public IP and basic geolocation details."""

from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.request

# Set SSL_NO_VERIFY=1 in corporate environments with SSL inspection proxies.
_SSL_CONTEXT = ssl._create_unverified_context() if os.getenv("SSL_NO_VERIFY") == "1" else None


def _http_get_json(url: str, timeout: int = 10) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "weather-ip-helper/1.0"})
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CONTEXT) as resp:
        data = resp.read().decode("utf-8")
    return json.loads(data)


def main() -> int:
    try:
        ip_payload = _http_get_json("https://api.ipify.org?format=json")
        public_ip = str(ip_payload.get("ip", ""))
        if not public_ip:
            raise ValueError("Failed to resolve public IP")

        geo_payload = _http_get_json(f"https://ipwho.is/{public_ip}")
        if not geo_payload.get("success", True):
            raise ValueError(str(geo_payload.get("message", "IP geo lookup failed")))

        data = {
            "ip": public_ip,
            "type": geo_payload.get("type"),
            "continent": geo_payload.get("continent"),
            "country": geo_payload.get("country"),
            "region": geo_payload.get("region"),
            "city": geo_payload.get("city"),
            "latitude": geo_payload.get("latitude"),
            "longitude": geo_payload.get("longitude"),
            "isp": geo_payload.get("connection", {}).get("isp"),
            "timezone": geo_payload.get("timezone", {}).get("id"),
        }

        print(json.dumps({"ok": True, "data": data}, ensure_ascii=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
