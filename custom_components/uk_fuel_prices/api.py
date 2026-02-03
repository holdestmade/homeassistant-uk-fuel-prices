from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import asin, cos, radians, sin, sqrt
from typing import Any

import aiohttp


BASE_URL = "https://www.fuel-finder.service.gov.uk"

# Matches your original script endpoints
TOKEN_URL = f"{BASE_URL}/api/v1/oauth/generate_access_token"
REFRESH_URL = f"{BASE_URL}/api/v1/oauth/regenerate_access_token"

PFS_PATH = "/api/v1/pfs"
PRICES_PATH = "/api/v1/pfs/fuel-prices"

RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


@dataclass
class FuelFinderConfig:
    client_id: str
    client_secret: str
    home_lat: float
    home_lon: float
    radius_miles: float


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance between two points (km)."""
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    return 6371 * c


def get_opening_today(station: dict[str, Any]) -> str | None:
    """Get today's opening hours."""
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    day = days[datetime.now().weekday()]

    opening_times = station.get("opening_times", {}).get("usual_days", {}).get(day)
    if not opening_times:
        return None

    if opening_times.get("is_24_hours"):
        return "24h"

    open_time = (opening_times.get("open", "") or "")[:5]
    close_time = (opening_times.get("close", "") or "")[:5]

    if not open_time or not close_time:
        return None
    if open_time == "00:00" and close_time == "00:00":
        return None

    return f"{open_time}-{close_time}"


