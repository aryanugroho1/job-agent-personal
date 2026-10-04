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
                    role_title = title_el.first.inner_text().strip() if title_el.count() > 0 else ""
                    company_el = page.locator(".job-details-jobs-unified-top-card__primary-description-container a, .job-details-jobs-unified-top-card__company-name")
                    company = company_el.first.inner_text().strip() if company_el.count() > 0 else ""

                    # Top Card / Applicant description container
                    top_card_desc = page.locator(".job-details-jobs-unified-top-card__primary-description-container, .jobs-unified-top-card__subtitle-primary-grouping")
                    desc_text = top_card_desc.first.inner_text() if top_card_desc.count() > 0 else ""

                    # Check Early-Bird criteria (< applicant_threshold applicants)
                    applicant_count = self._parse_linkedin_applicants(desc_text)
                    passed_early_bird = (applicant_count is not None and applicant_count <= applicant_threshold) or (
                        any(s in desc_text.lower() for s in ["under 10", "first 25", "under 25"])
                    )

                    # Full Job Description text
                    jd_el = page.locator("#job-details, .jobs-description__content")
                    jd_text = jd_el.first.inner_text().strip() if jd_el.count() > 0 else ""

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
        Automatically uses localized Indeed domain based on country.
        """
        page = self.context.new_page()
        jobs = []

        try:
            encoded_kw = urllib.parse.quote(keyword)
            encoded_loc = urllib.parse.quote(location)
            
            # Country-specific domain mapping for Indeed
            loc_lower = location.lower()
            if any(k in loc_lower for k in ["japan", "tokyo", "osaka"]):
                base_url = "https://jp.indeed.com"
                query_loc = "" if loc_lower == "japan" else location
            elif "singapore" in loc_lower:
                base_url = "https://sg.indeed.com"
                query_loc = ""
            elif any(k in loc_lower for k in ["united kingdom", "london", "uk"]):
                base_url = "https://uk.indeed.com"
                query_loc = "" if loc_lower in ["united kingdom", "uk"] else location
            elif any(k in loc_lower for k in ["germany", "berlin", "munich"]):
                base_url = "https://de.indeed.com"
                query_loc = "" if loc_lower == "germany" else location
            else:
                base_url = "https://www.indeed.com"
                query_loc = location

            encoded_kw = urllib.parse.quote(keyword)
            encoded_loc = urllib.parse.quote(query_loc) if query_loc else ""
            loc_param = f"&l={encoded_loc}" if encoded_loc else ""
            url = f"{base_url}/jobs?q={encoded_kw}{loc_param}&fromage=1"
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(3)

            # Check if Cloudflare challenge is present and allow resolution
            if "Just a moment" in page.title():
                for _ in range(8):
                    time.sleep(1)
                    if "Just a moment" not in page.title():
                        break

            cards = page.locator(".job_seen_beacon, .cardOutline, div[data-jk]").all()
            if len(cards) == 0 and "fromage=1" in url:
                # Fallback to last 7 days for niche tech roles if past 24h yields 0
                url_7d = f"{base_url}/jobs?q={encoded_kw}{loc_param}&fromage=7"
                page.goto(url_7d, wait_until="domcontentloaded", timeout=45000)
                time.sleep(3)
                if "Just a moment" in page.title():
                    for _ in range(8):
                        time.sleep(1)
                        if "Just a moment" not in page.title():
                            break
                cards = page.locator(".job_seen_beacon, .cardOutline, div[data-jk]").all()

            print(f"[Indeed Scraper] Found {len(cards)} job cards for '{keyword}' in '{location}' ({base_url})")

            for card in cards[:limit]:
                try:
                    card.scroll_into_view_if_needed()
                    card.click(timeout=5000)
                    time.sleep(1.5)

                    # Check Easily apply badge (English & Japanese)
                    card_text = card.inner_text().lower()
                    has_easy_apply = (
                        card.locator("[data-testid='indeedApply'], .iaIcon, .indeed-apply-widget").count() > 0
                        or any(k in card_text for k in ["easily apply", "apply now", "カンタン応募", "かんたん応募", "プロフィールだけでカンタン応募", "履歴書のみで応募"])
                    )
                    if not has_easy_apply:
                        continue

                    title_el = card.locator("h2.jobTitle span, a[data-jk]")
                    role_title = title_el.first.inner_text().strip() if title_el.count() > 0 else ""
                    comp_el = card.locator("[data-testid='company-name']")
                    company = comp_el.first.inner_text().strip() if comp_el.count() > 0 else ""

                    # Indeed job id
                    job_id = card.get_attribute("data-jk") or ""
                    if not job_id:
                        a_el = card.locator("a[data-jk]")
                        if a_el.count() > 0:
                            job_id = a_el.first.get_attribute("data-jk") or ""
                    if not job_id:
                        h2_a = card.locator("h2.jobTitle a")
                        if h2_a.count() > 0:
                            job_id = h2_a.first.get_attribute("data-jk") or ""

                    # Direct job URL
                    job_url = f"{base_url}/viewjob?jk={job_id}" if job_id else page.url

                    # Early bird: fromage=1 already ensures <=24h postings.
                    # Exclude only if marked with older age tags (e.g. reposted/sponsored)
                    date_el = card.locator(".date, [data-testid='myJobsStateDate']")
                    date_text = date_el.first.inner_text().lower() if date_el.count() > 0 else ""
                    is_old = any(b in date_text for b in ["30+", "14+", "7+", "30日前", "14日前", "7日前"])
                    passed_early_bird = not is_old

                    # JD text
                    jd_pane = page.locator("#jobDescriptionText")
                    jd_text = jd_pane.first.inner_text().strip() if jd_pane.count() > 0 else ""

                    jobs.append({
                        "platform": "Indeed",
                        "job_id": f"in-{job_id}" if job_id else f"in-{hash(role_title + company)}",
                        "company": company,
                        "role_title": role_title,
                        "location": location,
                        "url": job_url,
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
