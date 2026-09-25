"""
Confidence Scoring and Candidate Matching Engine for Social Profiles
"""

import re
from typing import Dict, Any, List, Tuple
from models import ConfidenceLevel, ContactDetail


def calculate_name_similarity(name1: str, name2: str) -> float:
    """
    Computes normalized similarity between two names using token overlap and string normalization.
    """
    clean1 = set(re.findall(r'\w+', name1.lower()))
    clean2 = set(re.findall(r'\w+', name2.lower()))
    
    if not clean1 or not clean2:
        return 0.0
    
    intersection = clean1.intersection(clean2)
    union = clean1.union(clean2)
    
    jaccard = len(intersection) / len(union)
    
    # Check exact substring match bonus
    if " ".join(clean1) in " ".join(clean2) or " ".join(clean2) in " ".join(clean1):
        jaccard = max(jaccard, 0.85)
        
    return round(jaccard, 3)


def evaluate_social_candidate(
    person_name: str,
    target_role: str,
    platform: str,
    candidate_url: str,
    profile_data: Dict[str, Any]
) -> ContactDetail:
    """
    Evaluates a candidate profile against target person metadata and computes a confidence score.
    """
    signals = []
    score = 0.0
    
    # 1. Official domain link cross-reference (Weight: 0.40)
    if profile_data.get("linked_from_official_site"):
        score += 0.40
        signals.append("OFFICIAL_DOMAIN_CROSS_REF")
        
    # 2. Platform verification badge (Weight: 0.20)
    if profile_data.get("is_verified"):
        score += 0.20
        signals.append("PLATFORM_VERIFIED_BADGE")
        
    # 3. Name Similarity (Weight: 0.25)
    cand_name = profile_data.get("profile_name", "")
    name_sim = calculate_name_similarity(person_name, cand_name)
    name_score = name_sim * 0.25
    score += name_score
    if name_sim >= 0.8:
        signals.append(f"NAME_MATCH_HIGH ({name_sim})")
    elif name_sim >= 0.5:
        signals.append(f"NAME_MATCH_MEDIUM ({name_sim})")
        
    # 4. Role / Bio Context Matching (Weight: 0.15)
    bio = profile_data.get("bio", "").lower()
    role_terms = [t.lower() for t in target_role.split() if len(t) > 3]
    role_matches = [t for t in role_terms if t in bio]
    if role_matches:
        role_score = min(0.15, len(role_matches) * 0.05)
        score += role_score
        signals.append(f"ROLE_BIO_MATCH ({','.join(role_matches)})")

    # Bound score between 0.0 and 1.0
    final_score = round(min(1.0, max(0.0, score)), 2)
    
    if final_score >= 0.80:
        level = ConfidenceLevel.HIGH
    elif final_score >= 0.50:
        level = ConfidenceLevel.MEDIUM
    else:
        level = ConfidenceLevel.LOW
        
    return ContactDetail(
        type=platform.lower(),
        value=candidate_url,
        label=f"{platform.capitalize()} Profile",
        note=profile_data.get("note"),
        confidence=final_score,
        confidence_level=level,
        verification_method="multi_signal_heuristic",
        signals=signals
    )
