from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, ATTR_BEST_E10, ATTR_BEST_B7, ATTR_STATIONS, ATTR_LAST_UPDATE

ICON = "mdi:gas-station"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        [
            UKFuelStationCountSensor(coordinator, entry),

            # Prices
            UKFuelBestPriceSensor(
                coordinator,
                entry,
                fuel_attr=ATTR_BEST_E10,
                name="Cheapest petrol (E10) price",
                unique_id=f"{DOMAIN}_cheapest_e10_price",
            ),
            UKFuelBestPriceSensor(
                coordinator,
                entry,
                fuel_attr=ATTR_BEST_B7,
                name="Cheapest diesel (B7) price",
                unique_id=f"{DOMAIN}_cheapest_b7_price",
            ),

            # Station name sensors
            UKFuelCheapestStationSensor(
                coordinator,
                entry,
                fuel_attr=ATTR_BEST_E10,
                name="Cheapest petrol (E10) station",
                unique_id=f"{DOMAIN}_cheapest_e10_station",
            ),
            UKFuelCheapestStationSensor(
                coordinator,
                entry,
                fuel_attr=ATTR_BEST_B7,
                name="Cheapest diesel station",
                unique_id=f"{DOMAIN}_cheapest_b7_station",
            ),

            # Diagnostic list + last update
            UKFuelStationsListSensor(coordinator, entry),
            UKFuelLastUpdateSensor(coordinator, entry),
        ]
    )


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    # One device per config entry.
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="UK Fuel Prices",
        manufacturer="UK Government",
        model="Fuel Finder API",
        configuration_url="https://www.fuel-finder.service.gov.uk",
    )


class _BaseUKFuelSensor(SensorEntity):
    _attr_icon = ICON
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        self.coordinator = coordinator
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        return _device_info(self._entry)

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))

    async def async_update(self) -> None:
        await self.coordinator.async_request_refresh()


class UKFuelStationCountSensor(_BaseUKFuelSensor):
    _attr_name = "Nearby fuel stations"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{DOMAIN}_count"

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        return data.get("state")

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        return {ATTR_LAST_UPDATE: data.get(ATTR_LAST_UPDATE)}


class UKFuelBestPriceSensor(_BaseUKFuelSensor):
    """State is the cheapest price for a fuel type; attrs include station details."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "p"
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator, entry: ConfigEntry, *, fuel_attr: str, name: str, unique_id: str) -> None:
        super().__init__(coordinator, entry)
        self._fuel_attr = fuel_attr
        self._attr_name = name
        self._attr_unique_id = unique_id

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        best = data.get(self._fuel_attr) or {}
        return best.get("price")

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        best = data.get(self._fuel_attr) or {}
        return {
            "station": best.get("name"),
            "postcode": best.get("postcode"),
            "miles": best.get("miles"),
            ATTR_LAST_UPDATE: data.get(ATTR_LAST_UPDATE),
        }


class UKFuelCheapestStationSensor(_BaseUKFuelSensor):
    """State is the station name for the cheapest price; attrs include price + distance."""

    def __init__(self, coordinator, entry: ConfigEntry, *, fuel_attr: str, name: str, unique_id: str) -> None:
        super().__init__(coordinator, entry)
        self._fuel_attr = fuel_attr
        self._attr_name = name
        self._attr_unique_id = unique_id

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        best = data.get(self._fuel_attr) or {}
        return best.get("name")

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        best = data.get(self._fuel_attr) or {}
        return {
            "price": best.get("price"),
            "postcode": best.get("postcode"),
            "miles": best.get("miles"),
            ATTR_LAST_UPDATE: data.get(ATTR_LAST_UPDATE),
        }


class UKFuelStationsListSensor(_BaseUKFuelSensor):
    _attr_name = "Stations"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{DOMAIN}_stations"

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        stations = data.get(ATTR_STATIONS) or []
        return len(stations)

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        return {
            ATTR_STATIONS: data.get(ATTR_STATIONS, []),
            ATTR_LAST_UPDATE: data.get(ATTR_LAST_UPDATE),
        }


class UKFuelLastUpdateSensor(_BaseUKFuelSensor):
    _attr_name = "Last update"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{DOMAIN}_last_update"

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        val = data.get(ATTR_LAST_UPDATE)
        if not val:
            return None
        try:
            if isinstance(val, str) and val.endswith("Z"):
                val = val[:-1] + "+00:00"
            return datetime.fromisoformat(val)
        except Exception:
            return None
