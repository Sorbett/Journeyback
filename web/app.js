const elements = {
  itinerary: document.querySelector("#itinerary"),
  signalList: document.querySelector("#signal-list"),
  monitoringStatus: document.querySelector("#monitoring-status"),
  simulateButton: document.querySelector("#simulate-button"),
  anotherButton: document.querySelector("#another-button"),
  loadingPanel: document.querySelector("#loading-panel"),
  loadingTitle: document.querySelector("#loading-title"),
  loadingDetail: document.querySelector("#loading-detail"),
  idleWorkspace: document.querySelector("#idle-workspace"),
  recoveryWorkspace: document.querySelector("#recovery-workspace"),
  disruptionAlert: document.querySelector("#disruption-alert"),
  agentActivity: document.querySelector("#agent-activity"),
  decisionCard: document.querySelector("#decision-card"),
  benefitMatch: document.querySelector("#benefit-match"),
  claimItems: document.querySelector("#claim-items"),
  completionValue: document.querySelector("#completion-value"),
  walletProgressBar: document.querySelector("#wallet-progress-bar"),
  workspaceProgress: document.querySelector("#workspace-progress"),
  workspaceProgressBar: document.querySelector("#workspace-progress-bar"),
  workspaceActions: document.querySelector("#workspace-actions"),
  processingMode: document.querySelector("#processing-mode"),
  handoffStatus: document.querySelector("#handoff-status"),
  evidenceStatus: document.querySelector("#evidence-status"),
  evidenceReview: document.querySelector("#evidence-review"),
  evidenceReviewContent: document.querySelector("#evidence-review-content"),
  artifactDialog: document.querySelector("#artifact-dialog"),
  artifactTitle: document.querySelector("#artifact-title"),
  artifactContent: document.querySelector("#artifact-content"),
  artifactCopy: document.querySelector("#artifact-copy"),
  artifactDownload: document.querySelector("#artifact-download"),
};

let currentTrip = null;
let currentRecovery = null;
let submittedProductCode = "";
let submittedEvidenceIds = [];
let latestUpload = null;
let decisionChange = null;
let artifactCopyText = "";
let loadingTimer = null;
let guidedPipelineRun = null;
let latestPipelineArtifact = null;

const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;").replaceAll("'", "&#039;");

function safeUrl(value) {
  try {
    const url = new URL(String(value), window.location.origin);
    return ["https:", "http:"].includes(url.protocol) ? escapeHtml(url.href) : "#";
  } catch (_) {
    return "#";
  }
}

function segmentIcon(type) {
  if (type === "flight") {
    return `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m3 11 18-7-7 18-3-8-8-3Z"></path><path d="m11 14 4-4"></path></svg>`;
  }
  return `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 21V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16M8 8h2m4 0h2M8 12h2m4 0h2M9 21v-5h6v5"></path></svg>`;
}

function renderTrip(trip) {
  currentTrip = trip;
  const shareableUrl = new URL(window.location.href);
  shareableUrl.searchParams.set("case_id", trip.case_id);
  window.history.replaceState(null, "", shareableUrl);
  document.querySelector("#trip-title").textContent = trip.title;
  document.querySelector("#trip-meta").textContent = `${trip.date_range} · ${trip.route}`;
  document.querySelector("#segment-count").textContent = `${trip.segments.length} reservations`;
  document.querySelector("#case-id").textContent = trip.case_id;
  document.querySelector("#demo-query").textContent = `${trip.simulation.event_label} · ${trip.card.product_name}`;
  document.title = `JourneyBack | ${trip.title}`;

  elements.monitoringStatus.className = `monitoring-status ${trip.monitoring.status}`;
  elements.monitoringStatus.innerHTML = `
    <span class="status-pulse" aria-hidden="true"></span>
    <div><strong>${escapeHtml(trip.monitoring.label)}</strong><small>${escapeHtml(trip.monitoring.last_checked)}</small></div>
  `;

  elements.itinerary.innerHTML = trip.segments.map((segment) => {
    const name = segment.type === "flight" ? segment.service_number : segment.name;
    const meta = segment.type === "flight"
      ? `${segment.origin_code} → ${segment.destination_code} · ${segment.departure_local}`
      : `${segment.location} · ${segment.check_in}–${segment.check_out}`;
    return `
      <article class="segment ${escapeHtml(segment.status)}">
        <span class="segment-icon">${segmentIcon(segment.type)}</span>
        <div><strong>${escapeHtml(name)}</strong><span>${escapeHtml(meta)}</span></div>
        <span class="segment-status ${escapeHtml(segment.status)}">${escapeHtml(segment.status_label)}</span>
      </article>
    `;
  }).join("");

  const signalRows = [
    ["Itinerary", `${trip.segments.length} reservations`, true],
    ["Card payment", trip.card.payment_verified ? "Verified" : "Needs confirmation", trip.card.payment_verified],
    ["Carrier status", trip.disruption ? trip.monitoring.label : "Connected", true],
  ];
  elements.signalList.innerHTML = signalRows.map(([label, value, ready]) => `
    <li><span><i class="${ready ? "ready" : "attention"}">${ready ? "✓" : "!"}</i>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></li>
  `).join("");
}

