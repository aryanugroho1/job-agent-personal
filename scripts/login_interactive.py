"""
scripts/login_interactive.py
Interactive Browser Login Helper for Indeed & LinkedIn.
Opens a visible browser window, allowing you to login via Google OAuth, 2FA, or SSO naturally.
Saves session cookies and storage state for automated headless runs.
"""
import sys
import argparse
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

CONFIG_DIR = Path("config")
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

URL_MAP = {
    "indeed": "https://secure.indeed.com/auth",
    "linkedin": "https://www.linkedin.com/login"
}

def main():
    parser = argparse.ArgumentParser(description="Interactive Login & Session Cookie Extractor")
    parser.add_argument("--platform", choices=["indeed", "linkedin"], default="indeed", help="Platform to log in to")
    args = parser.parse_args()

    platform = args.platform
    target_url = URL_MAP[platform]
    cookie_file = CONFIG_DIR / f"{platform}_cookies.json"
    state_file = CONFIG_DIR / f"{platform}_state.json"

    print("=" * 60)
    print(f"🌐 Membuka browser interaktif untuk login {platform.upper()}...")
    print(f"👉 Target URL: {target_url}")
    print("=" * 60)
    print("Instruksi:")
    print("1. Jendela browser akan terbuka secara otomatis.")
    print("2. Silakan klik 'Sign in with Google' atau login seperti biasa.")
    print("3. Setelah berhasil masuk ke dashboard / halaman utama:")
    print("   Kembali ke terminal ini dan tekan tombol [ENTER].\n")

    with sync_playwright() as p:
        # Launch with native Edge or Chromium and disable automation flags to bypass Google security checks
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox"
        ]
        try:
            browser = p.chromium.launch(
                channel="msedge",
                headless=False,
                args=launch_args,
                ignore_default_args=["--enable-automation"]
            )
        except Exception:
            browser = p.chromium.launch(
                headless=False,
                args=launch_args,
                ignore_default_args=["--enable-automation"]
            )

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 Edg/128.0.0.0"
        )
        # Wipe webdriver flag
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        page = context.new_page()
        page.goto(target_url)

        # Wait for user input in terminal
        input("Tekan [ENTER] di sini setelah Anda SELESAI login di browser...")

        # Save cookies & storage state
        import json
        cookies = context.cookies()
        with open(cookie_file, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2)

        context.storage_state(path=str(state_file))
        print(f"\n✅ Berhasil! Sesi {platform.upper()} telah disimpan ke:")
        print(f"   - Cookies: {cookie_file}")
        print(f"   - Storage State: {state_file}")
        print("💡 Agen sekarang dapat berjalan secara headless otomatis menggunakan sesi ini.")

        browser.close()

if __name__ == "__main__":
    main()
