"""
Serper.dev Google Search Engine with 1,000 Daily Quota Safety Limits and Disk Caching
Direct Google index queries with South African localization (gl=za).
"""

import os
import json
import urllib.request
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

DAILY_QUOTA_LIMIT = 1000
USAGE_FILE = "cache/daily_search_usage.json"
CACHE_FILE = "cache/serper_search_cache.json"


class DailyQuotaExceededError(Exception):
    """Raised when the daily search budget is exhausted."""
    pass


class SerperSearchEngine:
    def __init__(
        self,
        api_key: Optional[str] = None,
        max_daily_limit: int = DAILY_QUOTA_LIMIT
    ):
        self.api_key = api_key or os.getenv("SERPER_API_KEY")
        self.max_daily_limit = max_daily_limit

        if not self.api_key:
            self._load_dotenv()

        os.makedirs("cache", exist_ok=True)
        self.cache = self._load_json(CACHE_FILE)
        self.usage = self._load_usage()

    def _load_dotenv(self):
        env_path = ".env"
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip() == "SERPER_API_KEY" and not self.api_key:
                            self.api_key = v.strip().strip("'\"")

    def _load_json(self, path: str) -> dict:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_json(self, path: str, data: dict):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save {path}: {e}")

    def _load_usage(self) -> dict:
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        data = self._load_json(USAGE_FILE)
        if data.get("date") != today_str:
            data = {"date": today_str, "queries_used": 0}
            self._save_json(USAGE_FILE, data)
        return data

    def _increment_usage(self):
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.usage.get("date") != today_str:
            self.usage = {"date": today_str, "queries_used": 0}
        
        self.usage["queries_used"] += 1
        self._save_json(USAGE_FILE, self.usage)

    def get_remaining_daily_budget(self) -> int:
        """Returns the number of search queries remaining today."""
        self.usage = self._load_usage()
        used = self.usage.get("queries_used", 0)
        return max(0, self.max_daily_limit - used)

    def search(self, query: str, num_results: int = 10, gl: str = "za") -> List[Dict[str, str]]:
        """
        Executes Google search via Serper API with disk caching and quota enforcement.
        """
        # 1. Return from disk cache if query was already run
        if query in self.cache:
            return self.cache[query]

        # 2. Check safety quota limit
        remaining = self.get_remaining_daily_budget()
        if remaining <= 0:
            raise DailyQuotaExceededError(
                f"Daily search quota of {self.max_daily_limit} reached for {self.usage.get('date')}. "
                "Halting pipeline to protect budget."
            )

        if not self.api_key:
            raise ValueError("SERPER_API_KEY is not set.")

        # 3. Build HTTP request
        url = "https://google.serper.dev/search"
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json"
        }
        payload = json.dumps({
            "q": query,
            "gl": gl,
            "num": num_results
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                resp_data = json.loads(response.read().decode("utf-8"))
                
                # Record usage
                self._increment_usage()
                print(f"    [Google Search via Serper] Used: {self.usage['queries_used']}/{self.max_daily_limit} today")

                results = []
                for item in resp_data.get("organic", []):
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("link", ""),
                        "snippet": item.get("snippet", "")
                    })

                # Save to persistent cache
                self.cache[query] = results
                self._save_json(CACHE_FILE, self.cache)
                return results

        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            print(f"Serper API HTTP Error {e.code}: {err_body}")
            if e.code == 429:
                raise DailyQuotaExceededError("Serper rate limit / quota exceeded.")
            return []
        except Exception as e:
            print(f"Serper Search Error: {e}")
            return []


