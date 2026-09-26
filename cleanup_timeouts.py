#!/usr/bin/env python3
"""
Cleanup Script for Timed-Out Candidates
Extracts candidate IDs that suffered SerpentAPI read timeouts and re-runs
social discovery with the updated search engine (35s timeout + 3x auto-retry).
"""

import os
import re
import sys
import argparse
from db import get_db_connection
from run_pipeline import run_pipeline

LOG_DEFAULT = "/Users/arf/.gemini/antigravity-ide/brain/eeccf8e6-1b87-4006-837c-696fd7dee865/.system_generated/tasks/task-1825.log"
CSV_DEFAULT = "/Users/arf/Downloads/PEP data _ South Africa _ Tables _ 2026 _ Local Gorvenment Election Candidates - persons.csv"


def get_timed_out_candidate_ids(log_path: str = LOG_DEFAULT) -> list:
    if not os.path.exists(log_path):
        print(f"Log file not found: {log_path}")
        return []

    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    blocks = re.split(r'\[\d+/3000\] Candidate: ', text)
    timed_out_ids = []
    seen = set()

    for block in blocks[1:]:
        if "The read operation timed out" in block or "Request Error:" in block:
            first_line = block.split('\n')[0]
            m = re.search(r'\((pers_\d+)\)', first_line)
            if m:
                pid = m.group(1)
                if pid not in seen:
                    seen.add(pid)
                    timed_out_ids.append(pid)

    return timed_out_ids


def filter_already_completed(candidate_ids: list) -> list:
    """Filter out any candidates that already have accounts in the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    placeholders = ",".join(["?"] * len(candidate_ids))
    cursor.execute(f"SELECT DISTINCT person_id FROM social_accounts WHERE person_id IN ({placeholders})", candidate_ids)
    existing = {row[0] for row in cursor.fetchall()}
    conn.close()

    pending = [cid for cid in candidate_ids if cid not in existing]
    print(f"Total timed-out candidates: {len(candidate_ids)}")
    print(f"Already have accounts in DB: {len(candidate_ids) - len(pending)}")
    print(f"Remaining to clean up: {len(pending)}")
    return pending


def main():
    parser = argparse.ArgumentParser(description="Clean up and re-run candidates that timed out on SerpentAPI")
    parser.add_argument("--log", type=str, default=LOG_DEFAULT, help="Path to pipeline task log")
    parser.add_argument("--csv", type=str, default=CSV_DEFAULT, help="Path to candidates CSV")
    parser.add_argument("--provider", type=str, default="serpent", help="Search provider")
    parser.add_argument("--engines", type=str, default="google", help="Engines to query")
    parser.add_argument("--limit", type=int, default=None, help="Optional limit on candidates to re-run")
    parser.add_argument("--dry-run", action="store_true", help="Print target IDs without running")

    args = parser.parse_args()

    candidate_ids = get_timed_out_candidate_ids(args.log)
    if not candidate_ids:
        print("No timed-out candidates found in log.")
        return

    to_process = filter_already_completed(candidate_ids)
    if args.limit:
        to_process = to_process[:args.limit]

    if args.dry_run:
        print(f"Dry run: Would process {len(to_process)} candidate IDs:")
        print(",".join(to_process[:20]) + ("..." if len(to_process) > 20 else ""))
        return

    if not to_process:
        print("All timed-out candidates already have accounts in DB! Nothing to clean up.")
        return

    print(f"\n🚀 Launching cleanup pass for {len(to_process)} candidates using updated search engine...")
    run_pipeline(
        csv_file_path=args.csv,
        output_json_path="popolo_sa_candidates.json",
        limit_records=len(to_process),
        target_ids=to_process,
        provider=args.provider,
        engines=args.engines,
        max_quota=9000
    )


if __name__ == "__main__":
    main()
