const itinerary = document.querySelector("#itinerary");
const protectionDetails = document.querySelector("#protection-details");
const monitoringStatus = document.querySelector("#monitoring-status");
const simulateButton = document.querySelector("#simulate-button");
const demoNotice = document.querySelector("#demo-notice");
const loadingPanel = document.querySelector("#loading-panel");
const disruptionAlert = document.querySelector("#disruption-alert");
const recoveryPanel = document.querySelector("#recovery-panel");
const recoveryActions = document.querySelector("#recovery-actions");
const claimPanel = document.querySelector("#claim-panel");
const claimItems = document.querySelector("#claim-items");
const completionValue = document.querySelector("#completion-value");
const progressBar = document.querySelector("#progress-bar");
const benefitPanel = document.querySelector("#benefit-panel");
const benefitMatch = document.querySelector("#benefit-match");

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
  return type === "flight" ? "✈" : "▣";
}

function renderTrip(trip) {
  document.querySelector("#trip-meta").textContent = `${trip.date_range} · ${trip.route}`;
  monitoringStatus.className = `monitoring-status ${trip.monitoring.status}`;
  monitoringStatus.innerHTML = `
    <span class="status-dot"></span>
    <div><strong>${escapeHtml(trip.monitoring.label)}</strong><small>Last checked ${escapeHtml(trip.monitoring.last_checked)}</small></div>
  `;
  protectionDetails.innerHTML = `
    <div><dt>Card</dt><dd>${escapeHtml(trip.card.product_name)}</dd></div>
    <div><dt>Payment</dt><dd><span class="verified-mark">✓</span> Round trip verified</dd></div>
    <div><dt>Traveller</dt><dd>${escapeHtml(trip.traveller.display_name)}</dd></div>
    <div><dt>Reference</dt><dd>${escapeHtml(trip.card.display_number)}</dd></div>
  `;
  itinerary.innerHTML = trip.segments.map((segment) => {
    if (segment.type === "flight") {
      return `
        <article class="segment ${escapeHtml(segment.status)}">
          <span class="segment-icon" aria-hidden="true">${segmentIcon(segment.type)}</span>
          <div class="segment-main">
            <div class="segment-title"><strong>${escapeHtml(segment.service_number)}</strong><span>${escapeHtml(segment.carrier)}</span></div>
            <div class="route-row">
              <div><strong>${escapeHtml(segment.origin_code)}</strong><span>${escapeHtml(segment.origin_city)}</span><small>${escapeHtml(segment.departure_local)}</small></div>
              <div class="route-line"><span></span></div>
              <div><strong>${escapeHtml(segment.destination_code)}</strong><span>${escapeHtml(segment.destination_city)}</span><small>${escapeHtml(segment.arrival_local)}</small></div>
            </div>
          </div>
          <span class="segment-status ${escapeHtml(segment.status)}">${escapeHtml(segment.status_label)}</span>
        </article>
      `;
    }
    return `
      <article class="segment ${escapeHtml(segment.status)}">
        <span class="segment-icon hotel-icon" aria-hidden="true">${segmentIcon(segment.type)}</span>
        <div class="segment-main hotel-main">
          <div class="segment-title"><strong>${escapeHtml(segment.name)}</strong><span>${escapeHtml(segment.location)}</span></div>
          <div class="hotel-dates"><span>Check-in <strong>${escapeHtml(segment.check_in)}</strong></span><span>Check-out <strong>${escapeHtml(segment.check_out)}</strong></span></div>
        </div>
        <span class="segment-status confirmed">${escapeHtml(segment.status_label)}</span>
      </article>
    `;
  }).join("");
}

