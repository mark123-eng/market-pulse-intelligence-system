from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = BASE_DIR / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

START_URL = (
    "https://projects.worldbank.org/"
    "en/projects-operations/project-search"
)


def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("\nWORLD BANK RESULTS INSPECTOR")
    print("=" * 55)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(
            viewport={"width": 1440, "height": 1000}
        )

        print("\nOpening the World Bank project search page...")
        page.goto(
            START_URL,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        try:
            page.wait_for_load_state(
                "networkidle",
                timeout=15000,
            )
        except Exception:
            print("Page remains active; continuing inspection.")

        print("\nCURRENT PAGE:")
        print("URL:", page.url)
        print("TITLE:", page.title())

        print("\nBROWSER IS READY.")
        print("1. Select Project Status: Active.")
        print("2. Select Region: Africa.")
        print("3. Select Country: Kenya.")
        print("4. Check whether any additional filters are selected.")
        print("5. Click the actual SEARCH button.")
        print("6. Wait for the results to load.")
        print("7. Return to this terminal and press ENTER.")

        input("\nPress ENTER after the results are visible...")

        # Allow the rendered page to settle after the manual search.
        page.wait_for_timeout(3000)

        html_path = RAW_DIR / f"world_bank_results_{timestamp}.html"
        text_path = RAW_DIR / f"world_bank_results_{timestamp}.txt"
        screenshot_path = RAW_DIR / f"world_bank_results_{timestamp}.png"
        url_path = RAW_DIR / f"world_bank_results_{timestamp}_url.txt"

        html_path.write_text(
            page.content(),
            encoding="utf-8",
        )

        text_path.write_text(
            page.locator("body").inner_text(timeout=15000),
            encoding="utf-8",
        )

        page.screenshot(
            path=str(screenshot_path),
            full_page=True,
        )

        url_path.write_text(page.url, encoding="utf-8")

        print("\nCAPTURE COMPLETE")
        print("=" * 55)
        print("URL:", page.url)
        print("TITLE:", page.title())
        print("HTML:", html_path)
        print("TEXT:", text_path)
        print("SCREENSHOT:", screenshot_path)
        print("URL FILE:", url_path)

        print("\nVISIBLE PAGE TEXT PREVIEW:")
        print(page.locator("body").inner_text()[:5000])

        print("\nBrowser will remain open for 30 seconds.")
        page.wait_for_timeout(30000)
        browser.close()


if __name__ == "__main__":
    main()
