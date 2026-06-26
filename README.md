# Recruiter Risk Triage

A local-first agentic dashboard for deciding whether a recruiter message is worth replying to — and how to reply safely.

It was built for messy real-world outreach: LinkedIn DMs, recruiter emails, copied job descriptions, assessment links, GitHub repos, package-install requests, and crypto/Web3 roles. Instead of saying “looks legit” from vibes, it breaks the message into evidence lanes, checks what can be checked, flags unsafe behaviour, and produces a practical next step.

## Why this exists

Recruiter outreach has two separate problems that usually get mixed together:

1. **Is this real?**
   - Does the recruiter domain resolve?
   - Is there an official job page?
   - Does the agency/company exist?
   - Does the job description look copied from a real client role?

2. **Is this safe and worth time?**
   - Are they pushing a shortened link, wallet connection, local code execution, or package install?
   - Are they trying to move off-platform too early?
   - Is the role aligned with salary, remote, stack, and career goals?

This tool treats those as different questions. A role can be real but not worth pursuing. A recruiter can have a real email domain but still send a risky assessment. The dashboard keeps those distinctions visible.

## What it does

Paste recruiter outreach and run a full check. The app returns:

- **Decision** — e.g. `Do not engage`, `Hold until basics are confirmed`, `Proceed with qualifying questions`.
- **Safe reply** — a reply that asks for the right proof without taking unsafe action.
- **Main reasons** — the top human-readable decision drivers, not raw scanner spam.
- **Opportunity read** — legitimacy, security risk, opportunity fit, salary stance, reply focus, and open questions.
- **Verification digest** — plain-English technical checks such as DNS/MX, RDAP, Companies House, official/candidate JD evidence, and dates checked.
- **Original JD recon** — attempts to infer the likely original job/client from title, stack, salary, location, and wording.
- **Independent lane reports** — separate agent lanes for recruiter identity, agency legitimacy, client/company, JD verification, security assessment, and reputation patterns.
- **Raw details** — collapsed evidence ledger and Markdown report for audit/debugging.

## Example outcomes

### Risky assessment / crypto bait

If a message asks to move to Telegram, open a shortened assessment link, run local code, install packages, or connect a wallet, the expected result is:

```text
Decision: Do not engage
Security risk: high
Opportunity fit: poor
Safe reply: ask for official JD/company proof and confirmation that no wallet/local-code/package-install assessment is required.
```

### Real-looking recruiter role

If a message includes a plausible corporate recruiter domain and official careers URL, but salary/client/remote details are still unclear, the expected result is:

```text
Decision: Proceed with qualifying questions / Hold until basics are confirmed
Legitimacy: high
Security risk: low
Opportunity fit: medium until salary, remote setup, end client, and work split are confirmed.
```

## Architecture

The full check is graph-shaped:

```text
extract_entities
→ deterministic_risk_scan
→ original_jd_recon              (reverse-searches JD clues to infer likely end client)
  ├── recruiter_identity        (email/domain checks)
  ├── agency_legitimacy         (registry/search/domain checks)
  ├── client_company            (verifies named or inferred company lead)
  ├── job_jd_verification       (checks official/matched JD and GitHub metadata)
  ├── security_assessment       (link/package/repo/wallet/code-execution risk)
  └── reputation_pattern        (agency/company warning patterns)
→ merge_evidence
→ final_report
```

`original_jd_recon` runs first as a neutral lead generator. Only threshold-confident structured facts — such as inferred company, matched public JD URL, confidence score, and matched fields — are shared downstream. Other lanes do not see each other's conclusions; they independently verify against the original outreach and tool outputs.

The final evidence list is locked to input/tool-produced evidence. LLM lane synthesis can write summaries, but model-invented evidence is discarded.

Static architecture diagrams are committed in `artifacts/graph_mermaid*.png` for demo/readme use.

## Safety boundaries

This is not a “magic verifier” and it should not be treated as one.

- The app is intended to run locally on `127.0.0.1`.
- `.env` is ignored by git; `.env.example` is safe to commit.
- Live URL expansion is off by default via `EXPAND_URLS_LIVE=false`.
- Live URL/web metadata fetches only allow public `http/https` targets and block localhost, private IP ranges, link-local metadata services, non-HTTP schemes, embedded credentials, and unsafe redirects.
- Assessment repo sandboxing is off by default via `SECURITY_SANDBOX_LIVE=false`.
- With sandboxing disabled, GitHub/code-assessment links produce a no-network Docker sandbox **plan** and a “do not run on host” warning.
- With sandboxing enabled, analysis is designed for static inspection inside Docker with `--network none`, read-only mounts, non-root user, CPU/memory/time limits, and no project install/test script execution.

## Run locally

```bash
python3 -m pip install -r requirements.txt
python3 -m app.server
```

Open:

```text
http://127.0.0.1:8765
```

## Test

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest -q
```

Current expected suite:

```text
57 passed
```

## API

```bash
curl -s http://127.0.0.1:8765/api/full-check \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hi, we have a role. Please run npm install and connect your wallet for the assessment."}'
```

The endpoint returns the same structured output used by the UI: decision, score, safe reply, lane reports, verification digest, opportunity read, evidence ledger, gaps, and Markdown report.

## Configuration

Copy `.env.example` to `.env` and fill in only the integrations you want:

```bash
cp .env.example .env
```

Core optional keys:

```bash
COMPANIES_HOUSE_API_KEY=
SEARCH_API_PROVIDER=brave
SEARCH_API_KEY=
EXPAND_URLS_LIVE=false
SECURITY_SANDBOX_LIVE=false
```

Optional enrichment/tracing:

```bash
GITHUB_TOKEN=
URLSCAN_API_KEY=
VIRUSTOTAL_API_KEY=
LANGSMITH_TRACING=false
LANGSMITH_PROJECT=recruiter-risk-triage-v1
LANGSMITH_API_KEY=
```

Optional LLM lane synthesis:

```bash
ENABLE_LLM_LANE_SYNTHESIS=false
LLM_LANE_SYNTHESIS_LANES=original_jd_recon,recruiter_identity,agency_legitimacy,client_company,job_jd_verification,security_assessment,reputation_pattern
LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-4-5-20250929
ANTHROPIC_API_KEY=
LLM_API_BASE_URL=
LLM_API_KEY=
```

If synthesis is disabled or no LLM key is present, the graph falls back to deterministic lane reports.

## Current limitations

- It is a prototype, not a production SaaS app.
- No authentication is included because it is designed for local use.
- Dependency versions are pinned in requirements files, but there is no full lockfile yet.
- Public web/search results can be stale or incomplete; the UI labels candidate evidence separately from verified evidence.
- Companies House and search quality depend on configured API keys.

## Project intent

This is a portfolio/demo project showing a practical agent workflow: not just “ask an LLM if a message is suspicious”, but decompose the decision into verifiable lanes, preserve the evidence trail, and return a safe next action that fits a real career workflow.
