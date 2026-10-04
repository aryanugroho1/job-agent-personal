"""
run_daily_discovery.py
Phase 1: Daily Discovery, Early-Bird Filtering, Deduplication, AI Match Scoring, and Resume Prep.
Executed daily (e.g. 06:00 AM JST) via cron.
"""
import sys
import json
from pathlib import Path
from datetime import datetime, timezone
import yaml
from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from agents.crypto_env import load_encrypted_env
from agents.auth_manager import AuthManager
from agents.scraper import JobScraper
from agents.dedup import is_duplicate
from agents.matcher import evaluate_job_match
from agents.doc_generator import generate_custom_cv
from agents.timezone_resolver import resolve_timezone, calculate_target_utc
from agents.sheets_tracker import SheetsTracker
from agents.notifier import send_alert

def main():
    print("=" * 60)
    print(f"🚀 [Phase 1: Discovery Pipeline Started] {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    # 1. Load Encrypted Environment into RAM
    load_encrypted_env()

    # 2. Load Config & Master CV
    with open("config/settings.yaml", "r") as f:
        settings = yaml.safe_load(f)

    with open("master_data/master_cv.json", "r", encoding="utf-8") as f:
        master_cv = json.load(f)

    sheets = SheetsTracker()
    keywords = settings["search"]["keywords"]
    target_locations = settings["search"]["target_locations"]
    min_score = settings["ai_matching"]["min_match_score"]

    applicant_threshold = settings.get("safety", {}).get("applicant_threshold", 25)

    raw_candidates = []

    # 3. Launch Playwright Headless with anti-automation flags
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        li_state = "config/linkedin_state.json" if Path("config/linkedin_state.json").exists() else None
        context = browser.new_context(
            storage_state=li_state,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        # Auth setup
        if not li_state:
            li_auth = AuthManager("linkedin")
            li_auth.load_cookies(context)

        in_auth = AuthManager("indeed")
        in_auth.load_cookies(context)

        scraper = JobScraper(context)

        # Iterate keywords & locations
        for kw in keywords:
            for loc in target_locations:
                loc_name = loc["name"]
                print(f"\n🔍 Scanning LinkedIn for '{kw}' in '{loc_name}'...")
                li_jobs = scraper.scrape_linkedin(kw, loc_name, limit=10, applicant_threshold=applicant_threshold)
                raw_candidates.extend(li_jobs)

                print(f"🔍 Scanning Indeed for '{kw}' in '{loc_name}'...")
                in_jobs = scraper.scrape_indeed(kw, loc_name, limit=10)
                raw_candidates.extend(in_jobs)

        browser.close()

    print(f"\n📊 Total raw postings discovered: {len(raw_candidates)}")

    # 4. Filter & Deduplicate
    valid_jobs = []
    for job in raw_candidates:
        # Early-bird applicant check
        if not job.get("passed_early_bird", False):
            job["status"] = "SKIPPED_APPLICANTS"
            job["notes"] = f"Applicants ({job.get('applicant_count')}) >= {applicant_threshold}"
            sheets.append_job(job)
            continue

        # Check cross-platform deduplication
        dup_found = False
        for existing in valid_jobs:
            if is_duplicate(job, existing):
                dup_found = True
                break
        if dup_found:
            job["status"] = "SKIPPED_DUPLICATE"
            job["notes"] = "Identical role already discovered on higher priority platform"
            sheets.append_job(job)
            continue

        valid_jobs.append(job)

    print(f"🎯 Postings passing Early-Bird & Dedup: {len(valid_jobs)}")

    # 5. AI Evaluation, Resume Generation, & Queue Scheduling
    queued_count = 0
    for job in valid_jobs:
        print(f"\n🤖 Evaluating: {job['role_title']} at {job['company']}...")
        match_result = evaluate_job_match(master_cv, job)
        score = match_result.get("match_score", 0)
        job["match_score"] = score

        if score < min_score:
            print(f"❌ Match score {score}% is below threshold ({min_score}%). Skipping.")
            job["status"] = "SKIPPED_LOW_SCORE"
            job["notes"] = f"Match score {score}% < {min_score}%. {match_result.get('reasoning')}"
            sheets.append_job(job)
            continue

        print(f"✅ Match score {score}%! Tailoring resume...")
        tailored_title = match_result.get("tailored_role_title", job["role_title"])
        tailored_summary = match_result.get("tailored_summary", master_cv["summary"]["baseline"])

        pdf_path = generate_custom_cv(
            master_cv=master_cv,
            tailored_title=tailored_title,
            tailored_summary=tailored_summary,
            company_name=job["company"],
            job_id=job["job_id"].replace("li-", "").replace("in-", "")
        )
        job["pdf_path"] = str(pdf_path)

        # Resolve Timezone & Target 09:00 AM UTC
        tz_name = resolve_timezone(job["location"])
        scheduled_utc = calculate_target_utc(tz_name, target_hour=9)
        job["target_timezone"] = tz_name
        job["scheduled_utc"] = scheduled_utc.strftime("%Y-%m-%d %H:%M:%S")
        job["status"] = "QUEUED"
        job["notes"] = f"Queued for 09:00 AM local ({tz_name})"

        sheets.append_job(job)
        queued_count += 1

    send_alert(
        f"Daily Discovery complete. Queued {queued_count} high-match early-bird applications!",
        title="Discovery Pipeline Finished"
    )
    print("\n🏁 Discovery Pipeline Complete.")

if __name__ == "__main__":
    main()
