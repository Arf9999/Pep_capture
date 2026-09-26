"""
LLM Candidate Evaluator for PEP Social Accounts
Disciplined OSINT evaluation considering granular multi-tier geography (town/suburb vs broad country),
moderate baseline name weights, political party alignment, civic/councillor role corroboration,
and disqualifying party organization or conflicting political accounts.
"""

import re
from typing import Dict, Any, Optional, List, Tuple
from models import ContactDetail, ConfidenceLevel
from query_builder import SA_DISTRICT_CLUSTERS, get_district_keywords


# Major South African Political Parties & Abbreviations
MAJOR_SA_PARTIES = {
    "anc": ["african national congress", "anc"],
    "da": ["democratic alliance", "da"],
    "eff": ["economic freedom fighters", "eff"],
    "actionsa": ["actionsa", "action sa"],
    "ifp": ["inkatha freedom party", "ifp"],
    "vf plus": ["freedom front plus", "vryheidsfront plus", "vf plus", "vf+", "ff plus"],
    "pa": ["patriotic alliance", "pa"],
    "acdp": ["african christian democratic party", "acdp"],
    "atm": ["african transformation movement", "atm"],
    "udm": ["united democratic movement", "udm"],
    "good": ["good party", "good"],
    "pac": ["pan africanist congress", "pac"],
    "al jama-ah": ["al jama-ah", "al-jama'ah"],
    "mk": ["umkhonto wesizwe", "mk party", "m.k. party"],
    "ucdp": ["united christian democratic party", "ucdp"],
    "cope": ["congress of the people", "cope"],
    "pfp": ["people's freedom party", "peoples freedom party", "pfp"],
}

# Granular South African Geography Taxonomy: Local Towns vs Municipalities vs Provinces
SA_GEOGRAPHY_TAXONOMY = {
    "ugu": {
        "towns": ["port shepstone", "margate", "hibiscus coast", "umdoni", "scottburgh", "umzumbe", "umuziwabantu", "harding", "ramsgate", "southbroom", "shelly beach", "uvongo"],
        "municipality": ["ugu", "ray nkonyeni", "umdoni municipality"],
        "province": ["kwazulu-natal", "kzn"]
    },
    "matlosana": {
        "towns": ["klerksdorp", "jouberton", "kanana", "stilfontein", "orkney", "tigane", "hartbeesfontein"],
        "municipality": ["matlosana", "city of matlosana", "dr kenneth kaunda"],
        "province": ["north west", "nw"]
    },
    "maquassi hills": {
        "towns": ["wolmaransstad", "tswelelang", "leeudoringstad", "kgakala", "makwassie", "witpoort"],
        "municipality": ["maquassi hills", "dr kenneth kaunda"],
        "province": ["north west", "nw"]
    },
    "jb marks": {
        "towns": ["potchefstroom", "ventersdorp", "ikageng", "promosa"],
        "municipality": ["jb marks", "j.b. marks", "dr kenneth kaunda"],
        "province": ["north west", "nw"]
    },
    "buffalo city": {
        "towns": ["east london", "mdantsane", "king william's town", "king williams town", "qonce", "bhisho", "gonubie", "berlin", "dimbaza"],
        "municipality": ["buffalo city", "buf"],
        "province": ["eastern cape", "ec"]
    },
    "johannesburg": {
        "towns": ["soweto", "sandton", "randburg", "roodepoort", "midrand", "alexandra", "diepsloot", "lenasia", "orange farm", "ennerdale"],
        "municipality": ["city of johannesburg", "johannesburg", "jhb", "joburg"],
        "province": ["gauteng"]
    },
    "ekurhuleni": {
        "towns": ["benoni", "boksburg", "germiston", "kempton park", "springs", "brakpan", "alberton", "edenvale", "nigel"],
        "municipality": ["ekurhuleni", "east rand"],
        "province": ["gauteng"]
    },
    "tshwane": {
        "towns": ["pretoria", "centurion", "mamelodi", "soshanguve", "atteridgeville", "hammanskraal", "garankuwa"],
        "municipality": ["tshwane", "city of tshwane"],
        "province": ["gauteng"]
    },
    "ethekwini": {
        "towns": ["durban", "umhlanga", "chatsworth", "phoenix", "pinetown", "kwa mashu", "umlazi", "westville", "amanzimtoti", "hillcrest"],
        "municipality": ["ethekwini"],
        "province": ["kwazulu-natal", "kzn"]
    },
    "cape town": {
        "towns": ["bellville", "khayelitsha", "mitchells plain", "somerset west", "parow", "gugulethu", "athlone", "wynberg"],
        "municipality": ["city of cape town", "cape town", "cpt"],
        "province": ["western cape", "wc"]
    }
}

