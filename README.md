# UK Fuel Prices Home Assistant Integration

A Home Assistant custom integration that pulls live UK fuel prices from the UK Government Fuel Finder API https://www.developer.fuel-finder.service.gov.uk/access-latest-fuelprices. It tracks nearby stations within a configurable radius and exposes sensors for the cheapest petrol (E10) and diesel (B7) prices.

## Features

- Finds nearby fuel stations within a configurable radius.
- Tracks cheapest E10 petrol and B7 diesel prices.
- Provides station list metadata (postcode, distance, opening hours).
- Manual refresh button/service for station discovery.

## Installation

### Manual

1. Copy the `custom_components/uk_fuel_prices` directory into your Home Assistant `custom_components` directory.
2. Restart Home Assistant.

## Configuration

This integration is configured via the UI.

1. Go to **Settings** → **Devices & Services** → **Add Integration**.
2. Search for **UK Fuel Prices**.
3. Enter the following:
   - **Client ID** and **Client Secret** from the UK Government Fuel Finder API.
   - **Latitude** and **Longitude** for the search center.
   - **Radius** (miles) to search for stations (default: 10).
   - **Scan interval** (minutes) for updates (default: 15).

You can update these options later from the integration options menu.

## Entities

- **Nearby fuel stations**: Count of stations within range.
- **Cheapest petrol (E10) price**: Lowest E10 price (pence).
- **Cheapest diesel (B7) price**: Lowest B7 price (pence).
- **Cheapest petrol (E10) station**: Station name with cheapest E10 price.
- **Cheapest diesel station**: Station name with cheapest B7 price.
- **Stations** (diagnostic): List of stations and price metadata.
- **Last update** (diagnostic): Timestamp of the last refresh.
- **Refresh stations** button: Forces a station list refresh.

## Services

- `uk_fuel_prices.refresh_stations`
  - Optional field: `entry_id` (only required if multiple entries exist).

## Data Source

This integration uses the UK Government Fuel Finder API: https://www.fuel-finder.service.gov.uk
