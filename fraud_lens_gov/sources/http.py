from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any


USER_AGENT = "FraudLensGov/0.1 (+https://github.com/viamus/FraudLensGov)"


def get_json(url: str, params: dict[str, Any], timeout: int = 45) -> dict[str, Any]:
    query = urllib.parse.urlencode({key: value for key, value in params.items() if value is not None})
    full_url = f"{url}?{query}" if query else url
    request = urllib.request.Request(full_url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return json.loads(response.read().decode(charset))
