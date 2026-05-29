from __future__ import annotations

import os
from typing import Any

from .http import get_json


class GoogleProgrammableSearchClient:
    BASE_URL = "https://www.googleapis.com/customsearch/v1"

    def __init__(self, api_key: str, search_engine_id: str):
        self.api_key = api_key
        self.search_engine_id = search_engine_id

    @classmethod
    def from_env(cls) -> "GoogleProgrammableSearchClient":
        api_key = os.getenv("GOOGLE_API_KEY", "").strip()
        search_engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID", "").strip()
        if not api_key or not search_engine_id:
            raise RuntimeError(
                "Set GOOGLE_API_KEY and GOOGLE_SEARCH_ENGINE_ID to use Google Programmable Search."
            )
        return cls(api_key, search_engine_id)

    def search(self, query: str, site: str | None = None, limit: int = 10) -> list[dict[str, str]]:
        params: dict[str, Any] = {
            "key": self.api_key,
            "cx": self.search_engine_id,
            "q": query,
            "num": max(1, min(limit, 10)),
        }
        if site:
            params["siteSearch"] = site
        payload = get_json(self.BASE_URL, params)
        results = []
        for item in payload.get("items", []):
            if isinstance(item, dict):
                results.append(
                    {
                        "title": str(item.get("title", "")),
                        "link": str(item.get("link", "")),
                        "snippet": str(item.get("snippet", "")),
                    }
                )
        return results
