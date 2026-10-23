"""Fetch weather data and store it in the Market Pulse SQLite database."""

import logging

from src.api.weather_client import fetch_current_weather
from src.storage.database import (
    DATABASE_PATH,
    get_weather_count,
    save_weather_observation,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


def main() -> None:
    """Fetch one weather observation and save it to SQLite."""
    print("\nMARKET PULSE — WEATHER COLLECTION")
    print("-" * 40)

    try:
        observation = fetch_current_weather(
            latitude=-1.2864,
            longitude=36.8172,
            timezone="Africa/Nairobi",
        )

        inserted = save_weather_observation(
            observation,
            database_path=DATABASE_PATH,
        )

        print(f"Observation time: {observation['observation_time']}")
        print(f"Temperature: {observation['temperature_c']} °C")
        print(f"Precipitation: {observation['precipitation_mm']} mm")
        print(f"Wind speed: {observation['wind_speed_kmh']} km/h")
        print(f"New observation saved: {inserted}")
        print(f"Weather records in database: {get_weather_count()}")

    except Exception as exc:
        logger.error("Weather collection failed: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
