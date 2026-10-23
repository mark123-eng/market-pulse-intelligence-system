"""
World Bank Advanced Search — Browser Inspector

Purpose:
1. Open the World Bank project search page reliably.
2. Handle slow navigation without unnecessarily stopping execution.
3. Allow time for JavaScript-rendered content.
4. Inspect visible buttons, links, and inputs.
5. Identify the SEARCH control.
6. Save diagnostic HTML, text, screenshot, and URL.

Run from the project root:
    python src/scrapers/inspect_controls.py
"""

from pathlib import Path
from datetime import datetime
import logging

from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
)


# ---------------------------------------------------------
# 1. CONFIGURATION
# ---------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = BASE_DIR / "data" / "raw"

RAW_DIR.mkdir(parents=True, exist_ok=True)

URL = (
    "https://projects.worldbank.org/"
    "en/projects-operations/project-search"
)

NAVIGATION_TIMEOUT_MS = 30000
ELEMENT_TIMEOUT_MS = 10000
JAVASCRIPT_WAIT_MS = 12000


# ---------------------------------------------------------
# 2. LOGGING
# ---------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# 3. DIAGNOSTIC FILES
# ---------------------------------------------------------

def save_diagnostics(page):
    """Save the current browser state for later inspection."""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    html_path = RAW_DIR / f"world_bank_controls_{timestamp}.html"
    text_path = RAW_DIR / f"world_bank_controls_{timestamp}.txt"
    screenshot_path = RAW_DIR / f"world_bank_controls_{timestamp}.png"
    url_path = RAW_DIR / f"world_bank_controls_{timestamp}_url.txt"

    try:
        html_path.write_text(
            page.content(),
            encoding="utf-8",
        )
        logger.info("HTML saved: %s", html_path)
    except Exception as error:
        logger.warning("Could not save HTML: %s", error)

    try:
        visible_text = page.locator("body").inner_text(timeout=15000)

        text_path.write_text(
            visible_text,
            encoding="utf-8",
        )

        logger.info("Visible text saved: %s", text_path)

    except Exception as error:
        logger.warning("Could not save visible text: %s", error)

    try:
        page.screenshot(
            path=str(screenshot_path),
            full_page=True,
            timeout=20000,
        )

        logger.info("Screenshot saved: %s", screenshot_path)

    except Exception as error:
        logger.warning("Could not save screenshot: %s", error)

    try:
        url_path.write_text(
            page.url,
            encoding="utf-8",
        )

        logger.info("URL saved: %s", url_path)

    except Exception as error:
        logger.warning("Could not save URL: %s", error)


# ---------------------------------------------------------
# 4. NAVIGATION
# ---------------------------------------------------------

def open_search_page(page):
    """
    Navigate without waiting for every page resource to finish.

    'commit' allows us to proceed once the navigation response
    begins. We then wait separately for the rendered interface.
    """

    logger.info("Opening World Bank Advanced Search...")
    logger.info("URL: %s", URL)

    try:
        response = page.goto(
            URL,
            wait_until="commit",
            timeout=NAVIGATION_TIMEOUT_MS,
        )

        if response:
            logger.info("HTTP status: %s", response.status)
        else:
            logger.info("No main-document response was returned.")

    except PlaywrightTimeoutError:
        logger.warning(
            "Navigation timed out. Checking whether the page "
            "nevertheless opened."
        )

    except Exception as error:
        logger.warning("Navigation warning: %s", error)

    # Give the JavaScript application time to render.
    logger.info(
        "Waiting %s seconds for the page interface...",
        JAVASCRIPT_WAIT_MS / 1000,
    )

    page.wait_for_timeout(JAVASCRIPT_WAIT_MS)

    logger.info("Current URL: %s", page.url)

    try:
        logger.info("Page title: %s", page.title())
    except Exception as error:
        logger.warning("Could not retrieve title: %s", error)


# ---------------------------------------------------------
# 5. INSPECT VISIBLE CONTROLS
# ---------------------------------------------------------

