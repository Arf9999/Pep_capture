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
from models import Person, PopoloCollection
from query_builder import generate_consolidated_candidate_queries, infer_platform_from_url
from search_engine import SerperSearchEngine, DailyQuotaExceededError
from evaluator import evaluate_candidate_snippet
from profile_inspector import inspect_profile_deep
from db import init_database, upsert_person_with_accounts


def evaluate_single_result(row, result):
    """Worker task to evaluate an individual search result with deep profile inspection if confidence >= 0.50."""
    url = result.get("url")
    if not url:
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
    eval_workers: int = 4
):
    if not os.path.exists(csv_file_path):
        print(f"Error: CSV file not found at '{csv_file_path}'")
        return

    searcher = SerperSearchEngine(max_daily_limit=1000)
    collection = PopoloCollection()
    init_database()

    print(f"Daily Search API budget remaining today: {searcher.get_remaining_daily_budget()} / 1000 queries")

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

            # Generate consolidated query covering all target social platforms
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

            print(f"  ⚡ Found {len(raw_results)} candidate profile snippets. Evaluating in parallel ({eval_workers} workers)...")

            # Parallel evaluation of candidate search results
            if raw_results:
                with ThreadPoolExecutor(max_workers=eval_workers) as executor:
                    futures = [executor.submit(evaluate_single_result, row, res) for res in raw_results]
                    for f in futures:
                        contact = f.result()
                        if contact:
                            person.contact_details.append(contact)
                            print(f"    ✓ Matched [{contact.type.upper()}] {contact.value} (Score: {contact.confidence})")

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

    args = parser.parse_args()

    target_id_list = [i.strip() for i in args.ids.split(",") if i.strip()] if args.ids else None

    run_pipeline(
        csv_file_path=args.csv,
        output_json_path=args.output,
        limit_records=args.limit,
        start_record=args.start,
        start_id=args.start_id if args.start_id else None,
        target_ids=target_id_list,
        researcher_filter=args.researcher if args.researcher else None
    )
