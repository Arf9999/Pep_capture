"""
Query Builder & Multi-Permutation Generator for PEP Social Search
Generates exhaustive name variations and platform-specific site search queries.
"""

import re
from typing import List, Dict, Any

PLATFORM_DORKS = {
    "facebook": "site:facebook.com",
    "linkedin": "site:linkedin.com/in",
    "twitter": "site:x.com",
    "instagram": "site:instagram.com",
    "tiktok": "site:tiktok.com",
    "telegram": "site:t.me",
    "youtube": "site:youtube.com"
}


def generate_comprehensive_name_permutations(
    first_name: str,
    middle_name: str,
    last_name: str,
    full_name_raw: str = ""
) -> List[str]:
    """
    Generates exhaustive name variations:
    - First Last (e.g. Wilko Kunz)
    - Last First (e.g. Kunz Wilko)
    - Middle Last (e.g. Reimar Kunz, Justice Shusha)
    - Last Middle (e.g. Kunz Reimar, Shusha Justice)
    - First Middle (e.g. Wilko Reimar, Mlungisi Justice)
    - Full: First Middle Last (e.g. Wilko Reimar Kunz)
    - Reverse Full: Last First Middle (e.g. Kunz Wilko Reimar)
    """
    def clean(n: str) -> str:
        s = re.sub(r'(?i)\bpage\s+\d+\s+of\s+\d+\b', '', n or '').strip()
        return s.title()

    first = clean(first_name)
    middle = clean(middle_name)
    last = clean(last_name)

    if not first and not last and full_name_raw:
        cleaned_full = re.sub(r'(?i)\bpage\s+\d+\s+of\s+\d+\b', '', full_name_raw).strip()
        parts = [p.title() for p in re.split(r'[\s\-]+', cleaned_full) if p]
        if parts:
            first = parts[0]
            last = parts[-1]
            middle = " ".join(parts[1:-1])

    middle_tokens = [m for m in re.split(r'[\s\-]+', middle) if m and len(m) > 1]
    
    permutations = []

    def add_perm(p: str):
        if p and p not in permutations:
            permutations.append(p)

    # 1. Standard First + Last and Last + First
    if first and last:
        add_perm(f'"{first} {last}"')          # First Last
        add_perm(f'"{last} {first}"')          # Last First

    # 2. Middle Name Variations (Very common in South Africa)
    for m in middle_tokens:
        if last:
            add_perm(f'"{m} {last}"')          # Middle Last (e.g. Reimar Kunz, Dale Palmer)
            add_perm(f'"{last} {m}"')          # Last Middle (e.g. Kunz Reimar, Palmer Dale)
        if first:
            add_perm(f'"{first} {m}"')         # First Middle (common when omitting surname on FB)
            add_perm(f'"{m} {first}"')         # Middle First

    # 3. Three-Name Variations (Full and Inverted)
    for m in middle_tokens:
        if first and last:
            add_perm(f'"{first} {m} {last}"')  # First Middle Last
            add_perm(f'"{last} {first} {m}"')  # Last First Middle

    # Fallbacks if single name
    if not permutations:
        if first and last:
            add_perm(f'"{first} {last}"')
        elif first:
            add_perm(f'"{first}"')
        elif last:
            add_perm(f'"{last}"')

    return permutations


# District & Region Cluster Mapping for South African Municipalities
SA_DISTRICT_CLUSTERS = {
    "ugu": ["ugu", "port shepstone", "margate", "hibiscus coast", "umdoni", "scottburgh", "umzumbe", "umuziwabantu", "harding", "kwazulu-natal", "kzn"],
    "matlosana": ["matlosana", "matlosane", "klerksdorp", "jouberton", "kanana", "stilfontein", "dr kenneth kaunda", "north west"],
    "ethekwini": ["ethekwini", "durban", "umhlanga", "chatsworth", "phoenix", "pinetown", "kwazulu-natal", "kzn"],
    "johannesburg": ["johannesburg", "jhb", "soweto", "sandton", "randburg", "roodepoort", "midrand", "gauteng"],
    "ekurhuleni": ["ekurhuleni", "east rand", "benoni", "boksburg", "germiston", "kempton park", "springs", "brakpan", "gauteng"],
    "tshwane": ["tshwane", "pretoria", "centurion", "mamelodi", "soshanguve", "gauteng"],
    "cape town": ["cape town", "cpt", "bellville", "khayelitsha", "mitchells plain", "western cape"],
    "mangaung": ["mangaung", "bloemfontein", "botshabelo", "thaba nchu", "free state"],
    "nelson mandela": ["nelson mandela bay", "gqeberha", "port elizabeth", "pe", "uitenhage", "kariega", "eastern cape"],
    "buffalo city": ["buffalo city", "east london", "mdantsane", "king william's town", "qonce", "eastern cape"],
    "bojanala": ["bojanala", "rustenburg", "brits", "madibeng", "north west"],
    "umgungundlovu": ["umgungundlovu", "pietermaritzburg", "msunduzi", "howick", "kwazulu-natal", "kzn"],
    "king cetshwayo": ["king cetshwayo", "richards bay", "empangeni", "kwazulu-natal"],
    "ehlanzeni": ["ehlanzeni", "mbombela", "nelspruit", "white river", "mpumalanga"],
    "capricorn": ["capricorn", "polokwane", "pietersburg", "limpopo"],
    "sedibeng": ["sedibeng", "vereeniging", "vanderbijlpark", "gauteng"],
    "west rand": ["west rand", "krugersdorp", "mogale city", "randfontein", "gauteng"],
}


