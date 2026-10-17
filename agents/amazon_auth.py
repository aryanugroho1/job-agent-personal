"""
agents/amazon_auth.py
Manages authentication for Amazon Jobs (passport.amazon.jobs / account.amazon.jobs).
Supports:
1. Interactive Headful Login (One-Time Setup with 2FA/OTP handling)
2. Persistent Browser Profile storage in config/amazon_user_data
3. Session state export to config/amazon_state.json & config/amazon_cookies.json
4. Headless session validity verification
"""
import json
import os
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, BrowserContext, Page

CONFIG_DIR = Path("config")
PROFILE_DIR = CONFIG_DIR / "amazon_user_data"
STATE_FILE = CONFIG_DIR / "amazon_state.json"
COOKIES_FILE = CONFIG_DIR / "amazon_cookies.json"

class AmazonAuthManager:
    """Manages persistent candidate authentication sessions for amazon.jobs."""

    def __init__(self, profile_dir: Path = PROFILE_DIR, state_file: Path = STATE_FILE):
        self.profile_dir = profile_dir
        self.state_file = state_file
        self.cookies_file = COOKIES_FILE
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    def is_session_active(self, page: Page) -> bool:
        """
        Navigates to account.amazon.jobs to verify if the session is currently authenticated.
        Returns True if authenticated, False if redirected to passport.amazon.jobs or login wall.
        """
        try:
            print("[Amazon Auth] Verifying session validity on account.amazon.jobs...")
            page.goto("https://account.amazon.jobs/dashboard", wait_until="domcontentloaded", timeout=25000)
            time.sleep(2.5)

            curr_url = page.url.lower()
            if "passport.amazon.jobs" in curr_url or "/login" in curr_url or "/signin" in curr_url:
                print(f"[Amazon Auth] Redirected to login ({curr_url}). Session is NOT active.")
                return False

            # Check for candidate dashboard indicators
            is_dashboard = (
                "account.amazon.jobs" in curr_url
                and any(
                    page.locator(sel).count() > 0
                    for sel in [
                        "a[href*='/applications']",
                        "a[href*='/profile']",
                        "[data-test-id='dashboard']",
                        "button:has-text('Sign out')",
                        "button:has-text('Log out')",
                        "button:has-text('サインアウト')",
                        "button:has-text('ログアウト')",
                        "header",
                    ]
                )
            )
            return is_dashboard
        except Exception as e:
            print(f"[Amazon Auth] Error verifying session: {e}")
            return False

    def export_session_state(self, context: BrowserContext):
        """Exports the active session state and cookies to config/ files for headless workers."""
        try:
            context.storage_state(path=str(self.state_file))
            cookies = context.cookies()
            with open(self.cookies_file, "w", encoding="utf-8") as f:
                json.dump(cookies, f, indent=2)
            print(f"[Amazon Auth] Successfully exported session state to {self.state_file}")
        except Exception as e:
            print(f"[Amazon Auth Warning] Could not export session state: {e}")

    def interactive_login(self):
        """
        Launches a visible Chromium window with persistent user data directory.
        Allows the user to log in manually, complete 2FA/OTP, and persist the session.
        """
        print("=" * 65)
        print("🔐 AMAZON JOBS INTERACTIVE LOGIN (ONE-TIME SETUP)")
        print("=" * 65)
        print("A browser window is launching.")
        print("1. Log in with your Amazon account (or Google / LinkedIn).")
        print("2. Complete any SMS OTP, Authenticator app, or 2FA verification.")
        print("3. Once you reach your Candidate Dashboard, this tool will detect")
        print("   your session and save it automatically.")
        print("=" * 65)

        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--start-maximized"
                ],
                no_viewport=True,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://account.amazon.jobs/dashboard", wait_until="domcontentloaded")

            print("\n⏳ Waiting for login completion... (Press Ctrl+C in terminal if you wish to abort)")

            # Auto-detect login up to 5 minutes
            logged_in = False
            start_time = time.time()
            max_wait_seconds = 300

            while time.time() - start_time < max_wait_seconds:
                time.sleep(3)
                curr_url = page.url.lower()

                # If user successfully left passport.amazon.jobs and is on account.amazon.jobs
                if "account.amazon.jobs" in curr_url and "passport" not in curr_url and "signin" not in curr_url:
                    # Give page 2 seconds to settle
                    time.sleep(2)
                    logged_in = True
                    print("\n🎉 [SUCCESS] Candidate Dashboard access detected!")
                    break

            if logged_in:
                self.export_session_state(context)
                print("✅ Session saved! You can now run automated discovery and applications.")
            else:
                print("⚠️ Timeout waiting for login. Exporting current state anyway...")
                self.export_session_state(context)

            context.close()

    def check_session(self) -> bool:
        """Headless check to see if current session is still valid."""
        with sync_playwright() as p:
            launch_args = ["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            if self.state_file.exists():
                browser = p.chromium.launch(headless=True, args=launch_args)
                context = browser.new_context(
                    storage_state=str(self.state_file),
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                )
                page = context.new_page()
                is_valid = self.is_session_active(page)
                browser.close()
                return is_valid
            elif self.profile_dir.exists():
                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(self.profile_dir),
                    headless=True,
                    args=launch_args
                )
                page = context.pages[0] if context.pages else context.new_page()
                is_valid = self.is_session_active(page)
                context.close()
                return is_valid
            else:
                print("[Amazon Auth] No saved session state or profile found.")
                return False

if __name__ == "__main__":
    auth_mgr = AmazonAuthManager()
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        valid = auth_mgr.check_session()
        print(f"[Session Status] Active & Valid: {valid}")
        sys.exit(0 if valid else 1)
    else:
        auth_mgr.interactive_login()
