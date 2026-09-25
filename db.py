"""
Database Management Module for PEP Social Accounts
Uses SQLite with optimized indexes keyed by pers_xxx ID.
"""

import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_FILE = "peps.db"


def get_db_connection(db_path: str = DB_FILE) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_database(db_path: str = DB_FILE):
    """Initializes tables for PEP persons and social account links with foreign keys and indexes."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Persons Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS persons (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        first_name TEXT,
        middle_name TEXT,
        last_name TEXT,
        party_name TEXT,
        office TEXT,
        district TEXT,
        popolo_json TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Social Accounts / Contact Details Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS social_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        person_id TEXT NOT NULL,
        platform TEXT NOT NULL,
        profile_url TEXT NOT NULL,
        label TEXT,
        confidence REAL NOT NULL,
        confidence_level TEXT NOT NULL,
        rationale TEXT,
        signals TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (person_id) REFERENCES persons(id) ON DELETE CASCADE,
        UNIQUE(person_id, platform, profile_url)
    );
    """)

    # Indexes for fast lookup
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_persons_name ON persons(name);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_persons_party ON persons(party_name);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_persons_district ON persons(district);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_social_person_id ON social_accounts(person_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_social_platform ON social_accounts(platform);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_social_confidence ON social_accounts(confidence_level);")

    conn.commit()
    conn.close()


def upsert_person_with_accounts(person_dict: Dict[str, Any], db_path: str = DB_FILE):
    """Inserts or updates a Person record and their evaluated social accounts."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    person_id = person_dict["id"]
    now = datetime.utcnow().isoformat()

    cursor.execute("""
    INSERT INTO persons (id, name, first_name, middle_name, last_name, party_name, office, district, popolo_json, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        name = excluded.name,
        party_name = excluded.party_name,
        office = excluded.office,
        district = excluded.district,
        popolo_json = excluded.popolo_json,
        updated_at = excluded.updated_at;
    """, (
        person_id,
        person_dict.get("name", ""),
        person_dict.get("first_name"),
        person_dict.get("middle_name"),
        person_dict.get("last_name"),
        person_dict.get("party_name"),
        person_dict.get("office"),
        person_dict.get("district"),
        json.dumps(person_dict),
        now
    ))

    # Insert social accounts
    for cd in person_dict.get("contact_details", []):
        signals_str = json.dumps(cd.get("signals", []))
        cursor.execute("""
        INSERT INTO social_accounts (person_id, platform, profile_url, label, confidence, confidence_level, rationale, signals, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(person_id, platform, profile_url) DO UPDATE SET
            label = excluded.label,
            confidence = excluded.confidence,
            confidence_level = excluded.confidence_level,
            rationale = excluded.rationale,
            signals = excluded.signals,
            created_at = excluded.created_at;
        """, (
            person_id,
            cd.get("type", "").lower(),
            cd.get("value", ""),
            cd.get("label"),
            float(cd.get("confidence", 0.0)),
            cd.get("confidence_level", "LOW"),
            cd.get("rationale", ""),
            signals_str,
            now
        ))

    conn.commit()
    conn.close()


def query_person_by_id(person_id: str, db_path: str = DB_FILE) -> Optional[Dict[str, Any]]:
    """Retrieves a person and their social accounts by pers_xxx ID."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM persons WHERE id = ?", (person_id,))
    person_row = cursor.fetchone()
    if not person_row:
        conn.close()
        return None

    person_data = dict(person_row)
    cursor.execute("SELECT * FROM social_accounts WHERE person_id = ? ORDER BY confidence DESC", (person_id,))
    accounts = [dict(r) for r in cursor.fetchall()]
    for a in accounts:
        try:
            a["signals"] = json.loads(a["signals"])
        except Exception:
            a["signals"] = []
    person_data["social_accounts"] = accounts

    conn.close()
    return person_data


def search_peps(
    query_text: str = "",
    platform_filter: str = "",
    confidence_filter: str = "",
    limit: int = 50,
    offset: int = 0,
    db_path: str = DB_FILE
) -> List[Dict[str, Any]]:
    """Searches PEPs by ID, name, party, or district with filters."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    sql = """
    SELECT p.id, p.name, p.party_name, p.district, p.office, 
           COUNT(s.id) as account_count,
           MAX(s.confidence) as max_confidence
    FROM persons p
    LEFT JOIN social_accounts s ON p.id = s.person_id
    WHERE 1=1
    """
    params = []

    if query_text:
        sql += " AND (p.id LIKE ? OR p.name LIKE ? OR p.party_name LIKE ? OR p.district LIKE ?)"
        wildcard = f"%{query_text}%"
        params.extend([wildcard, wildcard, wildcard, wildcard])

    if platform_filter:
        sql += " AND s.platform = ?"
        params.append(platform_filter.lower())

    if confidence_filter:
        sql += " AND s.confidence_level = ?"
        params.append(confidence_filter.upper())

    sql += " GROUP BY p.id ORDER BY p.id ASC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor.execute(sql, params)
    results = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return results


def get_summary_stats(db_path: str = DB_FILE) -> Dict[str, Any]:
    """Retrieves high-level counts and stats for the dashboard."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM persons")
    total_persons = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM social_accounts")
    total_accounts = cursor.fetchone()[0]

    cursor.execute("SELECT platform, COUNT(*) as count FROM social_accounts GROUP BY platform")
    platform_counts = {r["platform"]: r["count"] for r in cursor.fetchall()}

    cursor.execute("SELECT confidence_level, COUNT(*) as count FROM social_accounts GROUP BY confidence_level")
    confidence_counts = {r["confidence_level"]: r["count"] for r in cursor.fetchall()}

    conn.close()
    return {
        "total_persons": total_persons,
        "total_accounts": total_accounts,
        "platforms": platform_counts,
        "confidence_levels": confidence_counts
    }
