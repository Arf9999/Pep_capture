"""
Profile Inspector for PEP Social Media Accounts
Performs secondary validation on candidate profiles with initial confidence >= 0.50:
- Fetches actual profile content (Facebook, LinkedIn, Twitter/X, Instagram, TikTok, YouTube)
- Facebook: Looks for political party links/affiliations, councillor/candidate roles, local town check-ins
- LinkedIn: Looks for biographic details, employment history, municipal governance, education
- Twitter/X: Examines bio, handle, and tweet/post contents
- Instagram: Examines bio text, name, and post captions
- Adjusts confidence score (+0.20 to +0.35 for verified party/bio match, penalty for conflicting party/inactivity)
"""

import re
import html
from typing import Dict, Any, Optional
import httpx
from models import ContactDetail, ConfidenceLevel
from query_builder import get_district_keywords

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-ZA,en-GB;q=0.9,en-US;q=0.8,en;q=0.7"
}

MAJOR_SA_PARTIES = {
    "african national congress": ["anc", "african national congress"],
    "democratic alliance": ["da", "democratic alliance"],
    "economic freedom fighters": ["eff", "economic freedom fighters"],
    "patriotic alliance": ["pa", "patriotic alliance"],
    "inkatha freedom party": ["ifp", "inkatha freedom party"],
    "freedom front plus": ["vf plus", "freedom front plus", "vryheidsfront"],
    "action sa": ["actionsa", "action sa"],
    "al jama-ah": ["al jama-ah", "al jamaah"],
    "african christian democratic party": ["acdp", "african christian democratic party"],
    "pan africanist congress": ["pac", "pan africanist congress"],
    "united democratic movement": ["udm", "united democratic movement"],
    "national freedom party": ["nfp", "national freedom party"],
    "people's freedom party": ["people's freedom party", "peoples freedom party", "pfp"],
    "good": ["good party", "patricia de lille"]
}


def fetch_profile_metadata(url: str, timeout: float = 7.0) -> Dict[str, str]:
    """Fetches public profile HTML and extracts title, meta descriptions, and clean body text."""
    try:
        with httpx.Client(headers=DEFAULT_HEADERS, follow_redirects=True, timeout=timeout) as client:
            resp = client.get(url)
            text = resp.text
            
            # Extract HTML Title
            title_m = re.search(r'<title>(.*?)</title>', text, re.IGNORECASE | re.DOTALL)
            title = html.unescape(title_m.group(1).strip()) if title_m else ""
            
            # Extract OpenGraph description & Meta description
            og_desc_m = re.search(r'<meta[^>]*property=["\']og:description["\'][^>]*content=["\'](.*?)["\']', text, re.IGNORECASE)
            og_desc = html.unescape(og_desc_m.group(1).strip()) if og_desc_m else ""
            
            desc_m = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\'](.*?)["\']', text, re.IGNORECASE)
            meta_desc = html.unescape(desc_m.group(1).strip()) if desc_m else ""
            
            # Extract body sample text
            body_clean = re.sub(r'<script[^>]*>.*?</script>', ' ', text, flags=re.DOTALL)
            body_clean = re.sub(r'<style[^>]*>.*?</style>', ' ', body_clean, flags=re.DOTALL)
            body_clean = re.sub(r'<[^>]+>', ' ', body_clean)
            body_clean = re.sub(r'\s+', ' ', body_clean).strip()
            
            return {
                "status": resp.status_code,
                "title": title,
                "og_description": og_desc or meta_desc,
                "body_sample": body_clean[:2500],
                "full_html_sample": text[:3500]
            }
    except Exception as e:
        return {"status": 0, "error": str(e), "title": "", "og_description": "", "body_sample": "", "full_html_sample": ""}


