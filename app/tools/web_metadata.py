from __future__ import annotations

import html
import re
from typing import Callable
from urllib.request import Request, urlopen

TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
DESC_RE = re.compile(r"<meta[^>]+name=[\"']description[\"'][^>]+content=[\"'](.*?)[\"'][^>]*>", re.I | re.S)


def _clean(value: str | None) -> str | None:
    if not value:
        return None
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value)).split())


def fetch_web_metadata(url: str, opener: Callable = urlopen) -> dict:
    request = Request(url, headers={"User-Agent": "recruiter-risk-triage/0.1", "Accept": "text/html,application/xhtml+xml"})
    try:
        with opener(request, timeout=10) as response:
            raw = response.read()[:250000].decode("utf-8", errors="ignore")
            final_url = response.geturl()
            status_code = getattr(response, "status", None)
    except TypeError:
        with opener(request) as response:
            raw = response.read()[:250000].decode("utf-8", errors="ignore")
            final_url = response.geturl()
            status_code = getattr(response, "status", None)
    except Exception as exc:
        return {"status": "error", "url": url, "error": str(exc)}
    title = _clean((TITLE_RE.search(raw) or [None, None])[1])
    description = _clean((DESC_RE.search(raw) or [None, None])[1])
    return {"status": "ok", "url": url, "final_url": final_url, "status_code": status_code, "title": title, "description": description}
