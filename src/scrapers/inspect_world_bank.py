from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://projects.worldbank.org/en/projects-operations/project-search"


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)

        try:
            page = browser.new_page()

            print("Opening World Bank project search...")
            page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            page.wait_for_timeout(5000)

            print("\nWORLD BANK SEARCH CONTROL INSPECTOR")
            print("=" * 50)

            elements = page.locator(
                "button, input, a, [role='button'], [onclick]"
            )

            total = elements.count()
            print(f"Total matching elements: {total}")

            for index in range(total):
                element = elements.nth(index)

                try:
                    details = element.evaluate(
                        """el => ({
                            tag: el.tagName,
                            text: (el.innerText || el.value || '').trim(),
                            id: el.id || '',
                            className: typeof el.className === 'string'
                                ? el.className : '',
                            type: el.getAttribute('type') || '',
                            ariaLabel: el.getAttribute('aria-label') || '',
                            visible: !!(
                                el.offsetWidth ||
                                el.offsetHeight ||
                                el.getClientRects().length
                            )
                        })"""
                    )

                    searchable = " ".join([
                        details["text"],
                        details["id"],
                        details["className"],
                        details["type"],
                        details["ariaLabel"],
                    ]).lower()

                    if (
                        "search" in searchable
                        or details["type"] == "submit"
                    ):
                        print(f"\nElement {index}:")
                        print(f"  Tag: {details['tag']}")
                        print(f"  Text: {details['text'][:150]}")
                        print(f"  ID: {details['id']}")
                        print(f"  Class: {details['className'][:150]}")
                        print(f"  Type: {details['type']}")
                        print(f"  Aria-label: {details['ariaLabel']}")
                        print(f"  Visible: {details['visible']}")

                except Exception as error:
                    print(f"Could not inspect element {index}: {error}")

            output_path = Path(
                "data/raw/world_bank_search_form.html"
            )

            output_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            output_path.write_text(
                page.content(),
                encoding="utf-8",
            )

            print(f"\nSaved HTML to {output_path.resolve()}")

            input("\nPress Enter to close the browser...")

        finally:
            browser.close()


if __name__ == "__main__":
    main()
