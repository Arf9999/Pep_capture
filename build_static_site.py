"""
Static Site Builder for GitHub Pages
Exports SQLite database and candidate discovery data into a 100% standalone static website.
Output directory: docs/ (native GitHub Pages folder)
"""

import os
import json
import sqlite3
import shutil
from datetime import datetime, timezone

DOCS_DIR = os.path.join(os.path.dirname(__file__), "docs")
DATA_DIR = os.path.join(DOCS_DIR, "data")
DB_FILE = os.path.join(os.path.dirname(__file__), "peps.db")
POPOLO_FILE = os.path.join(os.path.dirname(__file__), "popolo_sa_candidates.json")


def build_site():
    print(f"Building static website in '{DOCS_DIR}'...")
    os.makedirs(DATA_DIR, exist_ok=True)

    if not os.path.exists(DB_FILE):
        print(f"Error: {DB_FILE} not found!")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # 1. Fetch Overall Stats
    c.execute("SELECT count(*) FROM persons")
    total_persons = c.fetchone()[0]

    c.execute("SELECT count(DISTINCT person_id) FROM social_accounts")
    persons_with_accounts = c.fetchone()[0]

    c.execute("SELECT count(*) FROM social_accounts")
    total_accounts = c.fetchone()[0]

    c.execute("SELECT platform, count(*) FROM social_accounts GROUP BY platform ORDER BY count(*) DESC")
    platform_counts = dict(c.fetchall())

    c.execute("SELECT confidence_level, count(*) FROM social_accounts GROUP BY confidence_level")
    conf_counts = dict(c.fetchall())

    c.execute("SELECT DISTINCT party_name FROM persons WHERE party_name IS NOT NULL AND party_name != '' ORDER BY party_name")
    parties = [r[0] for r in c.fetchall()]

    c.execute("SELECT DISTINCT district FROM persons WHERE district IS NOT NULL AND district != '' ORDER BY district")
    districts = [r[0] for r in c.fetchall()]

    stats_data = {
        "total_persons": total_persons,
        "persons_with_accounts": persons_with_accounts,
        "total_accounts": total_accounts,
        "platforms": platform_counts,
        "confidence_levels": conf_counts,
        "parties": parties,
        "districts": districts,
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    }

    with open(os.path.join(DATA_DIR, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats_data, f, indent=2)

    # 2. Fetch All Candidates with their Social Accounts
    c.execute("""
        SELECT 
            p.id, p.name, p.first_name, p.middle_name, p.last_name, 
            p.party_name, p.district, p.office, p.popolo_json,
            count(s.id) as account_count,
            coalesce(max(s.confidence), 0.0) as max_confidence
        FROM persons p
        LEFT JOIN social_accounts s ON p.id = s.person_id
        GROUP BY p.id
        ORDER BY account_count DESC, p.id ASC
    """)
    candidate_rows = c.fetchall()

    # Fetch all social accounts mapped by person_id
    c.execute("""
        SELECT person_id, platform, profile_url, label, confidence, confidence_level, rationale, signals
        FROM social_accounts
        ORDER BY confidence DESC, platform ASC
    """)
    accounts_by_person = {}
    for acc in c.fetchall():
        pid = acc["person_id"]
        if pid not in accounts_by_person:
            accounts_by_person[pid] = []
        
        sig_raw = acc["signals"]
        try:
            sigs = json.loads(sig_raw) if sig_raw else []
        except:
            sigs = [sig_raw] if sig_raw else []

        accounts_by_person[pid].append({
            "platform": acc["platform"],
            "profile_url": acc["profile_url"],
            "label": acc["label"],
            "confidence": float(acc["confidence"]),
            "confidence_level": acc["confidence_level"],
            "rationale": acc["rationale"] or "",
            "signals": sigs
        })

    candidates_list = []
    for r in candidate_rows:
        pid = r["id"]
        candidates_list.append({
            "id": pid,
            "name": r["name"],
            "first_name": r["first_name"] or "",
            "middle_name": r["middle_name"] or "",
            "last_name": r["last_name"] or "",
            "party_name": r["party_name"] or "",
            "district": r["district"] or "",
            "office": r["office"] or "",
            "account_count": r["account_count"],
            "max_confidence": float(r["max_confidence"]),
            "social_accounts": accounts_by_person.get(pid, []),
            "popolo_json": r["popolo_json"] or "{}"
        })

    with open(os.path.join(DATA_DIR, "candidates.json"), "w", encoding="utf-8") as f:
        json.dump(candidates_list, f)

    conn.close()

    # 3. Copy SQLite database file and Popolo JSON to static folder
    dest_db = os.path.join(DATA_DIR, "peps.db")
    shutil.copy2(DB_FILE, dest_db)
    print(f"Copied SQLite database to {dest_db} ({os.path.getsize(dest_db) / (1024*1024):.2f} MB)")

    if os.path.exists(POPOLO_FILE):
        dest_popolo = os.path.join(DATA_DIR, "popolo_sa_candidates.json")
        shutil.copy2(POPOLO_FILE, dest_popolo)
        print(f"Copied Popolo JSON to {dest_popolo} ({os.path.getsize(dest_popolo) / (1024*1024):.2f} MB)")

    # 4. Generate Standalone docs/index.html & docs/methodology.html
    html_content = generate_static_html()
    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_content)

    methodology_content = generate_methodology_html()
    with open(os.path.join(DOCS_DIR, "methodology.html"), "w", encoding="utf-8") as f:
        f.write(methodology_content)

    # 5. Create .nojekyll for GitHub Pages
    nojekyll_path = os.path.join(DOCS_DIR, ".nojekyll")
    with open(nojekyll_path, "w", encoding="utf-8") as f:
        f.write("")

    print(f"\nStatic site build complete!")
    print(f"Location: {DOCS_DIR}")
    print(f"  - docs/index.html (Single Page App)")
    print(f"  - docs/methodology.html (Methodology & Limitations Explainer)")
    print(f"  - docs/data/peps.db (SQLite Database)")
    print(f"  - docs/data/candidates.json ({len(candidates_list)} candidates, {total_accounts} accounts)")
    print(f"  - docs/data/stats.json")
    print(f"  - docs/data/popolo_sa_candidates.json")
    print(f"  - docs/.nojekyll (ensures GitHub Pages does not ignore underscore files)")


def generate_static_html() -> str:
    static_file = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(static_file):
        with open(static_file, "r", encoding="utf-8") as f:
            return f.read()
    docs_file = os.path.join(DOCS_DIR, "index.html")
    if os.path.exists(docs_file):
        with open(docs_file, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def generate_methodology_html() -> str:
    static_file = os.path.join(os.path.dirname(__file__), "static", "methodology.html")
    if os.path.exists(static_file):
        with open(static_file, "r", encoding="utf-8") as f:
            return f.read()
    methodology_file = os.path.join(DOCS_DIR, "methodology.html")
    if os.path.exists(methodology_file):
        with open(methodology_file, "r", encoding="utf-8") as f:
            return f.read()
    return ""


if __name__ == "__main__":
    build_site()

