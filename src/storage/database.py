"""
Market Pulse Intelligence System — SQLite database layer.

Responsibilities:
- Create and initialize database tables.
- Import validated World Bank project records from CSV.
- Store weather observations from Open-Meteo.
- Prevent duplicate project and weather records.
- Provide database query helpers.
- Close database connections reliably.
"""

import csv
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


# ---------------------------------------------------------
# PATH CONFIGURATION
# ---------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIRECTORY = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIRECTORY / "market_pulse.db"

WORLD_BANK_CSV_PATH = (
    DATA_DIRECTORY / "processed" / "world_bank_projects.csv"
)


# ---------------------------------------------------------
# DATABASE CONNECTION MANAGEMENT
# ---------------------------------------------------------

@contextmanager
def get_connection(
    database_path: Path | str = DATABASE_PATH,
) -> Iterator[sqlite3.Connection]:
    """
    Open a SQLite connection and always close it.

    Successful operations are committed.
    Failed operations are rolled back.

    The finally block ensures the connection is closed,
    including when an exception occurs.
    """
    database_path = Path(database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(str(database_path))
    connection.row_factory = sqlite3.Row

    try:
        connection.execute("PRAGMA foreign_keys = ON")

        yield connection

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


# ---------------------------------------------------------
# DATABASE INITIALIZATION
# ---------------------------------------------------------

def initialize_database(
    database_path: Path | str = DATABASE_PATH,
) -> None:
    """
    Create the database tables if they do not already exist.
    """
    with get_connection(database_path) as connection:

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS world_bank_projects (
                project_id TEXT PRIMARY KEY,
                project_name TEXT NOT NULL,
                country TEXT NOT NULL,
                country_full_name TEXT,
                project_status TEXT,
                approval_date TEXT,
                closing_date TEXT,
                project_abstract TEXT,
                project_url TEXT,
                source TEXT,
                extracted_at_utc TEXT
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS weather_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                timezone TEXT NOT NULL,
                observation_time TEXT NOT NULL,
                temperature_c REAL,
                precipitation_mm REAL,
                wind_speed_kmh REAL,
                source TEXT NOT NULL,

                UNIQUE (
                    latitude,
                    longitude,
                    observation_time,
                    source
                )
            )
            """
        )


# ---------------------------------------------------------
# DATA CLEANING HELPERS
# ---------------------------------------------------------

def _clean_value(value):
    """
    Convert blank strings and common missing-value markers
    to None so that SQLite stores them as NULL.
    """
    if value is None:
        return None

    if isinstance(value, str):
        value = value.strip()

        if value.lower() in {
            "",
            "nan",
            "none",
            "null",
            "nat",
        }:
            return None

    return value


def _require_fields(
    record: dict,
    required_fields: tuple[str, ...],
    record_type: str,
) -> None:
    """
    Check that required fields exist and are not empty.
    """
    missing_fields = []

    for field in required_fields:
        value = _clean_value(record.get(field))

        if value is None:
            missing_fields.append(field)

    if missing_fields:
        raise ValueError(
            f"{record_type} is missing required fields: "
            f"{', '.join(missing_fields)}"
        )


# ---------------------------------------------------------
# WORLD BANK PROJECT IMPORT
# ---------------------------------------------------------

def import_world_bank_csv(
    csv_path: Path | str = WORLD_BANK_CSV_PATH,
    database_path: Path | str = DATABASE_PATH,
) -> int:
    """
    Import World Bank projects from a CSV file into SQLite.

    Records are inserted using project_id as the unique key.
    Reimporting a project updates its existing record rather
    than creating a duplicate.

    Missing values, including project_status, remain NULL.
    No missing status is fabricated from the API filter.

    Returns:
        Number of valid CSV records processed.
    """
    csv_path = Path(csv_path)

    if not csv_path.exists():
        raise FileNotFoundError(
            f"World Bank CSV file was not found: {csv_path}"
        )

    initialize_database(database_path)

    fields = (
        "project_id",
        "project_name",
        "country",
        "country_full_name",
        "project_status",
        "approval_date",
        "closing_date",
        "project_abstract",
        "project_url",
        "source",
        "extracted_at_utc",
    )

    required_fields = (
        "project_id",
        "project_name",
        "country",
    )

    processed_count = 0

    with csv_path.open(
        mode="r",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:

        reader = csv.DictReader(csv_file)

        if not reader.fieldnames:
            raise ValueError(
                "The World Bank CSV file has no header row."
            )

        missing_columns = [
            field
            for field in required_fields
            if field not in reader.fieldnames
        ]

        if missing_columns:
            raise ValueError(
                "The World Bank CSV is missing required columns: "
                + ", ".join(missing_columns)
            )

        with get_connection(database_path) as connection:

            for row_number, row in enumerate(reader, start=2):

                cleaned_record = {
                    field: _clean_value(row.get(field))
                    for field in fields
                }

                try:
                    _require_fields(
                        cleaned_record,
                        required_fields,
                        f"World Bank CSV row {row_number}",
                    )

                except ValueError as error:
                    raise ValueError(
                        f"Invalid World Bank CSV row {row_number}: "
                        f"{error}"
                    ) from error

                connection.execute(
                    """
                    INSERT INTO world_bank_projects (
                        project_id,
                        project_name,
                        country,
                        country_full_name,
                        project_status,
                        approval_date,
                        closing_date,
                        project_abstract,
                        project_url,
                        source,
                        extracted_at_utc
                    )
                    VALUES (
                        :project_id,
                        :project_name,
                        :country,
                        :country_full_name,
                        :project_status,
                        :approval_date,
                        :closing_date,
                        :project_abstract,
                        :project_url,
                        :source,
                        :extracted_at_utc
                    )
                    ON CONFLICT(project_id)
                    DO UPDATE SET
                        project_name = excluded.project_name,
                        country = excluded.country,
                        country_full_name = excluded.country_full_name,
                        project_status = excluded.project_status,
                        approval_date = excluded.approval_date,
                        closing_date = excluded.closing_date,
                        project_abstract = excluded.project_abstract,
                        project_url = excluded.project_url,
                        source = excluded.source,
                        extracted_at_utc = excluded.extracted_at_utc
                    """,
                    cleaned_record,
                )

                processed_count += 1

    return processed_count


# ---------------------------------------------------------
# WEATHER OBSERVATION STORAGE
# ---------------------------------------------------------

def save_weather_observation(
    observation: dict,
    database_path: Path | str = DATABASE_PATH,
) -> bool:
    """
    Save a weather observation to SQLite.

    Required fields:
        latitude, longitude, timezone, observation_time, source

    Optional measurements:
        temperature_c, precipitation_mm, wind_speed_kmh

    Returns:
        True  - a new observation was inserted.
        False - the same observation already existed.

    Raises:
        TypeError: if observation is not a dictionary.
        ValueError: if required fields are missing or invalid.
    """
    if not isinstance(observation, dict):
        raise TypeError(
            "Weather observation must be provided as a dictionary."
        )

    required_fields = (
        "latitude",
        "longitude",
        "timezone",
        "observation_time",
        "source",
    )

    cleaned = {
        key: _clean_value(value)
        for key, value in observation.items()
    }

    _require_fields(
        cleaned,
        required_fields,
        "Weather observation",
    )

    # Validate coordinates before inserting.
    try:
        latitude = float(cleaned["latitude"])
        longitude = float(cleaned["longitude"])

    except (TypeError, ValueError) as error:
        raise ValueError(
            "Weather latitude and longitude must be numeric."
        ) from error

    if not -90 <= latitude <= 90:
        raise ValueError(
            "Weather latitude must be between -90 and 90."
        )

    if not -180 <= longitude <= 180:
        raise ValueError(
            "Weather longitude must be between -180 and 180."
        )

    # Validate optional measurements when they are provided.
    measurement_fields = (
        "temperature_c",
        "precipitation_mm",
        "wind_speed_kmh",
    )

    for field in measurement_fields:
        value = cleaned.get(field)

        if value is not None:
            try:
                cleaned[field] = float(value)

            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Weather field '{field}' must be numeric "
                    "or None."
                ) from error

    cleaned["latitude"] = latitude
    cleaned["longitude"] = longitude

    initialize_database(database_path)

    with get_connection(database_path) as connection:

        cursor = connection.execute(
            """
            INSERT INTO weather_observations (
                latitude,
                longitude,
                timezone,
                observation_time,
                temperature_c,
                precipitation_mm,
                wind_speed_kmh,
                source
            )
            VALUES (
                :latitude,
                :longitude,
                :timezone,
                :observation_time,
                :temperature_c,
                :precipitation_mm,
                :wind_speed_kmh,
                :source
            )
            ON CONFLICT (
                latitude,
                longitude,
                observation_time,
                source
            )
            DO NOTHING
            """,
            {
                "latitude": cleaned["latitude"],
                "longitude": cleaned["longitude"],
                "timezone": cleaned["timezone"],
                "observation_time": cleaned["observation_time"],
                "temperature_c": cleaned.get("temperature_c"),
                "precipitation_mm": cleaned.get("precipitation_mm"),
                "wind_speed_kmh": cleaned.get("wind_speed_kmh"),
                "source": cleaned["source"],
            },
        )

        return cursor.rowcount == 1


# ---------------------------------------------------------
# DATABASE QUERY HELPERS
# ---------------------------------------------------------

def get_project_count(
    database_path: Path | str = DATABASE_PATH,
) -> int:
    """Return the total number of stored World Bank projects."""
    initialize_database(database_path)

    with get_connection(database_path) as connection:
        result = connection.execute(
            "SELECT COUNT(*) FROM world_bank_projects"
        ).fetchone()

        return int(result[0])


def get_weather_count(
    database_path: Path | str = DATABASE_PATH,
) -> int:
    """Return the total number of stored weather observations."""
    initialize_database(database_path)

    with get_connection(database_path) as connection:
        result = connection.execute(
            "SELECT COUNT(*) FROM weather_observations"
        ).fetchone()

        return int(result[0])


def get_recent_weather(
    limit: int = 10,
    database_path: Path | str = DATABASE_PATH,
) -> list[dict]:
    """
    Return the most recent weather observations.

    Results are returned as a list of dictionaries.
    """
    if limit < 1:
        raise ValueError("Limit must be at least 1.")

    initialize_database(database_path)

    with get_connection(database_path) as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                latitude,
                longitude,
                timezone,
                observation_time,
                temperature_c,
                precipitation_mm,
                wind_speed_kmh,
                source
            FROM weather_observations
            ORDER BY observation_time DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        return [dict(row) for row in rows]


def get_recent_projects(
    limit: int = 10,
    database_path: Path | str = DATABASE_PATH,
) -> list[dict]:
    """Return recently extracted World Bank projects."""
    if limit < 1:
        raise ValueError("Limit must be at least 1.")

    initialize_database(database_path)

    with get_connection(database_path) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM world_bank_projects
            ORDER BY extracted_at_utc DESC, project_id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        return [dict(row) for row in rows]


# ---------------------------------------------------------
# COMMAND-LINE ENTRY POINT
# ---------------------------------------------------------

def main() -> None:
    """
    Initialize the database and import World Bank project data.
    """
    print("=" * 55)
    print("MARKET PULSE — DATABASE INITIALIZATION")
    print("=" * 55)

    initialize_database()

    print(f"Database: {DATABASE_PATH}")

    if WORLD_BANK_CSV_PATH.exists():
        imported_count = import_world_bank_csv()

        print(
            "World Bank CSV records processed: "
            f"{imported_count}"
        )
    else:
        print(
            "World Bank CSV not found; database tables "
            "were initialized without importing projects."
        )

    print(f"Projects stored: {get_project_count()}")
    print(f"Weather records stored: {get_weather_count()}")
    print("Database operation completed successfully.")


if __name__ == "__main__":
    main()
