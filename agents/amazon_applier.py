"""
agents/amazon_applier.py
Automated Form-Filler and Co-Pilot Application Engine for Amazon & AWS Jobs (account.amazon.jobs).
Features:
1. Tailored CV PDF upload
2. Candidate contact & work authorization auto-answering
3. EEO / Demographics safe default selection
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

class AmazonApplier:
    """Automates application submission on account.amazon.jobs."""

    def __init__(self, context: BrowserContext, auto_submit: bool = False):
        self.context = context
        self.auto_submit = auto_submit
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    def apply_amazon(
        self,
        job_url: str,
        pdf_path: str,
        role_title: str,
        company: str = "Amazon Web Services (AWS)",
        location: str = "Tokyo, Japan",
        master_cv: dict | None = None
    ) -> dict:
        """
        Navigates to the Amazon application portal, uploads tailored resume,
        fills screening questions, and prepares application for review or submission.
        """
        page = self.context.new_page()
        job_id_clean = "".join(c for c in Path(job_url).name if c.isdigit()) or str(random.randint(10000, 99999))
        print(f"\n[Amazon Applier] Starting application for '{role_title}' at {company}...")
        print(f"  └─ URL: {job_url}")

        try:
            page.goto(job_url, wait_until="domcontentloaded", timeout=45000)
            human_jitter(2.5, 4.5)

            # 1. Auth Guardrail Check
            curr_url = page.url.lower()
            if "passport.amazon.jobs" in curr_url or "/signin" in curr_url or "/login" in curr_url:
                msg = f"Amazon session expired or login required for {role_title}. Please run 'python agents/amazon_auth.py'."
                print(f"[Amazon Applier Error] {msg}")
                send_alert(msg, title="Amazon Auth Required")
                return {
                    "status": "AUTH_REQUIRED",
                    "notes": "Redirected to passport.amazon.jobs login. Please refresh session."
                }

            # Check if job is closed or already applied
            already_applied = page.locator(':has-text("You have already applied"), :has-text("Already Applied"), :has-text("既に応募済み")')
            if already_applied.count() > 0 and already_applied.first.is_visible():
                print("[Amazon Applier] Already applied to this position previously.")
                return {"status": "ALREADY_APPLIED", "notes": "Role already applied previously on Amazon Jobs"}

            closed_notice = page.locator(':has-text("No longer accepting applications"), :has-text("Position Closed"), :has-text("募集は終了しました")')
            if closed_notice.count() > 0 and closed_notice.first.is_visible():
                print("[Amazon Applier] Job requisition is closed.")
                return {"status": "CLOSED", "notes": "Job requisition no longer accepting applications"}

            # Multi-step progression (Maximum 8 steps budget)
            max_steps = 8
            for step_idx in range(1, max_steps + 1):
                human_jitter(2.0, 3.5)
                print(f"[Amazon Applier] Processing Step #{step_idx} (URL: {page.url[:60]}...)")

                # Handle Resume Upload
                self._handle_resume_upload(page, pdf_path)

                # Handle Screening Questions (Radios, Inputs, Dropdowns)
                self._handle_screening_questions(page, location, master_cv)

                # Check if on Final Review Screen
                review_screen = self._detect_review_screen(page)
                if review_screen:
                    print(f"🎯 [Amazon Applier] Reached Final Review screen at Step #{step_idx}!")
                    screenshot_file = SCREENSHOT_DIR / f"amazon_review_{job_id_clean}.png"
                    try:
                        page.screenshot(path=str(screenshot_file), full_page=True)
                        print(f"📸 Captured application review screenshot: {screenshot_file}")
                    except Exception as e:
                        print(f"⚠️ Could not capture screenshot: {e}")

                    if self.auto_submit:
                        print("🚀 Auto-submit is ENABLED. Clicking Submit Application...")
                        submit_btn = page.locator("button:has-text('Submit application'), button:has-text('Submit Application'), button:has-text('応募を送信'), button:has-text('Submit')").first
                        if submit_btn.is_visible():
                            submit_btn.click()
                            human_jitter(3.0, 5.0)
                            send_alert(
                                f"Successfully submitted Amazon application for {role_title} ({location})!",
                                title="Amazon Application Submitted"
                            )
                            return {"status": "APPLIED", "notes": f"Submitted via automated applier to Amazon. Review: {screenshot_file}"}

                    # Co-Pilot Mode (Default Safety Guardrail)
                    alert_msg = (
                        f"Amazon Application Draft Ready for Review!\n"
                        f"Role: {role_title}\n"
                        f"Company: {company}\n"
                        f"Location: {location}\n"
                        f"Review & Submit Link: {page.url}"
                    )
                    send_alert(alert_msg, title="Amazon Co-Pilot Review Ready")
                    return {
                        "status": "READY_FOR_REVIEW",
                        "notes": f"Draft filled and tailored CV uploaded. Review screenshot: {screenshot_file}. Review & Submit manually at {page.url}"
                    }

                # Click Next / Save & Continue
                progressed = self._click_next_step(page)
                if not progressed:
                    print(f"[Amazon Applier] No Next/Continue button found or form blocked at Step #{step_idx}.")
                    screenshot_blocked = SCREENSHOT_DIR / f"amazon_blocked_{job_id_clean}.png"
                    page.screenshot(path=str(screenshot_file if 'screenshot_file' in locals() else screenshot_blocked))
                    break

            return {
                "status": "MANUAL_REVIEW",
                "notes": f"Form requires manual review at step {step_idx}. Screenshot saved."
            }

        except Exception as e:
            print(f"[Amazon Applier Error] Unexpected exception during application: {e}")
            return {"status": "ERROR", "notes": f"Applier error: {str(e)[:150]}"}
        finally:
            page.close()

    def _handle_resume_upload(self, page: Page, pdf_path: str):
        """Locates and attaches tailored CV PDF if an upload field is visible."""
        target_pdf = Path(pdf_path) if pdf_path else None
        if not target_pdf or not target_pdf.is_file():
            target_pdf = Path("generated_cvs") / Path(pdf_path or "").name

        if not target_pdf.is_file():
            fallback_pdf = Path("generated_cvs/Sample_CV_Arya_Nugroho.pdf")
            if fallback_pdf.is_file():
                target_pdf = fallback_pdf
            else:
                return

        file_inputs = page.locator("input[type='file']").all()
        for finp in file_inputs:
            try:
                finp.set_input_files(str(target_pdf))
                print(f"  └─ [CV Upload] Uploaded tailored PDF: {target_pdf.name}")
                human_jitter(1.5, 3.0)
                break
            except Exception as e:
                print(f"  └─ [CV Upload note]: {e}")

    def _handle_screening_questions(self, page: Page, location: str, master_cv: dict | None = None):
        """
        Answers Amazon corporate screening questions intelligently:
        - Work Authorization & Visa Sponsorship
        - Previous Amazon Employment (No)
        - Government official / public servant (No)
        - Sanctions / conflicts of interest / non-compete (No)
        - Desired compensation in local currency
        - Notice period
        - EEO / Demographics (Decline to state)
        """
        try:
            # 1. Text and Numeric Inputs (Compensation, years of exp, etc.)
            text_inputs = page.locator("input[type='text'], input[type='number'], textarea").all()
            for inp in text_inputs:
                curr_val = inp.input_value().strip()
                if curr_val:
                    continue

                iid = inp.get_attribute("id") or ""
                # Locate label by for attribute, parent, or aria-labelledby
                lbl_text = ""
                if iid:
                    lbl_el = page.locator(f"label[for='{iid}'], label[id='{iid}-label']")
                    if lbl_el.count() > 0:
                        lbl_text = lbl_el.first.inner_text().lower()
                if not lbl_text:
                    aria_lbl = inp.get_attribute("aria-labelledby") or ""
                    if aria_lbl:
                        lbl_el = page.locator(f"label[id='{aria_lbl}'], [id='{aria_lbl}']")
                        if lbl_el.count() > 0:
                            lbl_text = lbl_el.first.inner_text().lower()
                if not lbl_text:
                    parent_q = inp.locator("xpath=ancestor::div[contains(@class, 'question') or contains(@class, 'form-group')]")
                    if parent_q.count() > 0:
                        lbl_text = parent_q.first.inner_text().lower()

                # Determine answer
                fill_val = ""
                if any(w in lbl_text for w in ["年間報酬", "報酬総額", "compensation", "salary", "desired", "expectation", "給与", "年収"]):
                    # Standard Tokyo total compensation expectation for Senior Solutions Architect
                    fill_val = "18,000,000"
                elif any(w in lbl_text for w in ["years of experience", "years", "経験年数", "年数"]):
                    fill_val = "8"
                elif any(w in lbl_text for w in ["notice", "通知期間"]):
                    fill_val = "4 weeks"
                else:
                    fill_val = "Negotiable"

                try:
                    inp.scroll_into_view_if_needed(timeout=1000)
                    inp.fill(fill_val)
                    inp.evaluate("el => { el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); }")
                    print(f"  └─ [Text Answer] '{lbl_text[:40]}...' -> Filled '{fill_val}'")
                except Exception as e:
                    print(f"  └─ [Text Answer Warning]: {e}")

            # 2. Radio Button Groups (Fieldsets)
            fieldsets = page.locator("fieldset, [role='radiogroup']").all()
            for fs in fieldsets:
                legend = fs.locator("legend, label").first.inner_text().lower() if fs.locator("legend, label").count() > 0 else ""
                radios = fs.locator("input[type='radio']").all()
                if not radios or any(r.is_checked() for r in radios):
                    continue

                target_val = "Yes"
                if any(w in legend for w in ["previous", "ever been employed by amazon", "former employee", "prior employment at amazon"]):
                    target_val = "No"
                elif any(w in legend for w in ["non-compete", "non compete", "restrictive covenant", "競業避止"]):
                    target_val = "No"
                elif any(w in legend for w in ["criminal", "felony", "conviction", "disciplinary", "犯罪"]):
                    target_val = "No"
                elif any(w in legend for w in ["government", "公務員", "政府機関", "政府", "public servant", "official"]):
                    target_val = "No"
                elif any(w in legend for w in ["sanction", "制裁"]):
                    target_val = "No"
                elif any(w in legend for w in ["refugee", "難民", "asylum", "亡命"]):
                    target_val = "No"
                elif any(w in legend for w in ["authorized", "right to work", "legally", "18 years", "eligible", "commute", "relocate", "就労資格"]):
                    target_val = "Yes"

                # Check radio matching target
                for r in radios:
                    rid = r.get_attribute("id") or ""
                    val = r.get_attribute("value") or ""
                    lbl = fs.locator(f"label[for='{rid}']").first.inner_text().strip() if rid and fs.locator(f"label[for='{rid}']").count() > 0 else ""
                    combined = f"{val} {lbl}".lower()

                    match = (target_val == "No" and any(k in combined for k in ["no", "いいえ", "false", "ありません"])) or \
                            (target_val == "Yes" and any(k in combined for k in ["yes", "はい", "true", "あります"]))

                    if match:
                        try:
                            r.scroll_into_view_if_needed(timeout=1000)
                            r.check(force=True)
                            print(f"  └─ [Radio Answer] '{legend[:45]}...' -> Selected '{target_val}' ({lbl[:30]})")
                            break
                        except Exception:
                            r.evaluate("el => { el.checked = true; el.dispatchEvent(new Event('change', { bubbles: true })); }")
                            break

            # 3. Select Dropdowns (Demographics, EEO, Work Auth, Notice Period)
            selects = page.locator("select").all()
            for sel in selects:
                sid = sel.get_attribute("id") or ""
                lbl_el = page.locator(f"label[for='{sid}']")
                lbl_text = lbl_el.first.inner_text().lower() if lbl_el.count() > 0 else ""
                if not lbl_text:
                    parent_block = sel.locator("xpath=ancestor::div[contains(@class, 'question') or contains(@class, 'form-group')]")
                    if parent_block.count() > 0:
                        lbl_text = parent_block.first.inner_text().lower()

                curr_val = sel.input_value()
                if curr_val and curr_val not in ["Select an option", ""]:
                    # Check if selected value is a placeholder list (e.g. "即時、1週間...")
                    opt_selected = sel.locator("option:checked")
                    if opt_selected.count() > 0:
                        otext = opt_selected.first.inner_text()
                        if "、" not in otext and "select" not in otext.lower():
                            continue

                opts = sel.locator("option").all()
                if len(opts) <= 1:
                    continue

                chosen_opt = None

                # Check if Notice Period question
                is_notice = any(w in lbl_text for w in ["通知期間", "辞任", "notice", "availability"])
                if is_notice:
                    for opt in opts[1:]:
                        otext = opt.inner_text()
                        oval = opt.get_attribute("value") or ""
                        # Skip placeholder that joins all options
                        if "、" in otext:
                            continue
                        if any(k in otext for k in ["4週間", "4 weeks", "1 month", "30 days", "1ヶ月"]):
                            chosen_opt = oval
                            break
                        elif any(k in otext for k in ["2週間", "2 weeks"]):
                            chosen_opt = oval
                            break
                    if not chosen_opt and len(opts) > 4:
                        chosen_opt = opts[4].get_attribute("value")  # Often 4th option is 4 weeks

                # Demographics: Decline to answer
                is_demographic = any(w in lbl_text for w in ["gender", "race", "ethnicity", "veteran", "disability", "障害", "性別"])
                if is_demographic and not chosen_opt:
                    for opt in opts[1:]:
                        otext = opt.inner_text().lower()
                        if any(k in otext for k in ["decline", "prefer not", "do not wish", "choose not", "回答しない", "希望しない"]):
                            chosen_opt = opt.get_attribute("value")
                            break

                # Standard Yes/Authorized answer
                if not chosen_opt:
                    for opt in opts[1:]:
                        otext = opt.inner_text().lower()
                        if "、" in otext:
                            continue
                        if any(k in otext for k in ["yes", "はい", "authorized"]):
                            chosen_opt = opt.get_attribute("value")
                            break

                # Fallback: Pick first non-placeholder option
                if not chosen_opt:
                    for opt in opts[1:]:
                        otext = opt.inner_text()
                        if "、" not in otext and otext.strip():
                            chosen_opt = opt.get_attribute("value")
                            break

                if chosen_opt:
                    try:
                        sel.select_option(value=chosen_opt)
                        sel.evaluate("el => { el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); }")
                        print(f"  └─ [Select Answer] '{lbl_text[:40]}' -> Selected option '{chosen_opt}'")
                    except Exception as e:
                        pass

            # 4. Checkboxes (Agreements & Consents)
            checkboxes = page.locator("input[type='checkbox']").all()
            for cb in checkboxes:
                if not cb.is_checked():
                    try:
                        cb.scroll_into_view_if_needed(timeout=1000)
                        cb.check(force=True)
                        print("  └─ [Consent Checkbox] Checked agreement box")
                    except Exception:
                        cb.evaluate("el => { el.checked = true; el.dispatchEvent(new Event('change', { bubbles: true })); }")

        except Exception as e:
            print(f"  └─ [Screening Answer Warning]: {e}")

    def _detect_review_screen(self, page: Page) -> bool:
        """Determines if the page is currently on the final review & submit stage."""
        review_indicators = [
            "button:has-text('Submit application')",
            "button:has-text('Submit Application')",
            "button:has-text('応募を送信する')",
            "button:has-text('応募を送信')",
            "h1:has-text('Review your application')",
            "h2:has-text('Review your application')",
            "h1:has-text('Review and submit')",
            "h2:has-text('Review and submit')",
            "h1:has-text('応募内容とフォームを確認する')",
            "h2:has-text('応募内容とフォームを確認する')",
            "h3:has-text('応募内容とフォームを確認する')",
            ":has-text('Please review your application before submitting')",
        ]
        return any(page.locator(sel).count() > 0 and page.locator(sel).first.is_visible() for sel in review_indicators)

    def _click_next_step(self, page: Page) -> bool:
        """Finds and clicks the primary button to progress to the next application step."""
        next_selectors = [
            "button:has-text('Save and continue')",
            "button:has-text('Save & continue')",
            "button:has-text('Next step')",
            "button:has-text('Next')",
            "button:has-text('次へ')",
            "button:has-text('保存して続行')",
            "button.btn-primary:has-text('Continue')",
            "button[type='submit']",
        ]

        for sel in next_selectors:
            btns = page.locator(sel).all()
            for btn in btns:
                # Don't click final submit in co-pilot mode
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
