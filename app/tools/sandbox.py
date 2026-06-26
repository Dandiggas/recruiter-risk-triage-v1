from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.tools.github_public import parse_github_repo

SANDBOX_PROFILE = {
    "engine": "docker",
    "network": "none",
    "user": "non-root",
    "mounts": "assessment read-only",
    "limits": {"timeout_seconds": 30, "memory": "256m", "cpus": "1"},
    "execution_policy": "static analysis only; do not run project install/test scripts by default",
}

STATIC_SCAN_SCRIPT = r'''
import json, os, re
from pathlib import Path
root = Path('/assessment')
findings = []
files = []
keywords = re.compile(r'(seed phrase|mnemonic|private[_ -]?key|wallet|metamask|ethers|web3|drain|clipboard|telegram|discord|eval\(|child_process|curl\s|wget\s)', re.I)
for path in root.rglob('*'):
    if path.is_file() and path.stat().st_size <= 1_000_000:
        rel = str(path.relative_to(root))
        if any(part in rel for part in ['.git/', 'node_modules/', '__pycache__/']):
            continue
        files.append(rel)
        if path.name == 'package.json':
            try:
                payload = json.loads(path.read_text(errors='ignore'))
                scripts = payload.get('scripts') or {}
                for name, script in scripts.items():
                    if name in {'preinstall', 'install', 'postinstall', 'prepare'} or keywords.search(str(script)):
                        findings.append({'file': rel, 'type': 'package_script', 'detail': f'{name}: {script}'})
                deps = {**(payload.get('dependencies') or {}), **(payload.get('devDependencies') or {})}
                for dep in deps:
                    if dep.lower() in {'ethers', 'web3', '@solana/web3.js', 'puppeteer', 'playwright'}:
                        findings.append({'file': rel, 'type': 'sensitive_dependency', 'detail': dep})
            except Exception as exc:
                findings.append({'file': rel, 'type': 'parse_error', 'detail': str(exc)})
        if path.suffix.lower() in {'.js', '.ts', '.jsx', '.tsx', '.py', '.sh', '.mjs', '.cjs'}:
            text = path.read_text(errors='ignore')[:200_000]
            for match in keywords.finditer(text):
                start = max(0, match.start() - 80)
                end = min(len(text), match.end() + 120)
                findings.append({'file': rel, 'type': 'keyword_match', 'detail': text[start:end].replace('\n', ' ')[:240]})
                break
print(json.dumps({'files_scanned': len(files), 'findings': findings[:50]}, sort_keys=True))
'''


def _docker_available(runner=subprocess.run) -> bool:
    return shutil.which("docker") is not None and runner(
        ["docker", "version", "--format", "{{.Server.Version}}"],
        capture_output=True,
        text=True,
        timeout=8,
    ).returncode == 0


def sandbox_repo_static_analysis(url: str, live: bool = False, runner=subprocess.run) -> dict:
    """Plan or run a no-network Docker static scan for a GitHub assessment repo.

    Default is planning mode. Live mode must be explicitly enabled because it clones
    untrusted material and starts Docker, even though the container does not run the
    project code and has no network.
    """
    parsed = parse_github_repo(url)
    if not parsed:
        return {"status": "not_github_repo", "url": url, "sandbox_profile": SANDBOX_PROFILE}
    owner, repo = parsed
    repo_ref = f"{owner}/{repo}"
    if not live:
        return {
            "status": "planned",
            "url": url,
            "repo": repo_ref,
            "reason": "GitHub assessment detected; sandbox execution is gated behind SECURITY_SANDBOX_LIVE=true.",
            "sandbox_profile": SANDBOX_PROFILE,
        }
    if not _docker_available(runner):
        return {"status": "docker_unavailable", "url": url, "repo": repo_ref, "sandbox_profile": SANDBOX_PROFILE}

    with tempfile.TemporaryDirectory(prefix="triage-sandbox-") as tmp:
        tmp_path = Path(tmp)
        repo_dir = tmp_path / "repo"
        clone = runner(
            ["git", "clone", "--depth", "1", f"https://github.com/{repo_ref}.git", str(repo_dir)],
            capture_output=True,
            text=True,
            timeout=45,
        )
        if clone.returncode != 0:
            return {"status": "clone_failed", "url": url, "repo": repo_ref, "error": clone.stderr[-1000:], "sandbox_profile": SANDBOX_PROFILE}
        script = tmp_path / "scan.py"
        script.write_text(STATIC_SCAN_SCRIPT)
        scan = runner(
            [
                "docker", "run", "--rm", "--network", "none", "--cpus", "1", "--memory", "256m",
                "--read-only", "--user", "65534:65534",
                "-v", f"{repo_dir}:/assessment:ro", "-v", f"{script}:/scan.py:ro",
                "python:3.11-alpine", "python", "/scan.py",
            ],
            capture_output=True,
            text=True,
            timeout=40,
        )
        if scan.returncode != 0:
            return {"status": "scan_failed", "url": url, "repo": repo_ref, "error": scan.stderr[-1000:], "sandbox_profile": SANDBOX_PROFILE}
        try:
            parsed_output = json.loads(scan.stdout or "{}")
        except json.JSONDecodeError:
            parsed_output = {"raw_stdout": scan.stdout[-2000:]}
        return {"status": "ok", "url": url, "repo": repo_ref, "scan": parsed_output, "sandbox_profile": SANDBOX_PROFILE}