function renderRecovery(data) {
  currentRecovery = data;
  renderTrip(data.trip);
  elements.idleWorkspace.classList.add("hidden");
  elements.recoveryWorkspace.classList.remove("hidden");
  document.querySelector("#scenario-disclosure").textContent = data.workspace.disclosure;
  elements.simulateButton.disabled = true;
  elements.simulateButton.querySelector("span").textContent = "Disruption active";

  const disruption = data.disruption;
  const flight = data.trip.segments.find((segment) => segment.type === "flight");
  elements.disruptionAlert.innerHTML = `
    <div class="alert-symbol" aria-hidden="true">!</div>
    <div>
      <p class="eyebrow">DISRUPTION DETECTED</p>
      <h2>${escapeHtml(disruption.headline)}</h2>
      <p>${escapeHtml(flight.service_number)} · ${escapeHtml(flight.origin_code)} to ${escapeHtml(flight.destination_code)} · ${escapeHtml(disruption.duration)}</p>
    </div>
    <div class="event-source"><span>Source</span><strong>${escapeHtml(disruption.source)}</strong></div>
  `;

  renderActivity(data.workspace);
  renderDecision(data);
  renderBenefit(data);
  renderWallet(data);
  renderWorkspaceActions(data.workspace.handoff);
  renderEvidenceReview(data);
  elements.processingMode.textContent = data.workspace.processing.is_live ? "Live AI + RAG" : "Expected path";
  elements.processingMode.className = `mode-chip ${data.workspace.processing.is_live ? "live" : ""}`;
  elements.handoffStatus.textContent = data.workspace.handoff.ready ? "Review-ready" : "Draft mode";
}

function renderActivity(workspace) {
  const progress = workspace.progress;
  elements.workspaceProgress.textContent = `${progress.completed}/${progress.total}`;
  elements.workspaceProgressBar.style.width = `${progress.percent}%`;
  elements.workspaceProgressBar.parentElement.setAttribute("aria-valuenow", progress.percent);
  elements.agentActivity.innerHTML = workspace.activity.map((item, index) => `
    <li class="activity-item ${escapeHtml(item.status)}" style="--delay:${index * 70}ms">
      <span class="activity-marker">${item.status === "complete" ? "✓" : item.status === "blocked" ? "—" : "!"}</span>
      <div><strong>${escapeHtml(item.label)}</strong><span>${escapeHtml(item.detail)}</span><small>${escapeHtml(item.source)}</small></div>
    </li>
  `).join("");
}

