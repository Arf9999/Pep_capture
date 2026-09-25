"""
Main Runner Pipeline for PEP Social Profile Discovery & Popolo Export
Ingests 9,000+ SA Local Government Election Candidates, executes rate-limited search queries,
evaluates candidate profiles, and writes Popolo JSON & CSV output files.
"""

import csv
import json
import argparse
import os
from typing import List, Optional

from concurrent.futures import ThreadPoolExecutor
from models import Person, ContactDetail, ConfidenceLevel, PopoloCollection
from query_builder import (
    generate_consolidated_candidate_queries,
    generate_email_social_query,
    infer_platform_from_url
)
from search_engine import SerperSearchEngine, SerpentSearchEngine, DailyQuotaExceededError
from evaluator import evaluate_candidate_snippet
from profile_inspector import (
    extract_emails_from_text,
    fetch_peoples_assembly_emails,
    is_discovery_hub_url,
    inspect_discovery_hub_and_extract,
    inspect_profile_deep
)
from db import init_database, upsert_person_with_accounts


def evaluate_single_result(row, result):
    """Worker task to evaluate an individual search result with deep profile inspection if confidence >= 0.50."""
    url = result.get("url")
    if not url or is_discovery_hub_url(url):
        return None
    platform = infer_platform_from_url(url)
    contact = evaluate_candidate_snippet(pep_info=row, platform=platform, search_result=result)
    
    # Secondary validation: fetch actual profile page and examine for deep confirmation
    if contact and contact.confidence >= 0.50:
        contact = inspect_profile_deep(contact, row)
        
    return contact


