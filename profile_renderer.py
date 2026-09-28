#!/usr/bin/env python3
"""
Level 2 Evaluation: Headless Chrome Persona Profile Renderer
Uses Selenium to load Facebook, Instagram, LinkedIn, and X/Twitter profiles
within the user's active Chrome persona, capturing client-side rendered bio details
(e.g., 'Councillor Buffalo City Metropolitan Municipality', 'Bisho', 'DA')
to corroborate and upgrade candidate match confidence.

SAFETY GUARDS:
- Mimics personal Chrome persona with genuine authenticated cookies and session state.
- Respects personal accounts with rate-limiting, randomized human jitter, and jittered cooldowns.
- Automatic SQLite caching to ensure each URL is rendered at most once.
- Tripwire safety latch: aborts immediately if Meta issues a checkpoint/CAPTCHA/challenge.
"""

import os
import re
import time
import random
import shutil
import sqlite3
import threading
from typing import Dict, Any, Optional, List
from models import ContactDetail, ConfidenceLevel
from evaluator import MAJOR_SA_PARTIES, SA_GEOGRAPHY_TAXONOMY, FOREIGN_LOCATIONS

DEFAULT_CHROME_USER_DATA = "/Users/arf/Library/Application Support/Google/Chrome"
SCRATCH_CLONE_DIR = "/Users/arf/.gemini/antigravity-ide/brain/eeccf8e6-1b87-4006-837c-696fd7dee865/scratch/chrome_persona"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "peps.db")