function renderDecision(data) {
  const workspace = data.workspace;
  const question = workspace.primary_question;
  let control = "";
  if (question?.type === "product") {
    const options = question.options.map((product) => `<option value="${escapeHtml(product.code)}">${escapeHtml(product.name)}</option>`).join("");
    control = `
      <form id="primary-input-form" class="primary-form product-question" data-evidence-code="${escapeHtml(question.evidence_code)}">
        <label for="product-choice">Card or insurance product</label>
        <div class="input-action-row">
          <select id="product-choice" required><option value="">Select the exact product</option>${options}</select>
          <button class="button button-primary" type="submit">Confirm &amp; run live analysis</button>
        </div>
      </form>
    `;
  } else if (question?.type === "upload") {
    control = `
      <form id="primary-input-form" class="primary-form upload-question" data-evidence-code="${escapeHtml(question.evidence_code)}">
        <label id="drop-zone" class="drop-zone">
          <input id="evidence-file" type="file" required accept=".pdf,.jpg,.jpeg,.png,.txt,application/pdf,image/jpeg,image/png,text/plain">
          <span class="upload-icon">↑</span>
          <strong id="file-label">Drop a document here or choose a file</strong>
          <small>${question.accepted_formats.map(escapeHtml).join(" · ")} · up to 1.5 MB</small>
        </label>
        <label for="evidence-note">What should JourneyBack verify?</label>
        <input id="evidence-note" type="text" maxlength="500" required placeholder="For example: carrier confirmed a 6-hour delay">
        <button class="button button-primary" type="submit">Upload &amp; run live analysis</button>
      </form>
    `;
  } else if (question?.type === "review") {
    control = `<button class="button button-primary" type="button" data-action-code="build_evidence_pack">Build specialist review pack</button>`;
  } else {
    control = `
      <div class="ready-summary">
        <span class="ready-check">✓</span>
        <div><strong>No more customer input is blocking the handoff</strong><small>You can still inspect policy evidence before continuing.</small></div>
      </div>
    `;
  }

  const hasGuidedPipeline = Boolean(question?.guided_pipeline || guidedPipelineRun);
  if (hasGuidedPipeline && question?.type === "upload") {
    control = `
      <details class="manual-upload">
        <summary>Upload a file manually instead</summary>
        ${control}
      </details>
    `;
  }

  const changeMarkup = decisionChange ? `
    <div class="decision-change">
      <span>UPDATED</span>
      <div><strong>${escapeHtml(decisionChange.title)}</strong><small>${escapeHtml(decisionChange.detail)}</small></div>
    </div>
  ` : "";
  elements.decisionCard.className = `decision-card ${workspace.phase}`;
  elements.decisionCard.innerHTML = `
    <div class="decision-topline">
      <span class="decision-state">${escapeHtml(workspace.phase_label)}</span>
      <small>${escapeHtml(workspace.processing.label)}</small>
    </div>
    <p class="eyebrow">${escapeHtml(question?.eyebrow || "RECOVERY PATH")}</p>
    <h2>${escapeHtml(workspace.headline)}</h2>
    <p class="decision-summary">${escapeHtml(workspace.summary)}</p>
    ${changeMarkup}
    ${guidedPipelineMarkup(question?.guided_pipeline)}
    ${control}
  `;
  bindPrimaryInput();
  const guidedButton = elements.decisionCard.querySelector("#run-guided-pipeline");
  if (guidedButton) guidedButton.addEventListener("click", runGuidedPipeline);
  const artifactButton = elements.decisionCard.querySelector("#open-guided-artifact");
  if (artifactButton && latestPipelineArtifact) {
    artifactButton.addEventListener("click", () => openArtifact(latestPipelineArtifact));
  }
  elements.decisionCard.querySelectorAll("[data-action-code]").forEach((button) => {
    button.addEventListener("click", () => performRecoveryAction(button.dataset.actionCode, button));
  });
}

function createGuidedPipelineRun() {
  return {
    status: "running",
    error: "",
    steps: [
      { id: "load", label: "Load curated test evidence", detail: "Three synthetic TXT files", status: "pending" },
      { id: "flight_ticket", label: "Upload ticket and itinerary", detail: "Persist and extract readable text", status: "pending" },
      { id: "carrier_confirmation", label: "Upload carrier confirmation", detail: "Verify the disruption record", status: "pending" },
      { id: "receipts", label: "Upload itemised receipts", detail: "Verify expense evidence", status: "pending" },
      { id: "analysis", label: "Run live policy analysis", detail: "LLM reasoning + BGE-M3 retrieval", status: "pending" },
      { id: "artifact", label: "Build specialist review pack", detail: "Reuse the grounded live result", status: "pending" },
    ],
  };
}

