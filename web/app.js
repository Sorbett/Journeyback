const elements = {
  itinerary: document.querySelector("#itinerary"),
  protectionDetails: document.querySelector("#protection-details"),
  monitoringStatus: document.querySelector("#monitoring-status"),
  simulateButton: document.querySelector("#simulate-button"),
  anotherButton: document.querySelector("#another-button"),
  demoLab: document.querySelector("#demo-lab"),
  loadingPanel: document.querySelector("#loading-panel"),
  disruptionAlert: document.querySelector("#disruption-alert"),
  recoveryPanel: document.querySelector("#recovery-panel"),
  recoveryActions: document.querySelector("#recovery-actions"),
  claimPanel: document.querySelector("#claim-panel"),
  claimItems: document.querySelector("#claim-items"),
  completionValue: document.querySelector("#completion-value"),
  progressBar: document.querySelector("#progress-bar"),
  benefitPanel: document.querySelector("#benefit-panel"),
  benefitMatch: document.querySelector("#benefit-match"),
  resultMode: document.querySelector("#result-mode"),
  evidenceStatus: document.querySelector("#evidence-status"),
};

let currentTrip = null;
let submittedProductCode = "";
let submittedEvidenceIds = [];

const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;").replaceAll("'", "&#039;");

function safeUrl(value) {
  try {
    const url = new URL(String(value));
    return ["https:", "http:"].includes(url.protocol) ? escapeHtml(url.href) : "#";
  } catch (_) {
    return "#";
  }
}

function segmentIcon(type) {
  if (type === "flight") {
    return `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m3 11 18-7-7 18-3-8-8-3Z"></path><path d="m11 14 4-4"></path></svg>`;
  }
  return `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 21V5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v16M8 7h2m4 0h2M8 11h2m4 0h2M9 21v-5h6v5"></path></svg>`;
}

function renderTrip(trip) {
  currentTrip = trip;
  const shareableUrl = new URL(window.location.href);
  shareableUrl.searchParams.set("case_id", trip.case_id);
  window.history.replaceState(null, "", shareableUrl);
  document.querySelector("#trip-title").textContent = trip.title;
  document.querySelector("#trip-meta").textContent = `${trip.date_range} · ${trip.route}`;
  document.querySelector("#segment-count").textContent = `${trip.segments.length} monitored reservations`;
  document.title = `JourneyBack | ${trip.title}`;

  elements.monitoringStatus.className = `monitoring-status ${trip.monitoring.status}`;
  elements.monitoringStatus.innerHTML = `
    <span class="status-pulse" aria-hidden="true"></span>
    <div><strong>${escapeHtml(trip.monitoring.label)}</strong><small>${escapeHtml(trip.monitoring.last_checked)}</small></div>
  `;

  const paymentLabel = trip.card.payment_verified ? "Trip payment verified" : "Payment needs confirmation";
  elements.protectionDetails.innerHTML = `
    <div><dt>Card</dt><dd>${escapeHtml(trip.card.product_name)}</dd></div>
    <div><dt>Payment</dt><dd><span class="verified-mark">${trip.card.payment_verified ? "✓" : "!"}</span> ${paymentLabel}</dd></div>
    <div><dt>Traveller</dt><dd>${escapeHtml(trip.traveller.display_name)}</dd></div>
    <div><dt>Party</dt><dd>${escapeHtml(trip.traveller.traveller_type)} · ${trip.traveller.party_size} traveller${trip.traveller.party_size === 1 ? "" : "s"}</dd></div>
  `;

  elements.itinerary.innerHTML = trip.segments.map((segment) => {
    if (segment.type === "flight") {
      return `
        <article class="segment ${escapeHtml(segment.status)}">
          <span class="segment-icon">${segmentIcon(segment.type)}</span>
          <div class="segment-main">
            <div class="segment-title"><strong>${escapeHtml(segment.service_number)}</strong><span>${escapeHtml(segment.carrier)}</span></div>
            <div class="route-row">
              <div><strong>${escapeHtml(segment.origin_code)}</strong><span>${escapeHtml(segment.origin_city)}</span><small>${escapeHtml(segment.departure_local)}</small></div>
              <div class="route-line"><span></span><i aria-hidden="true"></i></div>
              <div><strong>${escapeHtml(segment.destination_code)}</strong><span>${escapeHtml(segment.destination_city)}</span><small>${escapeHtml(segment.arrival_local)}</small></div>
            </div>
          </div>
          <span class="segment-status ${escapeHtml(segment.status)}">${escapeHtml(segment.status_label)}</span>
        </article>
      `;
    }
    return `
      <article class="segment ${escapeHtml(segment.status)}">
        <span class="segment-icon">${segmentIcon(segment.type)}</span>
        <div class="segment-main hotel-main">
          <div class="segment-title"><strong>${escapeHtml(segment.name)}</strong><span>${escapeHtml(segment.location)}</span></div>
          <div class="hotel-dates"><span>Check-in <strong>${escapeHtml(segment.check_in)}</strong></span><span>Check-out <strong>${escapeHtml(segment.check_out)}</strong></span></div>
        </div>
        <span class="segment-status ${escapeHtml(segment.status)}">${escapeHtml(segment.status_label)}</span>
      </article>
    `;
  }).join("");

  const simulation = trip.simulation;
  document.querySelector("#case-id").textContent = simulation.case_id;
  document.querySelector("#demo-query").textContent = `${simulation.event_label} · ${trip.card.product_name}`;
}

