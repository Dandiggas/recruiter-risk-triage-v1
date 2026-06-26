from __future__ import annotations

import socket
import subprocess
from typing import Callable, List

from app.tools.rdap import domain_from_url_or_email


def default_resolver(domain: str, record_type: str) -> List[str]:
    record_type = record_type.upper()
    if record_type == "A":
        try:
            return sorted({item[4][0] for item in socket.getaddrinfo(domain, None)})
        except Exception:
            return []
    if record_type == "MX":
        try:
            proc = subprocess.run(["dig", "+short", "MX", domain], capture_output=True, text=True, timeout=5)
            if proc.returncode == 0:
                return [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        except Exception:
            return []
    return []


def check_email_domain(email_or_domain: str, resolver: Callable[[str, str], List[str]] = default_resolver) -> dict:
    domain = domain_from_url_or_email(email_or_domain)
    if not domain:
        return {"status": "empty_domain", "domain": domain, "has_mx": False, "mx_records": [], "a_records": []}
    mx_records = resolver(domain, "MX")
    a_records = resolver(domain, "A")
    return {
        "status": "ok",
        "domain": domain,
        "has_mx": bool(mx_records),
        "mx_records": mx_records,
        "has_a": bool(a_records),
        "a_records": a_records,
    }
