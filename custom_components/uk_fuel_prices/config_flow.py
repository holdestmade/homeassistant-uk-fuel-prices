from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_RADIUS,
    CONF_SCAN_INTERVAL,
    DEFAULT_RADIUS,
    DEFAULT_SCAN_INTERVAL_MINUTES,
)

STEP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CLIENT_ID): str,
        vol.Required(CONF_CLIENT_SECRET): str,
        vol.Required(CONF_LATITUDE): vol.All(vol.Coerce(float), vol.Range(min=-90, max=90)),
        vol.Required(CONF_LONGITUDE): vol.All(vol.Coerce(float), vol.Range(min=-180, max=180)),
        vol.Required(CONF_RADIUS, default=DEFAULT_RADIUS): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=1000)),
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL_MINUTES): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=720)
        ),
    }
)

class UKFuelPricesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(
                title="UK Fuel Prices",
                data={
                    CONF_CLIENT_ID: user_input[CONF_CLIENT_ID],
                    CONF_CLIENT_SECRET: user_input[CONF_CLIENT_SECRET],
                    CONF_LATITUDE: float(user_input[CONF_LATITUDE]),
                    CONF_LONGITUDE: float(user_input[CONF_LONGITUDE]),
                    CONF_RADIUS: float(user_input[CONF_RADIUS]),
                    CONF_SCAN_INTERVAL: int(user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES)),
                },
            )

        return self.async_show_form(step_id="user", data_schema=STEP_SCHEMA, errors={})

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return UKFuelPricesOptionsFlow(config_entry)

class UKFuelPricesOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input=None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    CONF_CLIENT_ID: user_input[CONF_CLIENT_ID],
                    CONF_CLIENT_SECRET: user_input[CONF_CLIENT_SECRET],
                    CONF_LATITUDE: float(user_input[CONF_LATITUDE]),
                    CONF_LONGITUDE: float(user_input[CONF_LONGITUDE]),
                    CONF_RADIUS: float(user_input[CONF_RADIUS]),
                    CONF_SCAN_INTERVAL: int(user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES)),
                },
            )

        data = {**self.entry.data, **self.entry.options}

        schema = vol.Schema(
            {
                vol.Required(CONF_CLIENT_ID, default=data.get(CONF_CLIENT_ID, "")): str,
                vol.Required(CONF_CLIENT_SECRET, default=data.get(CONF_CLIENT_SECRET, "")): str,
                vol.Required(CONF_LATITUDE, default=float(data.get(CONF_LATITUDE, 0.0))): vol.All(
                    vol.Coerce(float), vol.Range(min=-90, max=90)
                ),
                vol.Required(CONF_LONGITUDE, default=float(data.get(CONF_LONGITUDE, 0.0))): vol.All(
                    vol.Coerce(float), vol.Range(min=-180, max=180)
                ),
                vol.Required(CONF_RADIUS, default=float(data.get(CONF_RADIUS, DEFAULT_RADIUS))): vol.All(
                    vol.Coerce(float), vol.Range(min=0.1, max=1000)
                ),
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=int(data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES)),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=720)),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema, errors={})