PARTY_ORGANIZATION_KEYWORDS = [
    "official page of", "da official", "anc official", "eff official", "party account",
    "regional office", "branch page", "headquarters", "media team", "parliamentary caucus",
    "national office", "provincial office"
]

HIGH_CONFIDENCE_CIVIC_KEYWORDS = [
    "councillor", "ward councillor", "pr councillor", "candidate", "mayoral candidate",
    "ward candidate", "local government election", "lge", "proportional representation",
    "iec", "municipal council", "political party",
    # Multilingual & Visual Campaign Terms
    "election", "elections", "election poster", "campaign poster", "vote for", "ballot",
    "ukhetho", "zokhetho", "amavoti", "vota",           # isiZulu / isiXhosa
    "verkiesing", "stem vir", "kandidaat",              # Afrikaans
    "dikgetho", "kgetho"                                # Sesotho / Setswana / Sepedi
]

GENERAL_CIVIC_KEYWORDS = [
    "community leader", "activist", "local municipality", "civic", "parliament", "constituency", "governance"
]


FOREIGN_LOCATIONS = [
    "united kingdom", "uk", "london", "manchester", "birmingham",
    "united states", "usa", "new york", "california", "texas", "florida", "chicago",
    "canada", "toronto", "vancouver", "australia", "sydney", "melbourne",
    "nigeria", "lagos", "abuja", "kenya", "nairobi", "ghana", "accra", "zimbabwe", "harare",
    "india", "delhi", "mumbai", "new zealand", "auckland", "germany", "berlin",
    "france", "paris", "netherlands", "amsterdam", "ireland", "dublin"
]

SOUTH_AFRICA_ANCHORS = [
    "south africa", "south african", "rsa", "za", "s.a.", ".co.za", "+27",
    "gauteng", "kwazulu-natal", "kzn", "western cape", "eastern cape", "north west",
    "free state", "mpumalanga", "limpopo", "northern cape",
    "johannesburg", "pretoria", "cape town", "durban", "bloemfontein", "gqeberha",
    "port elizabeth", "east london", "polokwane", "nelspruit", "mbombela", "rustenburg",
    "klerksdorp", "potchefstroom", "port shepstone", "margate"
]


