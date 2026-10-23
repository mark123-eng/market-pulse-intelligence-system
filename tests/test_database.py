"""
Unit tests for the Market Pulse SQLite database layer.

The tests use temporary database files so that they do not
modify the project's real market_pulse.db database.
"""

import csv
import tempfile
import unittest
from pathlib import Path

from src.storage.database import (
    get_connection,
    get_project_count,
    get_weather_count,
    import_world_bank_csv,
    initialize_database,
    save_weather_observation,
)


class TestMarketPulseDatabase(unittest.TestCase):
    """Test database initialization, imports, and weather storage."""

    def setUp(self):
        """
        Create a separate temporary directory and database
        for each test.
        """
        self.temp_directory = tempfile.TemporaryDirectory()

        self.temp_path = Path(self.temp_directory.name)
        self.database_path = self.temp_path / "test_market_pulse.db"
        self.csv_path = self.temp_path / "world_bank_projects.csv"

        initialize_database(self.database_path)

    def tearDown(self):
        """
        Clean up the temporary database after each test.

        get_connection() closes connections automatically,
        so Windows can safely remove the temporary directory.
        """
        self.temp_directory.cleanup()

    # -----------------------------------------------------
    # TEST 1: DATABASE INITIALIZATION
    # -----------------------------------------------------

    def test_database_initializes_with_empty_tables(self):
        """New tables should exist and initially contain no records."""
        self.assertEqual(
            get_project_count(self.database_path),
            0,
        )

        self.assertEqual(
            get_weather_count(self.database_path),
            0,
        )

        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            ).fetchall()

            table_names = {row["name"] for row in rows}

        self.assertIn("world_bank_projects", table_names)
        self.assertIn("weather_observations", table_names)

    # -----------------------------------------------------
    # TEST 2: WORLD BANK CSV IMPORT
    # -----------------------------------------------------

    def test_imports_world_bank_project_from_csv(self):
        """A valid World Bank project should be stored."""
        project = {
            "project_id": "TEST-KE-001",
            "project_name": "Kenya Test Infrastructure Project",
            "country": "KE",
            "country_full_name": "Kenya",
            "project_status": "Active",
            "approval_date": "2025-01-15",
            "closing_date": "2030-12-31",
            "project_abstract": "Test infrastructure project.",
            "project_url": "https://example.com/project",
            "source": "World Bank API",
            "extracted_at_utc": "2026-10-23T12:00:00Z",
        }

        fieldnames = list(project.keys())

        with self.csv_path.open(
            "w",
            encoding="utf-8",
            newline="",
        ) as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=fieldnames,
            )

            writer.writeheader()
            writer.writerow(project)

        processed_count = import_world_bank_csv(
            self.csv_path,
            self.database_path,
        )

        self.assertEqual(processed_count, 1)
        self.assertEqual(
            get_project_count(self.database_path),
            1,
        )

        with get_connection(self.database_path) as connection:
            stored_project = connection.execute(
                """
                SELECT *
                FROM world_bank_projects
                WHERE project_id = ?
                """,
                ("TEST-KE-001",),
            ).fetchone()

        self.assertIsNotNone(stored_project)
        self.assertEqual(
            stored_project["project_name"],
            "Kenya Test Infrastructure Project",
        )
        self.assertEqual(stored_project["country"], "KE")

    # -----------------------------------------------------
    # TEST 3: DUPLICATE PROJECT PREVENTION
    # -----------------------------------------------------

    def test_reimporting_project_does_not_duplicate_it(self):
        """
        Importing the same project ID twice must not create
        two database records.
        """
        project = {
            "project_id": "TEST-KE-002",
            "project_name": "Kenya Road Project",
            "country": "KE",
            "country_full_name": "Kenya",
            "project_status": "",
            "approval_date": "2025-02-01",
            "closing_date": "",
            "project_abstract": "",
            "project_url": "",
            "source": "World Bank API",
            "extracted_at_utc": "2026-10-23T12:00:00Z",
        }

        with self.csv_path.open(
            "w",
            encoding="utf-8",
            newline="",
        ) as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=list(project.keys()),
            )

            writer.writeheader()
            writer.writerow(project)

        first_import = import_world_bank_csv(
            self.csv_path,
            self.database_path,
        )

        second_import = import_world_bank_csv(
            self.csv_path,
            self.database_path,
        )

        self.assertEqual(first_import, 1)
        self.assertEqual(second_import, 1)

        # Both imports process one CSV row, but only one
        # project record should exist in the database.
        self.assertEqual(
            get_project_count(self.database_path),
            1,
        )

        with get_connection(self.database_path) as connection:
            stored_project = connection.execute(
                """
                SELECT project_status, closing_date
                FROM world_bank_projects
                WHERE project_id = ?
                """,
                ("TEST-KE-002",),
            ).fetchone()

        # Missing data must remain NULL, not fabricated.
        self.assertIsNone(stored_project["project_status"])
        self.assertIsNone(stored_project["closing_date"])

    # -----------------------------------------------------
    # TEST 4: WEATHER STORAGE
    # -----------------------------------------------------

    def test_saves_weather_observation(self):
        """A valid weather observation should be stored."""
        observation = {
            "latitude": -1.2864,
            "longitude": 36.8172,
            "timezone": "Africa/Nairobi",
            "observation_time": "2026-10-23T12:00",
            "temperature_c": 27.0,
            "precipitation_mm": 0.0,
            "wind_speed_kmh": 10.0,
            "source": "Open-Meteo",
        }

        saved = save_weather_observation(
            observation,
            self.database_path,
        )

        self.assertTrue(saved)

        self.assertEqual(
            get_weather_count(self.database_path),
            1,
        )

        with get_connection(self.database_path) as connection:
            stored_observation = connection.execute(
                """
                SELECT *
                FROM weather_observations
                WHERE observation_time = ?
                """,
                ("2026-10-23T12:00",),
            ).fetchone()

        self.assertIsNotNone(stored_observation)
        self.assertAlmostEqual(
            stored_observation["temperature_c"],
            27.0,
        )
        self.assertEqual(
            stored_observation["source"],
            "Open-Meteo",
        )

    # -----------------------------------------------------
    # TEST 5: DUPLICATE WEATHER PREVENTION
    # -----------------------------------------------------

    def test_prevents_duplicate_weather_observations(self):
        """
        Saving the same location, timestamp, and source twice
        should create only one database record.
        """
        observation = {
            "latitude": -1.2864,
            "longitude": 36.8172,
            "timezone": "Africa/Nairobi",
            "observation_time": "2026-10-23T13:00",
            "temperature_c": 28.0,
            "precipitation_mm": 0.2,
            "wind_speed_kmh": 12.0,
            "source": "Open-Meteo",
        }

        first_save = save_weather_observation(
            observation,
            self.database_path,
        )

        second_save = save_weather_observation(
            observation,
            self.database_path,
        )

        self.assertTrue(first_save)
        self.assertFalse(second_save)

        self.assertEqual(
            get_weather_count(self.database_path),
            1,
        )

    # -----------------------------------------------------
    # TEST 6: REQUIRED WEATHER FIELD VALIDATION
    # -----------------------------------------------------

    def test_rejects_weather_missing_required_fields(self):
        """
        An observation without a timestamp must be rejected.
        """
        observation = {
            "latitude": -1.2864,
            "longitude": 36.8172,
            "timezone": "Africa/Nairobi",
            "temperature_c": 27.0,
            "precipitation_mm": 0.0,
            "wind_speed_kmh": 10.0,
            "source": "Open-Meteo",
            # observation_time is intentionally missing.
        }

        with self.assertRaises(ValueError):
            save_weather_observation(
                observation,
                self.database_path,
            )

        self.assertEqual(
            get_weather_count(self.database_path),
            0,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