function guidedPipelineMarkup(config) {
  if (!config && !guidedPipelineRun) return "";
  const run = guidedPipelineRun;
  const steps = run?.steps || createGuidedPipelineRun().steps;
  const isRunning = run?.status === "running";
  const isComplete = run?.status === "complete";
  const isError = run?.status === "error";
  const stepsMarkup = steps.map((step, index) => {
    const marker = step.status === "complete" ? "✓" : step.status === "error" ? "!" : String(index + 1);
    const stateLabel = step.status === "running" ? "Running" : step.status === "complete" ? "Complete" : step.status === "error" ? "Failed" : "Waiting";
    return `
      <li class="guided-step ${escapeHtml(step.status)}">
        <span class="guided-step-marker">${marker}</span>
        <div><strong>${escapeHtml(step.label)}</strong><small>${escapeHtml(step.detail)}</small></div>
        <span class="guided-step-state">${stateLabel}</span>
      </li>
    `;
  }).join("");
  const title = isComplete
    ? "Full pipeline completed"
    : isError
      ? "Pipeline stopped at a failed step"
      : isRunning
        ? "Running the complete pipeline"
        : "Test the complete pipeline with one click";
  const description = isComplete
    ? "All three files were processed, policy evidence was retrieved and the review pack is ready."
    : isError
      ? run.error
      : "Use the matched synthetic evidence set and watch every real API stage complete.";

  return `
    <section class="guided-pipeline ${isComplete ? "complete" : isError ? "error" : isRunning ? "running" : "idle"}" aria-live="polite">
      <div class="guided-pipeline-heading">
        <div><p class="eyebrow">GUIDED PIPELINE TEST</p><h3>${escapeHtml(title)}</h3></div>
        <span>3 files · Live AI + BGE-M3</span>
      </div>
      <p>${escapeHtml(description)}</p>
      <ol class="guided-pipeline-steps">${stepsMarkup}</ol>
      <div class="guided-pipeline-actions">
        <button id="run-guided-pipeline" class="button button-primary" type="button" ${isRunning ? "disabled" : ""}>
          ${isRunning ? "Pipeline running…" : isComplete || isError ? "Run again" : escapeHtml(config?.label || "Run complete pipeline")}
        </button>
        ${isComplete && latestPipelineArtifact ? '<button id="open-guided-artifact" class="button button-secondary" type="button">Open review pack</button>' : ""}
      </div>
    </section>
  `;
}

function updateGuidedPipelineStep(stepId, status, detail = "") {
  if (!guidedPipelineRun) return;
  const step = guidedPipelineRun.steps.find((item) => item.id === stepId);
  if (step) {
    step.status = status;
    if (detail) step.detail = detail;
  }
  if (currentRecovery) renderDecision(currentRecovery);
}

function pauseForPipelinePaint(delay = 220) {
  return new Promise((resolve) => window.setTimeout(resolve, delay));
}

