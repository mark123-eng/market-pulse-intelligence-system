"""
MarketPulse Intelligence System
World Bank project/document search scraper.

Run from the project root:
    python src/scrapers/scrapers.py

This implementation opens the World Bank search page with Playwright,
applies configured filters where possible, saves diagnostics, extracts
document-style results, paginates conservatively, deduplicates, and exports
CSV/JSON. The World Bank site is JavaScript-rendered and can change; inspect
saved diagnostics if its live HTML differs from the selectors used here.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urldefrag

import pandas as pd
from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
    Error as PlaywrightError,
)

# 1. Configuration
BASE_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
WORLD_BANK_URL = (
    "https://projects.worldbank.org/"
    "en/projects-operations/project-search"
)

HEADLESS = False
MAX_PAGES = 10
MAX_RECORDS = 1000
NAVIGATION_TIMEOUT_MS = 60000
ELEMENT_TIMEOUT_MS = 15000
REQUEST_DELAY_SECONDS = 1.5
COUNTRY_FILTER = "Kenya"
PROJECT_STATUS_FILTER = "Active"
PAUSE_FOR_MANUAL_INSPECTION = False
SAVE_SCREENSHOTS = True
FAIL_IF_NO_RECORDS = True

RAW_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(RAW_DIR / "world_bank_scraper.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("MarketPulse.WorldBank")


# 2. Data model
@dataclass
class DocumentRecord:
    document_title: str = ""
    document_type: str = ""
    document_date: str = ""
    disclosure_status: str = ""
    author: str = ""
    report_number: str = ""
    project_id: str = ""
    country: str = ""
    status: str = ""
    document_url: str = ""
    source_page: str = ""
    extracted_at: str = ""


# 3. Browser and diagnostics
def create_browser(playwright):
    """Launch Chromium and return browser, context, and page."""
    browser = playwright.chromium.launch(headless=HEADLESS)
    context = browser.new_context(
        viewport={"width": 1440, "height": 1000},
        locale="en-US",
    )
    page = context.new_page()
    page.set_default_timeout(ELEMENT_TIMEOUT_MS)
    page.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)
    return browser, context, page


def open_world_bank(page) -> None:
    """Open the search page and wait briefly for JavaScript rendering."""
    logger.info("Opening World Bank search page.")
    response = page.goto(
        WORLD_BANK_URL,
        wait_until="domcontentloaded",
        timeout=NAVIGATION_TIMEOUT_MS,
    )
    if response is not None:
        logger.info("Initial HTTP status: %s", response.status)
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except PlaywrightTimeoutError:
        logger.info("Network did not become idle; continuing with DOM inspection.")
    page.wait_for_timeout(2000)
    logger.info("Page title: %s", page.title())
    logger.info("Current URL: %s", page.url)


def save_diagnostics(page, label: str = "world_bank") -> None:
    """Save current page HTML and optional screenshot."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    html_path = RAW_DIR / f"{label}_{timestamp}.html"
    try:
        html_path.write_text(page.content(), encoding="utf-8")
        logger.info("Saved HTML diagnostic: %s", html_path)
    except Exception:
        logger.exception("Could not save HTML diagnostic.")
    if SAVE_SCREENSHOTS:
        screenshot_path = RAW_DIR / f"{label}_{timestamp}.png"
        try:
            page.screenshot(path=str(screenshot_path), full_page=True)
            logger.info("Saved screenshot diagnostic: %s", screenshot_path)
        except Exception:
            logger.exception("Could not save screenshot diagnostic.")


def inspect_visible_controls(page) -> list[dict[str, Any]]:
    """Save an inventory of visible controls for troubleshooting."""
    controls = page.locator(
        "input, select, textarea, button, a, [role='combobox'], [role='button']"
    )
    results: list[dict[str, Any]] = []
    for index in range(min(controls.count(), 500)):
        element = controls.nth(index)
        try:
            if not element.is_visible():
                continue
            item = element.evaluate(
                """el => ({
                    tag: el.tagName,
                    text: (el.innerText || el.value || '').trim().slice(0, 180),
                    id: el.id || '',
                    name: el.getAttribute('name') || '',
                    type: el.getAttribute('type') || '',
                    placeholder: el.getAttribute('placeholder') || '',
                    ariaLabel: el.getAttribute('aria-label') || '',
                    title: el.getAttribute('title') || '',
                    role: el.getAttribute('role') || '',
                    className: typeof el.className === 'string'
                        ? el.className.slice(0, 180) : '',
                    href: el.getAttribute('href') || ''
                })"""
            )
            results.append(item)
        except PlaywrightError:
            continue
    output = RAW_DIR / "world_bank_controls.json"
    output.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Saved %d visible controls to %s", len(results), output)
    return results


