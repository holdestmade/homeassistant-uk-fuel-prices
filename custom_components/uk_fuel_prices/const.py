"""Constants for the UK Fuel Prices integration."""
from __future__ import annotations

DOMAIN = "uk_fuel_prices"

# Configuration keys
CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_RADIUS = "radius"
CONF_SCAN_INTERVAL = "scan_interval"

# Default values
DEFAULT_RADIUS = 10.0
DEFAULT_SCAN_INTERVAL_MINUTES = 15

# UK geographical bounds for validation
UK_LAT_MIN = 49.9
UK_LAT_MAX = 60.9
UK_LON_MIN = -8.65
UK_LON_MAX = 1.77

# API limits
MAX_RADIUS_MILES = 50.0
MIN_RADIUS_MILES = 0.1
MIN_SCAN_INTERVAL_MINUTES = 5
MAX_SCAN_INTERVAL_MINUTES = 720

# Attribute keys
ATTR_BEST_E10 = "best_e10"
ATTR_BEST_E5 = "best_e5"
ATTR_BEST_B7 = "best_b7"
ATTR_STATIONS = "stations"
ATTR_LAST_UPDATE = "last_update"

# Storage
STORE_VERSION = 1
STORE_KEY = f"{DOMAIN}_store"

# Services
SERVICE_REFRESH_STATIONS = "refresh_stations"
SERVICE_FIELD_ENTRY_ID = "entry_id"

# Fuel types
FUEL_TYPE_E10 = "E10"
FUEL_TYPE_E5 = "E5"
FUEL_TYPE_B7 = "B7_STANDARD"

# API configuration
API_TIMEOUT_SECONDS = 30
API_MAX_RETRIES = 6
API_BACKOFF_BASE = 1.6
API_BACKOFF_JITTER = 0.5
TOKEN_REFRESH_BUFFER_SECONDS = 30

# Station cache validity (in hours)
STATION_CACHE_VALIDITY_HOURS = 24