function resetRecovery() {
  [elements.disruptionAlert, elements.recoveryPanel, elements.claimPanel, elements.benefitPanel]
    .forEach((element) => element.classList.add("hidden"));
  elements.simulateButton.disabled = false;
  elements.simulateButton.querySelector("span").textContent = "Simulate disruption";
  elements.demoLab.classList.remove("completed");
}

function renderRecovery(caseData) {
  const disruption = caseData.disruption;
  const flight = caseData.trip.segments.find((segment) => segment.type === "flight");
  elements.disruptionAlert.innerHTML = `
    <div class="alert-icon" aria-hidden="true"><span>!</span></div>
    <div class="alert-copy">
      <div class="alert-title-row"><p class="section-kicker">DISRUPTION DETECTED</p><span>${escapeHtml(caseData.case_id)}</span></div>
      <h2>${escapeHtml(disruption.headline)}</h2>
      <dl class="alert-facts">
        <div><dt>Journey</dt><dd>${escapeHtml(flight.service_number)} · ${escapeHtml(flight.origin_code)} to ${escapeHtml(flight.destination_code)}</dd></div>
        <div><dt>Duration</dt><dd>${escapeHtml(disruption.duration)}</dd></div>
      </dl>
    </div>
  `;

  const actions = caseData.recovery_actions || [];
  elements.recoveryActions.innerHTML = actions.map((action, index) => `
    <article class="recovery-action">
      <span class="action-number">${index + 1}</span>
      <div><h3>${escapeHtml(action.title)}</h3></div>
      <button class="text-button" type="button" data-action-index="${index}">Mark done</button>
    </article>
  `).join("");

  renderClaimPack(caseData.claim_pack, caseData.trip.simulation.product_options || []);

  const match = caseData.benefit_match;
  const citations = (match.policy_evidence || []).map((item) => `
    <a class="policy-link" href="${safeUrl(item.url)}" target="_blank" rel="noopener">
      <span>${escapeHtml(item.section)}</span><small>${item.pages?.length ? `Page ${item.pages.join(", ")}` : "Official public source"} ↗</small>
    </a>
  `).join("");
  const outcomeLabel = String(match.expected_eligibility || match.status_title).replaceAll("_", " ");
  elements.benefitMatch.innerHTML = `
    <span class="match-status ${escapeHtml(match.status)}">${escapeHtml(outcomeLabel)}</span>
    <h3>${escapeHtml(match.headline)}</h3>
    <p>${escapeHtml(match.summary)}</p>
    <details class="policy-details"><summary>Public policy evidence</summary>${citations || "<p>No benefit-specific citation is safe for this product.</p>"}</details>
  `;

  elements.resultMode.textContent = caseData.processing_mode === "live_llm_rag"
    ? `Reanalysed · ${(caseData.response_time_ms / 1000).toFixed(1)}s`
    : "Ready";
  [elements.disruptionAlert, elements.recoveryPanel, elements.claimPanel, elements.benefitPanel]
    .forEach((element) => element.classList.remove("hidden"));
  elements.demoLab.classList.add("completed");
  elements.simulateButton.querySelector("span").textContent = "Simulation complete";

  document.querySelectorAll("[data-action-index]").forEach((button) => {
    button.addEventListener("click", () => {
      button.textContent = "Completed";
      button.disabled = true;
      button.closest(".recovery-action").classList.add("completed");
    });
  });

  document.querySelectorAll("[data-evidence-form]").forEach((form) => {
    form.addEventListener("submit", (event) => submitEvidence(event, form));
    const fileInput = form.querySelector('input[type="file"]');
    if (fileInput) {
      fileInput.addEventListener("change", () => {
        const label = form.querySelector(".file-control span");
        label.textContent = fileInput.files[0]?.name || "Choose file";
      });
    }
  });

  elements.disruptionAlert.scrollIntoView({ behavior: "smooth", block: "center" });
}