# 4. Filter handling
def _safe_check_checkbox(page, checkbox_id: str) -> bool:
    """Check a status checkbox using the observed checkbox ID."""
    locator = page.locator(f"input[type='checkbox']#{checkbox_id}")
    if locator.count() == 0:
        logger.warning("Checkbox not found: %s", checkbox_id)
        return False
    checkbox = locator.first
    try:
        if not checkbox.is_checked():
            checkbox.check(timeout=ELEMENT_TIMEOUT_MS)
        logger.info("Selected status checkbox: %s", checkbox_id)
        return True
    except PlaywrightError:
        try:
            page.locator(f"label[for='{checkbox_id}']").first.click(
                timeout=ELEMENT_TIMEOUT_MS
            )
            logger.info("Selected checkbox using its label: %s", checkbox_id)
            return True
        except PlaywrightError:
            logger.exception("Could not select checkbox: %s", checkbox_id)
            return False


def _select_country(page, country: str) -> bool:
    """
    Search within the custom country selector and click the exact matching
    country checkbox/label. The function does not treat the region checkbox
    ID '3A' as Kenya.
    """
    if not country:
        return True

    search_input = page.locator("#country-search")
    if search_input.count():
        try:
            search_input.fill(country, timeout=ELEMENT_TIMEOUT_MS)
            page.wait_for_timeout(500)
        except PlaywrightError:
            logger.info("Could not type into #country-search; trying exact visible labels.")

    exact_label = page.locator("label").filter(
        has_text=re.compile(rf"^\s*{re.escape(country)}\s*$", re.I)
    )
    for index in range(min(exact_label.count(), 10)):
        label = exact_label.nth(index)
        try:
            if label.is_visible():
                label.click(timeout=ELEMENT_TIMEOUT_MS)
                logger.info("Selected country using exact label: %s", country)
                return True
        except PlaywrightError:
            continue

    # Try an exact checkbox label exposed by accessible name.
    try:
        checkbox = page.get_by_role(
            "checkbox",
            name=re.compile(rf"^{re.escape(country)}$", re.I),
        )
        if checkbox.count():
            if not checkbox.first.is_checked():
                checkbox.first.check(timeout=ELEMENT_TIMEOUT_MS)
            logger.info("Selected country checkbox: %s", country)
            return True
    except PlaywrightError:
        pass

    save_diagnostics(page, "world_bank_country_dropdown")
    logger.error("Could not verify selection of country '%s'.", country)
    return False


def apply_search_filters(page) -> bool:
    """Apply configured filters, submit the search, and save result diagnostics."""
    logger.info(
        "Requested filters: country=%r, status=%r",
        COUNTRY_FILTER,
        PROJECT_STATUS_FILTER,
    )

    if PROJECT_STATUS_FILTER:
        if PROJECT_STATUS_FILTER not in {"Active", "Closed", "Dropped", "Pipeline"}:
            raise ValueError(
                "PROJECT_STATUS_FILTER must be Active, Closed, Dropped, or Pipeline."
            )
        if not _safe_check_checkbox(page, PROJECT_STATUS_FILTER):
            save_diagnostics(page, "world_bank_status_filter_error")
            return False

    if COUNTRY_FILTER:
        # Use a normal CSS locator plus Playwright text filtering. This avoids
        # embedding a slash-containing regular expression in an attribute selector.
        dropdown = page.locator("button").filter(
            has_text=re.compile(r"Select Country/Area|Country/Area", re.IGNORECASE)
        )
        if dropdown.count():
            try:
                dropdown.first.click(timeout=ELEMENT_TIMEOUT_MS)
                page.wait_for_timeout(400)
            except PlaywrightError:
                logger.exception("Could not open Country/Area dropdown.")
                save_diagnostics(page, "world_bank_country_dropdown_error")
                return False
        else:
            fallback = page.get_by_text(
                re.compile(r"Select Country/Area", re.I)
            )
            if not fallback.count():
                logger.error("Country/Area dropdown was not found.")
                save_diagnostics(page, "world_bank_country_dropdown_error")
                return False
            try:
                fallback.first.click(timeout=ELEMENT_TIMEOUT_MS)
                page.wait_for_timeout(400)
            except PlaywrightError:
                logger.exception("Could not open Country/Area dropdown.")
                save_diagnostics(page, "world_bank_country_dropdown_error")
                return False

        if not _select_country(page, COUNTRY_FILTER):
            return False

    search_button = page.locator("a.primary-light-blue-btn")
    if not search_button.count():
        search_button = page.get_by_role(
            "link",
            name=re.compile(r"^\s*SEARCH\s*$", re.I),
        )
    if not search_button.count():
        logger.error("World Bank Search control was not found.")
        save_diagnostics(page, "world_bank_search_button_error")
        return False
    try:
        search_button.first.click(timeout=ELEMENT_TIMEOUT_MS)
    except PlaywrightError:
        logger.exception("Could not click the Search control.")
        save_diagnostics(page, "world_bank_search_click_error")
        return False

    logger.info("Search submitted; waiting for results.")
    page.wait_for_timeout(3000)
    save_diagnostics(page, "world_bank_search_results")
    logger.info("Results URL: %s", page.url)
    logger.info("Results title: %s", page.title())
    return True


