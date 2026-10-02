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

            # Locate Easy Apply button
            apply_btn = page.locator(".jobs-apply-button, button.jobs-apply-button--top-card")
            if apply_btn.count() == 0:
                return {"status": "FAILED", "notes": "Easy Apply button not found or already applied"}

            apply_btn.first.click()
            human_jitter(2, 3)

            # Check if modal opens
            modal = page.locator(".jobs-easy-apply-modal, [data-test-modal-id='easy-apply-modal']")
            if modal.count() == 0:
                return {"status": "FAILED", "notes": "Modal did not open"}

            # Iterate through multi-step form (maximum 8 steps)
            for step in range(8):
                human_jitter(1.5, 3)

                # 1. Check for Resume upload input
                file_input = page.locator("input[type='file']")
                if file_input.count() > 0 and Path(pdf_path).exists():
                    file_input.first.set_input_files(pdf_path)
                    print(f"[EasyApply] Uploaded tailored resume: {pdf_path}")
                    human_jitter(2, 3)

                # 2. Check for cover letter / message to hiring manager textarea
                cover_note_box = page.locator("textarea[name*='cover'], textarea[id*='cover'], textarea[aria-label*='cover'], textarea[name*='message']")
                if cover_note_box.count() > 0 and not cover_note_box.first.input_value():
                    print("[EasyApply] Detected cover letter/message box. Generating human-style note...")
                    note = generate_human_cover_note(role_title, company, jd_text)
                    cover_note_box.first.click()
                    cover_note_box.first.press_sequentially(note, delay=30)
                    human_jitter(2, 3)

                # 3. Check for Submit Application button
                submit_btn = page.locator("button[aria-label='Submit application'], button:has-text('Submit application')")
                if submit_btn.count() > 0:
                    submit_btn.first.click()
                    human_jitter(3, 5)
                    print(f"🎉 [EasyApply] Application submitted successfully for {role_title} at {company}!")
                    return {"status": "APPLIED", "notes": "Application successfully submitted via Easy Apply"}

                # 4. Check for Next button or Review button
                next_btn = page.locator("button[aria-label='Continue to next step'], button:has-text('Next'), button:has-text('Review')")
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
