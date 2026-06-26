import base64
import json
from unittest.mock import Mock

from app.config import load_settings
from app.tools.companies_house import companies_house_lookup
from app.tools.search import search_web
from app.tools.url_expand import expand_url
from app.tools.web_metadata import fetch_web_metadata


class FakeResponse:
    def __init__(self, payload=None, final_url="https://final.example/path", status=200):
        self.payload = payload or {}
        self._final_url = final_url
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def geturl(self):
        return self._final_url


def test_load_settings_reads_env_without_exposing_values(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("COMPANIES_HOUSE_API_KEY=abc123\nSEARCH_API_PROVIDER=brave\nSEARCH_API_KEY=search123\n")

    settings = load_settings(env_file)

    assert settings.companies_house_api_key == "abc123"
    assert settings.search_api_provider == "brave"
    assert settings.redacted() == {
        "COMPANIES_HOUSE_API_KEY": "present",
        "SEARCH_API_PROVIDER": "brave",
        "SEARCH_API_KEY": "present",
        "GITHUB_TOKEN": "missing",
        "URLSCAN_API_KEY": "missing",
        "VIRUSTOTAL_API_KEY": "missing",
        "EXPAND_URLS_LIVE": "disabled",
        "SECURITY_SANDBOX_LIVE": "disabled",
        "ENABLE_LLM_LANE_SYNTHESIS": "disabled",
        "LLM_LANE_SYNTHESIS_LANES": "none",
    }


def test_companies_house_lookup_uses_basic_auth_and_returns_structured_company():
    opener = Mock(return_value=FakeResponse({
        "items": [{
            "title": "ACME TALENT LTD",
            "company_number": "12345678",
            "company_status": "active",
            "date_of_creation": "2019-01-02",
            "address_snippet": "London",
        }]
    }))

    result = companies_house_lookup("Acme Talent", api_key="key123", opener=opener)

    request = opener.call_args.args[0]
    auth_header = request.headers["Authorization"]
    assert auth_header == "Basic " + base64.b64encode(b"key123:").decode()
    assert result["status"] == "ok"
    assert result["results"][0]["company_status"] == "active"
    assert result["results"][0]["company_number"] == "12345678"


def test_companies_house_lookup_gracefully_reports_missing_key():
    result = companies_house_lookup("Acme Talent", api_key=None)

    assert result["status"] == "missing_api_key"
    assert result["results"] == []


def test_expand_url_returns_final_url_and_shortener_signal():
    opener = Mock(return_value=FakeResponse(final_url="https://real-company.example/jobs/1"))

    result = expand_url("https://bit.ly/example", opener=opener, resolver=lambda host: ["93.184.216.34"])

    assert result["status"] == "ok"
    assert result["input_url"] == "https://bit.ly/example"
    assert result["final_url"] == "https://real-company.example/jobs/1"
    assert result["is_shortener"] is True


def test_expand_url_blocks_private_network_hosts_before_fetching():
    opener = Mock(return_value=FakeResponse())

    result = expand_url("http://127.0.0.1:8765/admin", opener=opener)

    assert result["status"] == "blocked_unsafe_url"
    opener.assert_not_called()


def test_expand_url_blocks_redirects_to_private_network_hosts():
    opener = Mock(return_value=FakeResponse(final_url="http://169.254.169.254/latest/meta-data"))

    result = expand_url("https://bit.ly/example", opener=opener, resolver=lambda host: ["93.184.216.34"])

    assert result["status"] == "error"
    assert "blocked address" in result["error"]


def test_fetch_web_metadata_blocks_non_http_and_private_hosts():
    opener = Mock(return_value=FakeResponse())

    private = fetch_web_metadata("http://localhost:8765", opener=opener)
    non_http = fetch_web_metadata("file:///etc/passwd", opener=opener)

    assert private["status"] == "blocked_unsafe_url"
    assert non_http["status"] == "blocked_unsafe_url"
    opener.assert_not_called()


def test_search_web_brave_uses_api_key_and_normalizes_results():
    opener = Mock(return_value=FakeResponse({
        "web": {
            "results": [
                {"title": "Acme Talent", "url": "https://acme.example", "description": "Recruitment agency"}
            ]
        }
    }))

    result = search_web("Acme Talent", provider="brave", api_key="search-key", opener=opener)

    request = opener.call_args.args[0]
    assert request.headers["X-subscription-token"] == "search-key"
    assert result["status"] == "ok"
    assert result["results"][0]["url"] == "https://acme.example"


def test_search_web_reports_missing_key_for_configured_provider():
    result = search_web("Acme Talent", provider="brave", api_key=None)

    assert result["status"] == "missing_api_key"
    assert result["results"] == []