function renderClaimPack(pack, productOptions) {
  elements.completionValue.textContent = `${pack.completion_percent}%`;
  elements.progressBar.style.width = `${pack.completion_percent}%`;
  elements.progressBar.parentElement.setAttribute("aria-valuenow", pack.completion_percent);
  elements.claimItems.dataset.completed = pack.completed;
  elements.claimItems.dataset.total = pack.total;
  elements.claimItems.innerHTML = pack.items.map((item) => {
    const complete = item.status === "complete";
    let control = '<span class="item-status complete">Ready</span>';
    if (!complete && item.code === "exact_card_product") {
      const options = productOptions.map((product) => `
        <option value="${escapeHtml(product.code)}">${escapeHtml(product.name)}</option>
      `).join("");
      control = `
        <form class="evidence-form product-form" data-evidence-form data-evidence-code="exact_card_product">
          <label class="sr-only" for="product-${escapeHtml(currentTrip.case_id)}">Card product</label>
          <select id="product-${escapeHtml(currentTrip.case_id)}" required>
            <option value="">Select Card product</option>${options}
          </select>
          <button type="submit">Confirm &amp; reanalyse</button>
        </form>
      `;
    } else if (!complete) {
      control = `
        <form class="evidence-form upload-form" data-evidence-form data-evidence-code="${escapeHtml(item.code)}">
          <label class="file-control">
            <span>Choose file</span>
            <input type="file" required accept=".pdf,.jpg,.jpeg,.png,.txt,application/pdf,image/jpeg,image/png,text/plain">
          </label>
          <label class="sr-only" for="note-${escapeHtml(item.code)}">Document note</label>
          <input id="note-${escapeHtml(item.code)}" class="evidence-note" type="text" maxlength="500" required placeholder="Document reference or short note">
          <button type="submit">Upload &amp; reanalyse</button>
          <small>Original stays local. Readable text and your note are sent to the configured AI.</small>
        </form>
      `;
    }
    return `
      <div class="claim-item ${escapeHtml(item.status)}">
        <span class="claim-check" aria-hidden="true">${complete ? "✓" : "+"}</span>
        <div class="claim-copy"><strong>${escapeHtml(item.label)}</strong><span>${escapeHtml(item.source)}</span></div>
        ${control}
      </div>
    `;
  }).join("");
}

