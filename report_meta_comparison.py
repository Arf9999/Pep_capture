#!/usr/bin/env python3
"""
Report on Meta (Facebook & Instagram) Detections: Google vs. Bing
Reads cache/meta_detections_comparison.jsonl and correlates with peps.db.
"""

import os
import json
import sqlite3
from typing import Dict, Any, List

COMPARISON_LOG = "cache/meta_detections_comparison.jsonl"
DB_PATH = "peps.db"

def generate_report():
    if not os.path.exists(COMPARISON_LOG):
        print(f"No comparison log found at '{COMPARISON_LOG}'. Run some queries with engines='google,bing' first.")
        return

    entries = []
    with open(COMPARISON_LOG, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass

    total_queries = len(entries)
    if total_queries == 0:
        print("Comparison log is empty.")
        return

    # Aggregate stats
    all_google_meta = set()
    all_bing_meta = set()
    queries_with_google_hits = 0
    queries_with_bing_hits = 0
    queries_with_both = 0
    queries_with_neither = 0

    for e in entries:
        g_urls = set(u.lower().rstrip('/') for u in e.get("google_meta_urls", []))
        b_urls = set(u.lower().rstrip('/') for u in e.get("bing_meta_urls", []))
        all_google_meta.update(g_urls)
        all_bing_meta.update(b_urls)

        has_g = len(g_urls) > 0
        has_b = len(b_urls) > 0

        if has_g and has_b:
            queries_with_both += 1
        elif has_g:
            queries_with_google_hits += 1
        elif has_b:
            queries_with_bing_hits += 1
        else:
            queries_with_neither += 1

    overlap_urls = all_google_meta.intersection(all_bing_meta)
    google_only_urls = all_google_meta - all_bing_meta
    bing_only_urls = all_bing_meta - all_google_meta
    total_unique_meta = all_google_meta.union(all_bing_meta)

    # Check against peps.db for confidence scores
    db_matches = {}
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT profile_url, confidence, confidence_level, person_id, label FROM social_accounts;")
            for r in c.fetchall():
                url_norm = r[0].lower().rstrip('/')
                db_matches[url_norm] = {
                    "confidence": r[1],
                    "level": r[2],
                    "person_id": r[3],
                    "label": r[4]
                }
            conn.close()
        except Exception as e:
            print(f"Warning: Could not read database: {e}")

    # Breakdown by confidence
    def score_set(url_set):
        high = 0
        medium = 0
        low = 0
        not_in_db = 0
        for u in url_set:
            if u in db_matches:
                conf = db_matches[u]["confidence"]
                if conf >= 0.70:
                    high += 1
                elif conf >= 0.55:
                    medium += 1
                else:
                    low += 1
            else:
                not_in_db += 1
        return {"high": high, "medium": medium, "low": low, "not_in_db": not_in_db}

    overlap_scores = score_set(overlap_urls)
    google_only_scores = score_set(google_only_urls)
    bing_only_scores = score_set(bing_only_urls)

    print("=" * 80)
    print("META (FACEBOOK & INSTAGRAM) DETECTION REPORT: GOOGLE vs. BING")
    print("=" * 80)
    print(f"Total Dual-Engine Queries Logged: {total_queries}\n")

    print("1. QUERY-LEVEL METRICS:")
    print(f"  • Queries where BOTH engines found Meta hits:   {queries_with_both:4d} ({queries_with_both/total_queries*100:.1f}%)")
    print(f"  • Queries where ONLY Google found Meta hits:    {queries_with_google_hits:4d} ({queries_with_google_hits/total_queries*100:.1f}%)")
    print(f"  • Queries where ONLY Bing found Meta hits:      {queries_with_bing_hits:4d} ({queries_with_bing_hits/total_queries*100:.1f}%)")
    print(f"  • Queries where NEITHER found Meta hits:        {queries_with_neither:4d} ({queries_with_neither/total_queries*100:.1f}%)\n")

    print("2. DISTINCT META PROFILES DISCOVERED:")
    print(f"  • Total Unique Meta URLs across all engines:    {len(total_unique_meta):4d}")
    print(f"  • Surfaced by Google:                           {len(all_google_meta):4d} ({len(all_google_meta)/max(1, len(total_unique_meta))*100:.1f}%)")
    print(f"  • Surfaced by Bing:                             {len(all_bing_meta):4d} ({len(all_bing_meta)/max(1, len(total_unique_meta))*100:.1f}%)")
    print(f"  • Discovered by BOTH (Overlap):                 {len(overlap_urls):4d} ({len(overlap_urls)/max(1, len(total_unique_meta))*100:.1f}%)")
    print(f"  • Discovered ONLY by Google:                    {len(google_only_urls):4d} ({len(google_only_urls)/max(1, len(total_unique_meta))*100:.1f}%)")
    print(f"  • Discovered ONLY by Bing:                      {len(bing_only_urls):4d} ({len(bing_only_urls)/max(1, len(total_unique_meta))*100:.1f}%)\n")

    print("3. VERIFICATION & QUALITY BREAKDOWN (Corroborated in peps.db):")
    print(f"  [OVERLAP (Both Engines)] Total: {len(overlap_urls)}")
    print(f"    - High/Medium Confidence (>=0.55): {overlap_scores['high'] + overlap_scores['medium']}")
    print(f"    - Low/Unlikely (<0.55):            {overlap_scores['low']}")
    print(f"  [GOOGLE ONLY] Total: {len(google_only_urls)}")
    print(f"    - High/Medium Confidence (>=0.55): {google_only_scores['high'] + google_only_scores['medium']}")
    print(f"    - Low/Unlikely (<0.55):            {google_only_scores['low']}")
    print(f"  [BING ONLY] Total: {len(bing_only_urls)}")
    print(f"    - High/Medium Confidence (>=0.55): {bing_only_scores['high'] + bing_only_scores['medium']}")
    print(f"    - Low/Unlikely (<0.55):            {bing_only_scores['low']}\n")

    if bing_only_urls:
        print("4. SAMPLE PROFILES DISCOVERED UNIQUELY BY BING:")
        for idx, u in enumerate(list(bing_only_urls)[:5]):
            info = db_matches.get(u, {})
            conf_str = f"conf={info.get('confidence', 'N/A')} ({info.get('level', 'unfiltered')})" if info else "evaluated"
            print(f"    {idx+1}. {u} [{conf_str}]")

    print("=" * 80)

if __name__ == "__main__":
    generate_report()