class FuelFinderApi:
    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def _request_json_with_retry(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        timeout_s: int = 30,
        retries: int = 6,
        backoff_base: float = 1.6,
        backoff_jitter: float = 0.5,
    ) -> Any:
        """
        Perform request and return parsed JSON.
        Retries on: 429, 500, 502, 503, 504, timeouts, connection errors.
        """
        last_exc: Exception | None = None

        for attempt in range(1, retries + 1):
            try:
                async with self._session.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json_body,
                    timeout=aiohttp.ClientTimeout(total=timeout_s),
                ) as resp:
                    # Retryable HTTP status codes
                    if resp.status in RETRYABLE_STATUSES and attempt < retries:
                        retry_after = resp.headers.get("Retry-After")
                        if retry_after:
                            try:
                                sleep_s = float(retry_after)
                            except ValueError:
                                sleep_s = (backoff_base ** (attempt - 1)) + backoff_jitter
                        else:
                            sleep_s = (backoff_base ** (attempt - 1)) + backoff_jitter

                        # Drain body before retrying (good hygiene)
                        try:
                            await resp.release()
                        except Exception:
                            pass

                        await asyncio.sleep(sleep_s)
                        continue

                    resp.raise_for_status()
                    return await resp.json()

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_exc = e
                if attempt < retries:
                    sleep_s = (backoff_base ** (attempt - 1)) + backoff_jitter
                    await asyncio.sleep(sleep_s)
                    continue
                raise

        raise last_exc or RuntimeError("request failed")

    async def get_token(
        self,
        cfg: FuelFinderConfig,
        token_state: dict[str, Any] | None,
    ) -> tuple[str, dict[str, Any]]:
        """
        Script-compatible OAuth behaviour:
        - If cached token is valid, use it
        - Else if refresh_token exists, POST JSON to regenerate_access_token
        - Else POST JSON to generate_access_token
        """
        token_state = token_state or {}

        access_token = token_state.get("access_token")
        expires_at = token_state.get("expires_at")
        refresh_token = token_state.get("refresh_token")

        if access_token and expires_at:
            try:
                exp = datetime.fromisoformat(expires_at)
                if _now_utc() < (exp - timedelta(seconds=30)):
                    return access_token, token_state
            except ValueError:
                pass

        if refresh_token:
            url = REFRESH_URL
            payload = {"client_id": cfg.client_id, "refresh_token": refresh_token}
        else:
            url = TOKEN_URL
            payload = {"client_id": cfg.client_id, "client_secret": cfg.client_secret}

        data = await self._request_json_with_retry(
            "POST",
            url,
            headers={"accept": "application/json"},
            json_body=payload,
            timeout_s=30,
            retries=8,
        )

        token_data = data.get("data", data)
        new_access = token_data["access_token"]
        expires_in = int(token_data.get("expires_in", 3600))
        new_refresh = token_data.get("refresh_token", refresh_token)

        new_state = {
            "access_token": new_access,
            "expires_at": (_now_utc() + timedelta(seconds=expires_in)).isoformat(),
            "refresh_token": new_refresh,
        }
        return new_access, new_state

    async def fetch_all_batches(
        self,
        token: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        headers = {"accept": "application/json", "authorization": f"Bearer {token}"}

        all_results: list[dict[str, Any]] = []
        batch = 1

        while True:
            query_params = dict(params or {})
            query_params["batch-number"] = batch

            batch_data = await self._request_json_with_retry(
                "GET",
                f"{BASE_URL}{path}",
                headers=headers,
                params=query_params,
                timeout_s=30,
                retries=6,
            )

            if not isinstance(batch_data, list):
                batch_data = []

            all_results.extend(batch_data)

            if len(batch_data) < 500:
                break

            batch += 1

        return all_results

    def process_stations(self, cfg: FuelFinderConfig, stations_data: list[dict[str, Any]]) -> dict[str, Any]:
        radius_km = float(cfg.radius_miles) * 1.609344
        nearby_stations: dict[str, Any] = {}

        for station in stations_data:
            node_id = station.get("node_id")
            if not node_id:
                continue

            if station.get("temporary_closure") or station.get("permanent_closure"):
                continue

            location = station.get("location", {})
            lat = location.get("latitude")
            lon = location.get("longitude")

            if lat is None or lon is None:
                continue

            try:
                lat_f = float(lat)
                lon_f = float(lon)
            except (ValueError, TypeError):
                continue

            km = haversine_km(cfg.home_lat, cfg.home_lon, lat_f, lon_f)
            if km > radius_km:
                continue

            miles = km / 1.609344

            nearby_stations[node_id] = {
                "id": node_id,
                "name": station.get("trading_name") or station.get("brand_name", ""),
                "brand": station.get("brand_name", ""),
                "postcode": location.get("postcode", ""),
                "lat": lat_f,
                "lon": lon_f,
                "miles": round(miles, 2),
                "open_today": get_opening_today(station),
                "is_mss": station.get("is_motorway_service_station", False),
                "is_supermarket": station.get("is_supermarket_service_station", False),
                "fuel_types": station.get("fuel_types", []),
                "amenities": station.get("amenities", []),
            }

        return nearby_stations

    def stations_cache_is_usable(self, cfg: FuelFinderConfig, state: dict[str, Any]) -> bool:
        cached = state.get("nearby_stations")
        if not isinstance(cached, dict) or not cached:
            return False

        cached_sig = state.get("stations_config")
        if not isinstance(cached_sig, dict):
            return False

        def close(a: Any, b: float, tol: float) -> bool:
            try:
                return abs(float(a) - float(b)) <= tol
            except Exception:
                return False

        return (
            close(cached_sig.get("home_lat"), float(cfg.home_lat), 1e-6)
            and close(cached_sig.get("home_lon"), float(cfg.home_lon), 1e-6)
            and close(cached_sig.get("radius_miles"), float(cfg.radius_miles), 1e-6)
        )

    def _parse_isoish(self, s: str) -> datetime | None:
        if not s:
            return None
        try:
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            return datetime.fromisoformat(s)
        except ValueError:
            return None

    def effective_start_timestamp_param(self, last_price_timestamp: str | None) -> str | None:
        if not last_price_timestamp:
            return None
        dt = self._parse_isoish(last_price_timestamp)
        if not dt:
            return None
        dt = dt - timedelta(minutes=30)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    def process_prices(
        self,
        prices_data: list[dict[str, Any]],
        nearby_station_ids: set[str],
    ) -> tuple[dict[str, Any], str | None]:
        prices_by_id: dict[str, Any] = {}
        max_timestamp: str | None = None

        for record in prices_data:
            node_id = record.get("node_id")
            if not node_id or node_id not in nearby_station_ids:
                continue

            fuel_prices = record.get("fuel_prices", [])
            station_prices: dict[str, Any] = {}

            for fuel in fuel_prices:
                fuel_type = fuel.get("fuel_type")
                if not fuel_type:
                    continue

                price = fuel.get("price")
                if price is None or price == "":
                    continue

                try:
                    price_f = float(price)
                except (ValueError, TypeError):
                    continue

                timestamp = fuel.get("price_last_updated")
                station_prices[fuel_type] = {"price": price_f, "timestamp": timestamp}

                if timestamp and (max_timestamp is None or timestamp > max_timestamp):
                    max_timestamp = timestamp

            if station_prices:
                prices_by_id[node_id] = station_prices

        return prices_by_id, max_timestamp

    def build_output(self, stations: dict[str, Any], prices: dict[str, Any]) -> dict[str, Any]:
        result: list[dict[str, Any]] = []

        for station_id, station in stations.items():
            station_prices = prices.get(station_id, {})
            if not station_prices:
                continue

            e10_data = station_prices.get("E10", {})
            b7_data = station_prices.get("B7_STANDARD", {})

            e10_price = e10_data.get("price")
            b7_price = b7_data.get("price")

            result.append(
                {
                    "id": station["id"],
                    "name": station["name"],
                    "postcode": station["postcode"],
                    "miles": station["miles"],
                    "open_today": station.get("open_today"),
                    "e10_price": round(float(e10_price), 1) if e10_price is not None else None,
                    "e10_updated": e10_data.get("timestamp"),
                    "b7_price": round(float(b7_price), 1) if b7_price is not None else None,
                    "b7_updated": b7_data.get("timestamp"),
                }
            )

        result.sort(key=lambda x: x.get("miles", 999999))

        def find_cheapest(fuel_key: str) -> dict[str, Any] | None:
            cheapest: dict[str, Any] | None = None
            for st in result:
                price = st.get(fuel_key)
                if price is None:
                    continue
                if cheapest is None or price < cheapest["price"]:
                    cheapest = {
                        "name": st.get("name"),
                        "postcode": st.get("postcode"),
                        "miles": st.get("miles"),
                        "price": price,
                    }
            return cheapest

        best_e10 = find_cheapest("e10_price")
        best_b7 = find_cheapest("b7_price")

        return {
            "state": len(result),
            "best_e10": best_e10,
            "best_b7": best_b7,
            "stations": result,
            "last_update": _now_utc().isoformat(),
        }
