from __future__ import annotations

import json
import re
from typing import Callable, Optional, Tuple
from urllib.request import Request, urlopen

GITHUB_RE = re.compile(r"github\.com/([^/\s]+)/([^/\s#?]+)", re.I)


def parse_github_repo(url: str) -> Optional[Tuple[str, str]]:
    url = url.strip().rstrip(".,;:)]}")
    match = GITHUB_RE.search(url)
    if not match:
        return None
    return match.group(1), match.group(2).removesuffix(".git")


def github_repo_check(url: str, opener: Callable = urlopen) -> dict:
    parsed = parse_github_repo(url)
    if not parsed:
        return {"status": "not_github_repo", "url": url}
    owner, repo = parsed
    request = Request(f"https://api.github.com/repos/{owner}/{repo}", headers={"Accept": "application/vnd.github+json", "User-Agent": "recruiter-risk-triage/0.1"})
    try:
        with opener(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except TypeError:
        with opener(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return {"status": "error", "url": url, "repo": f"{owner}/{repo}", "error": str(exc)}
    return {
        "status": "ok",
        "url": url,
        "repo": payload.get("full_name", f"{owner}/{repo}"),
        "created_at": payload.get("created_at"),
        "updated_at": payload.get("updated_at"),
        "stars": payload.get("stargazers_count"),
        "forks": payload.get("forks_count"),
        "archived": payload.get("archived"),
        "default_branch": payload.get("default_branch"),
    }
