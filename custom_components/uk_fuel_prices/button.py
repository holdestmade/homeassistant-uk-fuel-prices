from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="UK Fuel Prices",
        manufacturer="UK Government",
        model="Fuel Finder API",
        configuration_url="https://www.fuel-finder.service.gov.uk",
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([UKFuelRefreshStationsButton(coordinator, entry)])


class UKFuelRefreshStationsButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "Refresh stations"
    _attr_icon = "mdi:refresh"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        self.coordinator = coordinator
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_refresh_stations"

    @property
    def device_info(self) -> DeviceInfo:
        return _device_info(self._entry)

    async def async_press(self) -> None:
        await self.coordinator.async_force_refresh_stations()
