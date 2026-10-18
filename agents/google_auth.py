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
        Returns True if authenticated, False if redirected to accounts.google.com or Sign-in button is present.
        """
        try:
            print("[Google Auth] Verifying session validity on careers.google.com...")
            page.goto("https://www.google.com/about/careers/applications/", wait_until="domcontentloaded", timeout=30000)
            time.sleep(3.0)

            curr_url = page.url.lower()
            if "accounts.google.com" in curr_url:
                print(f"[Google Auth] Redirected to login wall ({curr_url[:60]}...). Session is NOT active.")
                return False

            # If Sign in button is still present, session is not logged in
            signin_count = page.locator("a:has-text('Sign in'), button:has-text('Sign in')").count()
            if signin_count > 0:
                print("[Google Auth] 'Sign in' button detected. User is NOT logged in.")
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
            print(f"[Google Auth] Successfully exported cookies to {self.cookies_file}")
        except Exception as e:
            print(f"[Google Auth Warning] Could not export session state: {e}")

    def interactive_login(self):
        """
        Launches a visible Chromium/Edge window with persistent user data directory.
        Allows the user to log in manually, complete 2FA/Google prompt, and persist the session.
        Waits for user to press ENTER before closing.
        """
        print("=" * 65)
        print("🔐 GOOGLE CAREERS INTERACTIVE LOGIN (ONE-TIME SETUP)")
        print("=" * 65)
        print("1. Jendela browser akan terbuka secara otomatis.")
        print("2. Silakan login dengan akun Google Anda dan selesaikan 2FA/OTP.")
        print("3. Setelah berhasil masuk ke dashboard Google Careers:")
        print("   Kembali ke terminal ini dan tekan tombol [ENTER].")
        print("=" * 65)

        with sync_playwright() as p:
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--start-maximized"
            ]

            # Try msedge first to bypass Google automation flags on Windows
            channel = None
            try:
                b = p.chromium.launch(channel="msedge", headless=True)
                b.close()
                channel = "msedge"
            except Exception:
                pass

            launch_kwargs = {
                "user_data_dir": str(self.profile_dir),
                "headless": False,
                "args": launch_args,
                "ignore_default_args": ["--enable-automation"],
                "no_viewport": True,
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 Edg/128.0.0.0"
            }
            if channel:
                launch_kwargs["channel"] = channel

            context = p.chromium.launch_persistent_context(**launch_kwargs)
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://www.google.com/about/careers/applications/", wait_until="domcontentloaded")
            time.sleep(2)

            # Auto click 'Sign in' button if visible so user directly gets the login box
            try:
                signin_btn = page.locator("a:has-text('Sign in'), button:has-text('Sign in')").first
                if signin_btn.count() > 0 and signin_btn.is_visible():
                    signin_btn.click()
            except Exception:
                pass

            print("\n⏳ Browser terbuka. Silakan lakukan proses login di jendela browser.")
            try:
                input("\n⌨️  Tekan [ENTER] di sini setelah Anda SELESAI login di browser...")
            except (KeyboardInterrupt, EOFError):
                print("\n[Google Auth] Proses dibatalkan oleh pengguna.")

            time.sleep(1)
            # Verify session and export
            is_valid = self.is_session_active(page)
            self.export_session_state(context)

            if is_valid:
                print("\n🎉 [SUCCESS] Sesi Google Careers aktif dan berhasil disimpan!")
                print("💡 Agen sekarang siap menjalankan aplikasi Google Careers secara otomatis.")
            else:
                print("\n⚠️ [CATATAN] Sesi belum terdeteksi aktif di dashboard, namun state browser telah disimpan.")
                print("   Jika Anda belum selesai login, silakan jalankan script ini lagi kapan saja.")

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
