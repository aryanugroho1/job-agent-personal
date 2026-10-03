import random
import time
from pathlib import Path
from playwright.sync_api import BrowserContext, Page
from agents.human_writer import generate_human_cover_note
from agents.notifier import send_alert

def human_jitter(min_s: float = 2.0, max_s: float = 5.0):
    time.sleep(random.uniform(min_s, max_s))

class EasyApplyRunner:
    def __init__(self, context: BrowserContext):
        self.context = context

    def apply_linkedin(self, job_url: str, pdf_path: str, role_title: str, company: str, jd_text: str = "") -> dict:
        """
        Executes sequential LinkedIn Easy Apply flow with tailored resume upload and human-like typing.
        """
        page = self.context.new_page()
        try:
            page.goto(job_url, wait_until="domcontentloaded", timeout=40000)
            human_jitter(2, 4)

            # Locate Easy Apply button (English & Japanese)
            apply_btn = page.locator(
                ".jobs-apply-button, button.jobs-apply-button--top-card, "
                "button:has-text('Easy Apply'), button:has-text('簡単応募'), "
                "[data-control-name='jobdetails_topcard_inapply']"
            )
            if apply_btn.count() == 0:
                return {"status": "FAILED", "notes": "Easy Apply button not found or already applied"}

            apply_btn.first.click()
            human_jitter(2, 3)

            # Check if modal opens
            modal = page.locator(".jobs-easy-apply-modal, [data-test-modal-id='easy-apply-modal'], div[role='dialog']")
            if modal.count() == 0:
                return {"status": "FAILED", "notes": "Modal did not open"}

            # Iterate through multi-step form (maximum 8 steps)
            for step in range(8):
                human_jitter(1.5, 3)

                # 1. Check for Resume upload input
                file_input = page.locator("input[type='file']")
                target_pdf = Path(pdf_path)
                if not target_pdf.exists():
                    target_pdf = Path("generated_cvs") / Path(pdf_path).name

                if file_input.count() > 0 and target_pdf.exists():
                    file_input.first.set_input_files(str(target_pdf))
                    print(f"[EasyApply] Uploaded tailored resume: {target_pdf}")
                    human_jitter(2, 3)

                # 2. Check for cover letter / message to hiring manager textarea
                cover_note_box = page.locator(
                    "textarea[name*='cover'], textarea[id*='cover'], textarea[aria-label*='cover'], "
                    "textarea[name*='message'], textarea[aria-label*='メッセージ']"
                )
                if cover_note_box.count() > 0 and not cover_note_box.first.input_value():
                    print("[EasyApply] Detected cover letter/message box. Generating human-style note...")
                    note = generate_human_cover_note(role_title, company, jd_text)
                    cover_note_box.first.click()
                    cover_note_box.first.press_sequentially(note, delay=30)
                    human_jitter(2, 3)

                # 3. Check for Submit Application button (English & Japanese)
                submit_btn = page.locator(
                    "button[aria-label='Submit application'], button:has-text('Submit application'), "
                    "button:has-text('応募を送信'), button:has-text('送信'), button[data-live-test-easy-apply-submit-button]"
                )
                if submit_btn.count() > 0:
                    submit_btn.first.click()
                    human_jitter(3, 5)
                    print(f"🎉 [EasyApply] Application submitted successfully for {role_title} at {company}!")
                    return {"status": "APPLIED", "notes": "Application successfully submitted via Easy Apply"}

                # 4. Check for Next button or Review button (English & Japanese)
                next_btn = page.locator(
                    "button[aria-label='Continue to next step'], button:has-text('Next'), button:has-text('Review'), "
                    "button:has-text('次へ'), button:has-text('確認'), button[data-live-test-easy-apply-next-button]"
                )
                if next_btn.count() > 0:
                    next_btn.first.click()
                else:
                    # Form might require answering unhandled custom questions
                    send_alert(
                        f"Custom questions or review required for {role_title} at {company}. URL: {job_url}",
                        title="Manual Application Required",
                        priority="high"
                    )
                    return {"status": "MANUAL_REVIEW", "notes": "Encountered unhandled custom questions"}

            return {"status": "MANUAL_REVIEW", "notes": "Exceeded maximum form steps without final submit"}

        except Exception as e:
            return {"status": "FAILED", "notes": f"Exception occurred: {str(e)}"}
        finally:
            page.close()

    def apply_indeed(self, job_url: str, pdf_path: str, role_title: str, company: str, jd_text: str = "") -> dict:
        """
        Executes sequential Indeed Easy Apply flow with tailored resume upload and human anti-bot behavior.
        """
        page = self.context.new_page()
        apply_page = page
        try:
            page.goto(job_url, wait_until="domcontentloaded", timeout=45000)
            human_jitter(2, 4)

            # Locate Indeed Apply button (data-testid, id, class, or text)
            apply_btn = page.locator(
                "button[data-testid='indeedApplyButton'], #indeedApplyButton, .ia-IndeedApplyButton, "
                "button:has-text('応募画面へ進む'), button:has-text('カンタン応募'), button:has-text('かんたん応募'), "
                "button:has-text('Apply now'), button:has-text('Easily apply')"
            )
            if apply_btn.count() == 0:
                apply_link = page.locator("a[data-testid='indeedApplyButton'], a.ia-IndeedApplyButton")
                if apply_link.count() > 0:
                    apply_btn = apply_link
                else:
                    return {"status": "FAILED", "notes": "Indeed Apply button not found or already applied"}

            # Click Apply button - check if popup opens or continues on page
            try:
                with page.expect_popup(timeout=6000) as popup_info:
                    apply_btn.first.click()
                apply_page = popup_info.value
                human_jitter(2, 4)
            except Exception:
                apply_page = page
                human_jitter(2, 3)

            # Step-through Indeed Apply Form (up to 8 steps)
            for step in range(8):
                human_jitter(1.5, 3)

                # 1. Check for file upload (Resume / CV)
                file_input = apply_page.locator("input[type='file']")
                if file_input.count() > 0 and Path(pdf_path).exists():
                    file_input.first.set_input_files(pdf_path)
                    print(f"[IndeedApply] Uploaded tailored resume: {pdf_path}")
                    human_jitter(2, 3)

                # 2. Check for cover letter / message box
                msg_box = apply_page.locator(
                    "textarea[name*='cover'], textarea[id*='cover'], textarea[name*='message'], "
                    "textarea[aria-label*='cover'], textarea[aria-label*='メッセージ']"
                )
                if msg_box.count() > 0 and not msg_box.first.input_value():
                    print("[IndeedApply] Generating human-style cover note...")
                    note = generate_human_cover_note(role_title, company, jd_text)
                    msg_box.first.click()
                    msg_box.first.press_sequentially(note, delay=30)
                    human_jitter(2, 3)

                # 3. Check for Submit button
                submit_btn = apply_page.locator(
                    "button[data-testid='submit-button'], button:has-text('応募を送信'), "
                    "button:has-text('Submit your application'), button:has-text('応募する')"
                )
                if submit_btn.count() > 0:
                    submit_btn.first.click()
                    human_jitter(3, 5)
                    print(f"🎉 [IndeedApply] Application submitted successfully for {role_title} at {company}!")
                    return {"status": "APPLIED", "notes": "Application successfully submitted via Indeed Easy Apply"}

                # 4. Check for Next / Continue / Review button
                next_btn = apply_page.locator(
                    "button[data-testid='continue-button'], button:has-text('次へ進む'), "
                    "button:has-text('Continue'), button:has-text('Next'), "
                    "button:has-text('確認画面へ進む'), button:has-text('Review')"
                )
                if next_btn.count() > 0:
                    next_btn.first.click()
                else:
                    # Require custom questions or manual review
                    send_alert(
                        f"Custom screening questions or manual review required on Indeed for {role_title} at {company}. URL: {job_url}",
                        title="Manual Indeed Application Required",
                        priority="high"
                    )
                    return {"status": "MANUAL_REVIEW", "notes": "Encountered unhandled custom screening questions on Indeed"}

            return {"status": "MANUAL_REVIEW", "notes": "Exceeded maximum form steps on Indeed without final submit"}

        except Exception as e:
            return {"status": "FAILED", "notes": f"Indeed application exception: {str(e)}"}
        finally:
            if apply_page != page:
                try:
                    apply_page.close()
                except Exception:
                    pass
            page.close()