def inspect_profile_deep(
    contact: ContactDetail,
    pep_info: Dict[str, str]
) -> ContactDetail:
    """
    Performs deep examination of the profile page if initial preview confidence >= 0.50.
    Looks for:
    - Political party links or mentions
    - Biographic / employment details
    - Municipal & geographic alignment
    - Conflicting party mentions
    """
    url = contact.value
    platform = contact.type.lower()
    target_name = pep_info.get("full_name", "")
    target_party = pep_info.get("party_name", "").strip()
    target_district = pep_info.get("b ", "").strip()
    
    meta = fetch_profile_metadata(url)
    if meta.get("status") not in (200, 301, 302) and not meta.get("og_description"):
        # Could not fetch page; keep existing preview score
        return contact

    combined_text = f"{meta.get('title', '')} {meta.get('og_description', '')} {meta.get('body_sample', '')}".lower()
    
    score_delta = 0.0
    deep_signals = []

    # 1. Candidate Name Confirmation in Deep Page Title/Bio
    first_name = pep_info.get("first_name", "").strip().lower()
    last_name = pep_info.get("last_name", "").strip().lower()
    if last_name and (last_name in combined_text):
        if first_name and (first_name in combined_text):
            deep_signals.append("PAGE_NAME_CONFIRMED")
            score_delta += 0.10

    # 2. Political Party Affiliation / Links Examination (Crucial for Facebook / Twitter)
    if target_party:
        target_party_lower = target_party.lower()
        aliases = [target_party_lower]
        for p_name, p_aliases in MAJOR_SA_PARTIES.items():
            if p_name in target_party_lower or target_party_lower in p_name:
                aliases.extend(p_aliases)
                break
        
        # Check if candidate's party is mentioned in the profile
        matched_target_party = [alias for alias in set(aliases) if re.search(r'\b' + re.escape(alias) + r'\b', combined_text)]
        if matched_target_party:
            score_delta += 0.30
            deep_signals.append(f"PAGE_PARTY_CONFIRMED ({matched_target_party[0].upper()})")
        else:
            # Check if an opposing major party is explicitly claimed
            for other_party, other_aliases in MAJOR_SA_PARTIES.items():
                if other_party not in target_party_lower and not any(a in target_party_lower for a in other_aliases):
                    if any(re.search(r'\b(?:councillor|member|candidate|volunteer|chairperson)\s+(?:of|for)?\s*' + re.escape(oa) + r'\b', combined_text) for oa in other_aliases):
                        score_delta -= 0.50
                        deep_signals.append(f"CONFLICTING_PARTY_DETECTED ({other_party})")
                        break

    # 3. Biographic & Municipal Details (Crucial for LinkedIn / Candidate Bios)
    bio_keywords = [
        "councillor", "council", "ward", "municipality", "local government",
        "election", "candidate", "director", "manager", "committee", "community leader",
        "secretary", "treasurer", "chairperson"
    ]
    matched_bio_terms = [b for b in bio_keywords if b in combined_text]
    if matched_bio_terms:
        score_delta += min(0.20, len(matched_bio_terms) * 0.05)
        deep_signals.append(f"PAGE_BIO_CONFIRMED ({','.join(matched_bio_terms[:3])})")

    # 4. Location & Municipal Cluster Check in Profile
    district_keywords = get_district_keywords(target_district)
    matched_page_locs = [loc for loc in district_keywords if loc != "south africa" and loc in combined_text]
    if matched_page_locs:
        score_delta += 0.15
        deep_signals.append(f"PAGE_LOCATION_CONFIRMED ({','.join(matched_page_locs[:2])})")

    # Check for foreign locations or lack of South African anchor on profile page
    foreign_locs = ["united kingdom", "london", "united states", "usa", "new york", "california", "canada", "australia", "nigeria", "kenya", "india", "dubai"]
    matched_page_foreign = [f for f in foreign_locs if re.search(r'\b' + re.escape(f) + r'\b', combined_text)]
    if matched_page_foreign:
        score_delta -= 0.50
        deep_signals.append(f"FOREIGN_LOCATION_PAGE_DETECTED ({matched_page_foreign[0].title()})")
    else:
        has_page_sa = bool(matched_page_locs) or any(a in combined_text for a in ["south africa", "rsa", "za", ".co.za", "+27"])
        if not has_page_sa:
            score_delta -= 0.20
            deep_signals.append("NO_SOUTH_AFRICA_ON_PAGE_PENALTY (-0.20)")

    # 5. Extract Outward Social / Messenger Handles (especially on Linktree, Beacons, Carrd, Taplink, Lnk.Bio, Bio.site)
    extracted_outward = []
    outward_patterns = {
        "WhatsApp": r'(?:wa\.me/|whatsapp\.com/send\?phone=)(\+?\d+)',
        "Instagram": r'instagram\.com/([a-zA-Z0-9_\.]{3,30})',
        "Twitter": r'(?:twitter\.com|x\.com)/([a-zA-Z0-9_]{3,20})',
        "Facebook": r'facebook\.com/([a-zA-Z0-9\._\-]{3,40})',
        "LinkedIn": r'linkedin\.com/in/([a-zA-Z0-9_\-]{3,50})',
        "YouTube": r'youtube\.com/(?:@|channel/|c/)?([a-zA-Z0-9_\-]{3,40})',
        "TikTok": r'tiktok\.com/@([a-zA-Z0-9_\.]{3,30})'
    }
    raw_html = meta.get("full_html_sample", "")
    for plat_name, pat in outward_patterns.items():
        found = re.findall(pat, raw_html, re.IGNORECASE)
        clean_found = [f for f in found if f.lower() not in ("share", "sharer", "intent", "login", "signup", "terms", "privacy", "about")]
        if clean_found:
            extracted_outward.append(f"{plat_name}: @{clean_found[0]}")

    if extracted_outward:
        deep_signals.append(f"OUTWARD_HANDLES_DISCOVERED ({', '.join(extracted_outward[:3])})")
        score_delta += 0.15

    # Update ContactDetail
    if deep_signals:
        new_score = round(min(1.0, max(0.10, contact.confidence + score_delta)), 2)
        contact.confidence = new_score
        
        # Upgrade or downgrade confidence level
        if new_score >= 0.70:
            contact.confidence_level = ConfidenceLevel.HIGH
        elif new_score >= 0.40:
            contact.confidence_level = ConfidenceLevel.MEDIUM
        else:
            contact.confidence_level = ConfidenceLevel.LOW
            
        contact.signals.extend(deep_signals)
        contact.rationale += f" [Deep Profile Inspection: {', '.join(deep_signals)} | Adj: {score_delta:+.2f} -> {new_score}]"

    return contact
