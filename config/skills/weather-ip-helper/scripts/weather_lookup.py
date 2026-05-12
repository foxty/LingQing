#!/usr/bin/env python3
"""Fetch current weather from Open-Meteo APIs."""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.parse
import urllib.request

# Set SSL_NO_VERIFY=1 in corporate environments with SSL inspection proxies.
_SSL_CONTEXT = ssl._create_unverified_context() if os.getenv("SSL_NO_VERIFY") == "1" else None


def _http_get_json(url: str, timeout: int = 10) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "weather-ip-helper/1.0"})
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CONTEXT) as resp:
        data = resp.read().decode("utf-8")
    return json.loads(data)


def _resolve_city(city: str) -> tuple[float, float, str]:
    encoded = urllib.parse.quote(city)
    url = f"https://geocoding-api.open-meteo.com/v1/search?name={encoded}&count=1&language=en&format=json"
    payload = _http_get_json(url)
    results = payload.get("results") or []
    if not results:
        raise ValueError(f"City not found: {city}")
    item = results[0]
    return float(item["latitude"]), float(item["longitude"]), str(item.get("name") or city)


def _fetch_weather(lat: float, lon: float) -> dict:
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,"
        "apparent_temperature,weather_code,wind_speed_10m&timezone=auto"
    )
    payload = _http_get_json(url)
    current = payload.get("current") or {}
    if not current:
        raise ValueError("No current weather data in response")

    return {
        "latitude": payload.get("latitude"),
        "longitude": payload.get("longitude"),
        "timezone": payload.get("timezone"),
        "current": {
            "time": current.get("time"),
            "temperature_c": current.get("temperature_2m"),
            "feels_like_c": current.get("apparent_temperature"),
            "humidity_pct": current.get("relative_humidity_2m"),
            "wind_speed_kmh": current.get("wind_speed_10m"),
            "weather_code": current.get("weather_code"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Get current weather by city or coordinates")
    parser.add_argument("--city", type=str, default="", help="City name, e.g. Shanghai")
    parser.add_argument("--lat", type=float, default=None, help="Latitude")
    parser.add_argument("--lon", type=float, default=None, help="Longitude")
    args = parser.parse_args()

    try:
        if args.city:
            lat, lon, resolved_name = _resolve_city(args.city)
            result = _fetch_weather(lat, lon)
            result["location_name"] = resolved_name
        else:
            if args.lat is None or args.lon is None:
                raise ValueError("Provide --city or both --lat and --lon")
            result = _fetch_weather(args.lat, args.lon)

        print(json.dumps({"ok": True, "data": result}, ensure_ascii=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
