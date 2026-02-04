"""Sensor platform for UK Fuel Prices integration."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_BEST_B7, ATTR_BEST_E10, ATTR_LAST_UPDATE, ATTR_STATIONS, DOMAIN

ICON = "mdi:gas-station"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up UK Fuel Prices sensors from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        [
            # Station count sensor
            UKFuelStationCountSensor(coordinator, entry),
            # Best price sensors
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
            # Diagnostic sensors
            UKFuelStationsListSensor(coordinator, entry),
            UKFuelLastUpdateSensor(coordinator, entry),
        ]
    )


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    """Return device info for UK Fuel Prices device."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="UK Fuel Prices",
        manufacturer="UK Government",
        model="Fuel Finder API",
        configuration_url="https://www.fuel-finder.service.gov.uk",
    )


class _BaseUKFuelSensor(CoordinatorEntity, SensorEntity):
    """Base class for UK Fuel sensors."""

    _attr_icon = ICON
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return _device_info(self._entry)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success



class UKFuelStationCountSensor(_BaseUKFuelSensor):
    """Sensor showing count of nearby fuel stations."""

    _attr_name = "Nearby fuel stations"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "stations"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{DOMAIN}_count"

    @property
    def native_value(self) -> int | None:
        """Return the state."""
        data = self.coordinator.data or {}
        return data.get("state")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        data = self.coordinator.data or {}
        return {ATTR_LAST_UPDATE: data.get(ATTR_LAST_UPDATE)}


class UKFuelBestPriceSensor(_BaseUKFuelSensor):
    """Sensor showing the cheapest price for a fuel type."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "p"
    _attr_suggested_display_precision = 1
    _attr_device_class = SensorDeviceClass.MONETARY

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        *,
        fuel_attr: str,
        name: str,
        unique_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._fuel_attr = fuel_attr
        self._attr_name = name
        self._attr_unique_id = unique_id
        # Remove diagnostic category for price sensors - they're primary entities
        self._attr_entity_category = None

    @property
    def native_value(self) -> float | None:
        """Return the state."""
        data = self.coordinator.data or {}
        best = data.get(self._fuel_attr) or {}
        return best.get("price")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        data = self.coordinator.data or {}
        best = data.get(self._fuel_attr) or {}
        return {
            "station": best.get("name"),
            "postcode": best.get("postcode"),
            "miles": best.get("miles"),
            ATTR_LAST_UPDATE: data.get(ATTR_LAST_UPDATE),
        }


class UKFuelCheapestStationSensor(_BaseUKFuelSensor):
    """Sensor showing the station name for the cheapest price."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        *,
        fuel_attr: str,
        name: str,
        unique_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._fuel_attr = fuel_attr
        self._attr_name = name
        self._attr_unique_id = unique_id

    @property
    def native_value(self) -> str | None:
        """Return the state."""
        data = self.coordinator.data or {}
        best = data.get(self._fuel_attr) or {}
        return best.get("name")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        data = self.coordinator.data or {}
        best = data.get(self._fuel_attr) or {}
        return {
            "price": best.get("price"),
            "postcode": best.get("postcode"),
            "miles": best.get("miles"),
            ATTR_LAST_UPDATE: data.get(ATTR_LAST_UPDATE),
        }


class UKFuelStationsListSensor(_BaseUKFuelSensor):
    """Sensor with list of all stations and their prices."""

    _attr_name = "Stations"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "stations"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{DOMAIN}_stations"

    @property
    def native_value(self) -> int:
        """Return the state."""
        data = self.coordinator.data or {}
        stations = data.get(ATTR_STATIONS) or []
        return len(stations)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        data = self.coordinator.data or {}
        return {
            ATTR_STATIONS: data.get(ATTR_STATIONS, []),
            ATTR_LAST_UPDATE: data.get(ATTR_LAST_UPDATE),
        }


class UKFuelLastUpdateSensor(_BaseUKFuelSensor):
    """Sensor showing last update timestamp."""

    _attr_name = "Last update"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{DOMAIN}_last_update"

    @property
    def native_value(self) -> datetime | None:
        """Return the state."""
        data = self.coordinator.data or {}
        val = data.get(ATTR_LAST_UPDATE)
        if not val:
            return None
        try:
            if isinstance(val, str) and val.endswith("Z"):
                val = val[:-1] + "+00:00"
            return datetime.fromisoformat(val)
        except (ValueError, TypeError):
            return None
