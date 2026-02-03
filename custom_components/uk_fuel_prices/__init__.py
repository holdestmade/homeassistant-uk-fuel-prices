from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FuelFinderApi, FuelFinderConfig
from .const import (
    DOMAIN,
    STORE_KEY,
    STORE_VERSION,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_RADIUS,
    CONF_SCAN_INTERVAL,
    SERVICE_REFRESH_STATIONS,
    SERVICE_FIELD_ENTRY_ID,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor", "button"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("_services_registered", False)

    session = async_get_clientsession(hass)
    api = FuelFinderApi(session)
    store = Store(hass, STORE_VERSION, STORE_KEY)

    coordinator = UKFuelPricesCoordinator(hass, entry, api, store)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}

    if not hass.data[DOMAIN]["_services_registered"]:
        _register_services(hass)
        hass.data[DOMAIN]["_services_registered"] = True

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


def _register_services(hass: HomeAssistant) -> None:
    async def handle_refresh_stations(call: ServiceCall) -> None:
        entry_id = call.data.get(SERVICE_FIELD_ENTRY_ID)

        coordinator = None
        if entry_id and entry_id in hass.data.get(DOMAIN, {}):
            coordinator = hass.data[DOMAIN][entry_id].get("coordinator")
        else:
            for k, v in hass.data.get(DOMAIN, {}).items():
                if k == "_services_registered":
                    continue
                if isinstance(v, dict) and v.get("coordinator"):
                    coordinator = v["coordinator"]
                    break

        if coordinator is None:
            raise UpdateFailed("No UK Fuel Prices coordinator found")

        await coordinator.async_force_refresh_stations()

    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH_STATIONS,
        handle_refresh_stations,
        schema=vol.Schema({vol.Optional(SERVICE_FIELD_ENTRY_ID): str}),
    )


class UKFuelPricesCoordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: FuelFinderApi, store: Store) -> None:
        self.entry = entry
        self.api = api
        self.store = store
        self._persisted: dict = {}
        self._force_stations_refresh: bool = False

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=self._scan_interval_minutes()),
        )

    def _scan_interval_minutes(self) -> int:
        data = {**self.entry.data, **self.entry.options}
        try:
            return max(1, int(data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES)))
        except (TypeError, ValueError):
            return DEFAULT_SCAN_INTERVAL_MINUTES

    def _cfg(self) -> FuelFinderConfig:
        data = {**self.entry.data, **self.entry.options}
        return FuelFinderConfig(
            client_id=data[CONF_CLIENT_ID],
            client_secret=data[CONF_CLIENT_SECRET],
            home_lat=float(data[CONF_LATITUDE]),
            home_lon=float(data[CONF_LONGITUDE]),
            radius_miles=float(data[CONF_RADIUS]),
        )

    async def async_force_refresh_stations(self) -> None:
        """Force stations refresh on next update (without clearing cached prices)."""
        self._force_stations_refresh = True
        await self.async_request_refresh()

    async def _load_store(self) -> None:
        if self._persisted:
            return
        stored = await self.store.async_load()
        self._persisted = stored if isinstance(stored, dict) else {}

    async def _save_store(self) -> None:
        await self.store.async_save(self._persisted)

    async def _async_update_data(self) -> dict:
        # keep update interval in sync with options
        self.update_interval = timedelta(minutes=self._scan_interval_minutes())

        await self._load_store()
        cfg = self._cfg()

        state: dict = self._persisted.get("state") if isinstance(self._persisted.get("state"), dict) else {}
        state.setdefault("last_prices", {})
        cached_prices = state.get("last_prices")
        if not isinstance(cached_prices, dict):
            cached_prices = {}
            state["last_prices"] = cached_prices

        # --- Token (script method) ---
        token_state = self._persisted.get("token")
        token: str | None = None

        try:
            token, new_token_state = await self.api.get_token(cfg, token_state)
            self._persisted["token"] = new_token_state
        except Exception as err:
            # If we have cached stations+prices, publish them and keep the integration running.
            _LOGGER.warning("Token acquisition failed (%s). Using cached data if available.", err)

            cached_stations = state.get("nearby_stations")
            if isinstance(cached_stations, dict) and cached_stations and isinstance(cached_prices, dict) and cached_prices:
                output = self.api.build_output(cached_stations, cached_prices)
                # keep last_update meaningful even in cached mode
                if not output.get("last_update"):
                    output["last_update"] = datetime.now(timezone.utc).isoformat()

                self._persisted["state"] = state
                await self._save_store()
                return output

            raise UpdateFailed(f"Token acquisition failed: {err!r}") from err

        # --- Stations (cached unless forced / config changed) ---
        nearby_stations = None
        if not self._force_stations_refresh and self.api.stations_cache_is_usable(cfg, state):
            cached = state.get("nearby_stations")
            if isinstance(cached, dict) and cached:
                nearby_stations = cached

        if nearby_stations is None:
            try:
                stations_data = await self.api.fetch_all_batches(token, "/api/v1/pfs")
                nearby_stations = self.api.process_stations(cfg, stations_data)

                state["nearby_stations"] = nearby_stations
                state["stations_config"] = {
                    "home_lat": float(cfg.home_lat),
                    "home_lon": float(cfg.home_lon),
                    "radius_miles": float(cfg.radius_miles),
                }
                state["stations_cached_at"] = datetime.now(timezone.utc).isoformat()
            except Exception as err:
                cached = state.get("nearby_stations")
                if isinstance(cached, dict) and cached:
                    nearby_stations = cached
                else:
                    raise UpdateFailed(f"Stations error: {err!r}") from err
            finally:
                self._force_stations_refresh = False

        nearby_ids = set(nearby_stations.keys())

        # --- Prices (incremental) ---
        params: dict[str, str] = {}
        last_price_timestamp = state.get("last_price_timestamp")
        eff = self.api.effective_start_timestamp_param(last_price_timestamp)
        if eff:
            params["effective-start-timestamp"] = eff

        try:
            prices_data = await self.api.fetch_all_batches(token, "/api/v1/pfs/fuel-prices", params)
            prices, max_timestamp = self.api.process_prices(prices_data, nearby_ids)

            # merge into cache (script behaviour)
            for node_id, fuels in prices.items():
                if not isinstance(fuels, dict):
                    continue
                existing = cached_prices.get(node_id)
                if not isinstance(existing, dict):
                    existing = {}
                existing.update(fuels)
                cached_prices[node_id] = existing

            state["last_prices"] = cached_prices
            if max_timestamp:
                state["last_price_timestamp"] = max_timestamp

        except Exception as err:
            _LOGGER.warning("Price fetch error, using cached prices: %s", err)

        output = self.api.build_output(nearby_stations, cached_prices)

        self._persisted["state"] = state
        await self._save_store()
        return output
