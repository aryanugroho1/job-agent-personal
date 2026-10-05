import os
import random
import time
from pathlib import Path
from playwright.sync_api import BrowserContext, Page, Locator
from agents.human_writer import generate_human_cover_note
from agents.notifier import send_alert

def human_jitter(min_s: float = 2.0, max_s: float = 5.0):
    time.sleep(random.uniform(min_s, max_s))

def auto_answer_screening_questions(container: Locator | Page):
    """
    Intelligently auto-answers screening questions:
    - Radio buttons: work authorization (Yes), visa sponsorship (Yes), commute/education (Yes)
    - Numeric & text fields: years of experience (8), salary (Negotiable), notice period (30 days)
    - Checkboxes: consents and agreements (checked)
    - Dropdowns: target positive/fluent/experienced answers
    """
    try:
        # 1. Radio Button Groups (Fieldsets & standalone radios)
        fieldsets = container.locator("fieldset").all()
        for fs in fieldsets:
            legend = fs.locator("legend").first.inner_text().lower() if fs.locator("legend").count() > 0 else ""
            radios = fs.locator("input[type='radio']").all()
            if not radios:
                continue

            if any(r.is_checked() for r in radios):
                continue

            # Determine desired answer based on prompt keywords
            target_val = "Yes"
            if any(w in legend for w in ["criminal", "felony", "conviction", "disciplinary", "offense"]):
                target_val = "No"
            elif any(w in legend for w in ["sponsorship", "require visa", "visa sponsorship", "スポンサーシップ", "ビザ支援", "visum", "sponsorship required"]):
                target_val = "Yes"
            elif any(w in legend for w in ["authorized", "right to work", "legally", "就労", "許可", "relocate", "commute", "background", "clearance", "degree", "education", "bachelor", "master", "hybrid"]):
                target_val = "Yes"

            selected = False
            for r in radios:
                rid = r.get_attribute("id")
                val = r.get_attribute("value") or ""
                aria = r.get_attribute("aria-label") or ""
                lbl = fs.locator(f"label[for='{rid}']").first.inner_text().strip() if rid and fs.locator(f"label[for='{rid}']").count() > 0 else ""
                combined = f"{val} {aria} {lbl}".lower()

                is_match = False
                if target_val == "No":
                    if any(k in combined for k in ["no", "いいえ", "nein"]):
                        is_match = True
                else:
                    if any(k in combined for k in ["yes", "はい", "ja"]):
                        is_match = True

                if is_match:
                    try:
                        r.scroll_into_view_if_needed(timeout=1000)
                        r.check(force=True)
                    except Exception:
                        r.evaluate("el => { el.checked = true; el.dispatchEvent(new Event('change', { bubbles: true })); el.dispatchEvent(new Event('input', { bubbles: true })); }")
                    selected = True
                    print(f"[AutoAnswer] Radio for '{legend[:40]}' -> Selected '{target_val}'")
                    break

            if not selected and radios:
                try:
                    radios[0].scroll_into_view_if_needed(timeout=1000)
                    radios[0].check(force=True)
                except Exception:
                    radios[0].evaluate("el => { el.checked = true; el.dispatchEvent(new Event('change', { bubbles: true })); el.dispatchEvent(new Event('input', { bubbles: true })); }")

        # 2. Text & Numeric Inputs
        text_inputs = container.locator("input[type='text'], input[type='number']").all()
        for inp in text_inputs:
            iid = inp.get_attribute("id") or ""
            val = inp.input_value().strip()
            if val:
                continue

            lbl_el = container.locator(f"label[for='{iid}']")
            lbl_text = lbl_el.first.inner_text().lower() if lbl_el.count() > 0 else ""

            is_numeric = "numeric" in iid.lower() or inp.get_attribute("type") == "number" or any(w in lbl_text for w in ["how many years", "years of work", "years", "年数", "経験年数"])
            if is_numeric:
                fill_val = "8"
            elif any(w in lbl_text for w in ["salary", "compensation", "desired", "expectation", "給与", "年収"]):
                fill_val = "Negotiable"
            elif any(w in lbl_text for w in ["notice", "notice period", "availability"]):
                fill_val = "30 days"
            else:
                fill_val = "8"

            try:
                inp.scroll_into_view_if_needed(timeout=1000)
                inp.fill(fill_val)
            except Exception:
                inp.evaluate(f"el => {{ el.value = '{fill_val}'; el.dispatchEvent(new Event('input', {{ bubbles: true }})); el.dispatchEvent(new Event('change', {{ bubbles: true }})); }}")
            print(f"[AutoAnswer] Filled input '{lbl_text[:40]}' -> '{fill_val}'")

        # 3. Checkboxes (Consents, agreements)
        checkboxes = container.locator("input[type='checkbox']").all()
        for cb in checkboxes:
            if not cb.is_checked():
                try:
                    cb.scroll_into_view_if_needed(timeout=1000)
                    cb.check(force=True)
                except Exception:
                    cb.evaluate("el => { el.checked = true; el.dispatchEvent(new Event('change', { bubbles: true })); }")
                print("[AutoAnswer] Checked agreement/consent checkbox")

        # 4. Dropdowns (<select>)
        selects = container.locator("select").all()
        for sel in selects:
            sid = sel.get_attribute("id") or ""
            lbl_el = container.locator(f"label[for='{sid}']")
            lbl_text = lbl_el.first.inner_text().lower() if lbl_el.count() > 0 else ""

            opts = sel.locator("option").all()
            if len(opts) <= 1:
                continue

            curr_val = sel.input_value()
            if curr_val and curr_val != "Select an option" and curr_val != "":
                continue

            best_opt_val = None
            for opt in opts[1:]:
                otext = opt.inner_text().strip().lower()
                oval = opt.get_attribute("value")
                if any(k in otext for k in ["yes", "はい", "professional", "fluent", "native", "5+", "8+", "10+"]):
                    best_opt_val = oval
                    break
            if not best_opt_val:
                best_opt_val = opts[1].get_attribute("value")

            if best_opt_val:
                try:
                    sel.select_option(value=best_opt_val)
                    print(f"[AutoAnswer] Dropdown for '{lbl_text[:40]}' -> Selected '{best_opt_val}'")
                except Exception as e:
                    print(f"[AutoAnswer] Select option exception: {e}")

    except Exception as e:
        print(f"[AutoAnswer] Question handler warning: {e}")


