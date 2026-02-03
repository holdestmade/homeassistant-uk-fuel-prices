from __future__ import annotations

DOMAIN = "uk_fuel_prices"

CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_RADIUS = "radius"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_RADIUS = 10.0
DEFAULT_SCAN_INTERVAL_MINUTES = 15

ATTR_BEST_E10 = "best_e10"
ATTR_BEST_B7 = "best_b7"
ATTR_STATIONS = "stations"
ATTR_LAST_UPDATE = "last_update"

STORE_VERSION = 1
STORE_KEY = f"{DOMAIN}_store"

SERVICE_REFRESH_STATIONS = "refresh_stations"
SERVICE_FIELD_ENTRY_ID = "entry_id"
