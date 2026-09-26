#!/usr/bin/env python3
"""
Full Recovery Runner:
1. Re-processes the 130 candidates that suffered timeouts during the first 1,056 rows.
2. Continues the remaining 1,944 candidates from pers_19645 to complete the 3,000 batch.
All calls use the updated search engine with 35s read timeout and 3x auto-retry.
"""

import sys
import os
from cleanup_timeouts import get_timed_out_candidate_ids, filter_already_completed
from run_pipeline import run_pipeline

CSV_FILE = "/Users/arf/Downloads/PEP data _ South Africa _ Tables _ 2026 _ Local Gorvenment Election Candidates - persons.csv"

def main():
    print("=" * 70)
    print("PHASE 1: CLEANUP OF TIMED-OUT CANDIDATES (130 targets)")
    print("=" * 70)
    
    timed_out_ids = get_timed_out_candidate_ids()
    to_process = filter_already_completed(timed_out_ids)
    
    if to_process:
        print(f"\nProcessing {len(to_process)} previously skipped candidates...")
        run_pipeline(
            csv_file_path=CSV_FILE,
            output_json_path="popolo_sa_candidates.json",
            limit_records=len(to_process),
            target_ids=to_process,
            provider="serpent",
            engines="google",
            max_quota=9000
        )
        print("\n✅ Phase 1 complete! All previously skipped candidates processed.")
    else:
        print("No candidates pending cleanup.")

    print("\n" + "=" * 70)
    print("PHASE 2: RESUMING PIPELINE FROM CANDIDATE 1056 (pers_19645) TO 3000")
    print("=" * 70)
    
    run_pipeline(
        csv_file_path=CSV_FILE,
        output_json_path="popolo_sa_candidates.json",
        limit_records=1944,
        start_id="pers_19645",
        researcher_filter="Andrew Fraser",
        provider="serpent",
        engines="google",
        max_quota=9000
    )
    print("\n🎉 Full 3,000 candidate batch complete!")

if __name__ == "__main__":
    main()
