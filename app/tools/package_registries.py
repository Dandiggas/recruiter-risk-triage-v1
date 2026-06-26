from __future__ import annotations

import json
from typing import Callable
from urllib.parse import quote
from urllib.request import Request, urlopen


def npm_package_check(package: str, opener: Callable = urlopen) -> dict:
    package = package.strip().rstrip(".,;:)]}")
    package = package.lstrip("@") if package.startswith("@/") else package
    if not package:
        return {"status": "empty_package", "package": package}
    request = Request(f"https://registry.npmjs.org/{quote(package)}", headers={"Accept": "application/json"})
    try:
        with opener(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except TypeError:
        with opener(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return {"status": "error", "package": package, "registry": "npm", "error": str(exc)}
    times = payload.get("time", {})
    return {
        "status": "ok",
        "registry": "npm",
        "package": payload.get("name", package),
        "version": payload.get("version") or payload.get("dist-tags", {}).get("latest"),
        "created": times.get("created"),
        "modified": times.get("modified"),
    }


def pypi_package_check(package: str, opener: Callable = urlopen) -> dict:
    package = package.strip().rstrip(".,;:)]}")
    if not package:
        return {"status": "empty_package", "package": package}
    request = Request(f"https://pypi.org/pypi/{quote(package)}/json", headers={"Accept": "application/json"})
    try:
        with opener(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except TypeError:
        with opener(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return {"status": "error", "package": package, "registry": "pypi", "error": str(exc)}
    info = payload.get("info", {})
    return {
        "status": "ok",
        "registry": "pypi",
        "package": info.get("name", package),
        "version": info.get("version"),
        "summary": info.get("summary"),
        "release_count": len(payload.get("releases", {})),
    }
