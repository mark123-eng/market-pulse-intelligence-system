from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = BASE_DIR / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

URL = "https://projects.worldbank.org/en/projects-operations/project-search"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        page = browser.new_page(
            viewport={"width": 1440, "height": 1000}
        )

        page.set_default_timeout(15000)

        try:
            print("Opening World Bank search page...")

            response = page.goto(
                URL,
                wait_until="commit",
                timeout=30000
            )

            print("HTTP status:", response.status if response else "Unknown")

            page.wait_for_timeout(15000)

            print("\nCURRENT URL:")
            print(page.url)

            print("\nPAGE TITLE:")
            print(page.title())

            print("\nVISIBLE BUTTONS AND LINKS:")

            elements = page.locator("button:visible, a:visible")

            for i in range(min(elements.count(), 150)):
                element = elements.nth(i)

                try:
                    text = element.inner_text(timeout=1000).strip()
                    tag = element.evaluate("(el) => el.tagName")
                    classes = element.get_attribute("class")
                    href = element.get_attribute("href")

                    if text or "primary-light-blue-btn" in (classes or ""):
                        print({
                            "tag": tag,
                            "text": text[:100],
                            "class": classes,
                            "href": href,
                        })

                except Exception:
                    continue

            print("\nSEARCH LINK COUNT:")
            print(
                page.locator(
                    "a.primary-light-blue-btn"
                ).count()
            )

            screenshot = RAW_DIR / "world_bank_search_diagnostic.png"
            html_file = RAW_DIR / "world_bank_search_diagnostic.html"

            page.screenshot(
                path=str(screenshot),
                full_page=True
            )

            html_file.write_text(
                page.content(),
                encoding="utf-8"
            )

            print("\nSaved screenshot:", screenshot)
            print("Saved HTML:", html_file)

            input("\nInspect the results, then press Enter to close...")

        finally:
            browser.close()


if __name__ == "__main__":
    main()