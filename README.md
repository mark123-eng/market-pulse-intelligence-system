# Market Pulse Intelligence System

**A Python-based data pipeline for collecting, validating, processing, and storing development-project data and weather observations.**

Market Pulse explores API integration, batched data extraction, data validation, structured exports, SQLite storage, browser inspection, and automated testing.

> **Project status:** The World Bank API extraction and SQLite database workflows have been tested. Weather collection has succeeded in recorded runs, although external APIs can return temporary errors. Playwright work includes browser-inspection experiments; a complete production browser scraper for the World Bank search interface has not been verified as finished.

## Table of Contents

1. [Project Overview](#project-overview)
2. [Objectives](#objectives)
3. [Features](#features)
4. [Architecture and Data Flow](#architecture-and-data-flow)
5. [Data Sources](#data-sources)
6. [Technology Stack](#technology-stack)
7. [Project Structure](#project-structure)
8. [Database Design](#database-design)
9. [Installation and Setup](#installation-and-setup)
10. [Running the Application](#running-the-application)
11. [Automated Testing](#automated-testing)
12. [Web Scraping and Browser Automation](#web-scraping-and-browser-automation)
13. [Data Quality and Limitations](#data-quality-and-limitations)
14. [Troubleshooting](#troubleshooting)
15. [Security and Version Control](#security-and-version-control)
16. [Future Improvements](#future-improvements)
17. [Author](#author)

## Project Overview

Market Pulse collects information from external APIs and prepares it for structured storage and further analysis.

The project currently integrates two principal data sources:

* World Bank development project information.
* Open-Meteo weather observations for Nairobi, Kenya.

The system demonstrates practical data-engineering concepts, including extraction, validation, normalization, deduplication, file exports, database persistence, and automated testing.

## Objectives

* Retrieve structured data from external APIs.
* Implement batched extraction and basic retry handling.
* Validate required fields and normalize inconsistent records.
* Export data in CSV and JSON formats.
* Store project and weather records in SQLite.
* Prevent duplicate database records.
* Explore JavaScript-rendered websites with Playwright.
* Test database operations and document limitations.

## Features

### World Bank API extraction

The World Bank API module retrieves project records using configured country and project-status filters.

The extraction workflow supports:

* Batched requests.
* Retry handling and request delays.
* Data normalization and required-field validation.
* Duplicate project ID handling.
* CSV and JSON exports.
* Extraction metadata and logging.

A recorded run retrieved 37 records, with 37 valid records and no rejected records or duplicate project IDs removed. These figures describe that run, not a guarantee that every future API response will return the same records.

Some API response fields may be missing even when a filter is applied. Missing values are preserved rather than invented.

### Weather collection

The weather client retrieves current weather observations from Open-Meteo for configured coordinates.

The collector records measurements such as:

* Temperature in degrees Celsius.
* Precipitation in millimetres.
* Wind speed in kilometres per hour.
* Observation time.
* Location coordinates and timezone.

External service availability can affect collection. A failed request should not be interpreted as a valid weather observation.

### SQLite storage

The database module supports:

* Database initialization.
* World Bank project imports from CSV.
* Weather observation storage.
* Duplicate prevention.
* Required-field validation.
* Retrieval of stored records.
* Database record counts.

### Browser inspection

Playwright scripts explore the World Bank project-search interface and save diagnostic information.

The browser-based workflow is experimental. Its selectors and interactions may require maintenance when the website changes. A complete, reliably verified browser scraper is not claimed as a finished feature.

## Architecture and Data Flow

The intended workflow is:

1. Retrieve project or weather data from an external source.
2. Normalize the response into structured fields.
3. Validate required data and handle duplicates.
4. Export processed project records where applicable.
5. Store records in SQLite.
6. Run automated tests to verify supported database behavior.

## Data Sources

### World Bank

The API extraction module uses the World Bank projects API.

Endpoint:

`https://search.worldbank.org/api/v3/projects`

The extraction configuration targets Kenyan projects with an active-status filter. Actual returned fields and values depend on the API response.

### Open-Meteo

The weather client uses the Open-Meteo forecast API to obtain current weather information for configured coordinates.

The example location is Nairobi, Kenya.

## Technology Stack

* Python
* Requests and Python standard-library networking tools
* pandas
* Playwright
* SQLite
* JSON and CSV
* `unittest`

Installed dependency versions are recorded in `requirements.txt`.

## Project Structure

```text
MARKET PULSE/
├── .gitignore
├── README.md
├── requirements.txt
├── inspect_world_bank_api.py
├── data/
│   ├── raw/              # Generated diagnostic and raw files
│   ├── processed/        # Generated CSV and JSON exports
│   └── market_pulse.db   # Local SQLite database
├── logs/                 # Generated logs
├── src/
│   ├── api/
│   │   ├── collect_weather.py
│   │   ├── test_weather.py
│   │   └── weather_client.py
│   ├── scrapers/
│   │   ├── scrapers.py
│   │   └── world_bank_api.py
│   └── storage/
│       └── database.py
└── tests/
    └── test_database.py
```

Additional exploratory scripts may be present locally and are not necessarily part of the final published structure.

## Database Design

The SQLite database contains two principal tables:

### `world_bank_projects`

Stores normalized project information, including project identifiers, names, country details, dates, abstracts, status, URLs, source information, and extraction timestamps where available.

The project identifier is used to prevent duplicate project records.

### `weather_observations`

Stores weather measurements alongside coordinates, observation time, timezone, and source.

A uniqueness constraint prevents duplicate observations with the same location, timestamp, and source.

## Installation and Setup

### Requirements

* A supported Python installation.
* Git for version control.
* Internet access for external API requests.
* A Chromium installation supported by Playwright if browser inspection is required.

### Create a virtual environment

From the project root, run:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### Install dependencies

```powershell
python -m pip install -r requirements.txt
```

If you need to use Playwright's Chromium browser, install its browser binary:

```powershell
python -m playwright install chromium
```

### Verify dependencies

```powershell
python -m pip check
```

## Running the Application

Run commands from the project root.

### Extract World Bank project data

```powershell
python -m src.scrapers.world_bank_api
```

This module retrieves, validates, and exports project data using the configured API workflow.

### Initialize the database and import project data

```powershell
python -m src.storage.database
```

The database module initializes the tables and imports the processed World Bank CSV when available.

### Collect weather observations

```powershell
python -m src.api.collect_weather
```

This retrieves a weather observation and attempts to store it in SQLite.

External APIs may occasionally return errors. Check the terminal output and logs when a request fails.

### Explore the browser-based scraper

```powershell
python src/scrapers/scrapers.py
```

This script uses Playwright to explore the World Bank project-search interface. Its results depend on the website's current behavior and the selectors implemented in the script.

## Automated Testing

Run the database tests with:

```powershell
python -m unittest discover -s tests -v
```

The current test suite covers:

* Database initialization.
* Importing a valid World Bank project.
* Preventing duplicate project records.
* Saving a valid weather observation.
* Preventing duplicate weather observations.
* Rejecting weather observations that lack required fields.

The six database tests passed in a recorded run. Run them again after making changes to confirm the current state.

## Web Scraping and Browser Automation

The project contains both API-based extraction and Playwright browser-inspection code.

These approaches serve different purposes:

* API extraction works with structured responses from the World Bank API.
* Browser inspection explores the JavaScript-rendered project-search interface.

The browser interface can change, and successful page loading alone does not establish that all records were extracted correctly. Verify selectors, pagination, extracted fields, and output quality before relying on browser results.

## Data Quality and Limitations

* API fields may be absent or inconsistent.
* External APIs may be temporarily unavailable.
* Weather values describe specific observation times, not permanent conditions.
* Browser selectors may break when the target website changes.
* The current automated tests primarily verify database behavior.
* A complete end-to-end workflow and production browser scraper have not been fully verified.

Missing source values should remain missing unless reliable evidence supports a correction.

## Troubleshooting

### Dependency problems

```powershell
python -m pip check
```

If dependencies are missing, reinstall them using `requirements.txt`.

### Test failures

```powershell
python -m unittest discover -s tests -v
```

Review the failing test and its traceback before changing application code.

### Weather API errors

Retry after a short delay and inspect the response and logs. Avoid saving failed requests as successful observations.

### Browser inspection problems

Confirm that Playwright and its Chromium browser are installed. Review diagnostic files and current page structure before changing selectors.

## Security and Version Control

The `.gitignore` file excludes local databases, generated data, logs, virtual environments, and environment files.

Before publishing:

* Review all files that will be committed.
* Never commit passwords, API keys, access tokens, or private credentials.
* Avoid committing unnecessary local databases and generated diagnostics.
* Verify the README and dependency instructions on a clean checkout.

## Future Improvements

* Strengthen end-to-end integration tests.
* Improve monitoring and reporting of API failures.
* Add reproducible data-quality reports.
* Verify browser pagination and extraction completeness.
* Add analytics and visualizations for stored records.
* Automate tests and quality checks with continuous integration.
* Improve configuration management and operational logging.

## Author

**Mark Kipkirui Rono**

Construction Engineering and Management student interested in data engineering, machine learning, and construction technology.