class EasyApplyRunner:
    def __init__(self, context: BrowserContext):
        self.context = context

    def apply_linkedin(self, job_url: str, pdf_path: str, role_title: str, company: str, jd_text: str = "") -> dict:
        """
        Executes sequential LinkedIn Easy Apply flow with tailored resume upload,
        intelligent screening question answering, and human-like typing.
        """
        page = self.context.new_page()
        try:
            page.goto(job_url, wait_until="domcontentloaded", timeout=40000)
            human_jitter(2, 4)

            # Check if job is expired or closed
            closed_el = page.locator(':has-text("No longer accepting applications"), :has-text("募集は終了しました")')
            if closed_el.count() > 0 and closed_el.first.is_visible():
                return {"status": "CLOSED", "notes": "Job posting is closed or no longer accepting applications"}

            # Locate Easy Apply button (English & Japanese, with text match prioritized)
            apply_btn = page.locator(
                "button:has-text('Easy Apply'), button:has-text('簡単応募'), "
                ".jobs-apply-button, button.jobs-apply-button--top-card, "
                "[data-control-name='jobdetails_topcard_inapply']"
            )
            if apply_btn.count() == 0:
                return {"status": "FAILED", "notes": "Easy Apply button not found or already applied"}

            apply_btn.first.click()
            human_jitter(2, 3)

            # Check if modal opens (LinkedIn uses HTML5 dialog or [role='dialog'])
            modal = page.locator("dialog, [role='dialog'], .jobs-easy-apply-modal, [data-test-modal-id='easy-apply-modal']")
            try:
                modal.first.wait_for(state="visible", timeout=8000)
            except Exception:
                pass

            if modal.count() == 0 or not modal.first.is_visible():
                return {"status": "FAILED", "notes": "Modal did not open"}

            current_dialog = modal.first

            # Iterate through multi-step form (maximum 12 steps budget)
            for step in range(12):
                human_jitter(1.5, 3)

                # 1. Check for required Phone Number input (often empty on step 1)
                phone_inp = current_dialog.locator("input[type='tel']")
                if phone_inp.count() > 0 and not phone_inp.first.input_value():
                    candidate_phone = os.getenv("CANDIDATE_PHONE", "07090934764")
                    print(f"[EasyApply] Auto-filling required phone number: {candidate_phone}")
                    phone_inp.first.fill(candidate_phone)
                    human_jitter(1, 2)

                # 2. Check for Resume upload input
                file_input = current_dialog.locator("input[type='file']")
                target_pdf = Path(pdf_path)
                if not target_pdf.exists():
                    target_pdf = Path("generated_cvs") / Path(pdf_path).name

                if file_input.count() > 0 and target_pdf.exists():
                    try:
                        file_input.first.set_input_files(str(target_pdf))
                        print(f"[EasyApply] Uploaded tailored resume: {target_pdf}")
                        human_jitter(2, 3)
                    except Exception as e:
                        print(f"[EasyApply] Resume upload note: {e}")

                # 3. Auto-answer custom screening questions (radios, selects, inputs, checkboxes)
                auto_answer_screening_questions(current_dialog)
                human_jitter(1, 2)

                # 4. Check for cover letter / message to hiring manager textarea
                cover_note_box = current_dialog.locator(
                    "textarea[name*='cover'], textarea[id*='cover'], textarea[aria-label*='cover'], "
                    "textarea[name*='message'], textarea[aria-label*='メッセージ']"
                )
                if cover_note_box.count() > 0 and not cover_note_box.first.input_value():
                    print("[EasyApply] Detected cover letter/message box. Generating human-style note...")
                    note = generate_human_cover_note(role_title, company, jd_text)
                    cover_note_box.first.click()
                    cover_note_box.first.press_sequentially(note, delay=30)
                    human_jitter(2, 3)

                # 5. Check for Submit Application button (English & Japanese)
                submit_btn = current_dialog.locator(
                    "button[aria-label='Submit application'], button:has-text('Submit application'), "
                    "button:has-text('応募を送信'), button:has-text('送信'), button[data-live-test-easy-apply-submit-button]"
                )
                if submit_btn.count() > 0:
                    submit_btn.first.click()
                    human_jitter(3, 5)
                    print(f"🎉 [EasyApply] Application submitted successfully for {role_title} at {company}!")
                    return {"status": "APPLIED", "notes": "Application successfully submitted via Easy Apply"}

                # 6. Check for Next button or Review button (English & Japanese)
                next_btn = current_dialog.locator(
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

            # Step-through Indeed Apply Form (up to 12 steps)
            for step in range(12):
                human_jitter(1.5, 3)

                # 1. Check for file upload (Resume / CV)
                file_input = apply_page.locator("input[type='file']")
                if file_input.count() > 0 and Path(pdf_path).exists():
                    file_input.first.set_input_files(pdf_path)
                    print(f"[IndeedApply] Uploaded tailored resume: {pdf_path}")
                    human_jitter(2, 3)

                # 2. Auto-answer custom screening questions on Indeed
                auto_answer_screening_questions(apply_page)
                human_jitter(1, 2)

                # 3. Check for cover letter / message box
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

                # 4. Check for Submit button
                submit_btn = apply_page.locator(
                    "button[data-testid='submit-button'], button:has-text('応募を送信'), "
                    "button:has-text('Submit your application'), button:has-text('応募する')"
                )
                if submit_btn.count() > 0:
                    submit_btn.first.click()
                    human_jitter(3, 5)
                    print(f"🎉 [IndeedApply] Application submitted successfully for {role_title} at {company}!")
                    return {"status": "APPLIED", "notes": "Application successfully submitted via Indeed Easy Apply"}

                # 5. Check for Next / Continue / Review button
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
