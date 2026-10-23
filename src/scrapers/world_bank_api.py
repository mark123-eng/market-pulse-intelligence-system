"""
Market Pulse Intelligence System
World Bank Projects API Scraper

Purpose:
    1. Retrieve Kenyan active projects from the World Bank API.
    2. Fetch records using pagination.
    3. Normalize and validate the returned data.
    4. Remove duplicate project IDs.
    5. Export the results to CSV and JSON.
    6. Log extraction and validation statistics.

Run from the project root:
    python -m src.scrapers.world_bank_api
"""

import json
import logging
import sys
import time

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


# ============================================================
# 1. PROJECT CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
LOG_DIR = PROJECT_ROOT / "logs"

API_URL = "https://search.worldbank.org/api/v3/projects"

COUNTRY_CODE = "KE"
PROJECT_STATUS = "Active"

BATCH_SIZE = 10
REQUEST_DELAY_SECONDS = 1.0
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3

USER_AGENT = "MarketPulse/1.0 (World Bank project data research)"

FIELDS = (
    "id,proj_id,project_name,project_abstract,"
    "countryshortname,countryname,boardapprovaldate,"
    "closingdate,projectstatusdisplay,url"
)

REQUIRED_COLUMNS = [
    "project_id",
    "project_name",
    "country",
]

EXPORT_COLUMNS = [
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
]


# ============================================================
# 2. CREATE DIRECTORIES
# ============================================================

for directory in [RAW_DIR, PROCESSED_DIR, LOG_DIR]:
    directory.mkdir(parents=True, exist_ok=True)


# ============================================================
# 3. LOGGING CONFIGURATION
# ============================================================

LOG_FILE = LOG_DIR / "world_bank_api.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)


# ============================================================
# 4. API REQUEST FUNCTION
# ============================================================

def fetch_api_batch(offset: int) -> dict[str, Any]:
    """
    Request one batch of projects from the World Bank API.

    Args:
        offset: Number of records to skip.

    Returns:
        Parsed JSON response as a dictionary.

    Raises:
        RuntimeError: If the API cannot be accessed or returns
                      invalid JSON after retries.
    """

    params = {
        "format": "json",
        "rows": BATCH_SIZE,
        "os": offset,
        "countrycode_exact": COUNTRY_CODE,
        "status_exact": PROJECT_STATUS,
        "fl": FIELDS,
    }

    request_url = f"{API_URL}?{urlencode(params)}"

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }

    request = Request(request_url, headers=headers)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(
                "Requesting API batch: offset=%s, attempt=%s/%s",
                offset,
                attempt,
                MAX_RETRIES,
            )

            with urlopen(
                request,
                timeout=REQUEST_TIMEOUT_SECONDS,
            ) as response:
                status_code = response.status
                response_text = response.read().decode("utf-8")

            if status_code != 200:
                raise RuntimeError(
                    f"Unexpected HTTP status: {status_code}"
                )

            data = json.loads(response_text)

            if not isinstance(data, dict):
                raise RuntimeError(
                    "API response is not a JSON object."
                )

            if not isinstance(data.get("projects"), dict):
                raise RuntimeError(
                    "API response does not contain a valid "
                    "'projects' dictionary."
                )

            return data

        except HTTPError as exc:
            logger.warning(
                "HTTP error on attempt %s: %s",
                attempt,
                exc,
            )

        except URLError as exc:
            logger.warning(
                "Network error on attempt %s: %s",
                attempt,
                exc,
            )

        except (TimeoutError, OSError) as exc:
            logger.warning(
                "Connection error on attempt %s: %s",
                attempt,
                exc,
            )

        except json.JSONDecodeError as exc:
            logger.warning(
                "Invalid JSON on attempt %s: %s",
                attempt,
                exc,
            )

        except RuntimeError:
            raise

        if attempt < MAX_RETRIES:
            wait_seconds = attempt * 2
            logger.info(
                "Retrying in %s seconds...",
                wait_seconds,
            )
            time.sleep(wait_seconds)

    raise RuntimeError(
        f"Unable to retrieve API batch at offset {offset} "
        f"after {MAX_RETRIES} attempts."
    )


# ============================================================
# 5. NORMALIZE ONE PROJECT
# ============================================================

