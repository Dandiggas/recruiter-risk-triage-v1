from __future__ import annotations

import base64
import json
from typing import Callable, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

COMPANIES_HOUSE_SEARCH_URL = "https://api.company-information.service.gov.uk/search/companies"


def companies_house_lookup(query: str, api_key: Optional[str], opener: Callable = urlopen, max_results: int = 5) -> dict:
    if not api_key:
        return {"status": "missing_api_key", "source": "companies_house", "query": query, "results": []}
    if not query.strip():
        return {"status": "empty_query", "source": "companies_house", "query": query, "results": []}

    url = f"{COMPANIES_HOUSE_SEARCH_URL}?{urlencode({'q': query, 'items_per_page': str(max_results)})}"
    auth = base64.b64encode(f"{api_key}:".encode("utf-8")).decode("ascii")
    request = Request(url, headers={"Authorization": f"Basic {auth}", "Accept": "application/json"})

    try:
        with opener(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except TypeError:
        # Unit-test mocks often do not accept timeout.
        with opener(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return {"status": "error", "source": "companies_house", "query": query, "error": str(exc), "results": []}

    results = []
    for item in payload.get("items", [])[:max_results]:
        results.append({
            "company_name": item.get("title"),
            "company_number": item.get("company_number"),
            "company_status": item.get("company_status"),
            "date_of_creation": item.get("date_of_creation"),
            "address_snippet": item.get("address_snippet"),
            "company_type": item.get("company_type"),
            "links": item.get("links", {}),
        })
    return {"status": "ok", "source": "companies_house", "query": query, "results": results}
