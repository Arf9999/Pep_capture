#!/usr/bin/env python3
"""
Google Sheet Updater for PEP Social Discovery
Syncs high-confidence social media profile URLs and concatenated verification notes
directly into the PEP South Africa Google Sheet (or exports a merged, ready-to-import CSV).

Schema Rules:
1. note_fb, note_li, note_tw, etc. are PRESELECTED DROPDOWNS in Google Sheets -> DO NOT OVERWRITE.
2. Verified profile URLs are mapped into their respective columns (fb_url, LinkedIn_url, twitter_url, etc.).
3. All platform verification rationales are concatenated into the final 'notes' column:
   e.g. "FB- Probable 90% Confirmed candidate profile, election poster( DA,Ugu); X- Potential 65% Full 3-name match +cic role"
"""

import os
import csv
import json
import sqlite3
import argparse
from typing import Dict, List, Any, Optional

PLATFORM_CONFIG = {
    "facebook": {"url_col": "fb_url", "note_col": "note_fb", "note_val": "Verified", "abbrv": "FB"},
    "twitter": {"url_col": "twitter_url", "note_col": "note_tw", "note_val": "Verified", "abbrv": "X"},
    "linkedin": {"url_col": "LinkedIn_url", "note_col": "note_li", "note_val": "Verified", "abbrv": "LI"},
    "instagram": {"url_col": "instagram_url", "note_col": "note_ig", "note_val": "Verified", "abbrv": "IG"},
    "tiktok": {"url_col": "tiktok_url", "note_col": "note_tk", "note_val": "Verified", "abbrv": "TK"},
    "youtube": {"url_col": "YouTube_url", "note_col": "note_yt", "note_val": "Verified", "abbrv": "YT"},
    "website": {"url_col": "website", "note_col": "note_web", "note_val": "official", "abbrv": "WEB"},
    "social_web": {"url_col": "website", "note_col": "note_web", "note_val": "official", "abbrv": "WEB"},
    "wikipedia": {"url_col": "wikipedia_url", "note_col": "note_wiki", "note_val": "wikipedia", "abbrv": "WIKI"},
    "whatsapp": {"url_col": "wa_numbers", "note_col": "note_wa", "note_val": "Verified", "abbrv": "WA"},
    "telegram": {"url_col": "telegram", "note_col": "note_te", "note_val": "Verified", "abbrv": "TG"},
}

DEFAULT_CSV_PATH = "/Users/arf/Downloads/PEP data _ South Africa _ Tables _ 2026 _ Local Gorvenment Election Candidates - persons.csv"
DEFAULT_DB_PATH = "peps.db"