def normalize_project(
    project: dict[str, Any],
    extracted_at: str,
) -> dict[str, Any]:
    """
    Convert one raw API project into a consistent record.
    """

    project_id = (
        project.get("id")
        or project.get("proj_id")
        or ""
    )

    project_name = project.get("project_name") or ""

    country = (
        project.get("countryshortname")
        or ""
    )

    country_full_name = (
        project.get("countryname")
        or ""
    )

    project_status = (
        project.get("projectstatusdisplay")
        or ""
    )

    approval_date = (
        project.get("boardapprovaldate")
        or ""
    )

    closing_date = (
        project.get("closingdate")
        or ""
    )

    project_abstract = (
        project.get("project_abstract")
        or ""
    )

    project_url = project.get("url") or ""

    # If the API does not provide a project URL, build the
    # conventional World Bank project-details URL from the ID.
    if project_id and not project_url:
        project_url = (
            "https://projects.worldbank.org/en/projects-operations/"
            f"project-detail/{project_id}"
        )

    return {
        "project_id": str(project_id).strip(),
        "project_name": str(project_name).strip(),
        "country": str(country).strip(),
        "country_full_name": str(country_full_name).strip(),
        "project_status": str(project_status).strip(),
        "approval_date": str(approval_date).strip(),
        "closing_date": str(closing_date).strip(),
        "project_abstract": str(project_abstract).strip(),
        "project_url": str(project_url).strip(),
        "source": "World Bank Projects API",
        "extracted_at_utc": extracted_at,
    }


# ============================================================
# 6. FETCH ALL PROJECTS USING PAGINATION
# ============================================================

def fetch_all_projects() -> tuple[list[dict[str, Any]], int]:
    """
    Fetch all matching projects using offset-based pagination.

    Returns:
        A tuple containing:
            - List of normalized project records.
            - Total number of records reported by the API.
    """

    all_projects = []
    seen_ids = set()

    offset = 0
    total_records = None
    extracted_at = datetime.now(timezone.utc).isoformat()

    while True:
        response = fetch_api_batch(offset)

        batch_projects = response.get("projects", {})

        try:
            reported_total = int(response.get("total", 0))
        except (TypeError, ValueError):
            reported_total = 0

        if total_records is None:
            total_records = reported_total

            logger.info(
                "API reports %s matching projects.",
                total_records,
            )

        records = list(batch_projects.values())

        if not records:
            logger.info(
                "No records returned at offset %s. "
                "Pagination complete.",
                offset,
            )
            break

        new_records_in_batch = 0

        for raw_project in records:
            if not isinstance(raw_project, dict):
                logger.warning(
                    "Skipping a record that is not a dictionary."
                )
                continue

            project = normalize_project(
                raw_project,
                extracted_at,
            )

            project_id = project["project_id"]

            if not project_id:
                logger.warning(
                    "Skipping a project without an ID: %s",
                    project["project_name"],
                )
                continue

            if project_id in seen_ids:
                logger.debug(
                    "Duplicate project skipped: %s",
                    project_id,
                )
                continue

            seen_ids.add(project_id)
            all_projects.append(project)
            new_records_in_batch += 1

        logger.info(
            "Offset %s: received %s records; "
            "added %s new records; collected %s so far.",
            offset,
            len(records),
            new_records_in_batch,
            len(all_projects),
        )

        offset += len(records)

        if total_records is not None and offset >= total_records:
            logger.info(
                "Reached the API-reported total."
            )
            break

        if len(records) < BATCH_SIZE:
            logger.info(
                "Received fewer records than the batch size. "
                "Pagination complete."
            )
            break

        if new_records_in_batch == 0:
            logger.warning(
                "The batch contained no new project IDs. "
                "Stopping to avoid an infinite loop."
            )
            break

        time.sleep(REQUEST_DELAY_SECONDS)

    return all_projects, total_records or 0


# ============================================================
# 7. VALIDATE PROJECT RECORDS
# ============================================================

