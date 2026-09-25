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
import urllib.parse
from typing import Dict, Any, Optional, List, Tuple
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


def decode_cloudflare_email(cfemail_hex: str) -> str:
    """Decodes Cloudflare email protection obfuscated hex string."""
    try:
        k = int(cfemail_hex[:2], 16)
        return "".join(chr(int(cfemail_hex[i:i+2], 16) ^ k) for i in range(2, len(cfemail_hex), 2))
    except Exception:
        return ""


EMAIL_REGEX = re.compile(r'\b[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+\b')
IGNORED_EMAIL_DOMAINS = {"example.com", "domain.com", "sentry.io", "wixpress.com"}
IGNORED_EMAIL_PREFIXES = (
    "privacy@", "support@", "help@", "info@pa.org.za", "info@peoplesassembly.org.za",
    "contact@pa.org.za", "feedback@", "press@", "media@", "security@", "abuse@",
    "webmaster@", "noreply@", "no-reply@", "donotreply@", "postmaster@", "mailer-daemon@",
    "info@pmg.org.za"
)
IGNORED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif", ".css", ".js")


def extract_emails_from_text(raw_text: str) -> List[str]:
    """
    Extracts, decodes, and validates candidate email addresses from raw text/HTML.
    Handles:
    - Standard plain text & mailto: links
    - Cloudflare protected emails (data-cfemail and /cdn-cgi/l/email-protection#)
    - Filters out static asset pseudo-emails and generic platform admin addresses
    """
    candidates = set()

    # 1. Cloudflare data-cfemail extraction
    for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', raw_text):
        dec = decode_cloudflare_email(cf)
        if dec:
            candidates.add(dec.strip().lower())

    # 2. Cloudflare href email-protection extraction
    for cf in re.findall(r'/email-protection#([a-fA-F0-9]+)', raw_text):
        dec = decode_cloudflare_email(cf)
        if dec:
            candidates.add(dec.strip().lower())

    # 3. mailto: links
    for m in re.findall(r'mailto:([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', raw_text, re.IGNORECASE):
        candidates.add(m.strip().lower())

    # 4. Standard email regex
    for e in EMAIL_REGEX.findall(raw_text):
        candidates.add(e.strip().lower())

    clean_emails = []
    for em in candidates:
        em = em.rstrip(".")
        if any(em.endswith(ext) for ext in IGNORED_EXTENSIONS):
            continue
        if any(em.startswith(pref) for pref in IGNORED_EMAIL_PREFIXES):
            continue
        domain = em.split("@")[-1]
        if domain in IGNORED_EMAIL_DOMAINS:
            continue
        if "." not in domain or len(domain.split(".")[-1]) < 2:
            continue
        clean_emails.append(em)

    return sorted(list(set(clean_emails)))


def fetch_peoples_assembly_emails(candidate_name: str, timeout: float = 6.0) -> List[str]:
    """
    Looks up a candidate on People's Assembly (pa.org.za) solely to discover verified
    email addresses (e.g. parliamentary or official party contacts).
    NOTE: A People's Assembly page is strictly an intelligence source for email extraction;
    it is NOT stored as a social account and does not boost social account confidence.
    """
    if not candidate_name or len(candidate_name.strip()) < 4:
        return []

    try:
        encoded = urllib.parse.quote_plus(candidate_name.strip())
        search_url = f"https://www.pa.org.za/search/?q={encoded}&section=persons"
        with httpx.Client(headers=DEFAULT_HEADERS, follow_redirects=True, timeout=timeout) as client:
            resp = client.get(search_url)
            if resp.status_code != 200:
                return []

            # Extract person profile links
            person_links = re.findall(r'href=["\'](/person/[^"\']+)["\']', resp.text)
            unique_links = list(dict.fromkeys(person_links))

            all_emails = []
            for pl in unique_links[:2]:
                full_url = f"https://www.pa.org.za{pl}"
                pr = client.get(full_url)
                if pr.status_code == 200:
                    emails = extract_emails_from_text(pr.text)
                    all_emails.extend(emails)

            return sorted(list(set(all_emails)))
    except Exception:
        return []