def match_geographic_granularity(target_district_raw: str, text: str) -> Tuple[float, List[str]]:
    """
    Evaluates geographic signals with strict granularity:
    - Specific Local Town / Suburb: +0.30
    - District Municipality / Metro: +0.20
    - Province: +0.05
    - South Africa Baseline: neutral (0.00)
    - PENALTY: Not matching South Africa at all: -0.25
    - STRONG PENALTY: Explicit foreign country or foreign city detected: -0.50
    """
    text_lower = text.lower()
    score = 0.0
    signals = []

    # 1. Foreign Location Detection (Strong Disqualifier)
    matched_foreign = [f for f in FOREIGN_LOCATIONS if re.search(r'\b' + re.escape(f) + r'\b', text_lower)]
    if matched_foreign:
        score -= 0.50
        signals.append(f"FOREIGN_LOCATION_PENALTY ({matched_foreign[0].title()})")
        return score, signals

    # 2. Target District & Local Granularity
    cleaned_target = re.sub(r"^[A-Z]{2,3}\d+\s*-\s*", "", target_district_raw).strip().lower() if target_district_raw else ""
    matched_entry = None
    for key, data in SA_GEOGRAPHY_TAXONOMY.items():
        if key in cleaned_target:
            matched_entry = data
            break

    has_local_geo = False
    if matched_entry:
        # Tier 1: Local Town / Suburb
        matched_towns = [t for t in matched_entry["towns"] if re.search(r'\b' + re.escape(t) + r'\b', text_lower)]
        if matched_towns:
            score += 0.30
            signals.append(f"LOCAL_TOWN_MATCH ({matched_towns[0].title()})")
            has_local_geo = True
        else:
            # Tier 2: Specific Municipality
            matched_munis = [m for m in matched_entry["municipality"] if re.search(r'\b' + re.escape(m) + r'\b', text_lower)]
            if matched_munis:
                score += 0.20
                signals.append(f"MUNICIPALITY_MATCH ({matched_munis[0].title()})")
                has_local_geo = True
            else:
                # Tier 3: Province
                matched_provs = [p for p in matched_entry["province"] if re.search(r'\b' + re.escape(p) + r'\b', text_lower)]
                if matched_provs:
                    score += 0.05
                    signals.append(f"PROVINCE_MATCH ({matched_provs[0].upper()})")
                    has_local_geo = True

    # 3. Check for South African Anchor
    has_sa_anchor = has_local_geo or any(re.search(r'\b' + re.escape(a) + r'\b', text_lower) for a in SOUTH_AFRICA_ANCHORS)

    # CRITICAL RULE: *Not* matching South Africa receives negative scoring
    if not has_sa_anchor:
        score -= 0.25
        signals.append("NO_SOUTH_AFRICA_MATCH_PENALTY (-0.25)")
    elif not has_local_geo:
        signals.append("BROAD_COUNTRY_ONLY (South Africa)")

    return score, signals