async function runGuidedPipeline() {
  if (!currentTrip || currentTrip.case_id !== "JB-SYN-0331") return;
  const before = currentRecovery?.benefit_match;
  guidedPipelineRun = createGuidedPipelineRun();
  latestPipelineArtifact = null;
  submittedProductCode = "";
  submittedEvidenceIds = [];
  latestUpload = null;
  renderDecision(currentRecovery);
  showEvidenceStatus("Running the curated end-to-end test…", "working");

  try {
    updateGuidedPipelineStep("load", "running", "Reading the matched evidence kit for JB-SYN-0331");
    const kit = await getJson(`/api/demo/pipeline-test-kit?case_id=${encodeURIComponent(currentTrip.case_id)}`);
    submittedProductCode = kit.product_code;
    await pauseForPipelinePaint();
    updateGuidedPipelineStep("load", "complete", `${kit.files.length} matched files ready`);

    for (const item of kit.files) {
      updateGuidedPipelineStep(item.evidence_code, "running", `Uploading ${item.file_name}`);
      latestUpload = await postJson("/api/evidence", {
        case_id: currentTrip.case_id,
        evidence_code: item.evidence_code,
        file_name: item.file_name,
        mime_type: item.mime_type,
        content_base64: item.content_base64,
        evidence_note: item.evidence_note,
      });
      if (!submittedEvidenceIds.includes(latestUpload.upload_id)) submittedEvidenceIds.push(latestUpload.upload_id);
      await pauseForPipelinePaint();
      const extraction = latestUpload.inspection?.text_extracted ? "text extracted" : "file persisted";
      updateGuidedPipelineStep(item.evidence_code, "complete", `${item.file_name} · ${extraction}`);
    }

    updateGuidedPipelineStep("analysis", "running", "Calling the LLM and retrieving product policy with BGE-M3");
    const data = await postJson("/api/reanalyse", {
      case_id: currentTrip.case_id,
      product_code: submittedProductCode,
      evidence_upload_ids: submittedEvidenceIds,
    });
    decisionChange = {
      title: before?.headline === data.benefit_match.headline ? "Evidence state refreshed" : "Policy guidance changed",
      detail: `${before?.headline || "Previous result"} → ${data.benefit_match.headline}`,
    };
    currentRecovery = data;
    const trace = data.trace || {};
    updateGuidedPipelineStep(
      "analysis",
      "complete",
      `${trace.retrieved_chunks || 0} policy chunks · ${trace.validated_citations || 0} citations · ${(data.response_time_ms / 1000).toFixed(1)}s`,
    );
    renderRecovery(data);

    updateGuidedPipelineStep("artifact", "running", "Packaging uploaded evidence and the grounded decision trace");
    latestPipelineArtifact = await postJson("/api/action", {
      case_id: currentTrip.case_id,
      action_code: "build_evidence_pack",
      product_code: submittedProductCode,
      evidence_upload_ids: submittedEvidenceIds,
    });
    await pauseForPipelinePaint();
    updateGuidedPipelineStep("artifact", "complete", "Downloadable review pack generated");
    guidedPipelineRun.status = "complete";
    renderRecovery(data);
    showEvidenceStatus("Complete: 3 files processed, live analysis run and review pack generated.", "success");
  } catch (error) {
    const activeStep = guidedPipelineRun.steps.find((step) => step.status === "running");
    if (activeStep) {
      activeStep.status = "error";
      activeStep.detail = error.message;
    }
    guidedPipelineRun.status = "error";
    guidedPipelineRun.error = error.message;
    renderDecision(currentRecovery);
    showEvidenceStatus(error.message, "error");
  }
}

function bindPrimaryInput() {
  const form = document.querySelector("#primary-input-form");
  if (!form) return;
  form.addEventListener("submit", (event) => submitPrimaryInput(event, form));
  const fileInput = form.querySelector('input[type="file"]');
  const dropZone = form.querySelector("#drop-zone");
  if (!fileInput || !dropZone) return;
  fileInput.addEventListener("change", () => updateFileLabel(fileInput.files[0]));
  ["dragenter", "dragover"].forEach((name) => dropZone.addEventListener(name, (event) => {
    event.preventDefault();
    dropZone.classList.add("dragging");
  }));
  ["dragleave", "drop"].forEach((name) => dropZone.addEventListener(name, (event) => {
    event.preventDefault();
    dropZone.classList.remove("dragging");
  }));
  dropZone.addEventListener("drop", (event) => {
    const file = event.dataTransfer.files[0];
    if (!file) return;
    const transfer = new DataTransfer();
    transfer.items.add(file);
    fileInput.files = transfer.files;
    updateFileLabel(file);
  });
}

function updateFileLabel(file) {
  const label = document.querySelector("#file-label");
  if (!label) return;
  label.textContent = file ? `${file.name} · ${formatBytes(file.size)}` : "Drop a document here or choose a file";
}

function renderBenefit(data) {
  const match = data.benefit_match;
  const evidence = match.policy_evidence || [];
  const statusLabel = String(match.expected_eligibility || match.status_title).replaceAll("_", " ");
  const citationMarkup = evidence.map((item, index) => `
    <a class="policy-source" href="${safeUrl(item.url)}" target="_blank" rel="noopener">
      <span>${index + 1}</span>
      <div><strong>${escapeHtml(item.section)}</strong><small>${escapeHtml(item.excerpt || item.citation || "Official public source")}</small></div>
      <i>↗</i>
    </a>
  `).join("");
  elements.benefitMatch.innerHTML = `
    <span class="match-status ${escapeHtml(match.status)}">${escapeHtml(statusLabel)}</span>
    <h3>${escapeHtml(match.headline)}</h3>
    <p>${escapeHtml(match.summary)}</p>
    <details class="policy-details" ${evidence.length === 1 ? "open" : ""}>
      <summary>${evidence.length} validated policy source${evidence.length === 1 ? "" : "s"}</summary>
      <div>${citationMarkup || '<p class="empty-copy">No benefit-specific citation is safe yet.</p>'}</div>
    </details>
    <div class="review-boundary"><span>Human review</span><p>No approval or payout is predicted.</p></div>
  `;
}

