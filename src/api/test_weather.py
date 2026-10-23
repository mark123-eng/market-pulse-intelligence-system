import requests

API_URL = "https://api.open-meteo.com/v1/forecast"

params = {
    "latitude": -1.2864,
    "longitude": 36.8172,
    "current": [
        "temperature_2m",
        "precipitation",
        "wind_speed_10m",
    ],
    "timezone": "Africa/Nairobi",
}

try:
    response = requests.get(
        API_URL,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    weather_data = response.json()

    print("API connection successful!")
    print("\nLocation:")
    print(f"Latitude: {weather_data['latitude']}")
    print(f"Longitude: {weather_data['longitude']}")

    print("\nCurrent weather:")
    print(weather_data["current"])

except requests.RequestException as error:
    print(f"API request failed: {error}")

except (KeyError, ValueError) as error:
    print(f"Unexpected API response: {error}")