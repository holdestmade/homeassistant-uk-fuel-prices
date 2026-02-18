"""API client for UK Government Fuel Finder service."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import asin, cos, radians, sin, sqrt
from typing import Any

import aiohttp

from .const import (
    API_BACKOFF_BASE,
    API_BACKOFF_JITTER,
    API_MAX_RETRIES,
    API_TIMEOUT_SECONDS,
    FUEL_TYPE_B7,
    FUEL_TYPE_E10,
    FUEL_TYPE_E5,
    TOKEN_REFRESH_BUFFER_SECONDS,
)


BASE_URL = "https://www.fuel-finder.service.gov.uk"
TOKEN_URL = f"{BASE_URL}/api/v1/oauth/generate_access_token"
REFRESH_URL = f"{BASE_URL}/api/v1/oauth/regenerate_access_token"
TOKEN_URL_V2 = f"{BASE_URL}/api/v2/oauth/generate_access_token"
REFRESH_URL_V2 = f"{BASE_URL}/api/v2/oauth/regenerate_access_token"

PFS_PATH = "/api/v1/pfs"
PRICES_PATH = "/api/v1/pfs/fuel-prices"

RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


class ApiError(Exception):
    """Base exception for API errors."""


class AuthenticationError(ApiError):
    """Exception raised for authentication failures."""


class RateLimitError(ApiError):
    """Exception raised when rate limit is exceeded."""


class ConnectionError(ApiError):
    """Exception raised for connection failures."""


@dataclass
class FuelFinderConfig:
    """Configuration for Fuel Finder API."""

    client_id: str
    client_secret: str
    home_lat: float
    home_lon: float
    radius_miles: float

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if not self.client_id or not self.client_secret:
            raise ValueError("Client ID and secret are required")
        if not -90 <= self.home_lat <= 90:
            raise ValueError("Latitude must be between -90 and 90")
        if not -180 <= self.home_lon <= 180:
            raise ValueError("Longitude must be between -180 and 180")
        if self.radius_miles <= 0:
            raise ValueError("Radius must be positive")


def _now_utc() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate distance between two points using Haversine formula.

    Args:
        lat1: First point latitude
        lon1: First point longitude
        lat2: Second point latitude
        lon2: Second point longitude

    Returns:
        Distance in kilometers
    """
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    return 6371 * c