function renderWallet(data) {
  const pack = data.claim_pack;
  elements.completionValue.textContent = `${pack.completion_percent}%`;
  elements.walletProgressBar.style.width = `${pack.completion_percent}%`;
  elements.walletProgressBar.parentElement.setAttribute("aria-valuenow", pack.completion_percent);
  elements.claimItems.innerHTML = pack.items.map((item) => {
    const complete = item.status === "complete";
    const isPrimary = data.workspace.primary_question?.evidence_code === item.code;
    return `
      <div class="claim-item ${complete ? "complete" : "required"} ${isPrimary ? "primary" : ""}">
        <span class="claim-check">${complete ? "✓" : isPrimary ? "1" : "•"}</span>
        <div><strong>${escapeHtml(item.label)}</strong><small>${escapeHtml(item.source)}</small></div>
        <span class="claim-state">${complete ? "Ready" : isPrimary ? "Needed now" : "Queued"}</span>
      </div>
    `;
  }).join("");
}

function renderWorkspaceActions(handoff) {
  elements.workspaceActions.innerHTML = handoff.actions.map((action) => {
    if (action.code === "open_claim_portal") {
      return `
        <a class="workspace-action ${action.available ? "" : "disabled"}" href="${action.available ? safeUrl(action.url) : "#"}" ${action.available ? 'target="_blank" rel="noopener"' : 'aria-disabled="true"'}>
          <span class="action-icon">↗</span>
          <div><strong>${escapeHtml(action.label)}</strong><small>${escapeHtml(action.available ? action.description : "Available when the review pack is ready.")}</small></div>
        </a>
      `;
    }
    return `
      <button class="workspace-action" type="button" data-action-code="${escapeHtml(action.code)}">
        <span class="action-icon">${action.code === "build_evidence_pack" ? "↓" : "✦"}</span>
        <div><strong>${escapeHtml(action.label)}</strong><small>${escapeHtml(action.description)}</small></div>
      </button>
    `;
  }).join("");
  elements.workspaceActions.querySelectorAll("button[data-action-code]").forEach((button) => {
    button.addEventListener("click", () => performRecoveryAction(button.dataset.actionCode, button));
  });
}

function renderEvidenceReview(data) {
  const evidence = data.submitted_information?.evidence || (latestUpload ? [latestUpload] : []);
  if (!evidence.length) {
    elements.evidenceReview.classList.add("hidden");
    return;
  }
  elements.evidenceReview.classList.remove("hidden");
  elements.evidenceReviewContent.innerHTML = evidence.map((item) => {
    const inspection = item.inspection || {};
    return `
      <article class="verified-document">
        <div class="document-icon">DOC</div>
        <div><strong>${escapeHtml(item.file_name)}</strong><span>${escapeHtml(item.mime_type || "")} · ${formatBytes(item.size_bytes || 0)}</span></div>
        <span class="integrity-mark">✓ Integrity</span>
      </article>
      <div class="inspection-grid">
        <div><span>Readable text</span><strong>${inspection.text_extracted ? "Extracted" : "Not interpreted"}</strong></div>
        <div><span>Analysis scope</span><strong>${escapeHtml(inspection.scope || "Metadata and customer note")}</strong></div>
      </div>
      ${inspection.excerpt ? `<blockquote>${escapeHtml(inspection.excerpt)}</blockquote>` : ""}
    `;
  }).join("");
}

