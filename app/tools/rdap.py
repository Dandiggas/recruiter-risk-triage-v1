from __future__ import annotations

import json
from typing import Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def domain_from_url_or_email(value: str) -> str:
    value = value.strip()
    if "@" in value and "://" not in value:
        value = value.rsplit("@", 1)[1]
    parsed = urlparse(value if "://" in value else f"//{value}")
    host = (parsed.netloc or parsed.path).lower().split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    return host.strip("/ ")


def _registrar(payload: dict) -> str | None:
    for entity in payload.get("entities", []):
        if "registrar" not in entity.get("roles", []):
            continue
        vcard = entity.get("vcardArray", [])
        if len(vcard) >= 2:
            for row in vcard[1]:
                if row and row[0] == "fn" and len(row) >= 4:
                    return row[3]
    return None


def _event(payload: dict, action: str) -> str | None:
    for event in payload.get("events", []):
        if event.get("eventAction") == action:
            return event.get("eventDate")
    return None


def rdap_domain_lookup(value: str, opener: Callable = urlopen) -> dict:
    domain = domain_from_url_or_email(value)
    if not domain:
        return {"status": "empty_domain", "domain": domain}
    request = Request(f"https://rdap.org/domain/{domain}", headers={"Accept": "application/rdap+json, application/json"})
    try:
        with opener(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except TypeError:
        with opener(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return {"status": "error", "domain": domain, "error": str(exc)}
    return {
        "status": "ok",
        "domain": domain,
        "handle": payload.get("handle"),
        "ldh_name": payload.get("ldhName"),
        "registration_date": _event(payload, "registration"),
        "last_changed": _event(payload, "last changed"),
        "expiration_date": _event(payload, "expiration"),
        "registrar": _registrar(payload),
    }
