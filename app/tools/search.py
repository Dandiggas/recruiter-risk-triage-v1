from __future__ import annotations

import json
from typing import Callable, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


def search_web(query: str, provider: str = "brave", api_key: Optional[str] = None, opener: Callable = urlopen, count: int = 5) -> dict:
    provider = (provider or "brave").lower()
    if provider != "brave":
        return {"status": "unsupported_provider", "provider": provider, "query": query, "results": []}
    if not api_key:
        return {"status": "missing_api_key", "provider": provider, "query": query, "results": []}
    if not query.strip():
        return {"status": "empty_query", "provider": provider, "query": query, "results": []}

    url = f"{BRAVE_SEARCH_URL}?{urlencode({'q': query, 'count': str(count)})}"
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "X-Subscription-Token": api_key,
        },
    )
    try:
        with opener(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except TypeError:
        with opener(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return {"status": "error", "provider": provider, "query": query, "error": str(exc), "results": []}

    results = []
    for item in payload.get("web", {}).get("results", [])[:count]:
        results.append({
            "title": item.get("title"),
            "url": item.get("url"),
            "description": item.get("description"),
        })
    return {"status": "ok", "provider": provider, "query": query, "results": results}
