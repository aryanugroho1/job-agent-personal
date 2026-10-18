"""
agents/google_scraper.py
Scraper for Google Careers (careers.google.com / Google Cloud) using Playwright.
Discovers jobs across Japan, Singapore, and United Kingdom, extracting Minimum and Preferred Qualifications.
"""
import re
import time
import urllib.parse
from typing import Any
from playwright.sync_api import BrowserContext, sync_playwright

class GoogleScraper:
    """
    Scrapes job listings from Google Careers portal (Single Page Application).
    """

    BASE_URL = "https://www.google.com/about/careers/applications/jobs/results/"

    def __init__(self, context: BrowserContext | None = None):
        self.context = context

    def scrape_jobs(
        self,
        keywords: list[str],
        locations: list[dict[str, str]],
        limit_per_query: int = 5
    ) -> list[dict[str, Any]]:
        """
        Discovers jobs on Google Careers across keywords and target locations.

        Args:
            keywords: List of search terms (e.g. ['Google Cloud', 'Solutions Architect'])
            locations: List of location dicts with 'name' and 'query_location'
            limit_per_query: Max results per keyword/location combination
        """
        discovered_jobs: list[dict[str, Any]] = []
        seen_job_ids: set[str] = set()

        # Check if caller passed a context, or instantiate our own
        should_close_browser = False
        if not self.context:
            p = sync_playwright().start()
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            )
            self.context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            self.context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            should_close_browser = True

        page = self.context.new_page()

        try:
            for loc in locations:
                loc_name = loc.get("name") or loc.get("query_location") or "Japan"
                query_loc = loc.get("query_location") or loc_name

                for kw in keywords:
                    print(f"[Google Scraper] Scanning Google Careers for '{kw}' in '{loc_name}'...")
                    encoded_q = urllib.parse.quote(kw)
                    encoded_loc = urllib.parse.quote(query_loc)
                    search_url = f"{self.BASE_URL}?q={encoded_q}&location={encoded_loc}"

                    try:
                        page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
                        time.sleep(3.5)

                        # Dismiss cookie consent banner if visible
                        agree_btn = page.locator("button:has-text('Agree'), button:has-text('No thanks')").first
                        if agree_btn.is_visible():
                            agree_btn.click()
                            time.sleep(1)

                        # Check job titles on page
                        title_locators = page.locator("h3.QJPWVe").all()
                        print(f"  └─ Found {len(title_locators)} job cards for '{kw}' (fetching up to {limit_per_query})")

                        for idx, title_el in enumerate(title_locators[:limit_per_query]):
                            try:
                                title_text = title_el.inner_text().strip()
                                if not title_text:
                                    continue

                                # Locate card container and ensure it is scrolled into view
                                card_box = title_el.locator("xpath=./ancestor::li | ./ancestor::div[contains(@class, 's5Nuxf')] | ./ancestor::div[@role='listitem'] | ./ancestor::div[contains(@class, 'lLfZXe')]").first
                                if card_box.count() > 0:
                                    try:
                                        card_box.scroll_into_view_if_needed(timeout=2000)
                                    except Exception:
                                        pass

                                # Click Learn more or the title itself to expand details
                                learn_more = card_box.locator("div.VfPpkd-LgbsSe:has-text('Learn more'), button:has-text('Learn more')").first if card_box.count() > 0 else title_el
                                target_click = learn_more if learn_more.is_visible() else title_el

                                try:
                                    target_click.scroll_into_view_if_needed(timeout=2000)
                                    target_click.click(timeout=3000)
                                except Exception:
                                    target_click.evaluate("el => el.click()")

                                time.sleep(2.0)

                                # Extract job ID from current URL
                                current_url = page.url
                                job_id_match = re.search(r"/jobs/results/(\d+)", current_url)
                                raw_id = job_id_match.group(1) if job_id_match else str(hash(title_text + loc_name))

                                if raw_id in seen_job_ids:
                                    continue
                                seen_job_ids.add(raw_id)

                                # Parse detailed job description pane
                                job_data = self._parse_job_details(page, raw_id, title_text, loc_name, current_url)
                                discovered_jobs.append(job_data)
                                print(f"    • Added: {title_text} (ID: {raw_id})")

                            except Exception as card_err:
                                print(f"    ⚠️ Error extracting card #{idx + 1}: {card_err}")
                                continue

                    except Exception as query_err:
                        print(f"  └─ [Error] Query failed for '{kw}' in '{loc_name}': {query_err}")
                        continue

        finally:
            page.close()
            if should_close_browser and self.context:
                browser = self.context.browser
                if browser:
                    browser.close()

        print(f"[Google Scraper] Finished scan. Total unique jobs discovered: {len(discovered_jobs)}")
        return discovered_jobs

    def _parse_job_details(
        self,
        page: Any,
        raw_id: str,
        title: str,
        location: str,
        job_url: str
    ) -> dict[str, Any]:
        """Extracts qualifications and text from Google's expanded job view."""
        min_quals_text = ""
        pref_quals_text = ""
        about_text = ""

        try:
            # Minimum qualifications
            min_loc = page.locator("xpath=//*[contains(text(), 'Minimum qualifications')]/following-sibling::ul[1] | //*[contains(text(), 'Minimum qualifications')]/..").first
            if min_loc.count() > 0 and min_loc.is_visible():
                raw_min = min_loc.inner_text()
                min_quals_text = raw_min.replace("Minimum qualifications:", "").replace("Minimum qualifications", "").strip()

            # Preferred qualifications
            pref_loc = page.locator("xpath=//*[contains(text(), 'Preferred qualifications')]/following-sibling::ul[1] | //*[contains(text(), 'Preferred qualifications')]/..").first
            if pref_loc.count() > 0 and pref_loc.is_visible():
                raw_pref = pref_loc.inner_text()
                pref_quals_text = raw_pref.replace("Preferred qualifications:", "").replace("Preferred qualifications", "").strip()

            # About the job
            about_loc = page.locator("xpath=//*[contains(text(), 'About the job')]/following-sibling::div[1] | //div[contains(@class, 'BDp6t')]").first
            if about_loc.count() > 0 and about_loc.is_visible():
                raw_about = about_loc.inner_text()
                about_text = raw_about.replace("About the job", "").strip()

        except Exception:
            pass

        # Build unified full description for LLM ATS matcher
        full_desc_parts = []
        if about_text:
            full_desc_parts.append(f"ABOUT THE JOB:\n{about_text}")
        if min_quals_text:
            full_desc_parts.append(f"MINIMUM QUALIFICATIONS:\n{min_quals_text}")
        if pref_quals_text:
            full_desc_parts.append(f"PREFERRED QUALIFICATIONS:\n{pref_quals_text}")

        full_description = "\n\n".join(full_desc_parts) or f"Google Role: {title} in {location}"

        # Determine clean company tag
        company_tag = "Google Cloud" if "cloud" in title.lower() or "cloud" in full_description.lower() else "Google"

        return {
            "platform": "Google",
            "job_id": f"goog-{raw_id}",
            "company": company_tag,
            "role_title": title,
            "location": location,
            "url": job_url,
            "apply_url": job_url,
            "applicant_count": 0,
            "passed_early_bird": True,
            "description": full_description,
            "minimum_qualifications": min_quals_text,
            "preferred_qualifications": pref_quals_text,
            "posted_date": "Recent",
        }

if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    scraper = GoogleScraper()
    test_locations = [
        {"name": "Japan", "query_location": "Japan"},
        {"name": "Singapore", "query_location": "Singapore"},
        {"name": "United Kingdom", "query_location": "United Kingdom"}
    ]
    test_kws = ["Google Cloud", "Pixel", "Data Engineer"]

    print("=" * 60)
    print("Testing Google Careers Scraper (Japan, Singapore, UK)")
    print("=" * 60)

    results = scraper.scrape_jobs(keywords=test_kws, locations=test_locations, limit_per_query=2)
    print(f"\n--- DISCOVERED GOOGLE ROLES ({len(results)}) ---")
    for idx, r in enumerate(results, start=1):
        print(f"{idx}. [{r['company']}] {r['role_title']} ({r['location']})")
        print(f"   URL: {r['url']}")
        print(f"   Min Quals Preview: {r['minimum_qualifications'][:100]}...\n")