def inspect_controls(page):
    """Inspect visible buttons, links, and input fields."""

    print("\n" + "=" * 65)
    print("WORLD BANK PAGE INSPECTION")
    print("=" * 65)

    print("\nCURRENT URL:")
    print(page.url)

    try:
        print("\nPAGE TITLE:")
        print(page.title())
    except Exception as error:
        print("Could not read title:", error)

    # Buttons
    print("\n" + "-" * 65)
    print("VISIBLE BUTTONS")
    print("-" * 65)

    try:
        buttons = page.locator("button:visible").evaluate_all(
            """
            elements => elements.map(element => ({
                text: (element.innerText || "").trim(),
                ariaLabel: element.getAttribute("aria-label"),
                title: element.getAttribute("title"),
                className: element.className
            }))
            """
        )

        for index, item in enumerate(buttons, start=1):
            print(f"{index}. {item}")

        if not buttons:
            print("No visible button elements found.")

    except Exception as error:
        print("Button inspection failed:", error)

    # Links
    print("\n" + "-" * 65)
    print("VISIBLE LINKS")
    print("-" * 65)

    try:
        links = page.locator("a:visible").evaluate_all(
            """
            elements => elements.map(element => ({
                text: (element.innerText || "").trim(),
                href: element.href,
                ariaLabel: element.getAttribute("aria-label"),
                className: element.className
            }))
            """
        )

        for index, item in enumerate(links, start=1):
            print(f"{index}. {item}")

        if not links:
            print("No visible links found.")

    except Exception as error:
        print("Link inspection failed:", error)

    # Input fields
    print("\n" + "-" * 65)
    print("VISIBLE INPUTS")
    print("-" * 65)

    try:
        inputs = page.locator("input:visible").evaluate_all(
            """
            elements => elements.map(element => ({
                type: element.type,
                name: element.name,
                value: element.value,
                placeholder: element.placeholder,
                ariaLabel: element.getAttribute("aria-label"),
                checked: element.checked
            }))
            """
        )

        for index, item in enumerate(inputs, start=1):
            print(f"{index}. {item}")

        if not inputs:
            print("No visible inputs found.")

    except Exception as error:
        print("Input inspection failed:", error)

    # Search-related controls
    print("\n" + "-" * 65)
    print("SEARCH-RELATED CONTROLS")
    print("-" * 65)

    try:
        candidates = page.locator(
            "a:visible, button:visible, "
            "[role='button']:visible, input:visible"
        ).evaluate_all(
            """
            elements => elements.map(element => ({
                tag: element.tagName,
                text: (
                    element.innerText ||
                    element.value ||
                    ""
                ).trim(),
                href: element.href || "",
                ariaLabel: element.getAttribute("aria-label") || "",
                title: element.getAttribute("title") || "",
                className: (
                    typeof element.className === "string"
                    ? element.className
                    : ""
                )
            }))
            """
        )

        matches = []

        for item in candidates:
            searchable_text = " ".join(
                str(value)
                for value in item.values()
            ).lower()

            if any(
                term in searchable_text
                for term in (
                    "search",
                    "submit",
                    "apply",
                    "filter",
                )
            ):
                matches.append(item)

        for index, item in enumerate(matches, start=1):
            print(f"{index}. {item}")

        if not matches:
            print("No visible search-related controls found.")

    except Exception as error:
        print("Search-control inspection failed:", error)


# ---------------------------------------------------------
# 6. LOCATE SEARCH LINK
# ---------------------------------------------------------

def find_search_link(page):
    """
    Find the visible SEARCH link using its actual text.

    The known page implementation renders SEARCH as an anchor,
    rather than a button.
    """

    search_link = page.locator(
        "a.primary-light-blue-btn:visible"
    ).filter(
        has_text="SEARCH"
    )

    count = search_link.count()

    print("\nSEARCH LINK COUNT:", count)

    if count:
        first_link = search_link.first

        print("SEARCH LINK TEXT:", repr(
            first_link.inner_text(timeout=ELEMENT_TIMEOUT_MS)
        ))

        print("SEARCH LINK HREF:", first_link.get_attribute("href"))

        print(
            "SEARCH LINK CLASS:",
            first_link.get_attribute("class"),
        )

        return first_link

    print(
        "The expected SEARCH link was not found. "
        "Review the visible-links output and saved screenshot."
    )

    return None


# ---------------------------------------------------------
# 7. MAIN PROGRAM
# ---------------------------------------------------------

def main():
    print("\nWORLD BANK ADVANCED SEARCH INSPECTOR")
    print("=" * 65)

    print("Project root:", BASE_DIR)
    print("Diagnostic folder:", RAW_DIR)

    with sync_playwright() as playwright:

        browser = None

        try:
            browser = playwright.chromium.launch(
                headless=False,
            )

            context = browser.new_context(
                viewport={
                    "width": 1440,
                    "height": 1000,
                },
            )

            page = context.new_page()

            page.set_default_timeout(ELEMENT_TIMEOUT_MS)
            page.set_default_navigation_timeout(
                NAVIGATION_TIMEOUT_MS
            )

            # Record browser-side errors that may explain
            # missing or malfunctioning page controls.
            page.on(
                "pageerror",
                lambda error: logger.warning(
                    "Browser JavaScript error: %s",
                    error,
                ),
            )

            page.on(
                "console",
                lambda message: logger.warning(
                    "Browser console error: %s",
                    message.text,
                ) if message.type == "error" else None,
            )

            open_search_page(page)

            inspect_controls(page)

            search_link = find_search_link(page)

            save_diagnostics(page)

            print("\n" + "=" * 65)
            print("INSPECTION FINISHED")
            print("=" * 65)

            if search_link:
                print(
                    "\nSEARCH is visible. "
                    "This script will NOT click it automatically."
                )

                print(
                    "Next, confirm that the filters and page "
                    "state match the intended search."
                )

            print(
                "\nThe browser will remain open for manual inspection."
            )

            input(
                "\nPress ENTER in this terminal to close the browser..."
            )

        except KeyboardInterrupt:
            logger.info("Inspection interrupted by user.")

        except Exception:
            logger.exception("Unexpected inspection failure.")

        finally:
            if browser is not None:
                browser.close()


if __name__ == "__main__":
    main()
