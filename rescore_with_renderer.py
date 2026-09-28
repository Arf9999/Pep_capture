#!/usr/bin/env python3
"""
Level 2 Evaluation Backfill Script
Safely re-evaluates candidate Facebook and Instagram accounts (0.40 <= confidence < 0.85)
using the user's authenticated Chrome persona with randomized human-like sleeps,
extended coffee breaks, persistent caching, and safety tripwires.
"""

import os
import sys
import json
import sqlite3
import argparse
import time
from typing import Dict, Any

from models import ContactDetail, ConfidenceLevel
from profile_renderer import ChromePersonaRenderer, render_and_upgrade_social_account
from update_google_sheet import update_google_sheet_webhook

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "peps.db")


def rescore_accounts(limit: int = 10, sync: bool = False, min_sleep: float = 7.0, max_sleep: float = 14.0):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Find candidates with Facebook or Instagram accounts between 0.40 and 0.85 confidence
    query = """
        SELECT 
            s.id, s.person_id, s.platform, s.profile_url, s.confidence, s.confidence_level, s.rationale, s.signals,
            p.name, p.party_name, p.district, p.popolo_json
        FROM social_accounts s
        JOIN persons p ON s.person_id = p.id
        WHERE s.platform IN ('facebook', 'instagram')
          AND s.confidence >= 0.40
          AND s.confidence < 0.85
        ORDER BY s.confidence DESC
    """
    if limit > 0:
        query += f" LIMIT {limit}"

    c.execute(query)
    rows = c.fetchall()
    
    total = len(rows)
    print(f"\n==================================================================")
    print(f"  Level 2 Persona Evaluator: {total} candidate accounts queued")
    print(f"  Safety Settings: {min_sleep}s - {max_sleep}s jitter | Coffee break every 6 requests")
    print(f"==================================================================\n")

    if total == 0:
        print("No accounts require Level 2 evaluation.")
        conn.close()
        return

    renderer = ChromePersonaRenderer(
        min_sleep=min_sleep,
        max_sleep=max_sleep,
        break_frequency=6,
        break_duration_min=20.0,
        break_duration_max=35.0
    )

    upgraded_count = 0

    try:
        for idx, row in enumerate(rows, 1):
            if renderer.safety_tripped:
                print("\n🚨 [SAFETY HALT] Stopping backfill due to account safety tripwire.")
                break

            s_id, person_id, platform, profile_url, old_conf, old_conf_level, old_rat, old_sig, p_name, party_name, district, popolo_raw = row
            
            print(f"[{idx}/{total}] {p_name} ({party_name} - {district})")
            print(f"    Target: {platform.upper()} -> {profile_url} (Current: {old_conf:.2f} {old_conf_level})")

            # Parse name into first / last for matching
            name_parts = p_name.strip().split()
            first_name = name_parts[0] if name_parts else ""
            last_name = name_parts[-1] if len(name_parts) > 1 else ""

            pep_info = {
                "first_name": first_name,
                "last_name": last_name,
                "party_name": party_name or "",
                "b ": district or "",
                "district": district or ""
            }

            contact = ContactDetail(
                type=platform,
                value=profile_url,
                confidence=old_conf,
                confidence_level=ConfidenceLevel(old_conf_level),
                rationale=old_rat or "",
                signals=json.loads(old_sig) if old_sig else []
            )

            # Perform Level 2 render with authenticated persona
            upgraded = render_and_upgrade_social_account(contact, pep_info, renderer=renderer)

            if upgraded.confidence != old_conf:
                upgraded_count += 1
                new_signals_json = json.dumps(upgraded.signals)
                
                # Update SQLite database
                c.execute("""
                    UPDATE social_accounts
                    SET confidence = ?, confidence_level = ?, rationale = ?, signals = ?
                    WHERE id = ?
                """, (upgraded.confidence, upgraded.confidence_level.value, upgraded.rationale, new_signals_json, s_id))

                # Update Popolo JSON blob in persons table
                if popolo_raw:
                    try:
                        p_dict = json.loads(popolo_raw)
                        for cd in p_dict.get("contact_details", []):
                            if cd.get("value") == profile_url:
                                cd["confidence"] = upgraded.confidence
                                cd["confidence_level"] = upgraded.confidence_level.value
                                cd["rationale"] = upgraded.rationale
                                cd["signals"] = upgraded.signals
                                break
                        c.execute("UPDATE persons SET popolo_json = ? WHERE id = ?", (json.dumps(p_dict), person_id))
                    except Exception as e:
                        print(f"    Warning updating Popolo JSON: {e}")

                conn.commit()
                print(f"    ✨ Updated database for {person_id}: {old_conf} -> {upgraded.confidence} ({upgraded.confidence_level.value})\n")
            else:
                print(f"    No score change. Kept at {old_conf:.2f}\n")

    finally:
        renderer.close()
        conn.close()

    print(f"\n==================================================================")
    print(f"  Level 2 Evaluation Complete: {upgraded_count} / {total} accounts upgraded")
    print(f"==================================================================\n")

    if sync and upgraded_count > 0:
        print("Synchronizing upgraded accounts to Google Sheet...")
        update_google_sheet_webhook(
            webhook_url="https://script.google.com/macros/s/AKfycbwYfWCWOVrVutXEX87N3GHYX03rM1QBp0beQqMFN3Qjip-fNfeIiaGVagfb5YRaCA7J/exec",
            min_confidence=0.55
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Level 2 Persona Evaluator Backfill")
    parser.add_argument("--limit", type=int, default=5, help="Number of accounts to evaluate (0 for all)")
    parser.add_argument("--sync", action="store_true", help="Sync upgraded results to Google Sheet")
    parser.add_argument("--min-sleep", type=float, default=7.0, help="Minimum sleep between requests (seconds)")
    parser.add_argument("--max-sleep", type=float, default=14.0, help="Maximum sleep between requests (seconds)")
    args = parser.parse_args()

    rescore_accounts(limit=args.limit, sync=args.sync, min_sleep=args.min_sleep, max_sleep=args.max_sleep)
