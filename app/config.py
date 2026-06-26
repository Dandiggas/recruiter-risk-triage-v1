from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class Settings:
    companies_house_api_key: Optional[str] = None
    search_api_provider: str = "brave"
    search_api_key: Optional[str] = None
    github_token: Optional[str] = None
    urlscan_api_key: Optional[str] = None
    virustotal_api_key: Optional[str] = None
    expand_urls_live: bool = False
    security_sandbox_live: bool = False
    enable_llm_lane_synthesis: bool = False
    llm_lane_synthesis_lanes: tuple[str, ...] = ()

    def redacted(self) -> dict:
        return {
            "COMPANIES_HOUSE_API_KEY": "present" if self.companies_house_api_key else "missing",
            "SEARCH_API_PROVIDER": self.search_api_provider,
            "SEARCH_API_KEY": "present" if self.search_api_key else "missing",
            "GITHUB_TOKEN": "present" if self.github_token else "missing",
            "URLSCAN_API_KEY": "present" if self.urlscan_api_key else "missing",
            "VIRUSTOTAL_API_KEY": "present" if self.virustotal_api_key else "missing",
            "EXPAND_URLS_LIVE": "enabled" if self.expand_urls_live else "disabled",
            "SECURITY_SANDBOX_LIVE": "enabled" if self.security_sandbox_live else "disabled",
            "ENABLE_LLM_LANE_SYNTHESIS": "enabled" if self.enable_llm_lane_synthesis else "disabled",
            "LLM_LANE_SYNTHESIS_LANES": ",".join(self.llm_lane_synthesis_lanes) or "none",
        }


def _read_env_file(path: Path) -> dict:
    values = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_settings(env_file: str | Path = ".env") -> Settings:
    env_path = Path(env_file)
    file_values = _read_env_file(env_path)

    def pick(name: str, default: Optional[str] = None) -> Optional[str]:
        return os.environ.get(name) or file_values.get(name) or default

    def enabled(name: str, default: str = "false") -> bool:
        return (pick(name, default) or default).lower() in {"1", "true", "yes", "on"}

    lanes = tuple(
        lane.strip()
        for lane in (pick("LLM_LANE_SYNTHESIS_LANES", "") or "").split(",")
        if lane.strip()
    )

    return Settings(
        companies_house_api_key=pick("COMPANIES_HOUSE_API_KEY"),
        search_api_provider=(pick("SEARCH_API_PROVIDER", "brave") or "brave").lower(),
        search_api_key=pick("SEARCH_API_KEY"),
        github_token=pick("GITHUB_TOKEN"),
        urlscan_api_key=pick("URLSCAN_API_KEY"),
        virustotal_api_key=pick("VIRUSTOTAL_API_KEY"),
        expand_urls_live=enabled("EXPAND_URLS_LIVE"),
        security_sandbox_live=enabled("SECURITY_SANDBOX_LIVE"),
        enable_llm_lane_synthesis=enabled("ENABLE_LLM_LANE_SYNTHESIS"),
        llm_lane_synthesis_lanes=lanes,
    )