def get_opening_today(station: dict[str, Any]) -> str | None:
    """
    Extract today's opening hours from station data.

    Args:
        station: Station data dictionary

    Returns:
        Opening hours string or None if not available
    """
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
    """API client for UK Government Fuel Finder service."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """
        Initialize the API client.

        Args:
            session: aiohttp client session
        """
        self._session = session

    async def _request_json_with_retry(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        timeout_s: int = API_TIMEOUT_SECONDS,
        retries: int = API_MAX_RETRIES,
        backoff_base: float = API_BACKOFF_BASE,
        backoff_jitter: float = API_BACKOFF_JITTER,
    ) -> Any:
        """
        Perform HTTP request with retry logic and return parsed JSON.

        Retries on: 429, 500, 502, 503, 504, timeouts, connection errors.

        Args:
            method: HTTP method
            url: Request URL
            headers: Optional request headers
            params: Optional query parameters
            json_body: Optional JSON body
            timeout_s: Request timeout in seconds
            retries: Maximum number of retry attempts
            backoff_base: Base for exponential backoff
            backoff_jitter: Jitter to add to backoff

        Returns:
            Parsed JSON response

        Raises:
            AuthenticationError: For 401/403 errors
            RateLimitError: For persistent rate limiting
            ConnectionError: For connection failures
            ApiError: For other API errors
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
                    # Handle authentication errors immediately
                    if resp.status in (401, 403):
                        error_text = await resp.text()
                        raise AuthenticationError(
                            f"Authentication failed (status {resp.status}): {error_text}"
                        )

                    # Retryable HTTP status codes
                    if resp.status in RETRYABLE_STATUSES and attempt < retries:
                        if resp.status == 429:
                            retry_after = resp.headers.get("Retry-After")
                            if retry_after:
                                try:
                                    sleep_s = float(retry_after)
                                except ValueError:
                                    sleep_s = (backoff_base ** (attempt - 1)) + backoff_jitter
                            else:
                                sleep_s = (backoff_base ** (attempt - 1)) + backoff_jitter
                        else:
                            sleep_s = (backoff_base ** (attempt - 1)) + backoff_jitter

                        # Drain response body before retrying
                        try:
                            await resp.release()
                        except Exception:
                            pass

                        await asyncio.sleep(sleep_s)
                        continue

                    resp.raise_for_status()
                    return await resp.json()

            except aiohttp.ClientError as e:
                last_exc = ConnectionError(f"Connection error: {e}")
                if attempt < retries:
                    sleep_s = (backoff_base ** (attempt - 1)) + backoff_jitter
                    await asyncio.sleep(sleep_s)
                    continue
                raise last_exc from e
            except asyncio.TimeoutError as e:
                last_exc = ConnectionError(f"Request timeout after {timeout_s}s")
                if attempt < retries:
                    sleep_s = (backoff_base ** (attempt - 1)) + backoff_jitter
                    await asyncio.sleep(sleep_s)
                    continue
                raise last_exc from e

        if last_exc:
            raise last_exc
        raise ApiError("Request failed with unknown error")

    async def get_token(
        self,
        cfg: FuelFinderConfig,
        token_state: dict[str, Any] | None,
    ) -> tuple[str, dict[str, Any]]:
        """
        Get or refresh OAuth access token.

        Implements token caching and automatic refresh using refresh tokens.

        Args:
            cfg: Fuel Finder configuration
            token_state: Cached token state

        Returns:
            Tuple of (access_token, new_token_state)

        Raises:
            AuthenticationError: If token acquisition fails
        """
        token_state = token_state or {}

        access_token = token_state.get("access_token")
        expires_at = token_state.get("expires_at")
        refresh_token = token_state.get("refresh_token")

        # Check if cached token is still valid
        if access_token and expires_at:
            try:
                exp = datetime.fromisoformat(expires_at)
                buffer = timedelta(seconds=TOKEN_REFRESH_BUFFER_SECONDS)
                if _now_utc() < (exp - buffer):
                    return access_token, token_state
            except ValueError:
                pass

        if refresh_token:
            attempts = [
                (
                    REFRESH_URL,
                    {
                        "client_id": cfg.client_id,
                        "client_secret": cfg.client_secret,
                        "refresh_token": refresh_token,
                    },
                ),
                (
                    REFRESH_URL,
                    {"client_id": cfg.client_id, "refresh_token": refresh_token},
                ),
                (
                    REFRESH_URL_V2,
                    {
                        "client_id": cfg.client_id,
                        "client_secret": cfg.client_secret,
                        "refresh_token": refresh_token,
                    },
                ),
                (
                    REFRESH_URL_V2,
                    {"client_id": cfg.client_id, "refresh_token": refresh_token},
                ),
            ]
        else:
            attempts = [
                (
                    TOKEN_URL,
                    {"client_id": cfg.client_id, "client_secret": cfg.client_secret},
                ),
                (
                    TOKEN_URL_V2,
                    {"client_id": cfg.client_id, "client_secret": cfg.client_secret},
                ),
            ]

        data: dict[str, Any] | None = None
        last_err: Exception | None = None
        for url, payload in attempts:
            try:
                data = await self._request_json_with_retry(
                    "POST",
                    url,
                    headers={"accept": "application/json"},
                    json_body=payload,
                    timeout_s=30,
                    retries=8,
                )
                break
            except Exception as err:
                last_err = err

        if data is None:
            raise AuthenticationError(f"Failed to obtain access token: {last_err}")

        token_data = self._extract_payload(data)
        new_access = token_data.get("access_token")
        if not new_access:
            raise AuthenticationError("No access token in response")

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
        """
        Fetch all batches from paginated API endpoint.

        The API returns up to 500 records per batch. This method automatically
        fetches all batches until fewer than 500 records are returned.

        Args:
            token: OAuth access token
            path: API endpoint path
            params: Optional query parameters

        Returns:
            List of all records from all batches

        Raises:
            ApiError: If batch fetch fails
        """
        headers = {"accept": "application/json", "authorization": f"Bearer {token}"}

        all_results: list[dict[str, Any]] = []
        batch = 1

        while True:
            query_params = dict(params or {})
            query_params["batch-number"] = batch

            try:
                response_data = await self._request_json_with_retry(
                    "GET",
                    f"{BASE_URL}{path}",
                    headers=headers,
                    params=query_params,
                    timeout_s=30,
                    retries=6,
                )
            except Exception as err:
                raise ApiError(f"Failed to fetch batch {batch}: {err}") from err

            batch_data, has_more = self._extract_batch_items(response_data)

            all_results.extend(batch_data)

            if has_more is not None:
                if not has_more:
                    break
            # Older API versions return fewer than 500 records when we've reached the end.
            elif len(batch_data) < 500:
                break

            batch += 1

        return all_results

    def process_stations(
        self, cfg: FuelFinderConfig, stations_data: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Filter and process stations within configured radius.

        Args:
            cfg: Fuel Finder configuration
            stations_data: Raw station data from API

        Returns:
            Dictionary of processed stations keyed by node_id
        """
        radius_km = float(cfg.radius_miles) * 1.609344
        nearby_stations: dict[str, Any] = {}

        for station in stations_data:
            node_id = station.get("node_id")
            if not node_id:
                continue

            # Skip closed stations
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

            # Calculate distance and filter by radius
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

    def stations_cache_is_usable(
        self, cfg: FuelFinderConfig, state: dict[str, Any]
    ) -> bool:
        """
        Check if cached station data is still valid.

        Station cache is valid if configuration hasn't changed.

        Args:
            cfg: Current Fuel Finder configuration
            state: Cached state data

        Returns:
            True if cache is valid, False otherwise
        """
        cached = state.get("nearby_stations")
        if not isinstance(cached, dict) or not cached:
            return False

        cached_sig = state.get("stations_config")
        if not isinstance(cached_sig, dict):
            return False

        def close(a: Any, b: float, tol: float = 1e-6) -> bool:
            """Check if two float values are within tolerance."""
            try:
                return abs(float(a) - float(b)) <= tol
            except (ValueError, TypeError):
                return False

        return (
            close(cached_sig.get("home_lat"), float(cfg.home_lat))
            and close(cached_sig.get("home_lon"), float(cfg.home_lon))
            and close(cached_sig.get("radius_miles"), float(cfg.radius_miles))
        )

    def _extract_payload(self, response: Any) -> dict[str, Any]:
        """Extract payload from API response supporting legacy and wrapped formats."""
        if isinstance(response, dict):
            data = response.get("data")
            if isinstance(data, dict):
                return data
            return response
        return {}

    def _extract_batch_items(
        self, response: Any
    ) -> tuple[list[dict[str, Any]], bool | None]:
        """Extract paginated items from API response with format fallbacks."""
        if isinstance(response, list):
            return [item for item in response if isinstance(item, dict)], None

        if not isinstance(response, dict):
            return [], None

        data = response.get("data", response)
        if isinstance(data, list):
            items = [item for item in data if isinstance(item, dict)]
        elif isinstance(data, dict):
            raw_items = data.get("items") or data.get("records") or []
            items = [item for item in raw_items if isinstance(item, dict)]
        else:
            items = []

        pagination = response.get("pagination")
        if not isinstance(pagination, dict) and isinstance(data, dict):
            pagination = data.get("pagination")

        has_more = None
        if isinstance(pagination, dict):
            if "has_next" in pagination:
                has_more = bool(pagination.get("has_next"))
            elif "has_next_page" in pagination:
                has_more = bool(pagination.get("has_next_page"))
            elif "total_pages" in pagination and "page" in pagination:
                try:
                    has_more = int(pagination["page"]) < int(pagination["total_pages"])
                except (TypeError, ValueError):
                    has_more = None

        return items, has_more

    def _parse_isoish(self, s: str) -> datetime | None:
        """
        Parse ISO-ish datetime string.

        Args:
            s: Datetime string

        Returns:
            Parsed datetime or None if invalid
        """
        if not s:
            return None
        try:
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            return datetime.fromisoformat(s)
        except ValueError:
            return None

    def effective_start_timestamp_param(
        self, last_price_timestamp: str | None
    ) -> str | None:
        """
        Calculate effective start timestamp for incremental price updates.

        Subtracts 30 minutes buffer to ensure no prices are missed.

        Args:
            last_price_timestamp: Last known price timestamp

        Returns:
            Formatted timestamp string or None
        """
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
        """
        Process and filter price data for nearby stations.

        Args:
            prices_data: Raw price data from API
            nearby_station_ids: Set of station IDs to include

        Returns:
            Tuple of (prices_by_station_id, max_timestamp)
        """
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

    def build_output(
        self, stations: dict[str, Any], prices: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Build final output data structure combining stations and prices.

        Args:
            stations: Station data dictionary
            prices: Price data dictionary

        Returns:
            Combined output dictionary with station count, best prices, and details
        """
        result: list[dict[str, Any]] = []
        total_stations = len(stations)

        for station_id, station in stations.items():
            station_prices = prices.get(station_id, {})
            if not station_prices:
                continue

            e10_data = station_prices.get(FUEL_TYPE_E10, {})
            e5_data = station_prices.get(FUEL_TYPE_E5, {})
            b7_data = station_prices.get(FUEL_TYPE_B7, {})

            e10_price = e10_data.get("price")
            e5_price = e5_data.get("price")
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
                    "e5_price": round(float(e5_price), 1) if e5_price is not None else None,
                    "e5_updated": e5_data.get("timestamp"),
                    "b7_price": round(float(b7_price), 1) if b7_price is not None else None,
                    "b7_updated": b7_data.get("timestamp"),
                }
            )

        # Sort by distance
        result.sort(key=lambda x: x.get("miles", 999999))

        def find_cheapest(fuel_key: str) -> dict[str, Any] | None:
            """Find station with cheapest price for given fuel type."""
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
        best_e5 = find_cheapest("e5_price")
        best_b7 = find_cheapest("b7_price")

        return {
            "state": total_stations,
            "best_e10": best_e10,
            "best_e5": best_e5,
            "best_b7": best_b7,
            "stations": result,
            "last_update": _now_utc().isoformat(),
        }