# 5. Result extraction
def _clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _extract_project_id(text: str, url: str = "") -> str:
    match = re.search(r"\bP\d{6}\b", f"{text} {url}", re.I)
    return match.group(0).upper() if match else ""


def _extract_document_date(text: str) -> str:
    patterns = [
        r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}\b",
        r"\b\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}\b",
        r"\b\d{4}-\d{2}-\d{2}\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(0)
    return ""


def _candidate_result_blocks(page) -> list[dict[str, Any]]:
    """Collect plausible visible result blocks and their links from the live DOM."""
    script = r"""
    () => {
      const visible = el => {
        const r = el.getBoundingClientRect();
        const s = window.getComputedStyle(el);
        return r.width > 0 && r.height > 0 &&
               s.visibility !== 'hidden' && s.display !== 'none';
      };
      const selectors = [
        '[class*="search-result"]',
        '[class*="result-item"]',
        '[class*="document-result"]',
        '[class*="result-card"]',
        'article',
        '[role="listitem"]'
      ];
      const blocks = [];
      for (const selector of selectors) {
        for (const el of document.querySelectorAll(selector)) {
          if (!visible(el)) continue;
          const text = (el.innerText || '').trim();
          if (text.length < 35 || text.length > 5000) continue;
          if (!/(document|disclosure|author|report no|financing agreement|procurement plan|implementation status|project id)/i.test(text)) continue;
          const links = Array.from(el.querySelectorAll('a[href]'))
            .filter(visible)
            .map(a => ({
              text: (a.innerText || a.getAttribute('aria-label') || '').trim(),
              href: a.href
            }));
          blocks.push({selector, text, links});
        }
      }
      const seen = new Set();
      return blocks.filter(b => {
        const key = b.text.replace(/\s+/g, ' ').trim();
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      }).sort((a,b) => a.text.length - b.text.length);
    }
    """
    try:
        return page.evaluate(script)
    except PlaywrightError:
        logger.exception("Could not inspect candidate result blocks.")
        return []


