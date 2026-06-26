const $ = (id) => document.getElementById(id);
let latestMarkdown = "";
let latestSafeReply = "";

const sample = `Hi Dan, urgent one. I’m Alex from ChainHire.
We have a confidential AI crypto platform role, £90,000 - £110,000, remote UK.
Can we move to Telegram today? The assessment is here: https://bit.ly/fake-assessment
You may need to clone the repo, run npm install locally and connect your wallet to test the flow.`;

const laneLabels = {
  original_jd_recon: "Original JD recon",
  recruiter_identity: "Recruiter identity",
  agency_legitimacy: "Agency legitimacy",
  client_company: "Client company",
  job_jd_verification: "JD verification",
  security_assessment: "Security assessment",
  reputation_pattern: "Reputation pattern",
};

const verdictLabels = {
  verified: "Verified",
  partially_verified: "Partially verified",
  unverified: "Unverified",
  concerning: "Concerning",
  not_applicable: "Not applicable",
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function fillList(id, items) {
  const el = $(id);
  el.innerHTML = "";
  const clean = (items || []).filter(Boolean);
  if (!clean.length) {
    const li = document.createElement("li");
    li.textContent = "None yet.";
    el.appendChild(li);
    return;
  }
  for (const item of clean) {
    const li = document.createElement("li");
    li.textContent = item;
    el.appendChild(li);
  }
}

function markdownSection(markdown, heading) {
  const marker = `## ${heading}`;
  const start = markdown.indexOf(marker);
  if (start === -1) return [];
  const next = markdown.indexOf("\n## ", start + marker.length);
  const body = markdown.slice(start + marker.length, next === -1 ? undefined : next);
  return body
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.startsWith("- "))
    .map((line) => line.slice(2));
}

function setStatus(message, mode = "idle") {
  const bar = $("statusBar");
  bar.textContent = message;
  bar.className = `status-bar ${mode}`;
}

function actionFromV1(result) {
  if (!result || !result.decision) return null;
  const levelByDecision = {
    "Safe to reply": "safe",
    "Proceed with qualifying questions": "safe",
    "Safe admin reply only": "safe",
    "Ask verification question first": "caution",
    "Hold until basics are confirmed": "caution",
    "Deep check needed": "deep_check",
    "Do not engage": "stop",
  };
  return {
    label: result.decision,
    level: levelByDecision[result.decision] || "deep_check",
    reason: result.reason || "No reason supplied.",
  };
}

function setFinalAction(action) {
  const card = $("decisionCard");
  const label = $("finalActionLabel");
  const reason = $("finalActionReason");
  label.className = "";
  card.className = "panel decision-card empty";
  if (!action) {
    label.textContent = "Awaiting check";
    reason.textContent = "Run a check to get a decision.";
    return;
  }
  label.textContent = action.label;
  label.className = `action-${action.level}`;
  card.className = `panel decision-card decision-${action.level}`;
  reason.textContent = action.reason;
}

function setScore(score) {
  const value = $("scoreValue");
  const band = $("scoreBand");
  if (!score) {
    value.textContent = "–/100";
    band.textContent = "not run";
    band.className = "";
    return;
  }
  value.textContent = `${score.overall}/100`;
  band.textContent = `${score.band} risk · ${score.confidence} confidence`;
  band.className = `score-${score.band}`;
}

