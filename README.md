# UK Fuel Prices Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub release](https://img.shields.io/github/release/holdestmade/homeassistant-uk-fuel-prices.svg)](https://github.com/holdestmade/homeassistant-uk-fuel-prices/releases)

A Home Assistant custom integration that pulls live UK fuel prices from the UK Government Fuel Finder API. It tracks nearby stations within a configurable radius and exposes sensors for the cheapest petrol (E10) and diesel (B7) prices.

NOTE: Enhanced and Optimised with Claude.ai

## Features

- 🔍 Finds nearby fuel stations within a configurable radius
- 💰 Tracks cheapest E10 petrol and B7 diesel prices
- 📍 Provides station list metadata (postcode, distance, opening hours)
- 🔄 Smart caching - stations cached until location changes, prices updated incrementally
- 🔐 Automatic OAuth2 token refresh with fallback to cached data
- 📊 Proper Home Assistant sensor entities with device classes and units
- 🔘 Manual refresh button and service for on-demand updates
- 🛡️ Robust error handling with graceful degradation

## Prerequisites

You need API credentials from the UK Government Fuel Finder service:

1. Visit [UK Government Fuel Finder Developer Portal](https://www.developer.fuel-finder.service.gov.uk/access-latest-fuelprices)
2. Register for an account
3. Create an application to get your **Client ID** and **Client Secret**

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Click on the three dots in the top right corner
3. Select **Custom repositories**
4. Add this repository URL: `https://github.com/holdestmade/homeassistant-uk-fuel-prices`
5. Select **Integration** as the category
6. Click **Add**
7. Click **Install** on the UK Fuel Prices integration
8. Restart Home Assistant

### Manual Installation

1. Download the [latest release](https://github.com/holdestmade/homeassistant-uk-fuel-prices/releases)
2. Extract the `custom_components/uk_fuel_prices` directory
3. Copy it to your Home Assistant `custom_components` directory
4. Restart Home Assistant

## Configuration

This integration is configured via the Home Assistant UI with built-in validation.

### Setup Steps

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **UK Fuel Prices**
3. Enter your configuration:
   - **Client ID**: Your API client ID from the Fuel Finder portal
   - **Client Secret**: Your API client secret from the Fuel Finder portal
   - **Latitude**: Center point for station search (must be within UK: 49.9 to 60.9)
   - **Longitude**: Center point for station search (must be within UK: -8.65 to 1.77)
   - **Radius**: Search radius in miles (0.1 to 50, default: 10)
   - **Scan Interval**: Update frequency in minutes (5 to 720, default: 15)

### Updating Configuration

You can update these settings anytime:

1. Go to **Settings** → **Devices & Services**
2. Find **UK Fuel Prices** and click **Configure**
3. Modify any settings and click **Submit**

**Note**: Changing latitude, longitude, or radius will trigger a full station refresh on the next update.

### Tips for Best Results

- **Latitude/Longitude**: Use your home coordinates for most relevant results
- **Radius**: Smaller radius = faster updates, larger radius = more stations
- **Scan Interval**: 
  - Minimum 5 minutes (API rate limiting)
  - 15-30 minutes recommended for daily use
  - Prices typically update once per day in early morning

## Entities

Once configured, the integration creates the following entities:

### Primary Sensors

- **Cheapest petrol (E10) price** (`sensor.uk_fuel_prices_cheapest_e10_price`)
  - State: Price in pence (p)
  - Attributes: Station name, postcode, distance, last update
  - Device class: Monetary
  
- **Cheapest diesel (B7) price** (`sensor.uk_fuel_prices_cheapest_b7_price`)
  - State: Price in pence (p)
  - Attributes: Station name, postcode, distance, last update
  - Device class: Monetary

### Diagnostic Sensors

- **Nearby fuel stations** (`sensor.uk_fuel_prices_nearby_fuel_stations`)
  - State: Count of stations within configured radius
  - Attributes: Last update timestamp

- **Cheapest petrol (E10) station** (`sensor.uk_fuel_prices_cheapest_e10_station`)
  - State: Station name with cheapest E10
  - Attributes: Price, postcode, distance, last update

- **Cheapest diesel station** (`sensor.uk_fuel_prices_cheapest_b7_station`)
  - State: Station name with cheapest B7
  - Attributes: Price, postcode, distance, last update

- **Stations** (`sensor.uk_fuel_prices_stations`)
  - State: Count of stations with price data
  - Attributes: Complete list of all stations with prices, postcodes, distances, and opening hours

- **Last update** (`sensor.uk_fuel_prices_last_update`)
  - State: Timestamp of last successful update
  - Device class: Timestamp

### Button

- **Refresh stations** (`button.uk_fuel_prices_refresh_stations`)
  - Forces a complete refresh of the station list (ignores cache)
  - Useful after moving location or when new stations open

## Services

### `uk_fuel_prices.refresh_stations`

Forces a complete refresh of the station list, ignoring the cache. Useful when:
- You've moved to a new location
- New stations have opened in your area
- You want to ensure you have the latest station data

**Parameters:**
- `entry_id` (optional): The config entry ID to refresh. Only needed if you have multiple instances configured.

**Examples:**

```yaml
# Refresh the default instance
service: uk_fuel_prices.refresh_stations

# Refresh a specific instance
service: uk_fuel_prices.refresh_stations
data:
  entry_id: "01234567890abcdef"
```

**Automation Example:**

```yaml
# Refresh stations every Sunday at 3 AM
automation:
  - alias: "Weekly Fuel Station Refresh"
    trigger:
      - platform: time
        at: "03:00:00"
    condition:
      - condition: time
        weekday:
          - sun
    action:
      - service: uk_fuel_prices.refresh_stations
```

## Data Source

This integration uses the UK Government Fuel Finder API: https://www.fuel-finder.service.gov.uk

**API Information:**
- Official UK Government service
- Real-time fuel price data from participating stations
- Updated regularly (typically daily)
- Requires free API credentials

## How It Works

### Smart Caching Strategy

The integration uses an intelligent caching system to minimize API calls:

1. **Station List**: Cached until your location or radius changes
   - Stations don't change frequently, so this reduces unnecessary API calls
   - Use the refresh button to manually update if needed

2. **Price Data**: Updated incrementally
   - Only fetches prices that have changed since the last update
   - Merges new data with cached prices for complete coverage

3. **Token Management**: Automatic OAuth2 token refresh
   - Tokens are cached and automatically refreshed before expiry
   - Falls back to cached data if API is temporarily unavailable

### Error Handling

The integration is designed to be resilient:

- **API Failures**: Falls back to cached data to keep sensors working
- **Authentication Errors**: Triggers Home Assistant's reauth flow
- **Rate Limiting**: Automatically retries with exponential backoff
- **Network Issues**: Comprehensive logging to help diagnose problems

## Troubleshooting

### Integration Not Loading

1. Check Home Assistant logs for errors: **Settings** → **System** → **Logs**
2. Verify your API credentials are correct
3. Ensure your Home Assistant can reach the internet
4. Try restarting Home Assistant

### No Stations Found

1. Verify your latitude/longitude are correct (must be within UK)
2. Check your radius isn't too small
3. Ensure there are fuel stations in your area
4. Click the "Refresh stations" button to force an update

### Prices Not Updating

1. Check the "Last update" sensor to see when data was last fetched
2. Verify your scan interval setting
3. Some stations may not report prices regularly
4. API may be temporarily unavailable (integration will use cached data)

### Authentication Errors

1. Verify your Client ID and Client Secret are correct
2. Check the API credentials haven't expired
3. Re-enter credentials via **Configure** in the integration settings
4. If needed, generate new credentials from the Fuel Finder portal

### Useful Log Commands

Enable debug logging by adding to `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.uk_fuel_prices: debug
```

## Limitations

- **Geographic Coverage**: UK only (coordinates validated to UK bounds)
- **Fuel Types**: Currently supports E10 petrol and B7 diesel only
- **Update Frequency**: Minimum 5-minute scan interval due to API rate limiting
- **Station Data**: Depends on stations reporting to the government API
- **Price Accuracy**: As accurate as the data provided by fuel stations

## Contributing

Contributions are welcome! Please feel free to:

1. Report bugs via [GitHub Issues](https://github.com/holdestmade/homeassistant-uk-fuel-prices/issues)
2. Submit pull requests with improvements
3. Suggest new features or enhancements
4. Improve documentation

## Support

- **Issues**: [GitHub Issues](https://github.com/holdestmade/homeassistant-uk-fuel-prices/issues)
- **Documentation**: [GitHub Repository](https://github.com/holdestmade/homeassistant-uk-fuel-prices)
- **API Documentation**: [UK Fuel Finder Developer Portal](https://www.developer.fuel-finder.service.gov.uk)

## License

This integration is provided as-is for use with Home Assistant.

## Acknowledgments

- UK Government for providing the Fuel Finder API
- Home Assistant community for development guidance
- https://phil-male.com/ for the initial python script
- All contributors and users providing feedback
