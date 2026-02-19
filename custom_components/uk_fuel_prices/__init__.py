"""The UK Fuel Prices integration."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AuthenticationError, FuelFinderApi, FuelFinderConfig
from .const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_RADIUS,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    SERVICE_FIELD_ENTRY_ID,
    SERVICE_REFRESH_STATIONS,
    STORE_KEY,
    STORE_VERSION,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor", "button"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up UK Fuel Prices from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("_services_registered", False)

    session = async_get_clientsession(hass)
    api = FuelFinderApi(session)
    store = Store(hass, STORE_VERSION, STORE_KEY)

    coordinator = UKFuelPricesCoordinator(hass, entry, api, store)

    await coordinator.async_initialize_from_cache()

    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}
    entry.async_on_unload(entry.add_update_listener(_async_update_options))

    # Register services only once
    if not hass.data[DOMAIN]["_services_registered"]:
        _register_services(hass)
        hass.data[DOMAIN]["_services_registered"] = True

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Run first refresh in the background so startup is not blocked by API latency.
    hass.async_create_task(_async_initial_refresh(coordinator, entry.entry_id))
    return True


async def _async_initial_refresh(
    coordinator: UKFuelPricesCoordinator,
    entry_id: str,
) -> None:
    """Run initial refresh without blocking Home Assistant startup."""
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryAuthFailed as err:
        _LOGGER.error("Initial refresh failed with authentication error for %s: %s", entry_id, err)
    except Exception as err:
        _LOGGER.warning("Initial refresh failed for %s: %s", entry_id, err)


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("coordinator")
    if coordinator is None:
        return

    coordinator.update_interval = timedelta(minutes=coordinator._scan_interval_minutes())
    await coordinator.async_request_refresh()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


def _register_services(hass: HomeAssistant) -> None:
    """Register integration services."""

    async def handle_refresh_stations(call: ServiceCall) -> None:
        """Handle refresh stations service call."""
        entry_id = call.data.get(SERVICE_FIELD_ENTRY_ID)

        coordinator = None
        if entry_id and entry_id in hass.data.get(DOMAIN, {}):
            coordinator = hass.data[DOMAIN][entry_id].get("coordinator")
        else:
            # Find first available coordinator if no entry_id specified
            for k, v in hass.data.get(DOMAIN, {}).items():
                if k == "_services_registered":
                    continue
                if isinstance(v, dict) and v.get("coordinator"):
                    coordinator = v["coordinator"]
                    break

        if coordinator is None:
            _LOGGER.error("No UK Fuel Prices coordinator found")
            return

        await coordinator.async_force_refresh_stations()

    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH_STATIONS,
        handle_refresh_stations,
        schema=vol.Schema({vol.Optional(SERVICE_FIELD_ENTRY_ID): str}),
    )


class UKFuelPricesCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching UK Fuel Prices data."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: FuelFinderApi,
        store: Store,
    ) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self.api = api
        self.store = store
        self._persisted: dict[str, Any] = {}
        self._force_stations_refresh: bool = False

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=self._scan_interval_minutes()),
        )

    def _scan_interval_minutes(self) -> int:
        """Get scan interval from configuration."""
        data = {**self.entry.data, **self.entry.options}
        try:
            interval = int(data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES))
            return max(1, interval)
        except (TypeError, ValueError):
            return DEFAULT_SCAN_INTERVAL_MINUTES

    def _cfg(self) -> FuelFinderConfig:
        """Build FuelFinderConfig from entry data."""
        data = {**self.entry.data, **self.entry.options}
        try:
            return FuelFinderConfig(
                client_id=data[CONF_CLIENT_ID],
                client_secret=data[CONF_CLIENT_SECRET],
                home_lat=float(data[CONF_LATITUDE]),
                home_lon=float(data[CONF_LONGITUDE]),
                radius_miles=float(data[CONF_RADIUS]),
            )
        except (KeyError, ValueError, TypeError) as err:
            raise UpdateFailed(f"Invalid configuration: {err}") from err

    async def async_force_refresh_stations(self) -> None:
        """Force stations refresh on next update."""
        _LOGGER.info("Forcing station refresh")
        self._force_stations_refresh = True
        await self.async_request_refresh()

    async def _load_store(self) -> None:
        """Load persisted data from storage."""
        if self._persisted:
            return
        stored = await self.store.async_load()
        self._persisted = stored if isinstance(stored, dict) else {}

    async def async_initialize_from_cache(self) -> None:
        """Restore cached state into coordinator data before first API refresh."""
        await self._load_store()

        state = self._persisted.get("state")
        if not isinstance(state, dict):
            return

        cached_stations = state.get("nearby_stations")
        cached_prices = state.get("last_prices")
        if not isinstance(cached_stations, dict) or not isinstance(cached_prices, dict):
            return

        cached_output = await self.hass.async_add_executor_job(
            self.api.build_output,
            cached_stations,
            cached_prices,
        )
        if cached_output:
            self.async_set_updated_data(cached_output)

    async def _save_store(self) -> None:
        """Save persisted data to storage."""
        try:
            await self.store.async_save(self._persisted)
        except Exception as err:
            _LOGGER.warning("Failed to save store: %s", err)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API."""
        # Update interval in sync with options
        self.update_interval = timedelta(minutes=self._scan_interval_minutes())

        await self._load_store()

        try:
            cfg = self._cfg()
        except UpdateFailed as err:
            raise err

        # Initialize state
        state: dict[str, Any] = (
            self._persisted.get("state")
            if isinstance(self._persisted.get("state"), dict)
            else {}
        )
        state.setdefault("last_prices", {})
        cached_prices = state.get("last_prices", {})
        if not isinstance(cached_prices, dict):
            cached_prices = {}
            state["last_prices"] = cached_prices

        # --- Token acquisition ---
        token_state = self._persisted.get("token")
        token: str | None = None

        try:
            token, new_token_state = await self.api.get_token(cfg, token_state)
            self._persisted["token"] = new_token_state
        except AuthenticationError as err:
            # Authentication failures should trigger reauth
            _LOGGER.error("Authentication failed: %s", err)

            # Try to use cached data if available
            cached_stations = state.get("nearby_stations")
            if (
                isinstance(cached_stations, dict)
                and cached_stations
                and isinstance(cached_prices, dict)
                and cached_prices
            ):
                _LOGGER.warning("Using cached data due to authentication failure")
                output = await self.hass.async_add_executor_job(
                    self.api.build_output,
                    cached_stations,
                    cached_prices,
                )
                if not output.get("last_update"):
                    output["last_update"] = datetime.now(timezone.utc).isoformat()

                self._persisted["state"] = state
                await self._save_store()
                return output

            raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err
        except Exception as err:
            _LOGGER.warning("Token acquisition failed: %s. Using cached data if available.", err)

            # Try to use cached data
            cached_stations = state.get("nearby_stations")
            if (
                isinstance(cached_stations, dict)
                and cached_stations
                and isinstance(cached_prices, dict)
                and cached_prices
            ):
                output = await self.hass.async_add_executor_job(
                    self.api.build_output,
                    cached_stations,
                    cached_prices,
                )
                if not output.get("last_update"):
                    output["last_update"] = datetime.now(timezone.utc).isoformat()

                self._persisted["state"] = state
                await self._save_store()
                return output

            raise UpdateFailed(f"Token acquisition failed: {err}") from err

        # --- Stations (cached unless forced or config changed) ---
        nearby_stations = None
        if not self._force_stations_refresh and self.api.stations_cache_is_usable(
            cfg, state
        ):
            cached = state.get("nearby_stations")
            if isinstance(cached, dict) and cached:
                nearby_stations = cached
                _LOGGER.debug("Using cached stations (%d stations)", len(nearby_stations))

        if nearby_stations is None:
            try:
                _LOGGER.info("Fetching stations from API")
                stations_data = await self.api.fetch_all_batches(token, "/api/v1/pfs")
                nearby_stations = await self.hass.async_add_executor_job(
                    self.api.process_stations,
                    cfg,
                    stations_data,
                )

                state["nearby_stations"] = nearby_stations
                state["stations_config"] = {
                    "home_lat": float(cfg.home_lat),
                    "home_lon": float(cfg.home_lon),
                    "radius_miles": float(cfg.radius_miles),
                }
                state["stations_cached_at"] = datetime.now(timezone.utc).isoformat()

                _LOGGER.info("Found %d stations within %.1f miles", len(nearby_stations), cfg.radius_miles)
            except Exception as err:
                _LOGGER.warning("Stations fetch error: %s. Using cached data if available.", err)
                cached = state.get("nearby_stations")
                if isinstance(cached, dict) and cached:
                    nearby_stations = cached
                else:
                    raise UpdateFailed(f"Stations error: {err}") from err
            finally:
                self._force_stations_refresh = False

        nearby_ids = set(nearby_stations.keys())

        # --- Prices (incremental updates) ---
        params: dict[str, str] = {}
        last_price_timestamp = state.get("last_price_timestamp")
        eff = self.api.effective_start_timestamp_param(last_price_timestamp)
        if eff:
            params["effective-start-timestamp"] = eff
            _LOGGER.debug("Fetching incremental prices since %s", eff)
        else:
            _LOGGER.debug("Fetching all prices (no previous timestamp)")

        try:
            prices_data = await self.api.fetch_all_batches(
                token, "/api/v1/pfs/fuel-prices", params
            )
            prices, max_timestamp = await self.hass.async_add_executor_job(
                self.api.process_prices,
                prices_data,
                nearby_ids,
            )

            # Merge into cache
            for node_id, fuels in prices.items():
                if not isinstance(fuels, dict):
                    continue
                existing = cached_prices.get(node_id, {})
                if not isinstance(existing, dict):
                    existing = {}
                existing.update(fuels)
                cached_prices[node_id] = existing

            state["last_prices"] = cached_prices
            if max_timestamp:
                state["last_price_timestamp"] = max_timestamp

            if prices:
                _LOGGER.debug("Updated prices for %d stations", len(prices))
        except Exception as err:
            _LOGGER.warning("Price fetch error, using cached prices: %s", err)

        # Build final output
        output = await self.hass.async_add_executor_job(
            self.api.build_output,
            nearby_stations,
            cached_prices,
        )

        # Persist state
        self._persisted["state"] = state
        await self._save_store()

        return output