def get_district_keywords(district_raw: str) -> List[str]:
    """Returns relevant geographic keywords for a district."""
    if not district_raw:
        return ["south africa"]
    
    cleaned = re.sub(r"^[A-Z]{2,3}\d+\s*-\s*", "", district_raw).strip().lower()
    keywords = ["south africa"]
    
    if cleaned:
        keywords.append(cleaned)
        for key, aliases in SA_DISTRICT_CLUSTERS.items():
            if key in cleaned:
                keywords.extend(aliases)
                break
                
    return list(dict.fromkeys(keywords))


def generate_consolidated_candidate_queries(row: Dict[str, str], max_queries: int = 1) -> List[str]:
    """
    Generates high-yield consolidated search query grouping top name order
    permutations into an OR group combined with social media platform dorks.
    Serper is configured with gl='za', naturally prioritizing South African results
    without suffocating profile hits.
    """
    name_perms = generate_comprehensive_name_permutations(
        first_name=row.get("first_name", ""),
        middle_name=row.get("middle_name", ""),
        last_name=row.get("last_name", ""),
        full_name_raw=row.get("full_name", "")
    )

    if not name_perms:
        return []

# Core Social & Link-in-Bio Platforms
CORE_SOCIAL_PLATFORMS = [
    "facebook.com/p/",
    "facebook.com/people/",
    "facebook.com/profile.php",
    "facebook.com",
    "linkedin.com/in",
    "x.com",
    "instagram.com",
    "tiktok.com",
    "youtube.com"
]

LINK_IN_BIO_PLATFORMS = [
    "linktr.ee", "beacons.ai", "carrd.co", "taplink.cc", "lnk.bio", "bio.site", "pallyy.com"
]

ALL_TARGET_PLATFORMS = CORE_SOCIAL_PLATFORMS + LINK_IN_BIO_PLATFORMS



def generate_consolidated_candidate_queries(row: Dict[str, str], max_queries: int = 1) -> List[str]:
    """
    Generates high-yield consolidated search query grouping top name order
    permutations into an OR group combined with social media platform dorks,
    creator link-in-bio hubs (Linktree, Beacons, Carrd, Taplink, Lnk.Bio, Bio.site, Pallyy),
    and civic monitoring records (pa.org.za).
    """
    name_perms = generate_comprehensive_name_permutations(
        first_name=row.get("first_name", ""),
        middle_name=row.get("middle_name", ""),
        last_name=row.get("last_name", ""),
        full_name_raw=row.get("full_name", "")
    )

    if not name_perms:
        return []

    # Prioritize top 4 permutations:
    selected_perms = name_perms[:4]
    names_or_group = f"({' OR '.join(selected_perms)})"

    # All platforms combined dork
    combined_dork = " OR ".join(f"site:{p}" for p in ALL_TARGET_PLATFORMS)
    query_primary = f"{names_or_group} ({combined_dork})"

    if max_queries <= 1:
        return [query_primary]

    # Query 2: Focused creator & link-in-bio landing hub dork
    bio_dork = " OR ".join(f"site:{p}" for p in LINK_IN_BIO_PLATFORMS)
    query_bio_hubs = f"{names_or_group} ({bio_dork})"

    return [query_primary, query_bio_hubs]


def generate_email_social_query(email: str) -> str:
    """
    Generates a targeted secondary search query across all social platforms
    and link-in-bio hubs using an extracted candidate email address.
    e.g. '"councillor@example.com" (site:facebook.com OR site:linkedin.com/in ...)'
    """
    clean_email = email.strip().lower()
    social_and_bio = CORE_SOCIAL_PLATFORMS + LINK_IN_BIO_PLATFORMS
    combined_dork = " OR ".join(f"site:{p}" for p in social_and_bio)
    return f'"{clean_email}" ({combined_dork})'


def infer_platform_from_url(url: str) -> str:
    """Infers social platform, civic site, or link-in-bio hub type from candidate URL."""
    u = url.lower()
    if "pa.org.za" in u:
        return "peoples_assembly"
    if "linktr.ee" in u:
        return "linktree"
    if "beacons.ai" in u:
        return "beacons"
    if "carrd.co" in u:
        return "carrd"
    if "taplink.cc" in u:
        return "taplink"
    if "lnk.bio" in u:
        return "lnk.bio"
    if "bio.site" in u or "biosites.com" in u:
        return "biosite"
    if "pallyy.com" in u:
        return "pallyy"
    if "facebook.com" in u:
        return "facebook"
    if "linkedin.com" in u:
        return "linkedin"
    if "x.com" in u or "twitter.com" in u:
        return "twitter"
    if "instagram.com" in u:
        return "instagram"
    if "tiktok.com" in u:
        return "tiktok"
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    if "t.me" in u:
        return "telegram"
    return "social_web"

