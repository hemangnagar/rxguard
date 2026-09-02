const queue = document.querySelector("#queue");
const detail = document.querySelector("#detail");
const runAllButton = document.querySelector("#run-all");
let scenarios = [];
let activeId = null;

const money = (value) => {
  if (value === null || value === undefined) return "—";
  const number = Number(value);
  return `${number < 0 ? "−" : ""}$${Math.abs(number).toFixed(2)}`;
};

function marginFor(row) {
  return row.actual_margin ?? row.benchmark_margin;
}

function renderQueue() {
  queue.innerHTML = scenarios.map((row) => {
    const margin = marginFor(row);
    return `
      <button class="queue-row ${activeId === row.id ? "active" : ""}" data-id="${row.id}" type="button">
        <span class="dot ${row.severity}" aria-label="${row.severity} priority"></span>
        <span class="queue-copy">
          <strong>${row.title}</strong>
          <small>${row.finding}</small>
        </span>
        <span class="queue-result">
          <strong class="${Number(margin) < 0 ? "negative" : ""}">${money(margin)}</strong>
          <small>${row.actual_margin !== null ? "actual" : "benchmark"}</small>
        </span>
      </button>`;
  }).join("");

  queue.querySelectorAll(".queue-row").forEach((button) => {
    button.addEventListener("click", () => inspect(button.dataset.id));
  });
}

function updateMetrics() {
  document.querySelector("#metric-total").textContent = scenarios.length;
  document.querySelector("#metric-high").textContent = scenarios.filter((item) => item.severity === "high").length;
  document.querySelector("#metric-loss").textContent = scenarios.filter((item) => item.actual_margin !== null && Number(item.actual_margin) < 0).length;
}

function renderDetail(run) {
  const result = run.result;
  const primary = result.findings[0];
  const margin = result.actual_margin ?? result.benchmark_margin;
  const proposal = run.explanation.accepted
    ? `${run.explanation.text}<span class="gate">✓ Explanation passed the evidence gate</span>`
    : `Explanation withheld: ${run.explanation.rejection_reason}<span class="gate">✕ Evidence gate rejected the proposal</span>`;
  const cost = result.facts.find((fact) => fact.id === "actual-cost" || fact.id === "nadac-benchmark-cost");
  const equation = cost
    ? `${money(result.total_revenue)} revenue ${Number(result.total_adjustments) < 0 ? "−" : "+"} ${money(Math.abs(Number(result.total_adjustments)))} adjustments − ${cost.formatted} cost = ${money(margin)}`
    : "Margin unavailable until cost evidence is supplied.";

  detail.innerHTML = `
    <div class="detail-head">
      <p class="eyebrow">${run.scenario.claim_status} · ${run.scenario.drug.ndc}</p>
      <h2>${run.scenario.title}</h2>
      <p>${run.scenario.drug.display} · quantity ${run.scenario.drug.quantity}</p>
    </div>
    <div class="detail-body">
      <div class="verdict">
        <div class="verdict-copy"><strong>${primary.title}</strong><span>${result.cost_basis.replace("-", " ")} basis</span></div>
        <div class="margin ${Number(margin) < 0 ? "negative" : ""}">${money(margin)}</div>
      </div>
      <div class="proposal">${proposal}</div>
      <div class="finding"><h3>Recommended next step</h3><p>${primary.action}</p></div>
      <div class="equation">${equation}</div>
      <div class="facts">
        ${result.facts.map((fact) => `<div class="fact"><span>${fact.label}</span><strong>${fact.formatted}</strong></div>`).join("")}
      </div>
      <p class="evidence-ok">${result.evidence_complete ? "✓ Every calculated amount has a source reference" : "✕ Evidence incomplete"}</p>
    </div>`;
}

async function inspect(id) {
  activeId = id;
  renderQueue();
  detail.innerHTML = '<div class="empty-detail"><p>Running deterministic checks…</p></div>';
  const response = await fetch(`/api/scenarios/${encodeURIComponent(id)}/run`, {method: "POST"});
  if (!response.ok) throw new Error("Scenario failed");
  renderDetail(await response.json());
  if (window.innerWidth < 900) detail.scrollIntoView({behavior: "smooth", block: "start"});
}

async function load() {
  try {
    const response = await fetch("/api/scenarios");
    scenarios = await response.json();
    renderQueue();
    updateMetrics();
    await inspect("retroactive-loss");
  } catch (error) {
    queue.innerHTML = '<div class="loading">RxGuard could not load the scenario suite.</div>';
  }
}

runAllButton.addEventListener("click", async () => {
  runAllButton.disabled = true;
  runAllButton.textContent = "Running…";
  for (const row of scenarios) {
    await fetch(`/api/scenarios/${encodeURIComponent(row.id)}/run`, {method: "POST"});
  }
  runAllButton.textContent = "6 / 6 checked";
  setTimeout(() => {
    runAllButton.disabled = false;
    runAllButton.textContent = "Run all";
  }, 1800);
});

load();

