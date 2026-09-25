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
    Serpent API (apiserpent.com) client supporting Google, Bing, Yahoo with South African localization.
    """
    def __init__(
        self,
        api_key: Optional[str] = None,
        max_daily_limit: int = 9000
    ):
        self.api_key = api_key or os.getenv("SERPENT_API_KEY")
        self.max_daily_limit = max_daily_limit

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
        Executes Google search via apiserpent.com Quick Search with disk caching and quota safety.
        """
        if query in self.cache:
            return self.cache[query]

        remaining = self.get_remaining_daily_budget()
        if remaining <= 0:
            raise DailyQuotaExceededError(
                f"Daily search quota of {self.max_daily_limit} reached for {self.usage.get('date')}."
            )

        if not self.api_key:
            raise ValueError("SERPENT_API_KEY is not set.")

        import urllib.parse
        base_url = "https://apiserpent.com/api/search/quick"
        params = {
            "q": query,
            "country": gl,
            "num": num_results,
            "engine": "google"
        }
        url = f"{base_url}?{urllib.parse.urlencode(params)}"
        headers = {
            "X-API-Key": self.api_key,
            "User-Agent": "Mozilla/5.0 (compatible; PEPSocialDiscovery/1.0)"
        }
        req = urllib.request.Request(url, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                resp_data = json.loads(response.read().decode("utf-8"))
                self._increment_usage()
                print(f"    [Google Search via SerpentAPI] Used: {self.usage['queries_used']}/{self.max_daily_limit} today")

                results = []
                res_obj = resp_data.get("results", {})
                organic = res_obj.get("organic", []) if isinstance(res_obj, dict) else resp_data.get("organic", [])
                if not organic and isinstance(resp_data.get("results"), list):
                    organic = resp_data.get("results")

                for item in organic:
                    u = item.get("url") or item.get("link", "")
                    t = item.get("title", "")
                    s = item.get("snippet") or item.get("description", "")
                    if u:
                        results.append({
                            "title": t,
                            "url": u,
                            "snippet": s
                        })

                self.cache[query] = results
                self._save_json(CACHE_FILE, self.cache)
                return results

        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            print(f"Serpent API HTTP Error {e.code}: {err_body}")
            if e.code in (401, 403):
                raise DailyQuotaExceededError(f"SerpentAPI auth/quota error: {err_body}")
            return []
        except Exception as e:
            print(f"Serpent API Request Error: {e}")
            return []