async function submitEvidence(event, form) {
  event.preventDefault();
  if (!currentTrip) return;
  const submitButton = form.querySelector('button[type="submit"]');
  const evidenceCode = form.dataset.evidenceCode;
  submitButton.disabled = true;
  showEvidenceStatus("Analysing the new information with policy evidence…", "working");
  try {
    if (evidenceCode === "exact_card_product") {
      const selectedProduct = form.querySelector("select").value;
      if (!selectedProduct) throw new Error("Select a Card product first.");
      submittedProductCode = selectedProduct;
    } else {
      const file = form.querySelector('input[type="file"]').files[0];
      if (!file) throw new Error("Choose a file first.");
      if (file.size > 1_500_000) throw new Error("The file must be 1.5 MB or smaller.");
      const upload = await postJson("/api/evidence", {
        case_id: currentTrip.case_id,
        evidence_code: evidenceCode,
        file_name: file.name,
        mime_type: file.type || "text/plain",
        content_base64: await fileToBase64(file),
        evidence_note: form.querySelector(".evidence-note").value,
      });
      if (!submittedEvidenceIds.includes(upload.upload_id)) submittedEvidenceIds.push(upload.upload_id);
    }

    const data = await postJson("/api/reanalyse", {
      case_id: currentTrip.case_id,
      product_code: submittedProductCode || null,
      evidence_upload_ids: submittedEvidenceIds,
    });
    renderTrip(data.trip);
    renderRecovery(data);
    showEvidenceStatus("Updated with live policy analysis.", "success");
  } catch (error) {
    showEvidenceStatus(error.message, "error");
    submitButton.disabled = false;
  }
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

async function fileToBase64(file) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  const chunkSize = 0x8000;
  for (let start = 0; start < bytes.length; start += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(start, start + chunkSize));
  }
  return btoa(binary);
}

function showEvidenceStatus(message, state) {
  elements.evidenceStatus.className = `evidence-status ${state}`;
  elements.evidenceStatus.textContent = message;
}

async function loadTrip(caseId = "") {
  const path = caseId ? `/api/trip?case_id=${encodeURIComponent(caseId)}` : "/api/trip";
  const response = await fetch(path, { cache: "no-store" });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "The journey could not be loaded.");
  submittedProductCode = "";
  submittedEvidenceIds = [];
  elements.evidenceStatus.className = "evidence-status hidden";
  resetRecovery();
  renderTrip(data);
}

async function simulateCurrentTrip() {
  if (!currentTrip) return;
  elements.simulateButton.disabled = true;
  elements.anotherButton.disabled = true;
  elements.loadingPanel.classList.remove("hidden");
  try {
    const response = await fetch("/api/detect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case_id: currentTrip.case_id, live: false }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "The disruption could not be processed.");
    renderTrip(data.trip);
    renderRecovery(data);
  } catch (error) {
    elements.disruptionAlert.innerHTML = `<div class="error-message"><strong>Recovery plan unavailable</strong><span>${escapeHtml(error.message)}</span></div>`;
    elements.disruptionAlert.classList.remove("hidden");
    elements.simulateButton.disabled = false;
  } finally {
    elements.loadingPanel.classList.add("hidden");
    elements.anotherButton.disabled = false;
  }
}

async function chooseAnotherTraveller() {
  elements.anotherButton.disabled = true;
  elements.simulateButton.disabled = true;
  elements.demoLab.classList.add("is-loading");
  try {
    await loadTrip();
    elements.demoLab.scrollIntoView({ behavior: "smooth", block: "center" });
  } catch (error) {
    document.querySelector("#demo-query").textContent = error.message;
  } finally {
    elements.demoLab.classList.remove("is-loading");
    elements.anotherButton.disabled = false;
    elements.simulateButton.disabled = false;
  }
}

elements.simulateButton.addEventListener("click", simulateCurrentTrip);
elements.anotherButton.addEventListener("click", chooseAnotherTraveller);

const initialCaseId = new URLSearchParams(window.location.search).get("case_id") || "";

loadTrip(initialCaseId).catch((error) => {
  elements.itinerary.innerHTML = `<div class="error-message"><strong>Demo unavailable</strong><span>${escapeHtml(error.message)}</span></div>`;
});
