"""
Rescore all PEP Candidates in peps.db
Applies the disciplined scoring model:
- Lower base name weight (0.18 for first+last, 0.30 for 3-name exact)
- Multi-tier granular geography (Town +0.30, Muni +0.20, Province +0.05)
- Negative scoring for missing South Africa (-0.25) & foreign locations (-0.50)
- Political party affiliation (+0.30) & civic/councillor roles (+0.25)
"""

import json
import sqlite3
import os
import re
from typing import Dict, List, Any
from query_builder import generate_consolidated_candidate_queries
from evaluator import evaluate_candidate_snippet
from models import Person, ContactDetail, Link, PopoloCollection, ConfidenceLevel


DB_PATH = "peps.db"
CACHE_PATH = "cache/serper_search_cache.json"


def get_platform_from_url(url: str) -> str:
    url_lower = url.lower()
    for p in ["facebook", "linkedin", "twitter", "instagram", "youtube", "tiktok", "t.me"]:
        if p in url_lower:
            return "telegram" if p == "t.me" else p
    if "x.com" in url_lower:
        return "twitter"
    return "social_web"


def rescore_all():
    if not os.path.exists(DB_PATH):
        print(f"Error: {DB_PATH} not found.")
        return

    cache = {}
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            cache = json.load(f)
        print(f"Loaded {len(cache)} cached search queries.")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM persons ORDER BY id ASC")
    persons = cursor.fetchall()
    total_persons = len(persons)
    print(f"Total candidates in database to re-score: {total_persons}")

    # Track statistics
    total_accounts_after = 0
    confidence_counts = {"PROBABLE": 0, "POTENTIAL": 0, "POSSIBLE": 0, "UNLIKELY": 0}
    candidates_with_accounts = 0

    collection = PopoloCollection()

    for idx, p in enumerate(persons):
        person_id = p["id"]
        row = {
            "id": person_id,
            "full_name": p["name"],
            "first_name": p["first_name"] or "",
            "middle_name": p["middle_name"] or "",
            "last_name": p["last_name"] or "",
            "party_name": p["party_name"] or "",
            "b ": p["district"] or "",
            "office": p["office"] or ""
        }

        parts = [x.strip().lower() for x in re.split(r'[\s,]+', p["name"]) if x.strip()]
        fn = row["first_name"].lower() or (parts[0] if parts else "")
        ln = row["last_name"].lower() or (parts[-1] if len(parts) > 1 else "")

        # 1. Fetch raw search results for this person from cache
        candidate_cache_items = []
        seen_urls = set()

        if fn and ln:
            for q, items in cache.items():
                q_lower = q.lower()
                if fn in q_lower and ln in q_lower:
                    for it in items:
                        u = it.get("link") or it.get("url")
                        if u and u not in seen_urls:
                            seen_urls.add(u)
                            candidate_cache_items.append(it)

        # 2. Evaluate all snippets with new 4-tier disciplined model & deep inspection
        scored_contacts: Dict[str, ContactDetail] = {}
        for it in candidate_cache_items:
            u = it.get("link") or it.get("url")
            plat = get_platform_from_url(u)
            s = {"title": it.get("title", ""), "snippet": it.get("snippet", ""), "url": u}
            contact = evaluate_candidate_snippet(row, plat, s)
            if contact:
                # Deep profile inspection for potential matches
                if contact.confidence >= 0.55:
                    from profile_inspector import inspect_profile_deep
                    contact = inspect_profile_deep(contact, row)

                # Keep highest score for this specific URL
                if u not in scored_contacts or contact.confidence > scored_contacts[u].confidence:
                    scored_contacts[u] = contact

        final_contacts = list(scored_contacts.values())
        final_contacts.sort(key=lambda c: c.confidence, reverse=True)

        if final_contacts:
            candidates_with_accounts += 1

        # 3. Update database records for this person
        cursor.execute("DELETE FROM social_accounts WHERE person_id = ?", (person_id,))
        for c_detail in final_contacts:
            cursor.execute("""
            INSERT INTO social_accounts (person_id, platform, profile_url, label, confidence, confidence_level, rationale, signals)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                person_id,
                c_detail.type,
                c_detail.value,
                c_detail.label,
                c_detail.confidence,
                c_detail.confidence_level.value,
                c_detail.rationale,
                json.dumps(c_detail.signals)
            ))
            total_accounts_after += 1
            confidence_counts[c_detail.confidence_level.value] += 1

        # 4. Update Popolo person record
        links = [Link(url=c.value, note=f"{c.type.capitalize()} profile ({c.confidence_level.value})") for c in final_contacts]
        p_obj = Person(
            id=person_id,
            name=row["full_name"],
            given_name=row["first_name"] or None,
            additional_name=row["middle_name"] or None,
            family_name=row["last_name"] or None,
            party_name=row["party_name"] or None,
            office=row["office"] or None,
            district=row["b "] or None,
            links=links,
            contact_details=final_contacts
        )
        collection.persons.append(p_obj)
        popolo_json_str = p_obj.model_dump_json()

        cursor.execute("UPDATE persons SET popolo_json = ? WHERE id = ?", (popolo_json_str, person_id))

        if (idx + 1) % 200 == 0 or (idx + 1) == total_persons:
            print(f"Processed {idx + 1} / {total_persons} candidates...")

    conn.commit()
    conn.close()

    print("\n" + "="*50)
    print("RE-SCORING COMPLETED!")
    print(f"Total Candidates: {total_persons}")
    print(f"Candidates with Verified Accounts: {candidates_with_accounts} ({candidates_with_accounts/total_persons*100:.1f}%)")
    print(f"Total Accounts Retained: {total_accounts_after}")
    print(f"Confidence Distribution (4 Tiers):")
    print(f"  🟢 PROBABLE  (> 0.70):        {confidence_counts['PROBABLE']}")
    print(f"  🔵 POTENTIAL (0.55 - 0.70):   {confidence_counts['POTENTIAL']}")
    print(f"  🟡 POSSIBLE  (0.40 - 0.54):   {confidence_counts['POSSIBLE']}")
    print(f"  ⚪ UNLIKELY  (< 0.40):        {confidence_counts['UNLIKELY']}")
    print("="*50)


if __name__ == "__main__":
    rescore_all()