class ChromePersonaRenderer:
    """Manages a headless Chrome instance initialized with the user's Chrome session persona,
    with strict pacing, random sleeps, and account safety tripwires."""
    
    _instance = None

    def __init__(
        self,
        user_data_src: str = DEFAULT_CHROME_USER_DATA,
        clone_dir: str = SCRATCH_CLONE_DIR,
        min_sleep: float = 7.0,
        max_sleep: float = 14.0,
        break_frequency: int = 6,
        break_duration_min: float = 20.0,
        break_duration_max: float = 35.0,
    ):
        self.user_data_src = user_data_src
        self.clone_dir = clone_dir
        self.min_sleep = min_sleep
        self.max_sleep = max_sleep
        self.break_frequency = break_frequency
        self.break_duration_min = break_duration_min
        self.break_duration_max = break_duration_max

        self.last_request_time: float = 0.0
        self.request_count: int = 0
        self.safety_tripped: bool = False
        self.driver = None
        self.lock = threading.Lock()

        self._init_cache_db()
        self._init_clone_dir()

    def _init_cache_db(self):
        """Initializes SQLite cache table for rendered profiles so URLs are never re-fetched."""
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS rendered_profiles (
                    url TEXT PRIMARY KEY,
                    platform TEXT,
                    title TEXT,
                    body_text TEXT,
                    rendered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[Renderer Cache] Warning initializing cache table: {e}")

    def _get_cached_profile(self, url: str) -> Optional[Dict[str, Any]]:
        """Returns cached rendered profile if available."""
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT title, body_text FROM rendered_profiles WHERE url = ?", (url,))
            row = c.fetchone()
            conn.close()
            if row:
                return {
                    "status": 200,
                    "title": row[0] or "",
                    "body_text": row[1] or "",
                    "from_cache": True
                }
        except Exception:
            pass
        return None

    def _save_cached_profile(self, url: str, platform: str, title: str, body_text: str):
        """Saves rendered profile to SQLite cache."""
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("""
                INSERT OR REPLACE INTO rendered_profiles (url, platform, title, body_text, rendered_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (url, platform, title, body_text))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[Renderer Cache] Error saving cache: {e}")

    def _init_clone_dir(self):
        """Copies session cookies, state, and preferences to avoid Chrome singleton lock."""
        default_dir = os.path.join(self.clone_dir, "Default")
        os.makedirs(default_dir, exist_ok=True)
        src_default = os.path.join(self.user_data_src, "Default")
        
        # 1. Copy Local State from Chrome root
        src_local_state = os.path.join(self.user_data_src, "Local State")
        if os.path.exists(src_local_state):
            try:
                shutil.copy2(src_local_state, os.path.join(self.clone_dir, "Local State"))
            except Exception:
                pass

        # 2. Copy Default profile session files
        if os.path.exists(src_default):
            for fname in ["Cookies", "Network Persistent State", "Preferences", "Secure Preferences"]:
                fpath = os.path.join(src_default, fname)
                if os.path.exists(fpath):
                    try:
                        shutil.copy2(fpath, os.path.join(default_dir, fname))
                    except Exception:
                        pass

    def get_driver(self):
        if self.safety_tripped:
            print("🚨 [Account Safety Latch Active] Refusing to start Chrome because a safety checkpoint was previously triggered.")
            return None

        if self.driver is not None:
            return self.driver

        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options

            options = Options()
            options.add_argument(f"--user-data-dir={self.clone_dir}")
            options.add_argument("--profile-directory=Default")
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--window-size=1920,1080")
            
            # Anti-detection & Keychain preservation flags
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["use-mock-keychain", "password-store", "enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)
            options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

            self.driver = webdriver.Chrome(options=options)
            
            # Remove navigator.webdriver detection
            try:
                self.driver.execute_cdp_cmd(
                    "Page.addScriptToEvaluateOnNewDocument",
                    {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"}
                )
            except Exception:
                pass

            return self.driver
        except Exception as e:
            print(f"Warning: Could not start headless Chrome with persona: {e}")
            return None

    def _pace_request(self, domain: str = "Meta"):
        """Enforces jittered delays and periodic coffee breaks to protect personal accounts."""
        now = time.time()
        elapsed = now - self.last_request_time
        
        # Periodic coffee break every N requests
        if self.request_count > 0 and (self.request_count % self.break_frequency == 0):
            coffee_break = round(random.uniform(self.break_duration_min, self.break_duration_max), 1)
            print(f"    ☕ [Persona Protection] Taking a scheduled human pause of {coffee_break}s after {self.request_count} requests...")
            time.sleep(coffee_break)
        elif self.last_request_time > 0 and elapsed < self.min_sleep:
            jittered_sleep = round(random.uniform(self.min_sleep, self.max_sleep) - elapsed, 2)
            if jittered_sleep > 0:
                print(f"    ⏱️ [Persona Pacing] Sleeping {jittered_sleep}s to respect {domain} session rate limits...")
                time.sleep(jittered_sleep)
        elif self.last_request_time > 0:
            jittered_sleep = round(random.uniform(2.0, 5.0), 2)
            time.sleep(jittered_sleep)

        self.last_request_time = time.time()
        self.request_count += 1

    def render_profile(self, url: str, platform: str = "general") -> Dict[str, Any]:
        """Loads a profile URL with human jitter and safety tripwires, returning extracted bio details."""
        # 1. Check persistent SQLite cache
        cached = self._get_cached_profile(url)
        if cached:
            return cached

        with self.lock:
            # Re-check cache under lock in case another thread just populated it
            cached = self._get_cached_profile(url)
            if cached:
                return cached

            if self.safety_tripped:
                return {"status": 0, "error": "Safety tripwire active", "body_text": "", "title": ""}

            driver = self.get_driver()
            if driver is None:
                return {"status": 0, "error": "Driver unavailable", "body_text": "", "title": ""}

            # 2. Pacing sleep to protect personal accounts
            is_meta = "facebook.com" in url or "instagram.com" in url
            domain_label = "Meta (Personal Account)" if is_meta else "Web"
            self._pace_request(domain=domain_label)

            try:
                driver.get(url)
                
                # Initial hydration wait with jitter
                initial_wait = round(random.uniform(3.0, 5.0), 2)
                time.sleep(initial_wait)
                
                curr_url = driver.current_url.lower()
                title = driver.title or ""
                title_lower = title.lower()

                # 3. Account Protection Tripwire Detection
                tripwire_terms = [
                    "checkpoint", "challenge", "two_factor", "login_attempt",
                    "help/contact", "restricted", "temporarily blocked", "suspended",
                    "confirm your identity", "security check"
                ]
                if any(term in curr_url or term in title_lower for term in tripwire_terms):
                    self.safety_tripped = True
                    print(f"\n🚨 [ACCOUNT SAFETY ALERT] Checkpoint/Challenge detected at {curr_url} (Title: '{title}').")
                    print("🚨 Halting all Level 2 renders immediately to protect your personal account.\n")
                    self.close()
                    return {"status": 403, "error": "Account security tripwire triggered", "body_text": "", "title": title}

                # 4. Human-like interaction: smooth scroll down to trigger lazy bio rendering
                try:
                    scroll_y = random.randint(300, 500)
                    driver.execute_script(f"window.scrollBy({{top: {scroll_y}, behavior: 'smooth'}});")
                    post_scroll_wait = round(random.uniform(1.5, 2.5), 2)
                    time.sleep(post_scroll_wait)
                except Exception:
                    pass

                # 5. Extract visible text
                try:
                    body_elem = driver.find_element("tag name", "body")
                    body_text = body_elem.text if body_elem else ""
                except Exception:
                    body_text = ""

                # 6. Save to cache
                if len(body_text.strip()) > 30:
                    self._save_cached_profile(url, platform, title, body_text)

                return {
                    "status": 200,
                    "title": title,
                    "body_text": body_text,
                    "from_cache": False
                }
            except Exception as e:
                return {"status": 0, "error": str(e), "body_text": "", "title": ""}

    def close(self):
        if self.driver is not None:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None


_global_renderer: Optional[ChromePersonaRenderer] = None

def get_shared_renderer() -> ChromePersonaRenderer:
    global _global_renderer
    if _global_renderer is None:
        _global_renderer = ChromePersonaRenderer()
    return _global_renderer


def render_and_upgrade_social_account(
    contact: ContactDetail,
    pep_info: Dict[str, str],
    renderer: Optional[ChromePersonaRenderer] = None
) -> ContactDetail:
    """
    Second-Level Evaluation:
    For identified social accounts evaluated as POSSIBLE or POTENTIAL (0.40 <= confidence < 0.85),
    renders the page via headless Chrome using the user's personal persona to examine dynamic bio details.
    Upgrades rating to PROBABLE (0.85 - 1.00) when civic role, municipal office, or party alignment
    are corroborated in the rendered profile.

    Does NOT hit Meta if confidence is already >= 0.85 (highly confident) or < 0.40 (disqualified)
    to minimize requests and protect the personal account.
    """
    # Only render profiles that need confirmation (0.40 <= confidence < 0.85)
    if contact.confidence < 0.40 or contact.confidence >= 0.85:
        return contact

    url = contact.value
    platform = contact.type.lower()
    
    # We focus Level 2 rendering on social platforms requiring JS / session rendering
    if platform not in ("facebook", "instagram", "linkedin", "twitter"):
        return contact

    if renderer is None:
        renderer = get_shared_renderer()

    if renderer.safety_tripped:
        return contact

    print(f"    🔍 [Level 2 Evaluation] Rendering profile page: {url}")
    result = renderer.render_profile(url, platform=platform)
    
    if result.get("from_cache"):
        print(f"      ⚡ [Cache Hit] Loaded rendered profile from local cache")

    body_text = result.get("body_text", "")
    title = result.get("title", "")
    combined_rendered = f"{title} {body_text}".lower()

    if len(body_text.strip()) < 20:
        # Page rendered minimal content
        return contact

    score_delta = 0.0
    level2_signals = []

    target_party = pep_info.get("party_name", "").strip()
    target_district = pep_info.get("b ", "").strip() or pep_info.get("district", "").strip()
    first_name = pep_info.get("first_name", "").strip().lower()
    last_name = pep_info.get("last_name", "").strip().lower()

    # 1. Candidate Name Confirmation in Rendered Bio
    if first_name and last_name and (first_name in combined_rendered) and (last_name in combined_rendered):
        score_delta += 0.05
        level2_signals.append("RENDERED_NAME_CONFIRMED")

    # 2. Political Party Affiliation in Rendered Bio (e.g., 'Democratic Alliance', 'DA', 'ANC', 'EFF')
    if target_party:
        target_party_lower = target_party.lower()
        party_aliases = [target_party_lower]
        for p_name, p_aliases in MAJOR_SA_PARTIES.items():
            if p_name in target_party_lower or target_party_lower in p_name:
                party_aliases.extend(p_aliases)
                break

        matched_party = [alias for alias in set(party_aliases) if re.search(r'\b' + re.escape(alias) + r'\b', combined_rendered)]
        if matched_party:
            score_delta += 0.30
            level2_signals.append(f"RENDERED_PARTY_MATCH ({matched_party[0].upper()})")
        else:
            # Check for conflicting opposition political party claim
            for other_party, other_aliases in MAJOR_SA_PARTIES.items():
                if other_party not in target_party_lower and not any(a in target_party_lower for a in other_aliases):
                    if any(re.search(r'\b(?:councillor|candidate|member|volunteer|chairperson)\s+(?:of|for)?\s*' + re.escape(oa) + r'\b', combined_rendered) for oa in other_aliases):
                        score_delta -= 0.50
                        level2_signals.append(f"RENDERED_CONFLICTING_PARTY ({other_party.upper()})")
                        break

    # 3. Local Town / Suburb Confirmation (e.g. 'Bisho', 'Mdantsane', 'East London')
    cleaned_district = re.sub(r"^[A-Z]{2,3}\d+\s*-\s*", "", target_district).strip().lower() if target_district else ""
    matched_entry = None
    for key, data in SA_GEOGRAPHY_TAXONOMY.items():
        if key in cleaned_district:
            matched_entry = data
            break

    if matched_entry:
        matched_towns = [t for t in matched_entry["towns"] if re.search(r'\b' + re.escape(t) + r'\b', combined_rendered)]
        if matched_towns:
            score_delta += 0.25
            level2_signals.append(f"RENDERED_TOWN_MATCH ({matched_towns[0].title()})")
        
        matched_munis = [m for m in matched_entry["municipality"] if re.search(r'\b' + re.escape(m) + r'\b', combined_rendered)]
        if matched_munis:
            score_delta += 0.20
            level2_signals.append(f"RENDERED_MUNICIPALITY_MATCH ({matched_munis[0].title()})")

    # 4. Exact Coupled Municipal Office (e.g. 'Councillor Buffalo City Metropolitan Municipality', 'PR Councillor BCMM')
    muni_search_terms = [cleaned_district] if cleaned_district else []
    if matched_entry:
        muni_search_terms.extend(matched_entry.get("municipality", []))
    
    coupled_office = False
    for m_term in muni_search_terms:
        if m_term and len(m_term) >= 3:
            pat = r'\b(?:councillor|cllr|mayor|deputy mayor|speaker|pr councillor|ward councillor|ward candidate)\s+(?:of\s+)?(?:the\s+)?' + re.escape(m_term)
            if re.search(pat, combined_rendered):
                coupled_office = True
                break
    if coupled_office:
        score_delta += 0.25
        level2_signals.append("RENDERED_EXACT_MUNICIPAL_OFFICE_CONFIRMED")
    else:
        # General Civic / Councillor role in rendered bio
        civic_terms = ["councillor", "cllr", "mayor", "municipality", "local government", "ward", "election candidate", "pr councillor"]
        matched_civic = [c for c in civic_terms if re.search(r'\b' + re.escape(c) + r'\b', combined_rendered)]
        if matched_civic:
            score_delta += 0.15
            level2_signals.append(f"RENDERED_CIVIC_ROLE ({matched_civic[0]})")

    # 5. Foreign Location Disqualification (protect SA towns like East London from triggering foreign 'London')
    clean_foreign_text = re.sub(r'\beast\s+london\b', '', combined_rendered)
    matched_foreign = [f for f in FOREIGN_LOCATIONS if re.search(r'\b' + re.escape(f) + r'\b', clean_foreign_text)]
    if matched_foreign:
        score_delta -= 0.50
        level2_signals.append(f"RENDERED_FOREIGN_LOCATION ({matched_foreign[0].title()})")

    # Update contact details if Level 2 examination yielded signals
    if level2_signals:
        new_score = round(min(1.0, max(0.10, contact.confidence + score_delta)), 2)
        old_score = contact.confidence
        contact.confidence = new_score
        
        if new_score >= 0.70:
            contact.confidence_level = ConfidenceLevel.PROBABLE
        elif new_score >= 0.55:
            contact.confidence_level = ConfidenceLevel.POTENTIAL
        elif new_score >= 0.40:
            contact.confidence_level = ConfidenceLevel.POSSIBLE
        else:
            contact.confidence_level = ConfidenceLevel.UNLIKELY

        # Append to rationale
        contact.rationale += f" [Level 2 Rendered Evaluation: {', '.join(level2_signals)} | Adj: {score_delta:+.2f} -> {new_score}]"
        contact.signals.extend(level2_signals)
        print(f"      → Level 2 Upgrade: {old_score} -> {new_score} ({contact.confidence_level}) | Signals: {level2_signals}")

    return contact
