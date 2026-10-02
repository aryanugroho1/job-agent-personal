import os
import json
import time
from pathlib import Path
from playwright.sync_api import BrowserContext, Page
from agents.notifier import send_alert

CONFIG_DIR = Path("config")

class AuthManager:
    def __init__(self, platform: str):
        self.platform = platform.lower()
        self.cookie_file = CONFIG_DIR / f"{self.platform}_cookies.json"
        self.state_file = CONFIG_DIR / f"{self.platform}_state.json"

    def load_session(self, context: BrowserContext) -> bool:
        """Loads saved session cookies or storage state into playwright context if available."""
        loaded = False
        if self.cookie_file.exists():
            try:
                with open(self.cookie_file, "r", encoding="utf-8") as f:
                    cookies = json.load(f)
                context.add_cookies(cookies)
                loaded = True
            except Exception as e:
                print(f"[Auth Error] Failed loading cookies for {self.platform}: {e}")

        return loaded

    def load_cookies(self, context: BrowserContext) -> bool:
        return self.load_session(context)

    def save_session(self, context: BrowserContext):
        """Saves current browser session cookies and storage state."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            cookies = context.cookies()
            with open(self.cookie_file, "w", encoding="utf-8") as f:
                json.dump(cookies, f, indent=2)
            context.storage_state(path=str(self.state_file))
            print(f"[Auth] Saved cookies and session state for {self.platform}.")
        except Exception as e:
            print(f"[Auth Error] Failed saving session for {self.platform}: {e}")

    def save_cookies(self, context: BrowserContext):
        self.save_session(context)

    def is_session_valid(self, page: Page) -> bool:
        """
        Navigates to home/feed to verify if current cookies maintain an authenticated session.
        """
        if self.platform == "linkedin":
            page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
            if any(x in page.url for x in ["/login", "/authwall", "/checkpoint"]):
                return False
            # Authenticated if on feed or nav header exists
            return "/feed" in page.url or "feed" in page.title().lower() or page.locator("#global-nav, nav").count() > 0
        elif self.platform == "indeed":
            page.goto("https://www.indeed.com/", wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
            if any(x in page.url for x in ["/auth", "/login"]):
                return False
            is_logged_in = page.locator("[data-gnav-element-name='Profile'], [aria-label='profile'], a[href*='/account']").count() > 0
            return is_logged_in
        return False

    def login_linkedin(self, page: Page, context: BrowserContext) -> bool:
        """
        Automates LinkedIn login using credentials from RAM environment.
        Sends ntfy.sh alert if OTP/2FA or CAPTCHA is detected.
        """
        user = os.getenv("LINKEDIN_USER")
        password = os.getenv("LINKEDIN_PASS")

        if not user or not password:
            print("[Auth Error] LINKEDIN_USER or LINKEDIN_PASS not set in environment.")
            return False

        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        page.fill("#username", user)
        page.fill("#password", password)
        page.click("button[type='submit']")
        time.sleep(5)

        # Check for OTP or Security Challenge
        if "challenge" in page.url or page.locator("input#input__email_verification_pin, input#input__phone_pin").count() > 0:
            send_alert(
                f"LinkedIn requires 2FA / OTP verification pin! URL: {page.url}",
                title="LinkedIn Auth Action Required",
                priority="urgent",
                tags=["warning", "key"]
            )
            print("⚠️ [Action Required] LinkedIn OTP/Challenge detected! Sent alert via ntfy.sh")
            # Wait up to 120s for manual OTP entry if running with headful or interactive
            return False

        if self.is_session_valid(page):
            self.save_cookies(context)
            return True

        return False
