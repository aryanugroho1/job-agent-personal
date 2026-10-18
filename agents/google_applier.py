"""
agents/google_applier.py
Automated Form-Filler and Co-Pilot Application Engine for Google Careers (careers.google.com).
Features:
1. Tailored CV PDF upload
2. Work authorization & legal questionnaire handling
3. Voluntary demographic / EEO safe default selection
4. Co-Pilot Review Mode: Saves screenshot, alerts user via ntfy.sh, and halts before final submit
   (Optionally supports --auto-submit if explicitly permitted)
"""
import os
import random
import time
from pathlib import Path
from playwright.sync_api import BrowserContext, Page, Locator
from agents.notifier import send_alert

SCREENSHOT_DIR = Path("generated_cvs")

def human_jitter(min_s: float = 2.0, max_s: float = 4.5):
    """Introduces human-like variable delays between form actions."""
    time.sleep(random.uniform(min_s, max_s))

class GoogleApplier:
    """Automates application submission on Google Careers."""

    def __init__(self, context: BrowserContext, auto_submit: bool = False):
        self.context = context
        self.auto_submit = auto_submit
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    def apply_google(
        self,
        job_url: str,
        pdf_path: str,
        role_title: str,
        company: str = "Google Cloud",
        location: str = "Tokyo, Japan",
        master_cv: dict | None = None
    ) -> dict:
        """
        Navigates to the Google job listing, clicks Apply, attaches tailored resume,
        fills screening questions, and prepares application for review or submission.
        """
        page = self.context.new_page()
        job_id_clean = "".join(c for c in Path(job_url.split("?")[0]).name if c.isdigit()) or str(random.randint(10000, 99999))
        print(f"\n[Google Applier] Starting application for '{role_title}' at {company}...")
        print(f"  └─ URL: {job_url}")

        try:
            page.goto(job_url, wait_until="domcontentloaded", timeout=45000)
            human_jitter(2.5, 4.0)

            # Dismiss cookie banner if present
            agree_btn = page.locator("button:has-text('Agree'), button:has-text('No thanks')").first
            if agree_btn.is_visible():
                agree_btn.click()
                time.sleep(1)

            # 1. Locate and click Apply button on Google Job page
            apply_btn = page.locator(
                "div.VfPpkd-LgbsSe:has-text('Apply'), "
                "button:has-text('Apply'), "
                "a:has-text('Apply')"
            ).first

            if not apply_btn.is_visible():
                print("[Google Applier] Apply button not found or role expired.")
                return {"status": "CLOSED", "notes": "Apply button not visible on Google listing"}

            apply_btn.click()
            human_jitter(3.0, 4.5)

            # 2. Auth Guardrail Check
            curr_url = page.url.lower()
            if "accounts.google.com/signin" in curr_url or "/v2/identifier" in curr_url:
                msg = f"Google session expired or login required for {role_title}. Please run 'python agents/google_auth.py'."
                print(f"[Google Applier Error] {msg}")
                send_alert(msg, title="Google Auth Required")
                return {
                    "status": "AUTH_REQUIRED",
                    "notes": "Redirected to Google sign-in. Run 'python agents/google_auth.py'."
                }

            # Check if role is already applied
            already_applied = page.locator(':has-text("Already applied"), :has-text("Application submitted"), :has-text("Submitted on")')
            if already_applied.count() > 0 and already_applied.first.is_visible():
                print("[Google Applier] Role already applied previously.")
                return {"status": "ALREADY_APPLIED", "notes": "Role already applied previously on Google Careers"}

            # Multi-step application wizard (Budget: up to 8 steps)
            max_steps = 8
            for step_idx in range(1, max_steps + 1):
                human_jitter(2.0, 3.5)
                print(f"[Google Applier] Processing Step #{step_idx} (URL: {page.url[:65]}...)")

                # Handle Resume Upload
                self._handle_resume_upload(page, pdf_path)

                # Handle Questionnaires (Work Auth, Education, Consents)
                self._handle_questions(page, location)

                # Check if on Review / Submit Screen
                if self._detect_review_screen(page):
                    print(f"🎯 [Google Applier] Reached Final Review screen at Step #{step_idx}!")
                    screenshot_file = SCREENSHOT_DIR / f"google_review_{job_id_clean}.png"
                    try:
                        page.screenshot(path=str(screenshot_file), full_page=True)
                        print(f"📸 Captured Google review screenshot: {screenshot_file}")
                    except Exception as e:
                        print(f"⚠️ Could not capture screenshot: {e}")

                    if self.auto_submit:
                        print("🚀 Auto-submit is ENABLED. Submitting application...")
                        submit_btn = page.locator("button:has-text('Submit'), div.VfPpkd-LgbsSe:has-text('Submit')").first
                        if submit_btn.is_visible():
                            submit_btn.click()
                            human_jitter(3.0, 5.0)
                            send_alert(
                                f"Successfully submitted Google application for {role_title} ({location})!",
                                title="Google Application Submitted"
                            )
                            return {"status": "APPLIED", "notes": f"Submitted automatically to Google. Review: {screenshot_file}"}

                    # Co-Pilot Mode (Default Safety Guardrail)
                    alert_msg = (
                        f"Google Application Draft Ready for Review!\n"
                        f"Role: {role_title}\n"
                        f"Company: {company}\n"
                        f"Location: {location}\n"
                        f"Review & Submit Link: {page.url}"
                    )
                    send_alert(alert_msg, title="Google Co-Pilot Review Ready")
                    return {
                        "status": "READY_FOR_REVIEW",
                        "notes": f"Draft filled and tailored CV uploaded. Review screenshot: {screenshot_file}. Review & Submit manually at {page.url}"
                    }

                # Click Next / Continue
                progressed = self._click_next_step(page)
                if not progressed:
                    print(f"[Google Applier] No Next/Continue button found or form blocked at Step #{step_idx}.")
                    screenshot_blocked = SCREENSHOT_DIR / f"google_blocked_{job_id_clean}.png"
                    page.screenshot(path=str(screenshot_blocked))
                    break

            return {
                "status": "MANUAL_REVIEW",
                "notes": f"Application requires manual review at step {step_idx}. Screenshot saved."
            }

        except Exception as e:
            print(f"[Google Applier Error] Unexpected exception during application: {e}")
            return {"status": "ERROR", "notes": f"Applier error: {str(e)[:150]}"}
        finally:
            page.close()

    def _handle_resume_upload(self, page: Page, pdf_path: str):
        """Attaches tailored PDF resume to Google file upload input."""
        target_pdf = Path(pdf_path)
        if not target_pdf.exists():
            target_pdf = Path("generated_cvs") / Path(pdf_path).name

        if not target_pdf.exists():
            return

        file_inputs = page.locator("input[type='file']").all()
        for finp in file_inputs:
            try:
                finp.set_input_files(str(target_pdf))
                print(f"  └─ [CV Upload] Uploaded tailored PDF to Google: {target_pdf.name}")
                human_jitter(2.0, 3.5)
                break
            except Exception as e:
                print(f"  └─ [CV Upload note]: {e}")

    def _handle_questions(self, page: Page, location: str):
        """
        Handles Google screening and compliance questions:
        - Work authorization & visa sponsorship
        - Non-compete and prior employment
        - Voluntary EEO / Demographics
        """
        try:
            # 1. Radio Button Groups (Fieldsets & role='radiogroup')
            fieldsets = page.locator("fieldset, [role='radiogroup']").all()
            for fs in fieldsets:
                legend = fs.locator("legend, label").first.inner_text().lower() if fs.locator("legend, label").count() > 0 else ""
                radios = fs.locator("input[type='radio'], [role='radio']").all()
                if not radios or any(r.is_checked() for r in radios if hasattr(r, 'is_checked')):
                    continue

                target_val = "Yes"
                if any(w in legend for w in ["non-compete", "restrictive", "conflict", "conviction"]):
                    target_val = "No"
                elif any(w in legend for w in ["authorized", "right to work", "legally", "18 years", "eligible", "relocate"]):
                    target_val = "Yes"

                for r in radios:
                    rid = r.get_attribute("id") or ""
                    val = r.get_attribute("value") or ""
                    lbl = fs.locator(f"label[for='{rid}']").first.inner_text().strip() if rid and fs.locator(f"label[for='{rid}']").count() > 0 else ""
                    combined = f"{val} {lbl}".lower()

                    match = (target_val == "No" and any(k in combined for k in ["no", "いいえ", "false"])) or \
                            (target_val == "Yes" and any(k in combined for k in ["yes", "はい", "true"]))

                    if match:
                        try:
                            r.scroll_into_view_if_needed(timeout=1000)
                            r.click(force=True)
                            print(f"  └─ [Google Radio] '{legend[:45]}...' -> Selected '{target_val}'")
                            break
                        except Exception:
                            r.evaluate("el => el.click()")
                            break

            # 2. Select Dropdowns (EEO, Demographics, Education)
            selects = page.locator("select, [role='combobox']").all()
            for sel in selects:
                tag = sel.evaluate("e => e.tagName")
                if tag == "SELECT":
                    sid = sel.get_attribute("id") or ""
                    lbl_el = page.locator(f"label[for='{sid}']")
                    lbl_text = lbl_el.first.inner_text().lower() if lbl_el.count() > 0 else ""

                    curr_val = sel.input_value()
                    if curr_val and curr_val != "Select an option" and curr_val != "":
                        continue

                    opts = sel.locator("option").all()
                    if len(opts) <= 1:
                        continue

                    # Demographics: Safely decline to answer
                    is_demographic = any(w in lbl_text for w in ["gender", "race", "ethnicity", "veteran", "disability", "障害", "性別"])
                    chosen_opt = None

                    if is_demographic:
                        for opt in opts[1:]:
                            otext = opt.inner_text().lower()
                            if any(k in otext for k in ["decline", "prefer not", "do not wish", "choose not", "回答しない"]):
                                chosen_opt = opt.get_attribute("value")
                                break

                    if not chosen_opt:
                        for opt in opts[1:]:
                            otext = opt.inner_text().lower()
                            if any(k in otext for k in ["yes", "はい", "authorized", "bachelor"]):
                                chosen_opt = opt.get_attribute("value")
                                break

                    if not chosen_opt and len(opts) > 1:
                        chosen_opt = opts[1].get_attribute("value")

                    if chosen_opt:
                        try:
                            sel.select_option(value=chosen_opt)
                            print(f"  └─ [Google Select] '{lbl_text[:40]}' -> Selected option")
                        except Exception:
                            pass

            # 3. Checkboxes (Agreements & Consents)
            checkboxes = page.locator("input[type='checkbox']").all()
            for cb in checkboxes:
                if not cb.is_checked():
                    try:
                        cb.scroll_into_view_if_needed(timeout=1000)
                        cb.check(force=True)
                        print("  └─ [Google Consent] Checked agreement box")
                    except Exception:
                        cb.evaluate("el => { el.checked = true; el.dispatchEvent(new Event('change', { bubbles: true })); }")

        except Exception as e:
            print(f"  └─ [Question Handler Warning]: {e}")

    def _detect_review_screen(self, page: Page) -> bool:
        """Detects if the page has reached the final Review & Submit step."""
        review_indicators = [
            "h1:has-text('Review your application')",
            "h2:has-text('Review your application')",
            "h3:has-text('Review your application')",
            "h1:has-text('Review and submit')",
            "h2:has-text('Review and submit')",
            ":has-text('Please review your application before submitting')",
            "button:has-text('Submit application')",
            "div.VfPpkd-LgbsSe:has-text('Submit application')",
        ]
        return any(page.locator(sel).count() > 0 and page.locator(sel).first.is_visible() for sel in review_indicators)

    def _click_next_step(self, page: Page) -> bool:
        """Finds and clicks the primary button to progress to the next application step."""
        next_selectors = [
            "button:has-text('Save and continue')",
            "button:has-text('Next')",
            "button:has-text('Continue')",
            "div.VfPpkd-LgbsSe:has-text('Next')",
            "div.VfPpkd-LgbsSe:has-text('Continue')",
            "div.VfPpkd-LgbsSe:has-text('Save and continue')",
            "button[type='submit']",
        ]

        for sel in next_selectors:
            btns = page.locator(sel).all()
            for btn in btns:
                text_lower = btn.inner_text().lower()
                if "submit" in text_lower or "送信" in text_lower:
                    continue

                if btn.is_visible() and btn.is_enabled():
                    try:
                        btn.scroll_into_view_if_needed(timeout=1000)
                        btn.click()
                        human_jitter(2.0, 3.5)
                        return True
                    except Exception:
                        pass
        return False