async function submitPrimaryInput(event, form) {
  event.preventDefault();
  if (!currentTrip) return;
  const submitButton = form.querySelector('button[type="submit"]');
  const evidenceCode = form.dataset.evidenceCode;
  const before = currentRecovery?.benefit_match;
  submitButton.disabled = true;
  elements.decisionCard.classList.add("working");
  showEvidenceStatus("Validating the new information and re-running policy analysis…", "working");
  startLoading([
    ["Validating your input", "Checking the submitted fact on the server"],
    ["Retrieving product policy", "Searching the public corpus with BGE-M3"],
    ["Updating the recovery path", "Grounding the next step in validated evidence"],
  ]);
  try {
    if (evidenceCode === "exact_card_product") {
      const selectedProduct = form.querySelector("select").value;
      if (!selectedProduct) throw new Error("Select a product first.");
      submittedProductCode = selectedProduct;
    } else {
      const file = form.querySelector('input[type="file"]').files[0];
      if (!file) throw new Error("Choose a document first.");
      if (file.size > 1_500_000) throw new Error("The file must be 1.5 MB or smaller.");
      latestUpload = await postJson("/api/evidence", {
        case_id: currentTrip.case_id,
        evidence_code: evidenceCode,
        file_name: file.name,
        mime_type: file.type || "text/plain",
        content_base64: await fileToBase64(file),
        evidence_note: form.querySelector("#evidence-note").value,
      });
      if (!submittedEvidenceIds.includes(latestUpload.upload_id)) submittedEvidenceIds.push(latestUpload.upload_id);
    }
    const data = await postJson("/api/reanalyse", {
      case_id: currentTrip.case_id,
      product_code: submittedProductCode || null,
      evidence_upload_ids: submittedEvidenceIds,
    });
    decisionChange = {
      title: before?.headline === data.benefit_match.headline ? "Evidence state refreshed" : "Policy guidance changed",
      detail: `${before?.headline || "Previous result"} → ${data.benefit_match.headline}`,
    };
    renderRecovery(data);
    showEvidenceStatus(`Live analysis completed in ${(data.response_time_ms / 1000).toFixed(1)}s.`, "success");
  } catch (error) {
    showEvidenceStatus(error.message, "error");
    submitButton.disabled = false;
    elements.decisionCard.classList.remove("working");
  } finally {
    stopLoading();
  }
}

async function performRecoveryAction(actionCode, button) {
  if (!currentTrip) return;
  button.disabled = true;
  const original = button.querySelector("strong")?.textContent || button.textContent;
  if (button.querySelector("strong")) button.querySelector("strong").textContent = "Creating…";
  try {
    const artifact = await postJson("/api/action", {
      case_id: currentTrip.case_id,
      action_code: actionCode,
      product_code: submittedProductCode || null,
      evidence_upload_ids: submittedEvidenceIds,
    });
    openArtifact(artifact);
    if (button.querySelector("strong")) button.querySelector("strong").textContent = "Created";
  } catch (error) {
    showEvidenceStatus(error.message, "error");
    if (button.querySelector("strong")) button.querySelector("strong").textContent = original;
  } finally {
    button.disabled = false;
  }
}

function openArtifact(artifact) {
  const preview = artifact.preview;
  elements.artifactTitle.textContent = preview.title;
  elements.artifactDownload.href = artifact.download_path;
  elements.artifactDownload.setAttribute("download", artifact.file_name);
  artifactCopyText = "";
  if (preview.type === "message_draft") {
    artifactCopyText = `Subject: ${preview.subject}\n\n${preview.body}`;
    elements.artifactContent.innerHTML = `
      <div class="artifact-subject"><span>Subject</span><strong>${escapeHtml(preview.subject)}</strong></div>
      <pre>${escapeHtml(preview.body)}</pre>
    `;
    elements.artifactCopy.classList.remove("hidden");
  } else {
    elements.artifactContent.innerHTML = `
      <div class="artifact-metrics">
        <div><strong>${preview.policy_sources}</strong><span>policy sources</span></div>
        <div><strong>${preview.evidence_items}</strong><span>uploaded files</span></div>
        <div><strong>${preview.remaining_items}</strong><span>open items</span></div>
      </div>
      <p class="artifact-note">The downloaded JSON is a structured draft for formal human review. It is not a submitted claim.</p>
    `;
    elements.artifactCopy.classList.add("hidden");
  }
  elements.artifactDialog.showModal();
}

async function copyArtifact() {
  if (!artifactCopyText) return;
  try {
    await navigator.clipboard.writeText(artifactCopyText);
  } catch (_) {
    const textArea = document.createElement("textarea");
    textArea.value = artifactCopyText;
    document.body.appendChild(textArea);
    textArea.select();
    document.execCommand("copy");
    textArea.remove();
  }
  elements.artifactCopy.textContent = "Copied";
}

