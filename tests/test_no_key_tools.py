import json
from unittest.mock import Mock

from app.tools.dns_checks import check_email_domain
from app.tools.github_public import github_repo_check, parse_github_repo
from app.tools.package_registries import npm_package_check, pypi_package_check
from app.tools.rdap import rdap_domain_lookup
from app.tools.web_metadata import fetch_web_metadata


class FakeResponse:
    def __init__(self, payload=None, text=None, final_url="https://example.com", status=200):
        self.payload = payload
        self.text = text
        self._final_url = final_url
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        if self.text is not None:
            return self.text.encode("utf-8")
        return json.dumps(self.payload or {}).encode("utf-8")

    def geturl(self):
        return self._final_url


def test_rdap_domain_lookup_normalizes_events_and_registrar():
    opener = Mock(return_value=FakeResponse({
        "handle": "EXAMPLE-COM",
        "ldhName": "example.com",
        "events": [{"eventAction": "registration", "eventDate": "1995-08-14T04:00:00Z"}],
        "entities": [{"roles": ["registrar"], "vcardArray": ["vcard", [["fn", {}, "text", "Example Registrar"]]]}],
    }))

    result = rdap_domain_lookup("https://www.example.com/jobs", opener=opener)

    assert result["status"] == "ok"
    assert result["domain"] == "example.com"
    assert result["registration_date"] == "1995-08-14T04:00:00Z"
    assert result["registrar"] == "Example Registrar"


def test_check_email_domain_uses_injected_dns_resolver():
    def resolver(domain, record_type):
        assert domain == "example.com"
        return ["mx1.example.com"] if record_type == "MX" else []

    result = check_email_domain("recruiter@example.com", resolver=resolver)

    assert result["status"] == "ok"
    assert result["domain"] == "example.com"
    assert result["has_mx"] is True
    assert result["mx_records"] == ["mx1.example.com"]


def test_fetch_web_metadata_extracts_title_description_and_final_url():
    html = """<html><head><title>Careers | Example</title><meta name="description" content="Build security tools"></head></html>"""
    opener = Mock(return_value=FakeResponse(text=html, final_url="https://example.com/careers"))

    result = fetch_web_metadata("https://example.com/jobs", opener=opener)

    assert result["status"] == "ok"
    assert result["title"] == "Careers | Example"
    assert result["description"] == "Build security tools"
    assert result["final_url"] == "https://example.com/careers"


def test_parse_github_repo_and_public_check_normalizes_repo_data():
    assert parse_github_repo("https://github.com/acme/security-assessment") == ("acme", "security-assessment")
    opener = Mock(return_value=FakeResponse({
        "full_name": "acme/security-assessment",
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-02-01T00:00:00Z",
        "stargazers_count": 3,
        "forks_count": 1,
        "archived": False,
        "default_branch": "main",
    }))

    result = github_repo_check("https://github.com/acme/security-assessment", opener=opener)

    assert result["status"] == "ok"
    assert result["repo"] == "acme/security-assessment"
    assert result["stars"] == 3


def test_npm_and_pypi_package_checks_normalize_registry_payloads():
    npm = npm_package_check("left-pad", opener=Mock(return_value=FakeResponse({
        "name": "left-pad",
        "version": "1.3.0",
        "time": {"created": "2014-03-14T00:00:00.000Z", "modified": "2020-01-01T00:00:00.000Z"},
    })))
    pypi = pypi_package_check("requests", opener=Mock(return_value=FakeResponse({
        "info": {"name": "requests", "version": "2.32.0", "summary": "HTTP for Humans"},
        "releases": {"2.32.0": [{}]},
    })))

    assert npm["status"] == "ok"
    assert npm["package"] == "left-pad"
    assert pypi["status"] == "ok"
    assert pypi["package"] == "requests"
