from __future__ import annotations

from typing import Callable
from urllib.parse import urlparse
from urllib.request import Request, build_opener, urlopen

SHORTENER_DOMAINS = {
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "buff.ly",
    "shorturl.at", "cutt.ly", "rebrand.ly", "lnkd.in",
}


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower().split(":", 1)[0]
    return host[4:] if host.startswith("www.") else host


def expand_url(url: str, opener: Callable | None = None) -> dict:
    domain = _domain(url)
    opener = opener or build_opener()
    request = Request(url, headers={"User-Agent": "recruiter-risk-triage/0.1"}, method="GET")
    open_call = opener if callable(opener) else opener.open
    try:
        with open_call(request, timeout=10) as response:
            final_url = response.geturl()
            status_code = getattr(response, "status", None)
    except TypeError:
        with open_call(request) as response:
            final_url = response.geturl()
            status_code = getattr(response, "status", None)
    except Exception as exc:
        return {
            "status": "error",
            "input_url": url,
            "final_url": None,
            "input_domain": domain,
            "final_domain": None,
            "is_shortener": domain in SHORTENER_DOMAINS,
            "error": str(exc),
        }
    return {
        "status": "ok",
        "input_url": url,
        "final_url": final_url,
        "input_domain": domain,
        "final_domain": _domain(final_url),
        "is_shortener": domain in SHORTENER_DOMAINS,
        "status_code": status_code,
    }