function renderRecovery(caseData) {
  const disruption = caseData.disruption;
  disruptionAlert.innerHTML = `
    <div class="alert-icon" aria-hidden="true">!</div>
    <div class="alert-copy">
      <p class="section-kicker">DISRUPTION DETECTED</p>
      <h2>${escapeHtml(disruption.headline)}</h2>
      <p>${escapeHtml(disruption.summary)}</p>
      <dl class="alert-facts">
        <div><dt>Flight</dt><dd>SQ 12 · SIN to NRT</dd></div>
        <div><dt>Detected</dt><dd>${escapeHtml(disruption.detected_at)}</dd></div>
        <div><dt>Carrier reference</dt><dd>${escapeHtml(disruption.carrier_reference)}</dd></div>
      </dl>
    </div>
  `;

  const actions = caseData.recovery_actions || [];
  recoveryActions.innerHTML = actions.map((action, index) => `
    <article class="recovery-action">
      <span class="action-number">${index + 1}</span>
      <div><h3>${escapeHtml(action.title)}</h3><p>${escapeHtml(action.description)}</p></div>
      <button class="text-button" type="button" data-action-index="${index}">Mark complete</button>
    </article>
  `).join("");

  const pack = caseData.claim_pack;
  completionValue.textContent = `${pack.completion_percent}%`;
  progressBar.style.width = `${pack.completion_percent}%`;
  claimItems.innerHTML = pack.items.map((item) => `
    <div class="claim-item" data-claim-code="${escapeHtml(item.code)}">
      <div><strong>${escapeHtml(item.label)}</strong><span>${escapeHtml(item.source)}</span></div>
      <span class="item-status ${escapeHtml(item.status)}">${item.status === "complete" ? "Complete" : "Required"}</span>
    </div>
  `).join("");

  const match = caseData.benefit_match;
  const citations = (match.policy_evidence || []).map((item) => `
    <a class="policy-link" href="${safeUrl(item.url)}" target="_blank" rel="noopener">
      <span>${escapeHtml(item.section)}</span><small>${item.pages?.length ? `Page ${item.pages.join(", ")}` : "Official source"} ↗</small>
    </a>
  `).join("");
  benefitMatch.innerHTML = `
    <span class="match-status">Potential match identified</span>
    <h3>${escapeHtml(match.product_name)}</h3>
    <p>${escapeHtml(match.summary)}</p>
    <dl class="benefit-facts">
      <div><dt>Card payment</dt><dd>Verified</dd></div>
      <div><dt>Formal review</dt><dd>Required</dd></div>
    </dl>
    <details class="policy-details"><summary>View public benefit wording</summary>${citations || "<p>No safely validated citation was returned.</p>"}</details>
    <p class="legal-note">${escapeHtml(caseData.safety_note)}</p>
  `;

  disruptionAlert.classList.remove("hidden");
  recoveryPanel.classList.remove("hidden");
  claimPanel.classList.remove("hidden");
  benefitPanel.classList.remove("hidden");
  document.querySelector("#page-heading").scrollIntoView({ behavior: "smooth", block: "start" });

  document.querySelectorAll("[data-action-index]").forEach((button) => {
    button.addEventListener("click", () => {
      button.textContent = "Completed";
      button.disabled = true;
      button.closest(".recovery-action").classList.add("completed");
    });
  });
}

async function loadTrip() {
  const response = await fetch("/api/trip");
  if (!response.ok) throw new Error("The trip could not be loaded.");
  renderTrip(await response.json());
}

simulateButton.addEventListener("click", async () => {
  simulateButton.disabled = true;
  demoNotice.classList.add("hidden");
  loadingPanel.classList.remove("hidden");
  try {
    const response = await fetch("/api/detect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "The disruption could not be processed.");
    renderTrip(data.trip);
    renderRecovery(data);
  } catch (error) {
    disruptionAlert.innerHTML = `<div class="error-message"><strong>Recovery plan unavailable</strong><span>${escapeHtml(error.message)}</span></div>`;
    disruptionAlert.classList.remove("hidden");
    demoNotice.classList.remove("hidden");
    simulateButton.disabled = false;
  } finally {
    loadingPanel.classList.add("hidden");
  }
});

loadTrip().catch((error) => {
  itinerary.innerHTML = `<div class="error-message"><strong>Trip unavailable</strong><span>${escapeHtml(error.message)}</span></div>`;
});
