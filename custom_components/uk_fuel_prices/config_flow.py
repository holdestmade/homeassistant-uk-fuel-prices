"""Config flow for UK Fuel Prices integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_RADIUS,
    CONF_SCAN_INTERVAL,
    DEFAULT_RADIUS,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    MAX_RADIUS_MILES,
    MAX_SCAN_INTERVAL_MINUTES,
    MIN_RADIUS_MILES,
    MIN_SCAN_INTERVAL_MINUTES,
    UK_LAT_MAX,
    UK_LAT_MIN,
    UK_LON_MAX,
    UK_LON_MIN,
)

# User step schema
STEP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CLIENT_ID): str,
        vol.Required(CONF_CLIENT_SECRET): str,
        vol.Required(CONF_LATITUDE): vol.All(
            vol.Coerce(float), vol.Range(min=UK_LAT_MIN, max=UK_LAT_MAX)
        ),
        vol.Required(CONF_LONGITUDE): vol.All(
            vol.Coerce(float), vol.Range(min=UK_LON_MIN, max=UK_LON_MAX)
        ),
        vol.Required(CONF_RADIUS, default=DEFAULT_RADIUS): vol.All(
            vol.Coerce(float), vol.Range(min=MIN_RADIUS_MILES, max=MAX_RADIUS_MILES)
        ),
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL_MINUTES): vol.All(
            vol.Coerce(int),
            vol.Range(min=MIN_SCAN_INTERVAL_MINUTES, max=MAX_SCAN_INTERVAL_MINUTES),
        ),
    }
)


class UKFuelPricesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for UK Fuel Prices."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        # Only allow single instance
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate client credentials are not empty
            if not user_input[CONF_CLIENT_ID].strip():
                errors[CONF_CLIENT_ID] = "invalid_client_id"
            if not user_input[CONF_CLIENT_SECRET].strip():
                errors[CONF_CLIENT_SECRET] = "invalid_client_secret"

            # Validate coordinates are reasonable for UK
            lat = float(user_input[CONF_LATITUDE])
            lon = float(user_input[CONF_LONGITUDE])

            if not (UK_LAT_MIN <= lat <= UK_LAT_MAX):
                errors[CONF_LATITUDE] = "invalid_latitude_uk"
            if not (UK_LON_MIN <= lon <= UK_LON_MAX):
                errors[CONF_LONGITUDE] = "invalid_longitude_uk"

            if not errors:
                return self.async_create_entry(
                    title="UK Fuel Prices",
                    data={
                        CONF_CLIENT_ID: user_input[CONF_CLIENT_ID].strip(),
                        CONF_CLIENT_SECRET: user_input[CONF_CLIENT_SECRET].strip(),
                        CONF_LATITUDE: lat,
                        CONF_LONGITUDE: lon,
                        CONF_RADIUS: float(user_input[CONF_RADIUS]),
                        CONF_SCAN_INTERVAL: int(
                            user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES)
                        ),
                    },
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_SCHEMA, errors=errors
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return UKFuelPricesOptionsFlow(config_entry)


class UKFuelPricesOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for UK Fuel Prices."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate client credentials are not empty
            if not user_input[CONF_CLIENT_ID].strip():
                errors[CONF_CLIENT_ID] = "invalid_client_id"
            if not user_input[CONF_CLIENT_SECRET].strip():
                errors[CONF_CLIENT_SECRET] = "invalid_client_secret"

            # Validate coordinates are reasonable for UK
            lat = float(user_input[CONF_LATITUDE])
            lon = float(user_input[CONF_LONGITUDE])

            if not (UK_LAT_MIN <= lat <= UK_LAT_MAX):
                errors[CONF_LATITUDE] = "invalid_latitude_uk"
            if not (UK_LON_MIN <= lon <= UK_LON_MAX):
                errors[CONF_LONGITUDE] = "invalid_longitude_uk"

            if not errors:
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_CLIENT_ID: user_input[CONF_CLIENT_ID].strip(),
                        CONF_CLIENT_SECRET: user_input[CONF_CLIENT_SECRET].strip(),
                        CONF_LATITUDE: lat,
                        CONF_LONGITUDE: lon,
                        CONF_RADIUS: float(user_input[CONF_RADIUS]),
                        CONF_SCAN_INTERVAL: int(
                            user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES)
                        ),
                    },
                )

        # Get current values
        data = {**self.entry.data, **self.entry.options}

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_CLIENT_ID, default=data.get(CONF_CLIENT_ID, "")
                ): str,
                vol.Required(
                    CONF_CLIENT_SECRET, default=data.get(CONF_CLIENT_SECRET, "")
                ): str,
                vol.Required(
                    CONF_LATITUDE, default=float(data.get(CONF_LATITUDE, 0.0))
                ): vol.All(
                    vol.Coerce(float), vol.Range(min=UK_LAT_MIN, max=UK_LAT_MAX)
                ),
                vol.Required(
                    CONF_LONGITUDE, default=float(data.get(CONF_LONGITUDE, 0.0))
                ): vol.All(
                    vol.Coerce(float), vol.Range(min=UK_LON_MIN, max=UK_LON_MAX)
                ),
                vol.Required(
                    CONF_RADIUS, default=float(data.get(CONF_RADIUS, DEFAULT_RADIUS))
                ): vol.All(
                    vol.Coerce(float),
                    vol.Range(min=MIN_RADIUS_MILES, max=MAX_RADIUS_MILES),
                ),
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=int(data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES)),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL_MINUTES, max=MAX_SCAN_INTERVAL_MINUTES),
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
