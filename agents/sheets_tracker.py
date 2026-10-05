import os
from pathlib import Path
from datetime import datetime, timezone
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

COLUMNS = [
    "timestamp", "platform", "job_id", "company", "role_title", "location",
    "target_timezone", "scheduled_utc", "applicant_count", "match_score",
    "pdf_path", "status", "applied_at", "notes"
]

class SheetsTracker:
    def __init__(self, credentials_path: str | None = None, spreadsheet_id: str | None = None):
        self.creds_path = credentials_path or os.getenv("GOOGLE_SHEETS_CREDENTIALS_FILE", "config/service_account.json")
        self.spreadsheet_id = spreadsheet_id or os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
        self.client = None
        self.sheet = None

    def connect(self):
        if not self.spreadsheet_id:
            print("[SheetsTracker Warning] GOOGLE_SHEETS_SPREADSHEET_ID not set. Running in local dummy mode.")
            return False

        if not Path(self.creds_path).exists():
            print(f"[SheetsTracker Warning] Service account credentials '{self.creds_path}' not found.")
            return False

        try:
            creds = Credentials.from_service_account_file(self.creds_path, scopes=SCOPES)
            self.client = gspread.authorize(creds)
            spreadsheet = self.client.open_by_key(self.spreadsheet_id)
            self.sheet = spreadsheet.sheet1
            
            # Check headers
            existing = self.sheet.row_values(1)
            if not existing:
                self.sheet.append_row(COLUMNS)
            return True
        except Exception as e:
            print(f"[SheetsTracker Error] Google Sheets connection error: {e}")
            return False

    def append_job(self, job_record: dict) -> bool:
        """
        Appends a new job record with its initial status.
        """
        if not self.sheet and not self.connect():
            # Dummy log to stdout if sheets not configured
            print(f"[SheetsTracker Local] Record appended: {job_record.get('job_id')} - {job_record.get('company')} ({job_record.get('status')})")
            return True

        row = [
            job_record.get("timestamp", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")),
            job_record.get("platform", ""),
            job_record.get("job_id", ""),
            job_record.get("company", ""),
            job_record.get("role_title", ""),
            job_record.get("location", ""),
            job_record.get("target_timezone", ""),
            job_record.get("scheduled_utc", ""),
            job_record.get("applicant_count", 0),
            job_record.get("match_score", 0),
            job_record.get("pdf_path", ""),
            job_record.get("status", "QUEUED"),
            job_record.get("applied_at", ""),
            job_record.get("notes", "")
        ]

        try:
            self.sheet.append_row(row)
            return True
        except Exception as e:
            print(f"[SheetsTracker Error] Append failed: {e}")
            return False

    def get_queued_jobs(self) -> list[dict]:
        """
        Retrieves all jobs with status == 'QUEUED'.
        """
        if not self.sheet and not self.connect():
            return []

        try:
            records = self.sheet.get_all_records()
            queued = []
            for idx, r in enumerate(records, start=2): # row index in sheet
                if r.get("status") == "QUEUED":
                    r["_row_number"] = idx
                    queued.append(r)
            return queued
        except Exception as e:
            print(f"[SheetsTracker Error] Failed reading queued jobs: {e}")
            return []

    def get_manual_review_jobs(self) -> list[dict]:
        """
        Retrieves all jobs with status == 'MANUAL_REVIEW'.
        """
        if not self.sheet and not self.connect():
            return []

        try:
            records = self.sheet.get_all_records()
            manual = []
            for idx, r in enumerate(records, start=2):
                if r.get("status") == "MANUAL_REVIEW":
                    r["_row_number"] = idx
                    manual.append(r)
            return manual
        except Exception as e:
            print(f"[SheetsTracker Error] Failed reading manual review jobs: {e}")
            return []

    def get_job_by_row(self, row_number: int) -> dict | None:
        """
        Retrieves a single job record by its row number in the sheet.
        """
        if not self.sheet and not self.connect():
            return None

        try:
            row_vals = self.sheet.row_values(row_number)
            if not row_vals:
                return None
            headers = self.sheet.row_values(1)
            record = dict(zip(headers, row_vals))
            record["_row_number"] = row_number
            return record
        except Exception as e:
            print(f"[SheetsTracker Error] Failed reading row {row_number}: {e}")
            return None

    def update_job_status(self, row_number: int, status: str, notes: str = "", applied_at: str = ""):
        """
        Updates the status, applied_at, and notes columns for a specific row.
        """
        if not self.sheet and not self.connect():
            print(f"[SheetsTracker Local] Row {row_number} status updated to {status}")
            return True

        try:
            # Column 12: status, Column 13: applied_at, Column 14: notes
            self.sheet.update_cell(row_number, 12, status)
            if applied_at:
                self.sheet.update_cell(row_number, 13, applied_at)
            if notes:
                self.sheet.update_cell(row_number, 14, notes)
            return True
        except Exception as e:
            print(f"[SheetsTracker Error] Update cell failed: {e}")
            return False