def extract_documents(page) -> list[DocumentRecord]:
    """Extract document records from plausible result blocks, avoiding navigation links."""
    logger.info("Extracting document records from the current page.")
    extracted_at = datetime.now(timezone.utc).isoformat()
    blocks = _candidate_result_blocks(page)
    records: list[DocumentRecord] = []

    for block in blocks:
        raw_text = block.get("text", "")
        text = _clean_text(raw_text)
        if not text or not re.search(
            r"(document|disclosure status|author|report no\.?|financing agreement|procurement plan|implementation status|P\d{6})",
            text,
            re.I,
        ):
            continue

        links = block.get("links", [])
        title = ""
        document_url = ""
        for link in links:
            link_text = _clean_text(link.get("text", ""))
            href = link.get("href", "")
            if not href:
                continue
            if (
                re.search(r"\.(pdf|docx?|xlsx?)(?:$|\?)", href, re.I)
                or re.search(
                    r"(financing agreement|procurement plan|implementation status|official documents|disclosable version|project appraisal|environmental|resettlement|report)",
                    link_text,
                    re.I,
                )
            ):
                title, document_url = link_text, href
                break

        if not title:
            for link in links:
                link_text = _clean_text(link.get("text", ""))
                if link_text:
                    title = link_text
                    document_url = link.get("href", "")
                    break

        if not title:
            lines = [_clean_text(line) for line in raw_text.splitlines()]
            title = next(
                (
                    line for line in lines
                    if len(line) > 12
                    and not re.fullmatch(
                        r"(document title|document type|document date|disclosure status|author|report no\.?)",
                        line,
                        re.I,
                    )
                ),
                "",
            )

        project_id = _extract_project_id(text, document_url)
        if not title and not project_id:
            continue

        document_type = ""
        document_date = _extract_document_date(text)
        disclosure_status = ""
        author = ""
        report_number = ""

        type_match = re.search(
            r"(?:Document Type|Type)\s*[:\-]?\s*(.{2,100}?)(?=\s+(?:Document Date|Date|Disclosure Status|Author|Report No\.?)\b|$)",
            text, re.I,
        )
        if type_match:
            document_type = _clean_text(type_match.group(1))

        date_match = re.search(
            r"(?:Document Date|Date)\s*[:\-]?\s*"
            r"([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}|\d{4}-\d{2}-\d{2})",
            text, re.I,
        )
        if date_match:
            document_date = _clean_text(date_match.group(1))

        disclosure_match = re.search(
            r"Disclosure Status\s*[:\-]?\s*(Disclosed|Not Disclosed|Disclosable|Undisclosed)",
            text, re.I,
        )
        if disclosure_match:
            disclosure_status = _clean_text(disclosure_match.group(1))

        author_match = re.search(
            r"Author\s*[:\-]?\s*(.{2,100}?)(?=\s+(?:Report No\.?|Document Type|Document Date|Disclosure Status)\b|$)",
            text, re.I,
        )
        if author_match:
            author = _clean_text(author_match.group(1))

        report_match = re.search(r"Report No\.?\s*[:\-]?\s*([A-Z0-9\-]+)", text, re.I)
        if report_match:
            report_number = report_match.group(1)

        if not document_type:
            for known_type in (
                "Financing Agreement",
                "Implementation Status and Results Report",
                "Procurement Plan",
                "Project Appraisal Document",
                "Environmental and Social Commitment Plan",
                "Environmental and Social Review Summary",
            ):
                if re.search(re.escape(known_type), title or text, re.I):
                    document_type = known_type
                    break

        records.append(
            DocumentRecord(
                document_title=title,
                document_type=document_type,
                document_date=document_date,
                disclosure_status=disclosure_status,
                author=author,
                report_number=report_number,
                project_id=project_id,
                country=COUNTRY_FILTER,
                status=PROJECT_STATUS_FILTER,
                document_url=urljoin(page.url, document_url) if document_url else "",
                source_page=page.url,
                extracted_at=extracted_at,
            )
        )

    if not records:
        logger.warning("No document records detected; saving visible-link inventory.")
        try:
            inventory = []
            anchors = page.locator("a[href]")
            for i in range(min(anchors.count(), 1000)):
                anchor = anchors.nth(i)
                try:
                    if not anchor.is_visible():
                        continue
                    href = anchor.get_attribute("href") or ""
                    text = _clean_text(anchor.inner_text())
                    if text:
                        inventory.append({
                            "text": text[:250],
                            "href": urljoin(page.url, href) if href else "",
                        })
                except PlaywrightError:
                    continue
            (RAW_DIR / "world_bank_result_links.json").write_text(
                json.dumps(inventory, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            logger.exception("Could not save visible-link inventory.")

    logger.info("Extracted %d candidate document records.", len(records))
    return records


# 6. Pagination
def _page_signature(page) -> tuple[str, str]:
    try:
        text = page.locator("body").inner_text(timeout=5000)
    except PlaywrightError:
        text = ""
    return page.url, re.sub(r"\s+", " ", text).strip()[:1500]


def _find_next_control(page):
    """Find a visible enabled Next control with a recognizable label."""
    selectors = [
        'button[aria-label*="next" i]',
        'a[aria-label*="next" i]',
        'button[title*="next" i]',
        'a[title*="next" i]',
        '[role="button"][aria-label*="next" i]',
        'a:has-text("Next")',
        'button:has-text("Next")',
        'a:has-text("›")',
        'button:has-text("›")',
        'a:has-text("»")',
        'button:has-text("»")',
    ]
    for selector in selectors:
        locator = page.locator(selector)
        for i in range(min(locator.count(), 10)):
            item = locator.nth(i)
            try:
                if not item.is_visible() or not item.is_enabled():
                    continue
                details = item.evaluate(
                    """el => ({
                        text: (el.innerText || '').trim(),
                        aria: el.getAttribute('aria-label') || '',
                        title: el.getAttribute('title') || '',
                        disabled: el.disabled === true ||
                            el.getAttribute('aria-disabled') === 'true'
                    })"""
                )
                if details["disabled"]:
                    continue
                label = " ".join(
                    [details["text"], details["aria"], details["title"]]
                ).lower()
                if "next" in label or "›" in label or "»" in label:
                    return item
            except PlaywrightError:
                continue
    return None


def go_to_next_page(page) -> bool:
    """Advance pagination only when the visible page changes."""
    control = _find_next_control(page)
    if control is None:
        logger.info("No verified Next-page control found.")
        return False
    before = _page_signature(page)
    try:
        control.click(timeout=ELEMENT_TIMEOUT_MS)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            page.wait_for_timeout(500)
            if _page_signature(page) != before:
                logger.info("Pagination changed the visible page.")
                return True
        logger.warning("Next was clicked but page content did not change.")
        save_diagnostics(page, "world_bank_pagination_unchanged")
        return False
    except PlaywrightError:
        logger.exception("Pagination click failed.")
        save_diagnostics(page, "world_bank_pagination_error")
        return False


# 7. Deduplication and export
def deduplicate_records(records: list[DocumentRecord]) -> list[DocumentRecord]:
    """Deduplicate documents by canonical URL, then report number/title."""
    unique: dict[str, DocumentRecord] = {}
    for record in records:
        if record.document_url:
            key = "url:" + urldefrag(record.document_url)[0].rstrip("/").lower()
        elif record.report_number:
            key = "report:" + record.report_number.lower()
        else:
            normalized_title = re.sub(r"\s+", " ", record.document_title).strip().lower()
            key = f"title:{normalized_title}|{record.project_id.upper()}"
        unique.setdefault(key, record)
    result = list(unique.values())
    logger.info("Deduplication: %d before, %d after.", len(records), len(result))
    return result


def save_records(records: list[DocumentRecord]) -> tuple[Path, Path] | None:
    """Export records to CSV and JSON."""
    if not records:
        logger.warning("No records to export.")
        return None
    data = [asdict(record) for record in records]
    dataframe = pd.DataFrame(data)
    csv_path = PROCESSED_DIR / "world_bank_documents.csv"
    json_path = PROCESSED_DIR / "world_bank_documents.json"
    dataframe.to_csv(csv_path, index=False, encoding="utf-8-sig")
    json_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("CSV exported: %s", csv_path)
    logger.info("JSON exported: %s", json_path)
    logger.info("Exported %d document records.", len(data))
    return csv_path, json_path


# 8. Main workflow
def scrape_world_bank() -> list[DocumentRecord]:
    """Run search, extract records, paginate, deduplicate, and export."""
    all_records: list[DocumentRecord] = []
    with sync_playwright() as playwright:
        browser, context, page = create_browser(playwright)
        try:
            open_world_bank(page)
            save_diagnostics(page, "world_bank_initial")
            inspect_visible_controls(page)

            if not apply_search_filters(page):
                raise RuntimeError(
                    "Filters could not be verified/applied. Inspect the latest "
                    "world_bank_* HTML and screenshot diagnostics before retrying."
                )

            visited_pages: set[tuple[str, str]] = set()
            for page_number in range(1, MAX_PAGES + 1):
                logger.info("Processing result page %d/%d.", page_number, MAX_PAGES)
                signature = _page_signature(page)
                if signature in visited_pages:
                    logger.warning("Repeated page signature; stopping pagination.")
                    break
                visited_pages.add(signature)

                try:
                    body_text = page.locator("body").inner_text(timeout=5000)
                except PlaywrightError:
                    body_text = ""
                count_match = re.search(r".{0,50}\b\d[\d,]*\s*results\b.{0,50}", body_text, re.I)
                if count_match:
                    logger.info("Visible result-count text: %s", count_match.group(0))

                all_records.extend(extract_documents(page))
                if len(all_records) >= MAX_RECORDS:
                    all_records = all_records[:MAX_RECORDS]
                    logger.info("MAX_RECORDS limit reached.")
                    break
                if page_number >= MAX_PAGES:
                    break
                if not go_to_next_page(page):
                    logger.info("Could not verify another result page; stopping.")
                    break
                time.sleep(REQUEST_DELAY_SECONDS)

            all_records = deduplicate_records(all_records)
            if not all_records and FAIL_IF_NO_RECORDS:
                save_diagnostics(page, "world_bank_no_records")
                raise RuntimeError(
                    "No document records were extracted. No empty dataset was exported. "
                    "Inspect the latest result HTML and screenshot."
                )

            save_records(all_records)
            logger.info("World Bank run completed with %d document records.", len(all_records))

            if PAUSE_FOR_MANUAL_INSPECTION:
                input("Inspect the browser, then press Enter to close it...")
            return all_records

        except (PlaywrightTimeoutError, PlaywrightError):
            logger.exception("Playwright operation failed.")
            save_diagnostics(page, "world_bank_playwright_error")
            raise
        except Exception:
            logger.exception("World Bank scraping failed.")
            save_diagnostics(page, "world_bank_error")
            raise
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    scrape_world_bank()