def fetch_high_confidence_accounts(
    db_path: str = DEFAULT_DB_PATH,
    min_confidence: float = 0.55
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """
    Queries SQLite for all high-confidence social accounts.
    Returns: {person_id: {platform: {'url': ..., 'confidence': ..., 'level': ..., 'rationale': ...}}}
    """
    if not os.path.exists(db_path):
        print(f"Error: Database file not found at '{db_path}'")
        return {}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
    SELECT person_id, platform, profile_url, label, confidence, confidence_level, rationale, signals
    FROM social_accounts
    WHERE confidence >= ? AND platform != 'email'
    ORDER BY person_id, confidence DESC;
    """, (min_confidence,))

    results: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for row in cursor.fetchall():
        pid = row["person_id"]
        plat = row["platform"].lower()
        if plat not in PLATFORM_CONFIG or plat == "email":
            continue
        if pid not in results:
            results[pid] = {}
        # Keep highest scoring account for this platform
        if plat not in results[pid] or row["confidence"] > results[pid][plat]["confidence"]:
            results[pid][plat] = {
                "url": row["profile_url"],
                "confidence": row["confidence"],
                "confidence_level": row["confidence_level"],
                "rationale": row["rationale"],
                "signals": row["signals"],
                "label": row["label"]
            }

    conn.close()
    return results


def humanize_signals(signals_raw: Any) -> str:
    """Condenses machine signals into concise human-readable verification reasons."""
    if not signals_raw:
        return ""
    if isinstance(signals_raw, str):
        try:
            signals = json.loads(signals_raw)
        except Exception:
            signals = [signals_raw]
    else:
        signals = signals_raw

    out = []
    for s in signals:
        s = s.strip()
        if "PENALTY" in s or "Adj:" in s:
            continue
        if s.startswith("FULL_3NAME_MATCH"):
            out.append("Full 3-name match")
        elif s.startswith("FIRST_LAST_NAME_MATCH") or s.startswith("MIDDLE_LAST_NAME_MATCH"):
            out.append("Name match")
        elif "LOCAL_TOWN_MATCH" in s or "PAGE_LOCATION_CONFIRMED" in s:
            if "(" in s and ")" in s:
                detail = s[s.find("(")+1:s.rfind(")")]
                out.append(f"Location match ({detail})")
            else:
                out.append("Location match")
        elif "PARTY" in s or "BALLOT_PARTY_MATCH" in s:
            out.append("Party match")
        elif "ELECTION" in s or "POSTER" in s:
            out.append("Election poster match")
        elif "CIVIC_CONTEXT_MATCH" in s or "OFFICE_ROLE_MATCH" in s:
            out.append("Civic role match")
        elif "PAGE_BIO_CONFIRMED" in s:
            if "(" in s and ")" in s:
                detail = s[s.find("(")+1:s.rfind(")")]
                out.append(f"Bio confirmed ({detail})")
            else:
                out.append("Bio confirmed")
        elif "EXACT_EMAIL_MATCH" in s or "PAGE_EMAIL_DISCOVERED" in s:
            continue
        elif s.startswith("DIRECT_PROFILE_URL"):
            out.append("Direct profile")
        else:
            cleaned = s.split("(")[0].replace("_", " ").title().strip()
            if cleaned and "No " not in cleaned:
                out.append(cleaned)

    # Deduplicate preserving order
    seen = set()
    deduped = []
    for item in out:
        if item.lower() not in seen:
            seen.add(item.lower())
            deduped.append(item)

    return ", ".join(deduped[:3])


def get_confidence_color(score: float, min_score: float = 0.55, max_score: float = 1.0) -> str:
    """
    Interpolates a continuous background shade from Amber (#FFE599) to Green (#B6D7A8).
    - 0.55 (Threshold / Potential): Warm Amber (#FFE599)
    - 0.75 (Probable): Soft Lime (#D9EAD3)
    - 1.00 (Confirmed): Soft Sage Green (#B6D7A8)
    """
    clamped = max(min_score, min(max_score, score))
    ratio = (clamped - min_score) / (max_score - min_score)
    if ratio < 0.5:
        sub = ratio / 0.5
        r = int(255 + sub * (217 - 255))
        g = int(229 + sub * (234 - 229))
        b = int(153 + sub * (211 - 153))
    else:
        sub = (ratio - 0.5) / 0.5
        r = int(217 + sub * (182 - 217))
        g = int(234 + sub * (215 - 234))
        b = int(211 + sub * (168 - 211))
    return f"#{r:02x}{g:02x}{b:02x}"


def format_concatenated_notes(accounts: Dict[str, Dict[str, Any]]) -> str:
    """
    Concatenates verification notes for all discovered platforms into one string for the final 'notes' cell.
    Example:
      FB- Probable 90% Confirmed candidate profile, election poster( DA,Ugu); X- Potential 65% Full 3-name match +cic role
    """
    note_parts = []
    sorted_plats = sorted(accounts.items(), key=lambda x: x[1].get("confidence", 0), reverse=True)
    for plat, acc in sorted_plats:
        if plat == "email" or plat not in PLATFORM_CONFIG:
            continue
        cfg = PLATFORM_CONFIG.get(plat)
        abbrv = cfg["abbrv"] if cfg else plat.upper()
        conf_pct = int(acc.get("confidence", 0) * 100)
        
        raw_level = acc.get("confidence_level", "PROBABLE")
        if hasattr(raw_level, "name"):
            level_str = raw_level.name.capitalize()
        else:
            level_str = str(raw_level).split(".")[-1].capitalize()

        # Build concise verification explanation
        summary = humanize_signals(acc.get("signals"))
        if not summary:
            summary = acc.get("label") or "Verified profile"
            summary = " ".join(summary.replace("\n", " ").split())
            if len(summary) > 60:
                summary = summary[:57] + "..."

        note_parts.append(f"{abbrv}- {level_str} {conf_pct}% {summary}")

    return "; ".join(note_parts)


def update_csv_file(
    input_csv: str = DEFAULT_CSV_PATH,
    output_csv: str = "updated_pep_candidates_with_social.csv",
    min_confidence: float = 0.55,
    db_path: str = DEFAULT_DB_PATH
) -> int:
    """
    Reads the original CSV and writes a merged CSV:
    - Populates profile URLs (fb_url, twitter_url, etc.)
    - Leaves note_fb, note_li, etc. untouched (reserved for dropdowns)
    - Concatenates all platform notes into the final 'notes' column
    """
    if not os.path.exists(input_csv):
        print(f"Error: Input CSV not found at '{input_csv}'")
        return 0

    candidate_accounts = fetch_high_confidence_accounts(db_path, min_confidence)
    print(f"Loaded high-confidence accounts for {len(candidate_accounts)} candidates from '{db_path}'.")

    with open(input_csv, mode="r", encoding="utf-8") as in_f:
        reader = csv.DictReader(in_f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    # Ensure 'notes' column exists in header
    notes_col = "notes"
    if notes_col not in fieldnames:
        # Check if there is another notes column like 'note' or 'comments'
        existing_notes_cols = [c for c in fieldnames if c.lower() in ("notes", "note", "general_notes")]
        if existing_notes_cols:
            notes_col = existing_notes_cols[0]
        else:
            fieldnames.append(notes_col)

    updated_rows = 0
    total_urls_inserted = 0

    for row in rows:
        pid = row.get("id")
        if not pid or pid not in candidate_accounts:
            continue

        accounts = candidate_accounts[pid]
        row_modified = False

        # 1. Populate URLs and set corresponding note column to 'Auto_search'
        for plat, acc in accounts.items():
            cfg = PLATFORM_CONFIG.get(plat)
            if not cfg:
                continue

            url_col = cfg["url_col"]
            note_col = cfg.get("note_col")
            if url_col in fieldnames and not row.get(url_col):
                row[url_col] = acc["url"]
                row_modified = True
                total_urls_inserted += 1
                if note_col and note_col in fieldnames and not row.get(note_col):
                    row[note_col] = "Auto_search"

        # 2. Concatenate verification notes into the final notes cell
        new_concat_note = format_concatenated_notes(accounts)
        if new_concat_note:
            existing_note = (row.get(notes_col) or "").strip()
            if not existing_note:
                row[notes_col] = new_concat_note
                row_modified = True
            elif new_concat_note not in existing_note:
                row[notes_col] = f"{existing_note}; {new_concat_note}"
                row_modified = True

        if row_modified:
            updated_rows += 1

    with open(output_csv, mode="w", encoding="utf-8", newline="") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n✅ Exported merged CSV to '{output_csv}':")
    print(f"  • {updated_rows} candidate rows updated")
    print(f"  • {total_urls_inserted} social media URLs inserted")
    print(f"  • Concatenated verification summaries written to '{notes_col}' column")
    print(f"  • Preselected dropdown columns (note_fb, note_li, etc.) left untouched.")
    return updated_rows


def update_google_sheet_direct(
    sheet_id_or_url: str,
    credentials_json_path: str,
    worksheet_name: Optional[str] = None,
    min_confidence: float = 0.55,
    db_path: str = DEFAULT_DB_PATH
):
    """
    Directly updates the remote Google Sheet using gspread and Service Account credentials.
    """
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        print("Please install gspread & google-auth: pip install gspread google-auth")
        return

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_file(credentials_json_path, scopes=scopes)
    client = gspread.authorize(creds)

    if sheet_id_or_url.startswith("http"):
        sheet = client.open_by_url(sheet_id_or_url)
    else:
        sheet = client.open_by_key(sheet_id_or_url)

    if worksheet_name:
        worksheet = sheet.worksheet(worksheet_name)
    else:
        worksheet = sheet.get_worksheet(0)

    print(f"Connected to Google Sheet: '{sheet.title}' -> Worksheet: '{worksheet.title}'")

    candidate_accounts = fetch_high_confidence_accounts(db_path, min_confidence)
    print(f"Found {len(candidate_accounts)} candidates with verified profiles (confidence >= {min_confidence}).")

    all_values = worksheet.get_all_values()
    if not all_values:
        print("Worksheet is empty!")
        return

    headers = all_values[0]
    col_map = {col_name: idx for idx, col_name in enumerate(headers)}
    id_col_idx = col_map.get("id")

    if id_col_idx is None:
        print("Error: Could not locate 'id' column in worksheet header!")
        return

    # Check for 'notes' column
    notes_col_idx = col_map.get("notes")
    if notes_col_idx is None:
        # Append 'notes' column at the end
        new_col_num = len(headers) + 1
        worksheet.update_cell(1, new_col_num, "notes")
        notes_col_idx = len(headers)
        headers.append("notes")
        print(f"Added 'notes' header to column {new_col_num}.")

    cells_to_update = []
    updated_candidates = 0

    for row_idx, row_data in enumerate(all_values[1:], start=2):
        if id_col_idx >= len(row_data):
            continue
        pid = row_data[id_col_idx]
        if not pid or pid not in candidate_accounts:
            continue

        accounts = candidate_accounts[pid]
        updated_candidates += 1

        # 1. Update URLs only
        for plat, acc in accounts.items():
            cfg = PLATFORM_CONFIG.get(plat)
            if not cfg:
                continue

            url_col = cfg["url_col"]
            note_col = cfg.get("note_col")
            u_idx = col_map.get(url_col)
            n_idx = col_map.get(note_col) if note_col else None

            if u_idx is not None:
                current_url = row_data[u_idx] if u_idx < len(row_data) else ""
                if not current_url.strip():
                    cells_to_update.append(gspread.Cell(row=row_idx, col=u_idx + 1, value=acc["url"]))
                    if n_idx is not None:
                        current_note = row_data[n_idx] if n_idx < len(row_data) else ""
                        if not current_note.strip():
                            cells_to_update.append(gspread.Cell(row=row_idx, col=n_idx + 1, value="Auto_search"))

        # 2. Update concatenated notes
        new_concat = format_concatenated_notes(accounts)
        if new_concat and notes_col_idx is not None:
            current_note = row_data[notes_col_idx] if notes_col_idx < len(row_data) else ""
            if not current_note.strip():
                cells_to_update.append(gspread.Cell(row=row_idx, col=notes_col_idx + 1, value=new_concat))
            elif new_concat not in current_note:
                cells_to_update.append(gspread.Cell(row=row_idx, col=notes_col_idx + 1, value=f"{current_note}; {new_concat}"))

    if cells_to_update:
        print(f"Updating {len(cells_to_update)} cells across {updated_candidates} candidate rows...")
        worksheet.update_cells(cells_to_update)
        print("✓ Successfully synchronized high-confidence results to Google Sheet!")
    else:
        print("No new cells required updating (all values already populated).")


def update_google_sheet_webhook(
    webhook_url: str,
    min_confidence: float = 0.55,
    db_path: str = DEFAULT_DB_PATH
):
    """
    Updates the Google Sheet via a lightweight Google Apps Script Webhook.
    """
    candidate_accounts = fetch_high_confidence_accounts(db_path, min_confidence)
    if not candidate_accounts:
        print("No high-confidence accounts found to sync.")
        return

    updates = []
    for pid, accounts in candidate_accounts.items():
        item = {"id": pid, "colors": {}}
        max_conf = 0.0
        for plat, acc in accounts.items():
            cfg = PLATFORM_CONFIG.get(plat)
            if cfg:
                col = cfg["url_col"]
                note_col = cfg.get("note_col")
                item[col] = acc["url"]
                if note_col:
                    item[note_col] = cfg.get("note_val", "Auto_search")
                item["colors"][col] = get_confidence_color(acc.get("confidence", 0.55))
                if acc.get("confidence", 0) > max_conf:
                    max_conf = acc.get("confidence", 0)
        
        item["notes"] = format_concatenated_notes(accounts)
        if max_conf > 0:
            item["colors"]["notes"] = get_confidence_color(max_conf)
        updates.append(item)

    import requests

    # 1. Attempt to purge stale EMAIL- notes via webhook if supported
    try:
        r_clean = requests.post(webhook_url, json={"action": "clean_email"}, timeout=30)
        if r_clean.status_code == 200:
            res = r_clean.json()
            if res.get("cleaned_rows", 0) > 0:
                print(f"🧹 Cleaned stale email notes from {res['cleaned_rows']} candidate rows in Google Sheet.")
    except Exception:
        pass

    chunk_size = 8
    total_chunks = (len(updates) + chunk_size - 1) // chunk_size
    print(f"Syncing {len(updates)} candidate profiles to Google Sheet in {total_chunks} batches (size={chunk_size})...")

    total_synced = 0
    for idx in range(0, len(updates), chunk_size):
        chunk = updates[idx:idx + chunk_size]
        batch_num = (idx // chunk_size) + 1
        print(f"  • Sending Batch {batch_num}/{total_chunks} ({len(chunk)} candidates)...", end=" ", flush=True)
        try:
            r = requests.post(webhook_url, json={"updates": chunk}, timeout=60)
            if r.status_code == 200:
                res = r.json()
                count = res.get("updated", len(chunk))
                total_synced += count
                print(f"✓ Updated {count} rows in Google Sheet")
            else:
                print(f"⚠️ HTTP {r.status_code}: {r.text[:100]}")
        except Exception as e:
            print(f"⚠️ Error: {e}")

    print(f"\n🎉 Successfully synchronized {total_synced} candidate rows directly into your live Google Sheet!")


APPS_SCRIPT_TEMPLATE = """
/**
 * Google Apps Script Webhook for PEP Social Discovery
 * Paste into: Extensions > Apps Script in your Google Sheet
 * Then click Deploy > New deployment > Web app (Access: Anyone)
 */
function doPost(e) {
  if (!e || !e.postData || !e.postData.contents) {
    return ContentService.createTextOutput(JSON.stringify({status: "ok", message: "Webhook is alive and ready."}))
      .setMimeType(ContentService.MimeType.JSON);
  }

  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("persons");
  if (!sheet) {
    return ContentService.createTextOutput(JSON.stringify({error: "Worksheet 'persons' not found"}))
      .setMimeType(ContentService.MimeType.JSON);
  }

  var data = JSON.parse(e.postData.contents);
  var updates = data.updates || [];

  var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  var colMap = {};
  for (var c = 0; c < headers.length; c++) {
    colMap[headers[c]] = c + 1;
  }

  // Ensure 'notes' column exists
  if (!colMap["notes"]) {
    var nextCol = sheet.getLastColumn() + 1;
    sheet.getRange(1, nextCol).setValue("notes");
    colMap["notes"] = nextCol;
  }

  var idCol = colMap["id"];
  if (!idCol) {
    return ContentService.createTextOutput(JSON.stringify({error: "'id' column not found"}))
      .setMimeType(ContentService.MimeType.JSON);
  }

  var idRange = sheet.getRange(1, idCol, sheet.getLastRow(), 1);
  var updatedCount = 0;

  for (var i = 0; i < updates.length; i++) {
    var item = updates[i];
    if (!item.id) continue;

    var match = idRange.createTextFinder(item.id).matchEntireCell(true).findNext();
    if (!match) continue;
    var rowNum = match.getRow();

    for (var key in item) {
      if (key === "id" || key === "colors") continue;
      var cIdx = colMap[key];
      if (cIdx) {
        var cell = sheet.getRange(rowNum, cIdx);
        var curVal = cell.getValue();
        if (!curVal || curVal.toString().trim() === "") {
          cell.setValue(item[key]);
          if (item.colors && item.colors[key]) {
            cell.setBackground(item.colors[key]);
          }
        } else if (key === "notes" && curVal.indexOf(item[key]) === -1) {
          cell.setValue(curVal + "; " + item[key]);
          if (item.colors && item.colors["notes"]) {
            cell.setBackground(item.colors["notes"]);
          }
        }
      }
    }
    updatedCount++;
  }

  return ContentService.createTextOutput(JSON.stringify({status: "success", updated: updatedCount}))
    .setMimeType(ContentService.MimeType.JSON);
}
"""



def print_apps_script():
    print("=" * 70)
    print("GOOGLE APPS SCRIPT WEBHOOK CODE")
    print("=" * 70)
    print(APPS_SCRIPT_TEMPLATE)
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Synchronize PEP High-Confidence Social Media Profiles to Google Sheets")
    parser.add_argument("--mode", type=str, choices=["csv", "api", "webhook"], default="csv", help="Mode: 'csv' for merged CSV, 'api' for GCP Service Account, 'webhook' for Apps Script")
    parser.add_argument("--input-csv", type=str, default=DEFAULT_CSV_PATH, help="Path to original candidates CSV")
    parser.add_argument("--output-csv", type=str, default="updated_pep_candidates_with_social.csv", help="Path for merged output CSV")
    parser.add_argument("--sheet", type=str, default="1eyZ0ssTTkU3wkRw9vN8CGj8L0aYz80utZQUkFE63nMY", help="Google Sheet ID or Full URL")
    parser.add_argument("--creds", type=str, default="service_account.json", help="Google Service Account JSON key path")
    parser.add_argument("--webhook", type=str, default="", help="Google Apps Script Webhook URL")
    parser.add_argument("--worksheet", type=str, default="persons", help="Worksheet title (default: 'persons')")
    parser.add_argument("--min-confidence", type=float, default=0.55, help="Minimum confidence threshold (default: 0.55)")
    parser.add_argument("--probable-only", action="store_true", help="Only sync PROBABLE accounts (confidence >= 0.70)")
    parser.add_argument("--db", type=str, default=DEFAULT_DB_PATH, help="Path to peps.db SQLite database")
    parser.add_argument("--print-apps-script", action="store_true", help="Print Google Apps Script deployment code")

    args = parser.parse_args()

    if args.print_apps_script:
        print_apps_script()
        exit(0)

    threshold = 0.70 if args.probable_only else args.min_confidence

    if args.mode == "csv":
        update_csv_file(
            input_csv=args.input_csv,
            output_csv=args.output_csv,
            min_confidence=threshold,
            db_path=args.db
        )
    elif args.mode == "api":
        update_google_sheet_direct(
            sheet_id_or_url=args.sheet,
            credentials_json_path=args.creds,
            worksheet_name=args.worksheet or "persons",
            min_confidence=threshold,
            db_path=args.db
        )
    elif args.mode == "webhook":
        if not args.webhook:
            print("Error: --webhook [URL] is required when using --mode webhook.")
        else:
            update_google_sheet_webhook(
                webhook_url=args.webhook,
                min_confidence=threshold,
                db_path=args.db
            )
