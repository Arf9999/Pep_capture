#!/usr/bin/env python3
"""
CLI Utility: Apply Human Verifications to SQLite Database & Google Sheet
Reads an exported verifications JSON file and updates 'peps.db'.
Optionally synchronizes with Google Sheets.
"""

import os
import sys
import json
import sqlite3
import argparse
from db import update_account_verification, init_database
from update_google_sheet import update_google_sheet_webhook

WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbwYfWCWOVrVutXEX87N3GHYX03rM1QBp0beQqMFN3Qjip-fNfeIiaGVagfb5YRaCA7J/exec"


def apply_verifications_file(file_path: str, sync_sheet: bool = False):
    if not os.path.exists(file_path):
        print(f"Error: File '{file_path}' not found.")
        sys.exit(1)

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        print("Error: JSON file must contain a list of verification items.")
        sys.exit(1)

    init_database()
    applied_verified = 0
    applied_rejected = 0
    applied_unreviewed = 0

    print(f"Loaded {len(data)} verification records from '{file_path}'...")

    for item in data:
        url = item.get("profile_url")
        status = item.get("human_verification") or item.get("status")
        acc_id = item.get("account_id")
        person_id = item.get("person_id")
        notes = item.get("notes") or ""

        if not url or not status:
            continue

        success = update_account_verification(
            account_id=int(acc_id) if acc_id else None,
            person_id=person_id,
            profile_url=url,
            status=status,
            notes=notes
        )

        if success:
            if status == "verified":
                applied_verified += 1
            elif status == "rejected":
                applied_rejected += 1
            else:
                applied_unreviewed += 1

    print(f"\nCompleted verification import:")
    print(f"  ✓ Verified:   {applied_verified}")
    print(f"  ✗ Rejected:   {applied_rejected}")
    print(f"  ⟲ Reset:      {applied_unreviewed}")

    if sync_sheet and (applied_verified > 0 or applied_rejected > 0):
        print("\nSynchronizing updated verifications to Google Sheet...")
        update_google_sheet_webhook(webhook_url=WEBHOOK_URL, min_confidence=0.55)
        print("Done!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply Human Verifications to Database")
    parser.add_argument("file", help="Path to exported verifications JSON file")
    parser.add_argument("--sync", action="store_true", help="Sync results to Google Sheet")
    args = parser.parse_args()

    apply_verifications_file(args.file, sync_sheet=args.sync)