def fetch_profile_metadata(url: str, timeout: float = 7.0) -> Dict[str, Any]:
    """Fetches public profile HTML and extracts title, meta descriptions, clean body text, and emails."""
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

            emails = extract_emails_from_text(text)
            
            return {
                "status": resp.status_code,
                "title": title,
                "og_description": og_desc or meta_desc,
                "body_sample": body_clean[:2500],
                "full_html_sample": text[:3500],
                "emails": emails
            }
    except Exception as e:
        return {"status": 0, "error": str(e), "title": "", "og_description": "", "body_sample": "", "full_html_sample": "", "emails": []}


DISCOVERY_HUB_DOMAINS = (
    "linktr.ee", "beacons.ai", "carrd.co", "taplink.cc",
    "lnk.bio", "bio.site", "biosites.com", "pallyy.com", "pa.org.za"
)

OUTWARD_SOCIAL_PATTERNS = {
    "whatsapp": r'(?:wa\.me/|whatsapp\.com/send\?phone=)(\+?\d+)',
    "instagram": r'https?://(?:www\.)?instagram\.com/([a-zA-Z0-9_\.]{3,30})/?',
    "twitter": r'https?://(?:www\.)?(?:twitter\.com|x\.com)/([a-zA-Z0-9_]{3,20})/?',
    "facebook": r'https?://(?:www\.)?facebook\.com/([a-zA-Z0-9\._\-]{3,50})/?',
    "linkedin": r'https?://(?:www\.)?linkedin\.com/in/([a-zA-Z0-9_\-]{3,50})/?',
    "youtube": r'https?://(?:www\.)?youtube\.com/(?:@|channel/|c/)?([a-zA-Z0-9_\-]{3,40})/?',
    "tiktok": r'https?://(?:www\.)?tiktok\.com/@([a-zA-Z0-9_\.]{3,30})/?'
}


def is_discovery_hub_url(url: str) -> bool:
    """Checks if a URL belongs to an intermediate discovery hub (Linktree, Carrd, Taplink, etc.) or People's Assembly."""
    u = url.lower()
    return any(hub in u for hub in DISCOVERY_HUB_DOMAINS)


def inspect_discovery_hub_and_extract(url: str) -> Dict[str, Any]:
    """
    Inspects a link-in-bio hub or civic page (Linktree, Beacons, Carrd, Taplink, Lnk.Bio, Bio.site, Pallyy, pa.org.za).
    Extracts outward social profile links and candidate emails.
    NOTE: The hub URL itself is NEVER stored as a social account result.
    """
    meta = fetch_profile_metadata(url)
    raw_html = meta.get("full_html_sample", "") + " " + meta.get("body_sample", "")
    emails = meta.get("emails", [])

    social_links = []
    seen_urls = set()
    for plat_name, pat in OUTWARD_SOCIAL_PATTERNS.items():
        for match in re.finditer(pat, raw_html, re.IGNORECASE):
            full_match = match.group(0).rstrip("/")
            identifier = match.group(1).lower()
            if identifier in ("share", "sharer", "intent", "login", "signup", "terms", "privacy", "about", "home", "explore"):
                continue
            if full_match.lower() not in seen_urls:
                seen_urls.add(full_match.lower())
                social_links.append({
                    "platform": plat_name,
                    "url": full_match,
                    "handle": identifier
                })

    return {
        "emails": emails,
        "social_links": social_links,
        "source_hub_url": url
    }



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

    # 6. Extract Candidate Emails from Profile / Link-in-Bio Landing Page
    page_emails = meta.get("emails", [])
    if page_emails:
        deep_signals.append(f"PAGE_EMAIL_DISCOVERED ({', '.join(page_emails[:2])})")
        setattr(contact, "discovered_emails", page_emails)
        if not contact.note:
            contact.note = f"Email: {page_emails[0]}"

    # Update ContactDetail
    if deep_signals:
        new_score = round(min(1.0, max(0.10, contact.confidence + score_delta)), 2)
        contact.confidence = new_score
        
        # Upgrade or downgrade confidence level
        if new_score > 0.70:
            contact.confidence_level = ConfidenceLevel.PROBABLE
        elif new_score >= 0.55:
            contact.confidence_level = ConfidenceLevel.POTENTIAL
        elif new_score >= 0.40:
            contact.confidence_level = ConfidenceLevel.POSSIBLE
        else:
            contact.confidence_level = ConfidenceLevel.UNLIKELY
            
        contact.signals.extend(deep_signals)
        contact.rationale += f" [Deep Profile Inspection: {', '.join(deep_signals)} | Adj: {score_delta:+.2f} -> {new_score}]"

    return contact
