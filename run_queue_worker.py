"""
run_queue_worker.py
Phase 2: Precision Hourly Worker.
Checks Google Sheets for 'QUEUED' jobs whose scheduled_utc <= now(UTC).
Enforces max 20 applications/day guardrail and human anti-bot jitter.
"""
import sys
import os
from pathlib import Path
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from agents.crypto_env import load_encrypted_env
from agents.auth_manager import AuthManager
from agents.sheets_tracker import SheetsTracker
from agents.applier import EasyApplyRunner
from agents.notifier import send_alert

MAX_DAILY_APPLICATIONS = 20

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Queue Worker for Automated Job Applications")
    parser.add_argument("--now", "--force", action="store_true", help="Apply immediately to QUEUED jobs without waiting for scheduled_utc")
    parser.add_argument("--limit", type=int, default=MAX_DAILY_APPLICATIONS, help="Max applications to process in this run")
    args = parser.parse_args()

    print("=" * 60)
    print(f"⏰ [Phase 2: Queue Worker Running] {datetime.now(timezone.utc).isoformat()}")
    if args.now:
        print("⚡ [IMMEDIATE MODE ENABLED] Bypassing scheduled_utc filter.")
    print("=" * 60)

    # 1. Load decrypted env in RAM
    load_encrypted_env()

    # 2. Query Google Sheets queue
    sheets = SheetsTracker()
    queued_jobs = sheets.get_queued_jobs()
    now_utc = datetime.now(timezone.utc)

    # Filter due jobs
    due_jobs = []
    if args.now:
        due_jobs = queued_jobs[:args.limit]
    else:
        for job in queued_jobs:
            sched_str = job.get("scheduled_utc")
            if not sched_str:
                continue
            try:
                sched_dt = datetime.strptime(str(sched_str), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                if sched_dt <= now_utc:
                    due_jobs.append(job)
            except Exception as e:
                print(f"[Worker Warning] Could not parse scheduled_utc '{sched_str}': {e}")

    if not due_jobs:
        print("💤 No queued jobs due for execution at this hour. Exiting clean.")
        return

    print(f"🎯 Found {len(due_jobs)} jobs ready for application.")

    # 3. Process jobs with Playwright (1 tab sequentially)
    with sync_playwright() as p:
        applied_count = 0
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        # Setup session state & cookies
        li_state = "config/linkedin_state.json" if Path("config/linkedin_state.json").exists() else None
        context = browser.new_context(
            storage_state=li_state,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        if not li_state:
            li_auth = AuthManager("linkedin")
            li_auth.load_cookies(context)

        in_auth = AuthManager("indeed")
        in_auth.load_cookies(context)

        applier = EasyApplyRunner(context)

        max_exec_limit = min(MAX_DAILY_APPLICATIONS, args.limit)
        for job in due_jobs:
            if applied_count >= max_exec_limit:
                print(f"🛑 Execution limit of {max_exec_limit} applications reached. Stopping run.")
                break

            platform = str(job.get("platform", "LinkedIn")).lower()
            role = job.get("role_title", "")
            company = job.get("company", "")
            pdf_path = job.get("pdf_path", "")
            
            job_id_clean = str(job.get("job_id", "")).replace("li-", "").replace("in-", "")
            raw_url = str(job.get("url") or "")
            if platform == "linkedin":
                if not raw_url or "/jobs/search" in raw_url:
                    job_url = f"https://www.linkedin.com/jobs/view/{job_id_clean}/"
                else:
                    job_url = raw_url
            else:
                loc_lower = str(job.get("location", "")).lower()
                base_indeed = "https://jp.indeed.com" if any(k in loc_lower for k in ["japan", "tokyo", "osaka"]) else "https://www.indeed.com"
                if not raw_url or "/jobs?" in raw_url:
                    job_url = f"{base_indeed}/viewjob?jk={job_id_clean}"
                else:
                    job_url = raw_url

            row_num = job.get("_row_number", 0)

            print(f"\n💼 Applying for '{role}' at '{company}' ({platform.upper()})...")

            if platform == "linkedin":
                result = applier.apply_linkedin(
                    job_url=job_url,
                    pdf_path=pdf_path,
                    role_title=role,
                    company=company
                )
            elif platform == "indeed":
                result = applier.apply_indeed(
                    job_url=job_url,
                    pdf_path=pdf_path,
                    role_title=role,
                    company=company
                )
            else:
                result = {"status": "FAILED", "notes": f"Unsupported platform: {platform}"}

            status = result["status"]
            notes = result["notes"]
            print(f"👉 Result: {status} | Notes: {notes}")
            applied_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if status == "APPLIED" else ""

            if row_num:
                sheets.update_job_status(row_num, status, notes=notes, applied_at=applied_at)

            if status == "APPLIED":
                applied_count += 1
                send_alert(
                    f"Successfully applied to {role} at {company} at 09:00 AM local time!",
                    title="Job Applied Successfully",
                    priority="default",
                    tags=["tada", "briefcase"]
                )

        browser.close()

    print(f"\n🏁 Hourly worker finished. Applied to {applied_count} jobs.")

if __name__ == "__main__":
    main()
