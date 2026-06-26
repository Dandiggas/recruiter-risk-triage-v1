# Recruiter Risk Triage V1

Local-first triage desk for recruiter/job outreach.

This is intentionally **not** a fake verifier. It extracts clues from pasted outreach, flags scam/security patterns, and gives Dan a safe next question plus live-research links.

## Run

```bash
python3 -m pip install -r requirements.txt
python3 -m app.server
```

Open: http://127.0.0.1:8765

## Test

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest -q
```

## V1 output contract

- Verified
- Unverified
- Concerning
- Safe next question
- Score
- Research links
- Verification digest cards: plain-English DNS/MX, RDAP, Companies House, website, and JD checks with checked/registered/incorporated/observed dates where available

## V1.5 LangGraph full check

The full check now runs a graph-shaped verification workflow:

```text
extract_entities
→ deterministic_risk_scan
→ original_jd_recon              (reverse-searches JD clues to infer likely end client)
  ├── recruiter_identity        (LLM chooses allowed identity tools)
  ├── agency_legitimacy         (LLM chooses allowed registry/search/domain tools)
  ├── client_company            (verifies named or threshold-inferred company lead)
  ├── job_jd_verification       (checks official/matched JD and GitHub metadata)
  ├── security_assessment       (behavioural risk first; URL/package/repo sandbox gate if artifacts exist)
  └── reputation_pattern        (checks agency/company warning patterns)
→ merge_evidence
→ final_report
```

Endpoint:

```bash
POST /api/full-check
{"text": "...recruiter message..."}
```

Current nodes are constrained tool-using agents. `original_jd_recon` runs first as a neutral lead generator: it reverse-searches title, salary, location, stack, phrasing, and assessment clues to find a likely original public JD. Only threshold-confident structured facts (`inferred_client_company`, `confidence_score >= 70`, `matched_original_jd_url`, `matched_fields`) are shared downstream. Other lanes do not see each other's verdicts/summaries; they independently verify the recon lead or original outreach facts. Tool outputs become the only new evidence.

The committed `artifacts/graph_mermaid*.png` files are static architecture diagrams for README/demo use, not runtime outputs.

- Original JD Recon: Search API + optional metadata fetch to infer likely end client from JD clues
- Recruiter Identity: email-domain DNS/MX checks
- Agency Legitimacy: Companies House + Search API + RDAP/WHOIS
- Client / Company: Search API + optional website metadata fetch
- Job/JD Verification: GitHub public repo metadata + optional careers-page metadata fetch
- Security Assessment: optional live URL expansion + NPM/PyPI package metadata checks

With synthesis enabled, the LLM is inside each lane agent: it chooses from that lane's allowed tools, observes their results, then writes the lane report. The final evidence list is still locked to input/tool-produced evidence; model-invented evidence is discarded.

```bash
ENABLE_LLM_LANE_SYNTHESIS=true
LLM_LANE_SYNTHESIS_LANES=original_jd_recon,recruiter_identity,agency_legitimacy,client_company,job_jd_verification,security_assessment,reputation_pattern
LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-4-5-20250929
ANTHROPIC_API_KEY=***
```

The current setup uses Claude Sonnet for each lane agent. If synthesis is enabled but no LLM key is present, the graph falls back to deterministic lane reports.

Optional LangSmith tracing is wired around the full graph, each graph node, each lane-agent loop, LLM calls, and agent-selected tools:

```bash
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=recruiter-risk-triage-v1
LANGSMITH_API_KEY=***
```

`LANGSMITH_TRACING=true` without `LANGSMITH_API_KEY` is intentionally a no-op, so local tests do not spam hosted LangSmith with unauthorized trace attempts.

## API key/config setup

Create `.env` in the project root:

```bash
COMPANIES_HOUSE_API_KEY=...
SEARCH_API_PROVIDER=brave
SEARCH_API_KEY=...
EXPAND_URLS_LIVE=false
SECURITY_SANDBOX_LIVE=false
```

Optional later:

```bash
GITHUB_TOKEN=...
URLSCAN_API_KEY=...
VIRUSTOTAL_API_KEY=...
```

Keep `EXPAND_URLS_LIVE=false` unless you want the app to make live GET requests to pasted links/shorteners. The tool is read-only, but it still touches the remote URL. Live URL fetches are guarded to allow only public `http/https` targets and block localhost, private IP ranges, link-local metadata services, non-HTTP schemes, embedded credentials, and unsafe redirects.

Keep `SECURITY_SANDBOX_LIVE=false` by default. With it disabled, GitHub/code-assessment links produce a no-network Docker sandbox **plan** and a hard "do not run on host" warning. Set it to `true` only when you explicitly want the security lane to clone the repo and run static analysis inside Docker with `--network none`, read-only mounts, non-root user, CPU/memory/time limits, and no project install/test script execution.