def run_pipeline(
    csv_file_path: str,
    output_json_path: str = "popolo_sa_candidates.json",
    limit_records: Optional[int] = 10,
    start_record: int = 0,
    start_id: Optional[str] = None,
    target_ids: Optional[List[str]] = None,
    researcher_filter: Optional[str] = None,
    provider: str = "serpent",
    max_quota: int = 9000,
    eval_workers: int = 4
):
    if not os.path.exists(csv_file_path):
        print(f"Error: CSV file not found at '{csv_file_path}'")
        return

    if provider == "serpent":
        searcher = SerpentSearchEngine(max_daily_limit=max_quota)
    else:
        searcher = SerperSearchEngine(max_daily_limit=max_quota)

    collection = PopoloCollection()
    init_database()

    print(f"[{provider.upper()} API] Daily Search API budget remaining today: {searcher.get_remaining_daily_budget()} / {max_quota} queries")

    target_id_set = set(target_ids) if target_ids else None

    with open(csv_file_path, mode="r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        total_rows = len(reader)

        # Apply researcher filter if specified
        if researcher_filter:
            rf = researcher_filter.lower().strip()
            reader = [r for r in reader if rf in r.get("researcher ", "").lower()]
            print(f"Filtered to {len(reader)} records assigned to researcher: '{researcher_filter}'.")

        # Locate start_id if specified
        start_idx = start_record
        if start_id:
            found_idx = next((i for i, r in enumerate(reader) if r.get("id") == start_id), None)
            if found_idx is not None:
                start_idx = found_idx
                print(f"Starting from record ID '{start_id}' at index {start_idx}.")

        if target_id_set:
            candidate_rows = [(idx, r) for idx, r in enumerate(reader) if r.get("id") in target_id_set]
            print(f"Matched {len(candidate_rows)} specific targets by ID.")
        else:
            end_idx = min(len(reader), start_idx + limit_records) if limit_records else len(reader)
            candidate_rows = [(idx, reader[idx]) for idx in range(start_idx, end_idx)]
            print(f"Processing {len(candidate_rows)} records (index {start_idx} to {end_idx})...")

        for count, (idx, row) in enumerate(candidate_rows):
            person_id = row.get("id", f"pers_{idx+1}")
            full_name = row.get("full_name", "")
            party = row.get("party_name", "")
            district = row.get("b ", "")

            print(f"\n[{count+1}/{len(candidate_rows)}] Candidate: {full_name} ({person_id}) | Party: {party} | District: {district}")

            person = Person(
                id=person_id,
                name=full_name,
                first_name=row.get("first_name"),
                middle_name=row.get("middle_name"),
                last_name=row.get("last_name"),
                party_name=party,
                office=row.get("office"),
                district=district
            )

            # 1. Primary candidate search across social media platforms
            queries = generate_consolidated_candidate_queries(row, max_queries=2)
            raw_results = []
            seen_urls = set()

            try:
                for query_str in queries:
                    print(f"  🔎 Google Query: {query_str}")
                    search_hits = searcher.search(query_str, num_results=10)
                    for h in search_hits:
                        u = h.get("url")
                        if u and u not in seen_urls:
                            seen_urls.add(u)
                            raw_results.append(h)
            except DailyQuotaExceededError as e:
                print(f"\n⚠️  {e}")
                print("Saving all progress processed so far and stopping.")
                break

            # 2. Extract Candidate Emails & Outward Social Handles from Discovery Hubs
            # NOTE: Link-in-bio hubs and People's Assembly are NOT targets themselves;
            # they are used solely as bridges to extract candidate emails and outward personal social handles.
            candidate_emails = set()

            # A. Extract emails from search snippets
            for r in raw_results:
                snippet_text = f"{r.get('title', '')} {r.get('snippet', '')}"
                candidate_emails.update(extract_emails_from_text(snippet_text))

            # B. Query People's Assembly (pa.org.za) solely for official email discovery
            try:
                pa_emails = fetch_peoples_assembly_emails(full_name)
                if pa_emails:
                    candidate_emails.update(pa_emails)
                    print(f"  🏛️  People's Assembly: Discovered official email(s): {', '.join(pa_emails)}")
            except Exception as e:
                pass

            # C. Inspect discovery hubs (Linktree, Beacons, Carrd, Taplink, Lnk.Bio, Bio.site, Pallyy)
            # Hubs are used strictly to harvest candidate social addresses/handles and emails.
            # They are NEVER targets for scoring themselves, but assist to provide confidence to outward handles.
            hub_corroborated_urls = set()
            hub_handles = set()
            outward_hub_snippets = []
            for r in raw_results:
                u = r.get("url", "")
                if is_discovery_hub_url(u):
                    hub_data = inspect_discovery_hub_and_extract(u)
                    if hub_data.get("emails"):
                        candidate_emails.update(hub_data["emails"])
                    for s_item in hub_data.get("social_links", []):
                        s_url = s_item["url"]
                        s_handle = s_item["handle"]
                        hub_corroborated_urls.add(s_url.lower())
                        hub_handles.add(s_handle.lower())
                        outward_hub_snippets.append({
                            "title": f"{full_name} ({s_item['platform'].capitalize()})",
                            "snippet": f"Personal profile link discovered on candidate landing hub {u}",
                            "url": s_url
                        })

            # Store verified candidate email on Person record
            primary_email = sorted(list(candidate_emails))[0] if candidate_emails else None
            if primary_email:
                person.email = primary_email
                person.contact_details.append(ContactDetail(
                    type="email",
                    value=primary_email,
                    label="Candidate Verified Contact Email",
                    confidence=0.95,
                    confidence_level=ConfidenceLevel.PROBABLE,
                    rationale=f"Official contact email extracted for {full_name} via civic records / profile metadata.",
                    signals=["CANDIDATE_EMAIL_EXTRACTED"]
                ))
                print(f"  📧 Verified Candidate Email: {primary_email}")

            # 3. SECONDARY SEARCH: Use extracted email as a secondary search term across social sites!
            secondary_social_results = []
            if primary_email:
                email_query = generate_email_social_query(primary_email)
                print(f"  🔎 Secondary Social Search (via Email): {email_query}")
                try:
                    email_hits = searcher.search(email_query, num_results=10)
                    for eh in email_hits:
                        u = eh.get("url")
                        if u and u not in seen_urls and not is_discovery_hub_url(u):
                            seen_urls.add(u)
                            secondary_social_results.append(eh)
                except DailyQuotaExceededError as e:
                    print(f"  ⚠️ Search quota reached during email secondary search: {e}")

            # 4. Parallel evaluation of candidate direct social search results & outward hub handles
            all_social_to_eval = [
                r for r in raw_results if not is_discovery_hub_url(r.get("url", ""))
            ] + secondary_social_results + outward_hub_snippets

            row_context = {
                **row,
                "email": primary_email or "",
                "hub_corroborated_urls": hub_corroborated_urls,
                "hub_handles": hub_handles
            }

            print(f"  ⚡ Found {len(all_social_to_eval)} candidate social snippets. Evaluating in parallel ({eval_workers} workers)...")

            if all_social_to_eval:
                with ThreadPoolExecutor(max_workers=eval_workers) as executor:
                    futures = [executor.submit(evaluate_single_result, row_context, res) for res in all_social_to_eval]
                    for f in futures:
                        contact = f.result()
                        if contact:
                            if not any(c.value.lower() == contact.value.lower() for c in person.contact_details):
                                person.contact_details.append(contact)
                                print(f"    ✓ Matched [{contact.type.upper()}] {contact.value} (Score: {contact.confidence} | {contact.confidence_level})")

            # Save person to in-memory collection and SQLite database
            collection.persons.append(person)
            upsert_person_with_accounts(person.model_dump())

    # Save to Popolo JSON output file
    output_data = collection.model_dump()
    with open(output_json_path, "w", encoding="utf-8") as out_f:
        json.dump(output_data, out_f, indent=2)

    print(f"\nCompleted run! Exported Popolo records to '{output_json_path}'.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PEP Social Media Discovery Pipeline")
    parser.add_argument(
        "--csv",
        type=str,
        default="/Users/arf/Downloads/PEP data _ South Africa _ Tables _ 2026 _ Local Gorvenment Election Candidates - persons.csv",
        help="Path to candidates CSV file"
    )
    parser.add_argument("--output", type=str, default="popolo_sa_candidates.json", help="Output JSON path")
    parser.add_argument("--limit", type=int, default=10, help="Number of records to process")
    parser.add_argument("--start", type=int, default=0, help="Start record index")
    parser.add_argument("--start-id", type=str, default="", help="Candidate ID to start from (e.g. pers_18589)")
    parser.add_argument("--researcher", type=str, default="", help="Filter candidates assigned to a specific researcher (e.g. 'Andrew Fraser')")
    parser.add_argument("--ids", type=str, default="", help="Comma-separated list of candidate IDs (e.g. pers_18589,pers_18590)")

    parser.add_argument("--provider", type=str, default="serpent", choices=["serpent", "serper"], help="Search provider to use")
    parser.add_argument("--max-quota", type=int, default=9000, help="Maximum search quota limit")

    args = parser.parse_args()

    target_id_list = [i.strip() for i in args.ids.split(",") if i.strip()] if args.ids else None

    run_pipeline(
        csv_file_path=args.csv,
        output_json_path=args.output,
        limit_records=args.limit,
        start_record=args.start,
        start_id=args.start_id if args.start_id else None,
        target_ids=target_id_list,
        researcher_filter=args.researcher if args.researcher else None,
        provider=args.provider,
        max_quota=args.max_quota
    )