async function simulateCurrentTrip() {
  if (!currentTrip) return;
  elements.simulateButton.disabled = true;
  elements.anotherButton.disabled = true;
  startLoading([
    ["Receiving carrier event", "A new operational signal changed the journey"],
    ["Matching connected records", "Checking itinerary and Card payment"],
    ["Building the recovery path", "Finding the minimum safe next step"],
  ]);
  try {
    const data = await postJson("/api/detect", { case_id: currentTrip.case_id, live: false });
    decisionChange = null;
    renderRecovery(data);
    elements.recoveryWorkspace.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    elements.idleWorkspace.innerHTML = `<div class="error-message"><strong>Recovery workspace unavailable</strong><span>${escapeHtml(error.message)}</span></div>`;
    elements.simulateButton.disabled = false;
  } finally {
    stopLoading();
    elements.anotherButton.disabled = false;
  }
}

async function chooseAnotherTraveller() {
  elements.anotherButton.disabled = true;
  elements.simulateButton.disabled = true;
  startLoading([["Selecting another traveller", "Loading a reproducible scenario from the 600-case coverage set"]]);
  try {
    await loadTrip();
    document.querySelector(".scenario-bar").scrollIntoView({ behavior: "smooth", block: "center" });
  } catch (error) {
    document.querySelector("#demo-query").textContent = error.message;
  } finally {
    stopLoading();
    elements.anotherButton.disabled = false;
    elements.simulateButton.disabled = false;
  }
}

async function loadTrip(caseId = "") {
  const path = caseId ? `/api/trip?case_id=${encodeURIComponent(caseId)}` : "/api/trip";
  const response = await fetch(path, { cache: "no-store" });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "The journey could not be loaded.");
  submittedProductCode = "";
  submittedEvidenceIds = [];
  latestUpload = null;
  decisionChange = null;
  guidedPipelineRun = null;
  latestPipelineArtifact = null;
  currentRecovery = null;
  elements.recoveryWorkspace.classList.add("hidden");
  elements.idleWorkspace.classList.remove("hidden");
  elements.simulateButton.querySelector("span").textContent = "Trigger disruption";
  elements.simulateButton.disabled = false;
  elements.evidenceStatus.className = "evidence-status hidden";
  document.querySelector("#scenario-disclosure").textContent = "Synthetic coverage case · not a model accuracy result";
  renderTrip(data);
}

function startLoading(stages) {
  stopLoading();
  elements.loadingPanel.classList.remove("hidden");
  let index = 0;
  const render = () => {
    const [title, detail] = stages[index % stages.length];
    elements.loadingTitle.textContent = title;
    elements.loadingDetail.textContent = detail;
    index += 1;
  };
  render();
  if (stages.length > 1) loadingTimer = window.setInterval(render, 1200);
}

function stopLoading() {
  if (loadingTimer) window.clearInterval(loadingTimer);
  loadingTimer = null;
  elements.loadingPanel.classList.add("hidden");
}

function showEvidenceStatus(message, state) {
  elements.evidenceStatus.className = `evidence-status ${state}`;
  elements.evidenceStatus.textContent = message;
}

async function postJson(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "The request could not be completed.");
  return data;
}

async function getJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "The request could not be completed.");
  return data;
}

async function fileToBase64(file) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  const chunkSize = 0x8000;
  for (let start = 0; start < bytes.length; start += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(start, start + chunkSize));
  }
  return btoa(binary);
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024).toFixed(1)} KB`;
}

elements.simulateButton.addEventListener("click", simulateCurrentTrip);
elements.anotherButton.addEventListener("click", chooseAnotherTraveller);
document.querySelector("#artifact-close").addEventListener("click", () => elements.artifactDialog.close());
elements.artifactCopy.addEventListener("click", copyArtifact);
elements.artifactDialog.addEventListener("click", (event) => {
  if (event.target === elements.artifactDialog) elements.artifactDialog.close();
});

const initialCaseId = new URLSearchParams(window.location.search).get("case_id") || "";
loadTrip(initialCaseId).catch((error) => {
  elements.idleWorkspace.innerHTML = `<div class="error-message"><strong>Demo unavailable</strong><span>${escapeHtml(error.message)}</span></div>`;
});
