import re
import time
import urllib.parse
from playwright.sync_api import BrowserContext, Page

class JobScraper:
    def __init__(self, context: BrowserContext):
        self.context = context

    def scrape_linkedin(self, keyword: str, location: str, limit: int = 15, applicant_threshold: int = 25) -> list[dict]:
        """
        Discovers LinkedIn jobs with Easy Apply filter and posted past 24h.
        Applies early-bird filter (< applicant_threshold applicants).
        """
        page = self.context.new_page()
        jobs = []

        try:
            # f_AL=true: Easy Apply, f_TPR=r86400: Past 24 hours
            encoded_kw = urllib.parse.quote(keyword)
            encoded_loc = urllib.parse.quote(location)
            url = f"https://www.linkedin.com/jobs/search/?keywords={encoded_kw}&location={encoded_loc}&f_AL=true&f_TPR=r86400"
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(3)

            # Find job cards
            job_cards = page.locator(".jobs-search-results-list li.jobs-search-results__list-item, .job-card-container").all()
            print(f"[LinkedIn Scraper] Found {len(job_cards)} job cards for '{keyword}' in '{location}'")

            for card in job_cards[:limit]:
                try:
                    card.scroll_into_view_if_needed()
                    card.click(timeout=5000)
                    time.sleep(1.5)

                    # Extract Job ID
                    job_id = card.get_attribute("data-occludable-job-id") or card.get_attribute("data-job-id") or ""
                    title_el = page.locator(".job-details-jobs-unified-top-card__job-title, h1.t-24")
                    role_title = title_el.inner_text().strip() if title_el.count() > 0 else ""
                    company_el = page.locator(".job-details-jobs-unified-top-card__primary-description-container a, .job-details-jobs-unified-top-card__company-name")
                    company = company_el.inner_text().strip() if company_el.count() > 0 else ""

                    # Top Card / Applicant description container
                    top_card_desc = page.locator(".job-details-jobs-unified-top-card__primary-description-container, .jobs-unified-top-card__subtitle-primary-grouping")
                    desc_text = top_card_desc.inner_text() if top_card_desc.count() > 0 else ""

                    # Check Early-Bird criteria (< applicant_threshold applicants)
                    applicant_count = self._parse_linkedin_applicants(desc_text)
                    passed_early_bird = (applicant_count is not None and applicant_count <= applicant_threshold) or (
                        any(s in desc_text.lower() for s in ["under 10", "first 25", "under 25"])
                    )

                    # Full Job Description text
                    jd_el = page.locator("#job-details, .jobs-description__content")
                    jd_text = jd_el.inner_text().strip() if jd_el.count() > 0 else ""

                    jobs.append({
                        "platform": "LinkedIn",
                        "job_id": f"li-{job_id}",
                        "company": company,
                        "role_title": role_title,
                        "location": location,
                        "url": page.url,
                        "applicant_count": applicant_count if applicant_count is not None else 0,
                        "passed_early_bird": passed_early_bird,
                        "description": jd_text
                    })
                except Exception as e:
                    print(f"[LinkedIn Scraper] Error parsing individual card: {e}")
                    continue

        finally:
            page.close()

        return jobs

    def _parse_linkedin_applicants(self, text: str) -> int | None:
        """Parses applicant count from LinkedIn subtitle text."""
        if not text:
            return None
        lower = text.lower()
        if "under 10 applicants" in lower:
            return 5
        if "first 25 applicants" in lower or "under 25" in lower:
            return 20
        if "over" in lower:
            return 50

        match = re.search(r"(\d+)\s+applicant", lower)
        if match:
            return int(match.group(1))
        return None

    def scrape_indeed(self, keyword: str, location: str, limit: int = 15) -> list[dict]:
        """
        Discovers Indeed jobs posted in last 24h (fromage=1) with Easily Apply.
        """
        page = self.context.new_page()
        jobs = []

        try:
            encoded_kw = urllib.parse.quote(keyword)
            encoded_loc = urllib.parse.quote(location)
            # fromage=1: past 24h
            url = f"https://www.indeed.com/jobs?q={encoded_kw}&l={encoded_loc}&fromage=1"
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(3)

            cards = page.locator(".job_seen_beacon, .cardOutline").all()
            print(f"[Indeed Scraper] Found {len(cards)} job cards for '{keyword}' in '{location}'")

            for card in cards[:limit]:
                try:
                    card.scroll_into_view_if_needed()
                    card.click(timeout=5000)
                    time.sleep(1.5)

                    # Check Easily apply badge
                    has_easy_apply = card.locator("[data-testid='indeedApply'], .iaIcon").count() > 0 or "Easily apply" in card.inner_text()
                    if not has_easy_apply:
                        continue

                    title_el = card.locator("h2.jobTitle span, a[data-jk]")
                    role_title = title_el.inner_text().strip() if title_el.count() > 0 else ""
                    comp_el = card.locator("[data-testid='company-name']")
                    company = comp_el.inner_text().strip() if comp_el.count() > 0 else ""

                    # Indeed job id
                    job_id = card.get_attribute("data-jk") or ""

                    # Early bird: check date badge (Just posted / Today)
                    date_el = card.locator(".date, [data-testid='myJobsStateDate']")
                    date_text = date_el.inner_text().lower() if date_el.count() > 0 else ""
                    passed_early_bird = any(b in date_text for b in ["just posted", "today", "active", "1 day ago"])

                    # JD text
                    jd_pane = page.locator("#jobDescriptionText")
                    jd_text = jd_pane.inner_text().strip() if jd_pane.count() > 0 else ""

                    jobs.append({
                        "platform": "Indeed",
                        "job_id": f"in-{job_id}",
                        "company": company,
                        "role_title": role_title,
                        "location": location,
                        "url": page.url,
                        "applicant_count": 0,
                        "passed_early_bird": passed_early_bird,
                        "description": jd_text
                    })
                except Exception as e:
                    print(f"[Indeed Scraper] Error parsing card: {e}")
                    continue
        finally:
            page.close()

        return jobs
