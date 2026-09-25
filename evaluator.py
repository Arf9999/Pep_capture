"""
LLM Candidate Evaluator for PEP Social Accounts
Evaluates candidate profiles considering name overlap, geography, candidate bio alignment,
and penalizing political party organization accounts.
"""

import re
from typing import Dict, Any, Optional
from models import ContactDetail, ConfidenceLevel
from query_builder import get_district_keywords


PARTY_ORGANIZATION_KEYWORDS = [
    "official page of", "da official", "anc official", "eff official", "party account",
    "regional office", "branch page", "headquarters", "media team", "parliamentary caucus"
]


def evaluate_candidate_snippet(
    pep_info: Dict[str, str],
    platform: str,
    search_result: Dict[str, str]
) -> Optional[ContactDetail]:
    """
    Evaluates a single search result snippet against target candidate parameters:
    - Name match (token overlap & permutations)
    - Location match (district/municipality keyword alignment)
    - Role & Bio match (candidate, councillor, ward, election keywords)
    - Disqualifies official party organizational accounts
    """
    target_name = pep_info.get("full_name", "")
    target_party = pep_info.get("party_name", "")
    target_location = pep_info.get("b ", "")
    title = search_result.get("title", "")
    snippet = search_result.get("snippet", "")
    url = search_result.get("url", "")

    title_lower = title.lower()
    snippet_lower = snippet.lower()

    # Rule Check: Disqualify Official Party Accounts
    is_party_account = any(kw in title_lower or kw in snippet_lower for kw in PARTY_ORGANIZATION_KEYWORDS)
    
    signals = []
    score = 0.0

    # 1. Name Match Score (Weight: 0.50)
    first_name = pep_info.get("first_name", "").strip().lower()
    middle_name = pep_info.get("middle_name", "").strip().lower()
    last_name = pep_info.get("last_name", "").strip().lower()
    target_tokens = set(re.findall(r'\w+', target_name.lower()))
    title_tokens = set(re.findall(r'\w+', title_lower))

    middle_tokens = [m for m in re.split(r'[\s\-]+', middle_name) if m and len(m) > 1]

    # Check 1: First + Last Name match (or Last + First)
    if first_name and last_name and first_name in title_tokens and last_name in title_tokens:
        score += 0.50
        signals.append("FIRST_LAST_EXACT_MATCH")
    # Check 2: Middle + Last Name match (e.g. Reimar Kunz, Justice Shusha, Dale Palmer)
    elif any(m in title_tokens for m in middle_tokens) and last_name and last_name in title_tokens:
        matched_m = [m for m in middle_tokens if m in title_tokens][0]
        score += 0.50
        signals.append(f"MIDDLE_LAST_EXACT_MATCH ({matched_m} {last_name})")
    # Check 3: First + Middle Name match (common when registering on FB/IG without formal surname)
    elif first_name and any(m in title_tokens for m in middle_tokens):
        matched_m = [m for m in middle_tokens if m in title_tokens][0]
        score += 0.40
        signals.append(f"FIRST_MIDDLE_EXACT_MATCH ({first_name} {matched_m})")
    # Check 4: General Token Overlap
    elif target_tokens:
        overlap = len(target_tokens.intersection(title_tokens)) / len(target_tokens)
        if overlap >= 0.5:
            score += 0.35
            signals.append(f"NAME_OVERLAP ({round(overlap, 2)})")

    # 2. Location / District / Municipal Cluster Alignment (Weight: 0.30)
    sub_locations = get_district_keywords(target_location)
    matched_locs = [loc for loc in sub_locations if loc in snippet_lower or loc in title_lower]
    if matched_locs:
        score += 0.30
        signals.append(f"LOCATION_MATCH ({','.join(matched_locs[:2])})")

    # Disqualify Directory, Aggregator, and Post URLs (Not individual profiles)
    url_lower = url.lower()
    disqualified_url_patterns = [
        "/public/",              # Facebook directory (e.g. facebook.com/public/Name)
        "/pub/dir/",             # LinkedIn directory (e.g. linkedin.com/pub/dir/Name)
        "/directory/",           # General directory
        "/groups/",              # Facebook group post
        "/posts/",               # Single post
        "/hashtag/",             # Hashtag page
        "/tags/",                # Tag page
        "/search",               # Search result page
        "/events/",              # Event page
        "/status/",              # Single tweet/post
        "/video/",               # Single video
        "/reel/",                # Single reel
        "instagram.com/p/",      # Single Instagram photo post (do NOT block facebook.com/p/)
    ]
    if any(pat in url_lower for pat in disqualified_url_patterns):
        return None

    # Verify if URL is a genuine direct candidate profile
    is_direct_profile = (
        ("linkedin.com/in/" in url_lower) or
        ("x.com/" in url_lower and not any(x in url_lower for x in ["/i/", "/intent", "/home", "/explore"])) or
        ("facebook.com/" in url_lower) or
        ("instagram.com/" in url_lower) or
        ("tiktok.com/@" in url_lower) or
        ("youtube.com/@" in url_lower or "youtube.com/channel/" in url_lower)
    )
    if is_direct_profile:
        score += 0.15
        signals.append("DIRECT_PROFILE_URL")

    # 4. Role / Campaign / Professional Bio Context (Weight: 0.15)
    campaign_keywords = ["candidate", "councillor", "ward", "election", "politician", "public figure", "employed", "self employed", "director", "manager", "secondary school"]
    if target_party:
        campaign_keywords.append(target_party.lower())

    matched_keywords = [k for k in campaign_keywords if k in snippet_lower or k in title_lower]
    if matched_keywords:
        score += min(0.15, len(matched_keywords) * 0.05)
        signals.append(f"BIO_CONTEXT_MATCH ({','.join(matched_keywords[:2])})")

    # 5. Penalty for Party Organization Pages
    if is_party_account:
        score -= 0.50
        signals.append("PARTY_ORGANIZATION_PENALTY")

    final_score = round(min(1.0, max(0.0, score)), 2)

    # Filter out scores below 0.30
    if final_score < 0.30:
        return None

    if final_score >= 0.75:
        level = ConfidenceLevel.HIGH
    elif final_score >= 0.50:
        level = ConfidenceLevel.MEDIUM
    else:
        level = ConfidenceLevel.LOW

    rationale = (
        f"Target: '{target_name}' in '{target_location}' ({target_party}). "
        f"Match score: {final_score}. Title: '{title}'. "
        f"Signals: {', '.join(signals)}."
    )

    return ContactDetail(
        type=platform,
        value=url,
        label=title,
        confidence=final_score,
        confidence_level=level,
        rationale=rationale,
        signals=signals
    )