function shortText(value, max = 150) {
  const text = String(value || "").trim();
  if (!text || text.startsWith("{") || text.startsWith("[")) return "";
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

function evidenceWeight(row) {
  const laneScore = {
    security_assessment: 0,
    recruiter_identity: 1,
    job_jd_verification: 2,
    reputation_pattern: 3,
    client_company: 4,
    agency_legitimacy: 5,
  }[row.lane] ?? 9;
  const confidenceScore = {high: 0, medium: 1, low: 2}[row.confidence] ?? 2;
  const sourcePenalty = row.source_type === "tool_result" ? 2 : 0;
  return laneScore * 10 + confidenceScore + sourcePenalty;
}

function driverLabel(row) {
  const text = `${row.finding || ""} ${row.quote || ""} ${row.source || ""}`.toLowerCase();
  if (text.includes("wallet")) return {label: "Wallet interaction requested before trust is established", severity: "bad"};
  if (text.includes("telegram") || text.includes("off-platform") || text.includes("off platform")) return {label: "Asked to move off-platform before verification", severity: "bad"};
  if (text.includes("bit.ly") || text.includes("shortener") || text.includes("shortened")) return {label: "Shortened assessment/job link needs expansion before clicking", severity: "warn"};
  if (text.includes("npm install") || text.includes("pip install") || text.includes("install command") || text.includes("dependency")) return {label: "Assessment may require installing dependencies", severity: "bad"};
  if (text.includes("clone") || text.includes("repo") || text.includes("repository") || text.includes("run locally") || text.includes("code-assessment")) return {label: "Assessment may require local code execution", severity: "bad"};
  if (text.includes("urgent") || text.includes("today")) return {label: "Urgency pressure is present", severity: "warn"};
  if (text.includes("official") && (text.includes("career") || text.includes("jobs"))) return {label: "Official job/JD evidence was found", severity: "good"};
  if (text.includes("dns") || text.includes("has_mx")) return {label: "Recruiter email domain has DNS/MX evidence", severity: "good"};
  if (text.includes("rdap") || text.includes("registration_date")) return {label: "Domain registration data was checked", severity: "good"};
  if (text.includes("companies house") || text.includes("company_number")) return {label: "Company registration evidence was checked", severity: "good"};
  if ((row.finding || "").toLowerCase().includes("deterministic safety scanner")) return null;
  if (row.confidence === "high" && row.lane === "security_assessment") return {label: row.finding || "High-confidence security signal", severity: "warn"};
  return null;
}

function renderEvidence(rows) {
  const evidence = (rows || []).slice().sort((a, b) => evidenceWeight(a) - evidenceWeight(b));
  const seen = new Set();
  const drivers = [];
  for (const row of evidence) {
    const driver = driverLabel(row);
    if (!driver || seen.has(driver.label)) continue;
    seen.add(driver.label);
    drivers.push(driver);
    if (drivers.length >= 6) break;
  }

  $("summaryPill").textContent = `${drivers.length} reasons`;
  const list = $("keyEvidence");
  list.innerHTML = "";
  if (!drivers.length) {
    list.innerHTML = '<li class="empty-driver">No main reasons yet. Raw evidence is still available below.</li>';
    return;
  }
  for (const driver of drivers) {
    const li = document.createElement("li");
    li.className = `driver driver-${driver.severity}`;
    li.textContent = driver.label;
    list.appendChild(li);
  }
}

function renderOpportunityRead(read) {
  const pill = $("opportunityPill");
  const summary = $("opportunitySummary");
  const metrics = $("opportunityMetrics");
  const salary = $("salaryStance");
  const questions = $("opportunityQuestions");
  const data = read || {};
  const assessed = data.summary || data.recommended_action;
  pill.textContent = assessed ? data.recommended_action || "assessed" : "not assessed";
  summary.textContent = data.summary || "Run a check to separate legitimacy, security risk, and opportunity fit.";
  const cells = [
    ["Legitimacy", data.legitimacy || "unknown"],
    ["Security risk", data.security_risk || "unknown"],
    ["Opportunity fit", data.opportunity_fit || "unknown"],
    ["Reply focus", data.reply_focus || "not generated"],
  ];
  metrics.innerHTML = cells.map(([label, value]) => {
    const slug = String(value).toLowerCase().replace(/[^a-z0-9_-]+/g, "-");
    return `
    <article class="opportunity-metric metric-${escapeHtml(slug)}">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </article>
  `;
  }).join("");
  salary.textContent = data.salary_stance || "";
  questions.innerHTML = "";
  for (const question of (data.open_questions || []).slice(0, 5)) {
    const li = document.createElement("li");
    li.textContent = question;
    questions.appendChild(li);
  }
}

function renderVerificationDigest(cards) {
  const grid = $("verificationDigest");
  const pill = $("digestPill");
  const items = cards || [];
  pill.textContent = `${items.length} checks`;
  grid.innerHTML = "";
  if (!items.length) {
    grid.innerHTML = '<article class="digest-card empty">No readable verification checks yet. Raw evidence is still available below.</article>';
    return;
  }
  for (const card of items) {
    const article = document.createElement("article");
    article.className = `digest-card digest-${card.status || "info"}`;
    const dates = Object.entries(card.dates || {})
      .map(([key, value]) => `<span><b>${escapeHtml(key.replaceAll("_", " "))}</b>: ${escapeHtml(value)}</span>`)
      .join("");
    const details = (card.details || []).slice(0, 4).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
    article.innerHTML = `
      <div class="digest-top">
        <strong>${escapeHtml(card.title)}</strong>
        <span class="digest-status">${escapeHtml(card.status || "info")}</span>
      </div>
      <p>${escapeHtml(card.plain_english)}</p>
      <div class="digest-meta">
        <span><b>Check</b>: ${escapeHtml(card.technical_check)}</span>
        <span><b>Source</b>: ${escapeHtml(card.source)}</span>
        ${dates}
      </div>
      <p class="why">${escapeHtml(card.why_it_matters)}</p>
      ${details ? `<ul>${details}</ul>` : ""}
    `;
    grid.appendChild(article);
  }
}

function renderLaneCards(lanes) {
  const grid = $("laneCards");
  grid.innerHTML = "";
  const entries = Object.entries(lanes || {});
  if (!entries.length) {
    grid.innerHTML = '<article class="lane-card empty">Run a check to see lane reports.</article>';
    return;
  }

  const order = ["original_jd_recon", "security_assessment", "recruiter_identity", "client_company", "job_jd_verification", "agency_legitimacy", "reputation_pattern"];
  entries.sort(([a], [b]) => order.indexOf(a) - order.indexOf(b));

  for (const [lane, report] of entries) {
    const concerns = (report.concerns || []).slice(0, 2).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
    const gaps = (report.gaps || []).slice(0, 1).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
    const card = document.createElement("article");
    card.className = `lane-card verdict-${report.verdict}`;
    card.innerHTML = `
      <div class="lane-top">
        <h3>${escapeHtml(laneLabels[lane] || lane)}</h3>
        <span class="lane-pill">${escapeHtml(verdictLabels[report.verdict] || report.verdict)} · ${escapeHtml(report.confidence)}</span>
      </div>
      <p>${escapeHtml(report.summary || "No summary.")}</p>
      ${concerns || gaps ? `<ul>${concerns}${gaps}</ul>` : ""}
    `;
    grid.appendChild(card);
  }
}

function renderRecon(recon) {
  const pill = $("reconPill");
  const summary = $("reconSummary");
  const facts = $("reconFacts");
  const company = recon?.inferred_client_company;
  const score = recon?.confidence_score;
  if (!company) {
    pill.textContent = "no confident lead yet";
    summary.textContent = "The recon agent did not find a threshold-confident company/JD lead. Other agents continue from neutral facts only.";
    facts.innerHTML = '<span class="empty-chip">No shared inferred company.</span>';
    return;
  }
  pill.textContent = `${score || "?"}/100 confidence`;
  summary.textContent = recon.summary || "Recon found a threshold-gated company/JD lead for downstream verification.";
  const items = [
    `Likely company: ${company}`,
    recon.matched_original_jd_url ? `Matched JD: ${recon.matched_original_jd_url}` : "Matched JD URL: not available",
    (recon.matched_fields || []).length ? `Matched clues: ${(recon.matched_fields || []).join(", ")}` : "Matched clues: not supplied",
  ];
  facts.innerHTML = "";
  for (const item of items) {
    const chip = document.createElement("span");
    chip.className = "chip chip-medium";
    chip.textContent = item;
    facts.appendChild(chip);
  }
}

function renderEvidenceLedger(rows) {
  const body = $("evidenceLedger");
  body.innerHTML = "";
  if (!rows || rows.length === 0) {
    body.innerHTML = '<tr><td colspan="5">No evidence yet.</td></tr>';
    return;
  }
  for (const row of rows) {
    const tr = document.createElement("tr");
    for (const key of ["lane", "source", "finding", "quote", "confidence"]) {
      const td = document.createElement("td");
      td.textContent = row[key] || "–";
      tr.appendChild(td);
    }
    body.appendChild(tr);
  }
}

function renderV1(result) {
  const details = result.details || {};
  const ledger = details.evidence_ledger || [];
  latestMarkdown = result.markdown || "";
  latestSafeReply = result.safe_next_question || "";

  setFinalAction(actionFromV1(result));
  setScore(result.score);
  $("safeQuestion").textContent = latestSafeReply || "Ask for official JD, end client, and assessment safety details.";
  renderEvidence(ledger);
  renderOpportunityRead(details.opportunity_read || {});
  renderVerificationDigest(details.verification_digest || []);
  renderEvidenceLedger(ledger);
  renderRecon(details.original_jd_recon || {});
  renderLaneCards(details.lane_reports || {});
  fillList("laneReports", Object.entries(details.lane_reports || {}).map(([lane, report]) => `${lane}: ${report.verdict} / ${report.confidence}`));
  fillList("traceOrder", details.trace || []);
  fillList("verified", markdownSection(latestMarkdown, "Verified"));
  fillList("unverified", [...(details.gaps || []), ...markdownSection(latestMarkdown, "Unverified")]);
  fillList("concerning", markdownSection(latestMarkdown, "Concerning"));
  $("markdown").textContent = latestMarkdown || "Run a check to generate copyable Markdown.";
  setStatus(`Check complete · ${result.decision} · ${result.score?.overall ?? "–"}/100`, result.decision === "Do not engage" ? "bad" : "ok");
}

function renderLegacy(result) {
  latestMarkdown = result.markdown || result.final_report || "";
  latestSafeReply = result.safe_next_question || "";
  setFinalAction(result.final_action || null);
  setScore(result.score || null);
  renderEvidence([]);
  renderOpportunityRead({});
  renderVerificationDigest([]);
  renderEvidenceLedger([]);
  renderRecon({});
  renderLaneCards({});
  fillList("verified", result.verified);
  fillList("unverified", result.unverified);
  fillList("concerning", result.concerning);
  $("safeQuestion").textContent = latestSafeReply || "Run a check.";
  fillList("laneReports", []);
  fillList("traceOrder", []);
  $("markdown").textContent = latestMarkdown || "Run a check to generate copyable Markdown.";
}

function render(result) {
  if (result && result.status === "ok" && result.details) {
    renderV1(result);
  } else {
    renderLegacy(result || {});
  }
}

async function postCheck(path, buttonId, label) {
  const text = $("message").value.trim();
  if (!text) {
    $("message").focus();
    setStatus("Paste a recruiter message first.", "warn");
    return;
  }
  const button = $(buttonId);
  button.disabled = true;
  button.textContent = "Checking…";
  setStatus("Running JD recon, then independent verifier lanes. This can take a minute with live LLM/tool calls…", "busy");
  try {
    const res = await fetch(path, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({text}),
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(payload.error || `HTTP ${res.status}`);
    render(payload);
  } catch (err) {
    setStatus(`Check failed: ${err.message}`, "bad");
  } finally {
    button.disabled = false;
    button.textContent = label;
  }
}

function fullCheck() {
  return postCheck("/api/full-check", "fullCheckBtn", "Run full check");
}

async function copyText(buttonId, value, resetLabel) {
  if (!value) {
    setStatus("Nothing to copy yet — run a check first.", "warn");
    return;
  }
  await navigator.clipboard.writeText(value);
  const button = $(buttonId);
  button.textContent = "Copied";
  setTimeout(() => (button.textContent = resetLabel), 900);
}

$("fullCheckBtn").addEventListener("click", fullCheck);
$("sampleBtn").addEventListener("click", () => {
  $("message").value = sample;
  setStatus("Risky sample loaded. Run full check when ready.", "idle");
});
$("copyReplyBtn").addEventListener("click", () => copyText("copyReplyBtn", latestSafeReply, "Copy safe reply"));
$("copyBtn").addEventListener("click", () => copyText("copyBtn", latestMarkdown, "Copy report"));

$("message").value = sample;