def evaluate_candidate_snippet(
    pep_info: Dict[str, str],
    platform: str,
    search_result: Dict[str, str]
) -> Optional[ContactDetail]:
    """
    Disciplined evaluation of a search result snippet against target candidate:
    - Conservative Name Weighting (0.18 base for first+last; 0.30 for 3-name exact)
    - Granular Geography (Town +0.30, Muni +0.20, Province +0.05, Country +0.01)
    - Political Party Alignment (+0.30)
    - Civic / Councillor Role Corroboration (+0.25)
    - Penalties for Conflicting Parties (-0.50) & Official Org Accounts (-0.50)
    """
    target_name = pep_info.get("full_name", "")
    target_party = pep_info.get("party_name", "")
    target_location = pep_info.get("b ", "")
    title = search_result.get("title", "")
    snippet = search_result.get("snippet", "")
    url = search_result.get("url", "")

    title_lower = title.lower()
    snippet_lower = snippet.lower()
    combined_snippet_text = f"{title_lower} {snippet_lower}"

    # Disqualify Directory, Aggregator, and Post URLs
    url_lower = url.lower()
    disqualified_url_patterns = [
        "/public/",              # Facebook directory
        "/pub/dir/",             # LinkedIn directory
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
        "instagram.com/p/",      # Single Instagram photo post
    ]
    if any(pat in url_lower for pat in disqualified_url_patterns):
        return None

    # People's Assembly (pa.org.za) and Link-in-Bio hubs (Linktree, Beacons, Carrd, Taplink, Lnk.Bio, Bio.site, Pallyy)
    # are intermediate discovery sources used solely to extract outward social handles and emails.
    # They are NEVER stored as social accounts themselves, nor scored as target accounts.
    discovery_hub_domains = [
        "pa.org.za", "linktr.ee", "beacons.ai", "carrd.co", "taplink.cc",
        "lnk.bio", "bio.site", "biosites.com", "pallyy.com"
    ]
    if any(hub in url_lower for hub in discovery_hub_domains) or platform in (
        "peoples_assembly", "linktree", "beacons", "carrd", "taplink", "lnk.bio", "biosite", "pallyy"
    ):
        return None

    signals = []
    score = 0.0

    # 1. Conservative Name Matching (Weight: 0.10 - 0.30)
    # Rationale: In South Africa, First + Last name overlap is common and alone proves little.
    first_name = pep_info.get("first_name", "").strip().lower()
    middle_name = pep_info.get("middle_name", "").strip().lower()
    last_name = pep_info.get("last_name", "").strip().lower()

    # Fallback to parsing canonical target_name if individual fields are empty
    if (not first_name or not last_name) and target_name:
        raw_parts = [p.strip().lower() for p in re.split(r'[\s,]+', target_name) if p.strip()]
        if len(raw_parts) >= 2:
            if not first_name:
                first_name = raw_parts[0]
            if not last_name:
                last_name = raw_parts[-1]
            if not middle_name and len(raw_parts) > 2:
                middle_name = " ".join(raw_parts[1:-1])

    target_tokens = set(re.findall(r'\w+', target_name.lower()))
    title_tokens = set(re.findall(r'\w+', title_lower))

    middle_tokens = [m for m in re.split(r'[\s\-]+', middle_name) if m and len(m) > 1]

    # Check 1: Full 3-Name Match (First + Middle + Last) -> Highly Distinctive
    if first_name and last_name and any(m in title_tokens for m in middle_tokens) and first_name in title_tokens and last_name in title_tokens:
        score += 0.30
        matched_m = [m for m in middle_tokens if m in title_tokens][0]
        signals.append(f"FULL_3NAME_MATCH ({first_name} {matched_m} {last_name})")
    # Check 2: First + Last Name match (Common in population)
    elif first_name and last_name and first_name in title_tokens and last_name in title_tokens:
        score += 0.18
        signals.append("FIRST_LAST_NAME_MATCH")
    # Check 3: Middle + Last Name match
    elif any(m in title_tokens for m in middle_tokens) and last_name and last_name in title_tokens:
        matched_m = [m for m in middle_tokens if m in title_tokens][0]
        score += 0.15
        signals.append(f"MIDDLE_LAST_NAME_MATCH ({matched_m} {last_name})")
    # Check 4: First + Middle Name match
    elif first_name and any(m in title_tokens for m in middle_tokens):
        matched_m = [m for m in middle_tokens if m in title_tokens][0]
        score += 0.08
        signals.append(f"FIRST_MIDDLE_NAME_MATCH ({first_name} {matched_m})")
    # Check 5: General Token Overlap
    elif target_tokens:
        overlap = len(target_tokens.intersection(title_tokens)) / len(target_tokens)
        if overlap >= 0.5:
            score += 0.08
            signals.append(f"PARTIAL_NAME_OVERLAP ({round(overlap, 2)})")

    # If no name match at all, discard immediately
    if score == 0.0:
        return None

    # 2. Granular Geographic Alignment (Weight: 0.00 - 0.30)
    geo_score, geo_signals = match_geographic_granularity(target_location, combined_snippet_text)
    score += geo_score
    signals.extend(geo_signals)

    # 3. Political Party Alignment (Weight: +0.30 or -0.50 penalty)
    if target_party:
        target_party_lower = target_party.lower()
        party_aliases = [target_party_lower]
        for p_key, aliases in MAJOR_SA_PARTIES.items():
            if p_key in target_party_lower or target_party_lower in p_key:
                party_aliases.extend(aliases)
                break

        # Check if candidate's registered party appears in snippet
        matched_party = [alias for alias in set(party_aliases) if re.search(r'\b' + re.escape(alias) + r'\b', combined_snippet_text)]
        if matched_party:
            score += 0.30
            signals.append(f"PARTY_AFFILIATION_MATCH ({matched_party[0].upper()})")
        else:
            # Check for conflicting opposition political party claim
            for other_party, other_aliases in MAJOR_SA_PARTIES.items():
                if other_party not in target_party_lower and not any(a in target_party_lower for a in other_aliases):
                    if any(re.search(r'\b(?:councillor|candidate|member|chairperson)\s+(?:of|for)?\s*' + re.escape(oa) + r'\b', combined_snippet_text) for oa in other_aliases):
                        score -= 0.50
                        signals.append(f"CONFLICTING_PARTY_DETECTED ({other_party.upper()})")
                        break

    # 4. Civic / Candidate / Councillor Role Corroboration (Weight: 0.10 - 0.25)
    matched_high_civic = [kw for kw in HIGH_CONFIDENCE_CIVIC_KEYWORDS if re.search(r'\b' + re.escape(kw) + r'\b', combined_snippet_text)]
    if matched_high_civic:
        score += 0.25
        signals.append(f"CIVIC_ROLE_MATCH ({matched_high_civic[0]})")
    else:
        matched_gen_civic = [kw for kw in GENERAL_CIVIC_KEYWORDS if re.search(r'\b' + re.escape(kw) + r'\b', combined_snippet_text)]
        if matched_gen_civic:
            score += 0.10
            signals.append(f"CIVIC_CONTEXT_MATCH ({matched_gen_civic[0]})")

    # 5. Direct Profile URL Check
    is_direct_profile = (
        ("linkedin.com/in/" in url_lower) or
        ("x.com/" in url_lower and not any(x in url_lower for x in ["/i/", "/intent", "/home", "/explore"])) or
        ("facebook.com/" in url_lower) or
        ("instagram.com/" in url_lower) or
        ("tiktok.com/@" in url_lower) or
        ("youtube.com/@" in url_lower or "youtube.com/channel/" in url_lower)
    )
    if is_direct_profile:
        score += 0.05
        signals.append("DIRECT_PROFILE_URL")

    # 6. Candidate Personal Bio Hub Corroboration (Assisting Confidence: +0.25)
    # Linktree, Beacons, Carrd, Taplink, and Lnk.Bio are NOT targets themselves.
    # But if this social handle was discovered on or linked from the candidate's bio hub,
    # it assists to provide confidence in this outward social profile.
    hub_corroborated_urls = pep_info.get("hub_corroborated_urls", set())
    hub_handles = pep_info.get("hub_handles", set())
    if (url_lower in hub_corroborated_urls) or any(h in url_lower for h in hub_handles if len(h) >= 3):
        score += 0.25
        signals.append("BIO_HUB_CORROBORATION")

    # 8. Disqualify Official Party Organizational Accounts
    is_party_account = any(kw in combined_snippet_text for kw in PARTY_ORGANIZATION_KEYWORDS)
    if is_party_account:
        score -= 0.50
        signals.append("PARTY_ORGANIZATION_PENALTY")

    final_score = round(min(1.0, max(0.0, score)), 2)

    # Discard non-viable candidates below 0.20
    if final_score < 0.20:
        return None

    # Strict 4-Tier Granular Confidence Allocation:
    # PROBABLE:  > 0.70 (Multi-factor: Name + Granular Town/Muni + Party/Civic role)
    # POTENTIAL: 0.55 - 0.70 (Strong correlation: Name + specific local town/suburb)
    # POSSIBLE:  0.40 - 0.54 (Moderate correlation: Name + municipality or civic context)
    # UNLIKELY:  < 0.40 (Tentative match: Name + broad country anchor without local confirmation)
    if final_score > 0.70:
        level = ConfidenceLevel.PROBABLE
    elif final_score >= 0.55:
        level = ConfidenceLevel.POTENTIAL
    elif final_score >= 0.40:
        level = ConfidenceLevel.POSSIBLE
    else:
        level = ConfidenceLevel.UNLIKELY

    rationale = (
        f"Target: '{target_name}' in '{target_location}' ({target_party}). "
        f"Match score: {final_score} ({level.value}). Title: '{title}'. "
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

