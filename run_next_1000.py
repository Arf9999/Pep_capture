#!/usr/bin/env python3
"""
Runner for the Next 1,000 Candidates (Rows 3,001 to 4,000):
Starts from pers_21589 (Andrew Fraser batch) and runs until completion or rate limit.
Automatically synchronizes any discovered high-confidence profiles to Google Sheets.
"""

import sys
import os
from run_pipeline import run_pipeline
from update_google_sheet import update_google_sheet_webhook, update_csv_file

CSV_FILE = "/Users/arf/Downloads/PEP data _ South Africa _ Tables _ 2026 _ Local Gorvenment Election Candidates - persons.csv"
WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbwYfWCWOVrVutXEX87N3GHYX03rM1QBp0beQqMFN3Qjip-fNfeIiaGVagfb5YRaCA7J/exec"

def main():
    print("=" * 75)
    print("STARTING BATCH: NEXT 1,000 CANDIDATES (pers_21589 -> pers_22588)")
    print("Researcher: Andrew Fraser | Engine: Google (SerpentAPI)")
    print("=" * 75)
    
    try:
        run_pipeline(
            csv_file_path=CSV_FILE,
            output_json_path="popolo_sa_candidates.json",
            limit_records=1000,
            start_id="pers_21589",
            researcher_filter="Andrew Fraser",
            provider="serpent",
            engines="google",
            max_quota=9000
        )
        print("\n🎉 Completed batch of 1,000 candidates!")
    except Exception as e:
        print(f"\n⚠️ Pipeline stopped: {e}")
    finally:
        print("\n" + "=" * 75)
        print("SYNCHRONIZING RESULTS TO GOOGLE SHEET & LOCAL CSV")
        print("=" * 75)
        try:
            update_google_sheet_webhook(webhook_url=WEBHOOK_URL, min_confidence=0.55)
            update_csv_file()
            print("✅ Live Google Sheet & CSV synchronized successfully!")
        except Exception as sync_err:
            print(f"⚠️ Sync error: {sync_err}")

if __name__ == "__main__":
    main()