def validate_projects(
    projects: list[dict[str, Any]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Separate valid records from records missing required fields.

    Returns:
        valid_df, rejected_df
    """

    if not projects:
        raise RuntimeError(
            "No project records were fetched. "
            "Refusing to export an empty dataset."
        )

    df = pd.DataFrame(projects)

    for column in EXPORT_COLUMNS:
        if column not in df.columns:
            df[column] = ""

    df = df[EXPORT_COLUMNS].copy()

    # Trim whitespace in text columns.
    text_columns = [
        column
        for column in df.columns
        if column != "extracted_at_utc"
    ]

    for column in text_columns:
        df[column] = df[column].fillna("").astype(str).str.strip()

    # Required fields must not be blank.
    missing_required = pd.Series(
        False,
        index=df.index,
    )

    for column in REQUIRED_COLUMNS:
        missing_required |= df[column].eq("")

    rejected_df = df.loc[missing_required].copy()
    valid_df = df.loc[~missing_required].copy()

    # Deduplicate using the project ID.
    before_deduplication = len(valid_df)

    valid_df = valid_df.drop_duplicates(
        subset=["project_id"],
        keep="first",
    ).reset_index(drop=True)

    duplicates_removed = (
        before_deduplication - len(valid_df)
    )

    logger.info(
        "Validation: %s valid records; %s rejected; "
        "%s duplicate records removed.",
        len(valid_df),
        len(rejected_df),
        duplicates_removed,
    )

    # Validate dates without silently changing the source strings.
    for column in ["approval_date", "closing_date"]:
        nonblank = valid_df[column].ne("")

        parsed_dates = pd.to_datetime(
            valid_df.loc[nonblank, column],
            errors="coerce",
            utc=True,
        )

        invalid_count = int(parsed_dates.isna().sum())

        if invalid_count:
            logger.warning(
                "%s contains %s nonblank date values "
                "that could not be parsed.",
                column,
                invalid_count,
            )

    if valid_df.empty:
        raise RuntimeError(
            "All fetched records failed validation. "
            "No processed dataset was exported."
        )

    return valid_df, rejected_df


# ============================================================
# 8. EXPORT DATASETS
# ============================================================

def export_projects(
    valid_df: pd.DataFrame,
    rejected_df: pd.DataFrame,
) -> None:
    """
    Export valid projects and rejected records.
    """

    csv_path = (
        PROCESSED_DIR / "world_bank_projects.csv"
    )

    json_path = (
        PROCESSED_DIR / "world_bank_projects.json"
    )

    rejected_path = (
        PROCESSED_DIR / "world_bank_rejected_records.csv"
    )

    # UTF-8 with BOM improves compatibility with Excel.
    valid_df.to_csv(
        csv_path,
        index=False,
        encoding="utf-8-sig",
    )

    valid_df.to_json(
        json_path,
        orient="records",
        indent=2,
        force_ascii=False,
    )

    if not rejected_df.empty:
        rejected_df.to_csv(
            rejected_path,
            index=False,
            encoding="utf-8-sig",
        )

        logger.warning(
            "Rejected records saved to %s",
            rejected_path,
        )

    logger.info(
        "CSV export complete: %s",
        csv_path,
    )

    logger.info(
        "JSON export complete: %s",
        json_path,
    )

    logger.info(
        "Exported %s valid project records.",
        len(valid_df),
    )


# ============================================================
# 9. SAVE RAW API METADATA
# ============================================================

def save_run_metadata(
    reported_total: int,
    fetched_count: int,
    exported_count: int,
) -> None:
    """
    Save a small JSON summary of the extraction run.
    """

    metadata = {
        "source": API_URL,
        "country_filter": COUNTRY_CODE,
        "status_filter": PROJECT_STATUS,
        "api_reported_total": reported_total,
        "unique_records_fetched": fetched_count,
        "valid_records_exported": exported_count,
        "batch_size": BATCH_SIZE,
        "completed_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    metadata_path = (
        RAW_DIR / "world_bank_api_run_metadata.json"
    )

    with metadata_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            metadata,
            file,
            indent=2,
            ensure_ascii=False,
        )

    logger.info(
        "Run metadata saved to %s",
        metadata_path,
    )


# ============================================================
# 10. MAIN PIPELINE
# ============================================================

def main() -> None:
    """
    Run the complete World Bank project extraction pipeline.
    """

    started_at = time.time()

    logger.info("=" * 65)
    logger.info("MARKET PULSE — WORLD BANK API SCRAPER")
    logger.info("=" * 65)

    logger.info("Project root: %s", PROJECT_ROOT)
    logger.info("Country filter: %s", COUNTRY_CODE)
    logger.info("Status filter: %s", PROJECT_STATUS)
    logger.info("Batch size: %s", BATCH_SIZE)

    projects, reported_total = fetch_all_projects()

    logger.info(
        "Unique project records fetched: %s",
        len(projects),
    )

    logger.info(
        "API-reported total: %s",
        reported_total,
    )

    if reported_total and len(projects) != reported_total:
        logger.warning(
            "Fetched %s unique records, while the API reports "
            "%s. Investigate missing records before treating "
            "the extraction as complete.",
            len(projects),
            reported_total,
        )

    valid_df, rejected_df = validate_projects(projects)

    export_projects(
        valid_df,
        rejected_df,
    )

    save_run_metadata(
        reported_total=reported_total,
        fetched_count=len(projects),
        exported_count=len(valid_df),
    )

    elapsed = time.time() - started_at

    logger.info("=" * 65)
    logger.info("EXTRACTION COMPLETED")
    logger.info("API total: %s", reported_total)
    logger.info("Unique records fetched: %s", len(projects))
    logger.info("Valid records exported: %s", len(valid_df))
    logger.info("Rejected records: %s", len(rejected_df))
    logger.info("Elapsed time: %.2f seconds", elapsed)
    logger.info("=" * 65)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning(
            "Extraction interrupted by the user."
        )
        sys.exit(130)
    except Exception:
        logger.exception(
            "World Bank API extraction failed."
        )
        sys.exit(1)
