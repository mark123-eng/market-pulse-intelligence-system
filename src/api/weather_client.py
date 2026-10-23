"""
Market Pulse weather client.

Retrieves current weather observations from the Open-Meteo API,
validates the response, and returns a normalized dictionary.
"""

from datetime import datetime
from typing import Any

import requests


API_URL = "https://api.open-meteo.com/v1/forecast"

NAIROBI = {
    "latitude": -1.2864,
    "longitude": 36.8172,
    "timezone": "Africa/Nairobi",
}


class WeatherAPIError(Exception):
    """Raised when the weather API request or response is invalid."""


def fetch_current_weather(
    latitude: float = NAIROBI["latitude"],
    longitude: float = NAIROBI["longitude"],
    timezone: str = NAIROBI["timezone"],
) -> dict[str, Any]:
    """
    Fetch and validate current weather for a location.

    Returns:
        A normalized dictionary containing location, time,
        temperature, precipitation, and wind speed.

    Raises:
        WeatherAPIError: If the request fails or the response is invalid.
    """

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": [
            "temperature_2m",
            "precipitation",
            "wind_speed_10m",
        ],
        "timezone": timezone,
    }

    try:
        response = requests.get(
            API_URL,
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()

    except requests.RequestException as exc:
        raise WeatherAPIError(
            f"Weather API request failed: {exc}"
        ) from exc

    except ValueError as exc:
        raise WeatherAPIError(
            "Weather API returned invalid JSON."
        ) from exc

    try:
        current = payload["current"]

        observation_time = current["time"]
        temperature = float(current["temperature_2m"])
        precipitation = float(current["precipitation"])
        wind_speed = float(current["wind_speed_10m"])

        returned_latitude = float(payload["latitude"])
        returned_longitude = float(payload["longitude"])

    except (KeyError, TypeError, ValueError) as exc:
        raise WeatherAPIError(
            f"Weather API response is missing valid required fields: {exc}"
        ) from exc

    # Check that the timestamp follows the expected date-time format.
    try:
        datetime.fromisoformat(observation_time)
    except (TypeError, ValueError) as exc:
        raise WeatherAPIError(
            f"Invalid weather observation timestamp: {observation_time}"
        ) from exc

    # Reject impossible negative precipitation or wind values.
    if precipitation < 0:
        raise WeatherAPIError("Precipitation cannot be negative.")

    if wind_speed < 0:
        raise WeatherAPIError("Wind speed cannot be negative.")

    return {
        "latitude": returned_latitude,
        "longitude": returned_longitude,
        "timezone": timezone,
        "observation_time": observation_time,
        "temperature_c": temperature,
        "precipitation_mm": precipitation,
        "wind_speed_kmh": wind_speed,
        "source": "Open-Meteo",
    }


if __name__ == "__main__":
    try:
        weather = fetch_current_weather()

        print("MARKET PULSE — CURRENT WEATHER")
        print("-" * 40)

        for key, value in weather.items():
            print(f"{key}: {value}")

    except WeatherAPIError as error:
        print(f"Weather retrieval failed: {error}")
        raise SystemExit(1)
