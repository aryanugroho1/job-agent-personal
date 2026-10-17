import html
import json
import re
import urllib.parse
import urllib.request
from typing import Any

# ISO 3166-1 alpha-3 mapping for target countries
COUNTRY_NAME_TO_CODE = {
    "japan": "JPN",
    "jpn": "JPN",
    "singapore": "SGP",
    "sgp": "SGP",
    "united kingdom": "GBR",
    "uk": "GBR",
    "gbr": "GBR",
    "great britain": "GBR",
    "united states": "USA",
    "usa": "USA",
    "germany": "DEU",
    "deu": "DEU",
}

CODE_TO_COUNTRY_NAME = {
    "JPN": "Japan",
    "SGP": "Singapore",
    "GBR": "United Kingdom",
    "USA": "United States",
    "DEU": "Germany",
}

def clean_html_text(raw_html: str | None) -> str:
    """Cleans HTML tags and entities from Amazon job descriptions."""
    if not raw_html:
        return ""
    # Normalize line breaks and list items
    text = re.sub(r"<br\s*/?>", "\n", raw_html, flags=re.IGNORECASE)
    text = re.sub(r"</?(li|p|div|h[1-6])>", "\n", text, flags=re.IGNORECASE)
    # Strip remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode HTML entities like &amp;, &quot;, &lt;
    text = html.unescape(text)
    # Collapse multiple empty lines
    lines = [line.strip() for line in text.split("\n")]
    cleaned_lines = []
    prev_blank = False
    for line in lines:
        if not line:
            if not prev_blank:
                cleaned_lines.append("")
                prev_blank = True
        else:
            cleaned_lines.append(line)
            prev_blank = False
    return "\n".join(cleaned_lines).strip()

class AmazonScraper:
    """
    Amazon & AWS Jobs Scraper utilizing the official amazon.jobs search REST API.
    Does not require headless browser overhead for job discovery.
    """

    BASE_URL = "https://www.amazon.jobs/en/search.json"

    def __init__(self, user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"):
        self.headers = {
            "User-Agent": user_agent,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        }

    def scrape_jobs(
        self,
        keywords: list[str],
        countries: list[str],
        limit_per_query: int = 10,
        sort: str = "recent"
    ) -> list[dict[str, Any]]:
        """
        Discovers jobs on Amazon across specified keywords and country codes.
        
        Args:
            keywords: List of search terms (e.g. ['Solutions Architect', 'Data Engineer'])
            countries: List of country codes or names (e.g. ['JPN', 'SGP', 'GBR'])
            limit_per_query: Max results per keyword/country combination
            sort: 'recent' (newest first) or 'relevance'
        """
        discovered_jobs: list[dict[str, Any]] = []
        seen_job_ids: set[str] = set()

        # Normalize country codes
        normalized_codes = []
        for c in countries:
            code = COUNTRY_NAME_TO_CODE.get(c.lower().strip(), c.upper().strip())
            if code not in normalized_codes:
                normalized_codes.append(code)

        for country_code in normalized_codes:
            country_name = CODE_TO_COUNTRY_NAME.get(country_code, country_code)
            for kw in keywords:
                print(f"[Amazon Scraper] Querying '{kw}' in {country_name} ({country_code})...")
                params = [
                    ("base_query", kw),
                    ("normalized_country_code[]", country_code),
                    ("sort", sort),
                    ("result_limit", str(limit_per_query)),
                ]
                query_string = urllib.parse.urlencode(params)
                req_url = f"{self.BASE_URL}?{query_string}"

                try:
                    req = urllib.request.Request(req_url, headers=self.headers)
                    with urllib.request.urlopen(req, timeout=15) as res:
                        data = json.loads(res.read().decode("utf-8"))
                        jobs_list = data.get("jobs", [])
                        total_hits = data.get("hits", 0)
                        print(f"  └─ Found {total_hits} total hits on Amazon (fetching top {len(jobs_list)})")

                        for item in jobs_list:
                            raw_id = str(item.get("id") or item.get("id_icims") or "")
                            if not raw_id or raw_id in seen_job_ids:
                                continue
                            seen_job_ids.add(raw_id)

                            job_record = self._format_job_item(item, country_name, country_code)
                            discovered_jobs.append(job_record)

                except Exception as e:
                    print(f"  └─ [Error] Failed querying Amazon for '{kw}' in {country_code}: {e}")

        print(f"[Amazon Scraper] Total unique jobs discovered across {normalized_codes}: {len(discovered_jobs)}")
        return discovered_jobs

    def _format_job_item(self, item: dict[str, Any], country_name: str, country_code: str) -> dict[str, Any]:
        """Formats raw Amazon API job JSON into the standardized application agent schema."""
        raw_id = str(item.get("id") or item.get("id_icims") or "")
        title = item.get("title", "").strip()
        company = item.get("company_name") or "Amazon Web Services (AWS)"
        city = item.get("city") or ""
        location_str = f"{city}, {country_name}".strip(", ")

        job_path = item.get("job_path") or f"/en/jobs/{raw_id}"
        web_url = f"https://www.amazon.jobs{job_path}"
        apply_url = item.get("url_next_step") or f"https://account.amazon.jobs/jobs/{raw_id}/apply"

        desc_raw = item.get("description", "")
        basic_raw = item.get("basic_qualifications", "")
        pref_raw = item.get("preferred_qualifications", "")

        desc_clean = clean_html_text(desc_raw)
        basic_clean = clean_html_text(basic_raw)
        pref_clean = clean_html_text(pref_raw)

        # Build full structured description for LLM ATS matching
        full_description_parts = []
        if desc_clean:
            full_description_parts.append(f"JOB OVERVIEW:\n{desc_clean}")
        if basic_clean:
            full_description_parts.append(f"BASIC QUALIFICATIONS:\n{basic_clean}")
        if pref_clean:
            full_description_parts.append(f"PREFERRED QUALIFICATIONS:\n{pref_clean}")
        full_description = "\n\n".join(full_description_parts)

        return {
            "platform": "Amazon",
            "job_id": f"amz-{raw_id}",
            "company": company,
            "role_title": title,
            "location": location_str,
            "country_code": country_code,
            "city": city,
            "url": web_url,
            "apply_url": apply_url,
            "applicant_count": 0,
            "passed_early_bird": True,
            "description": full_description,
            "basic_qualifications": basic_clean,
            "preferred_qualifications": pref_clean,
            "posted_date": item.get("posted_date", ""),
            "department": item.get("business_category", ""),
        }

if __name__ == "__main__":
    # Test script standalone for Japan, Singapore, and United Kingdom
    scraper = AmazonScraper()
    test_keywords = ["Solutions Architect", "Data Engineer", "Telecom", "Cloud Architect"]
    test_countries = ["Japan", "Singapore", "United Kingdom"]

    print("=" * 60)
    print("Testing Amazon & AWS Job Scraper for Japan, Singapore & UK")
    print("=" * 60)

    results = scraper.scrape_jobs(keywords=test_keywords, countries=test_countries, limit_per_query=3)

    print("\n--- SAMPLE DISCOVERED JOBS ---")
    for idx, j in enumerate(results[:10], start=1):
        print(f"{idx}. [{j['country_code']}] {j['role_title']} ({j['company']})")
        print(f"   Location: {j['location']}")
        print(f"   Web URL: {j['url']}")
        print(f"   Apply URL: {j['apply_url']}")
        print(f"   Basic Quals Preview: {j['basic_qualifications'][:120]}...\n")
