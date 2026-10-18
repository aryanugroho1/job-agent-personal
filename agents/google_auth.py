"""
agents/google_auth.py
Manages persistent authentication for Google Careers (careers.google.com / Google Cloud).
Supports:
1. Interactive Headful Login (One-Time Setup with Google 2FA / Prompt handling)
2. Persistent Browser Profile storage in config/google_user_data
3. Session state export to config/google_state.json & config/google_cookies.json
4. Headless session validity verification
"""
import json
import os
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, BrowserContext, Page

CONFIG_DIR = Path("config")
PROFILE_DIR = CONFIG_DIR / "google_user_data"
STATE_FILE = CONFIG_DIR / "google_state.json"
COOKIES_FILE = CONFIG_DIR / "google_cookies.json"

class GoogleAuthManager:
    """Manages persistent candidate authentication sessions for Google Careers."""

    def __init__(self, profile_dir: Path = PROFILE_DIR, state_file: Path = STATE_FILE):
        self.profile_dir = profile_dir
        self.state_file = state_file
        self.cookies_file = COOKIES_FILE
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    def is_session_active(self, page: Page) -> bool:
        """
        Navigates to Google Careers application portal to verify if the session is currently authenticated.
        Returns True if authenticated, False if redirected to accounts.google.com login.
        """
        try:
            print("[Google Auth] Verifying session validity on careers.google.com...")
            page.goto("https://www.google.com/about/careers/applications/", wait_until="domcontentloaded", timeout=30000)
            time.sleep(3.0)

            curr_url = page.url.lower()
            if "accounts.google.com/signin" in curr_url or "/v2/identifier" in curr_url:
                print(f"[Google Auth] Redirected to login wall ({curr_url[:60]}...). Session is NOT active.")
                return False

            # Check for candidate dashboard / authenticated account indicators
            auth_indicators = [
                "button[aria-label*='Google Account']",
                "a[href*='SignOutOptions']",
                "img[alt*='Google Account']",
                "a:has-text('Sign out')",
                "button:has-text('Sign out')",
                "a[href*='/applications/user/']",
                ":has-text('My applications')",
                ":has-text('Submitted applications')",
            ]
            is_authenticated = any(page.locator(sel).count() > 0 for sel in auth_indicators)
            return is_authenticated
        except Exception as e:
            print(f"[Google Auth] Error verifying session: {e}")
            return False

    def export_session_state(self, context: BrowserContext):
        """Exports the active session state and cookies to config/ files for headless workers."""
        try:
            context.storage_state(path=str(self.state_file))
            cookies = context.cookies()
            with open(self.cookies_file, "w", encoding="utf-8") as f:
                json.dump(cookies, f, indent=2)
            print(f"[Google Auth] Successfully exported session state to {self.state_file}")
        except Exception as e:
            print(f"[Google Auth Warning] Could not export session state: {e}")

    def interactive_login(self):
        """
        Launches a visible Chromium window with persistent user data directory.
        Allows the user to log in manually, complete 2FA/Google prompt, and persist the session.
        """
        print("=" * 65)
        print("🔐 GOOGLE CAREERS INTERACTIVE LOGIN (ONE-TIME SETUP)")
        print("=" * 65)
        print("A browser window is launching.")
        print("1. Log in with your Google account.")
        print("2. Complete any 2-Step Verification, phone prompt, or OTP.")
        print("3. Once you reach the Google Careers portal / dashboard,")
        print("   your session will be detected and saved automatically.")
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
            page.goto("https://www.google.com/about/careers/applications/", wait_until="domcontentloaded")

            print("\n⏳ Waiting for login completion... (Press Ctrl+C in terminal to abort)")

            logged_in = False
            start_time = time.time()
            max_wait_seconds = 300

            while time.time() - start_time < max_wait_seconds:
                time.sleep(3)
                curr_url = page.url.lower()

                # Detect if user left login page and is back on careers portal
                if "careers/applications" in curr_url and "accounts.google.com" not in curr_url:
                    # Check for account menu / avatar
                    if any(page.locator(sel).count() > 0 for sel in ["button[aria-label*='Google Account']", "a[href*='SignOutOptions']", "img[alt*='Google Account']", "header"]):
                        time.sleep(2)
                        logged_in = True
                        print("\n🎉 [SUCCESS] Google Careers access detected!")
                        break

            if logged_in:
                self.export_session_state(context)
                print("✅ Google session saved! You can now run automated applications.")
            else:
                print("⚠️ Timeout waiting for login. Exporting current state anyway...")
                self.export_session_state(context)

            context.close()

    def check_session(self) -> bool:
        """Headless check to verify if current Google session is active."""
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
                print("[Google Auth] No saved session state or profile found.")
                return False

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    auth_mgr = GoogleAuthManager()
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        valid = auth_mgr.check_session()
        print(f"[Session Status] Google Active & Valid: {valid}")
        sys.exit(0 if valid else 1)
    else:
        auth_mgr.interactive_login()