class SerpentSearchEngine(SerperSearchEngine):
    """
    Serpent API (apiserpent.com) client supporting Google, Bing, Yahoo, DuckDuckGo, and Brave
    with South African localization and multi-engine result aggregation.
    """
    def __init__(
        self,
        api_key: Optional[str] = None,
        max_daily_limit: int = 9000,
        engines: Optional[List[str]] = None
    ):
        self.api_key = api_key or os.getenv("SERPENT_API_KEY")
        self.max_daily_limit = max_daily_limit
        if isinstance(engines, str):
            self.engines = [e.strip().lower() for e in engines.split(",") if e.strip()]
        else:
            self.engines = engines or ["google"]

        if not self.api_key:
            self._load_dotenv_serpent()

        os.makedirs("cache", exist_ok=True)
        self.cache = self._load_json(CACHE_FILE)
        self.usage = self._load_usage()

    def _load_dotenv_serpent(self):
        env_path = ".env"
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip() == "SERPENT_API_KEY" and not self.api_key:
                            self.api_key = v.strip().strip("'\"")

    def search(self, query: str, num_results: int = 10, gl: str = "za") -> List[Dict[str, str]]:
        """
        Executes search via apiserpent.com across configured engines (Google, Bing, Brave, etc.)
        with URL deduplication, disk caching, and quota enforcement.
        """
        engines_tag = ",".join(sorted(self.engines))
        cache_key = f"{query}__engines={engines_tag}"

        if cache_key in self.cache:
            return self.cache[cache_key]
        if len(self.engines) == 1 and query in self.cache:
            return self.cache[query]

        if not self.api_key:
            raise ValueError("SERPENT_API_KEY is not set.")

        import urllib.parse
        base_url = "https://apiserpent.com/api/search/quick"
        all_results = []
        seen_urls = set()

        for engine_name in self.engines:
            remaining = self.get_remaining_daily_budget()
            if remaining <= 0:
                print(f"    ⚠️ Search budget exhausted ({self.max_daily_limit} queries today).")
                break

            params = {
                "q": query,
                "country": gl,
                "num": num_results,
                "engine": engine_name
            }
            url = f"{base_url}?{urllib.parse.urlencode(params)}"
            headers = {
                "X-API-Key": self.api_key,
                "User-Agent": "Mozilla/5.0 (compatible; PEPSocialDiscovery/1.0)"
            }
            req = urllib.request.Request(url, headers=headers)

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    with urllib.request.urlopen(req, timeout=35) as response:
                        resp_data = json.loads(response.read().decode("utf-8"))
                        self._increment_usage()
                        print(f"    [{engine_name.upper()} via SerpentAPI] Used: {self.usage['queries_used']}/{self.max_daily_limit} today")

                        res_obj = resp_data.get("results", {})
                        organic = res_obj.get("organic", []) if isinstance(res_obj, dict) else resp_data.get("organic", [])
                        if not organic and isinstance(resp_data.get("results"), list):
                            organic = resp_data.get("results")

                        engine_added = 0
                        for item in organic:
                            u = item.get("url") or item.get("link", "")
                            t = item.get("title", "")
                            s = item.get("snippet") or item.get("description", "")
                            if u and u.lower() not in seen_urls:
                                seen_urls.add(u.lower())
                                all_results.append({
                                    "title": t,
                                    "url": u,
                                    "snippet": s,
                                    "engine": engine_name
                                })
                                engine_added += 1
                        print(f"      → Retrieved {engine_added} distinct results from {engine_name.upper()}.")
                        break

                except urllib.error.HTTPError as e:
                    err_body = e.read().decode("utf-8", errors="ignore")
                    print(f"    ⚠️ Serpent API ({engine_name}) HTTP Error {e.code}: {err_body}")
                    if e.code in (401, 402, 403):
                        print("    ⚠️ Account credit limit reached or payment required on SerpentAPI.")
                        raise DailyQuotaExceededError(f"SerpentAPI payment/credit limit: {err_body}")
                    elif e.code == 429:
                        if attempt == max_retries - 1:
                            print("    ⚠️ Serpent API rate limit persisted across all retries.")
                            raise DailyQuotaExceededError(f"SerpentAPI rate limit reached (HTTP 429): {err_body}")
                        import time
                        wait_sec = min(5, 2 * (attempt + 1))
                        print(f"    ⏳ Soft limit / rate limit (429) hit. Retrying in {wait_sec}s before retry {attempt + 2}/{max_retries}...")
                        time.sleep(wait_sec)
                        continue
                    else:
                        break
                except (urllib.error.URLError, TimeoutError, Exception) as e:
                    err_msg = str(e)
                    is_timeout = "timed out" in err_msg.lower() or isinstance(e, (TimeoutError, urllib.error.URLError))
                    if is_timeout and attempt < max_retries - 1:
                        import time
                        wait_sec = 3 * (attempt + 1)
                        print(f"    ⏳ Serpent API ({engine_name}) timed out / network glitch. Retrying attempt {attempt + 2}/{max_retries} in {wait_sec}s...")
                        time.sleep(wait_sec)
                        continue
                    else:
                        print(f"    ⚠️ Serpent API ({engine_name}) Request Error: {e}")
                        break

        # Save to persistent cache
        if all_results:
            self.cache[cache_key] = all_results
            if len(self.engines) == 1:
                self.cache[query] = all_results
            self._save_json(CACHE_FILE, self.cache)

        return all_results
