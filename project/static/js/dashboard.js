/**
 * Dashboard page. Pulls everything from the FastAPI backend (see
 * static/js/api.js) — nothing here is hardcoded except the initial
 * skeleton markup already in dashboard.html.
 */
document.addEventListener(
  "DOMContentLoaded",
  () => {

    // Load production profile dropdown
    wireMachineProfileSelector();

    // Load dashboard data
    refreshDashboard();

    setInterval(
      refreshDashboard,
      5000
    );

    document
      .getElementById(
        "health-trend-range"
      )
      ?.addEventListener(
        "change",
        loadHealthTrend
      );
  }
);


function refreshDashboard() {

  loadLiveContext();

  loadOverview();

  loadMaintenanceNeeds();

  loadAlerts();

  loadHealthTrend();
}

async function loadLiveContext() {
  const chip = document.getElementById("live-context-chip");
  const intervalChip = document.getElementById("cycle-interval-chip");
  try {
    const status = await Api.getLiveMachine();
    if (chip) chip.textContent = `Now monitoring ${status.selected_mold} · ${status.material} · ${status.cycle_id}`;
    if (intervalChip) intervalChip.textContent = `1 CSV row every ${status.cycle_seconds}s · next cycle in ${status.next_cycle_in_seconds}s`;
  } catch (err) {
    if (chip) chip.textContent = "Could not load current cycle.";
  }
}

async function wireMachineProfileSelector() {
  const select = document.getElementById("machine-profile-select");
  if (!select) return;
  try {
    const status = await Api.getLiveMachine();
    select.innerHTML = status.profiles.map((p) =>
      `<option value="${Utils.escapeHtml(p.mold)}">${Utils.escapeHtml(p.material)} · ${p.tonnage}T · ${p.cycle_seconds}s/cycle</option>`
    ).join("");
    select.value = status.selected_mold;
    select.addEventListener("change", async () => {
      select.disabled = true;
      try {
        await Api.selectLiveMachine(select.value);
        await loadLiveContext();
        await loadOverview();
        if (window.MoldGuardRefreshSchematic) await window.MoldGuardRefreshSchematic();
        Utils.toast("Live simulation switched to the selected mold profile.", "success");
      } catch (err) { Utils.toast(err.message || "Could not switch machine profile.", "error"); }
      finally { select.disabled = false; }
    });
  } catch (err) { Utils.toast(err.message || "Could not load machine profiles.", "error"); }
}

async function loadOverview() {
  try {
    const data = await Api.getSubsystems();
    populateKpis(data.machine);
    populateSubsystemCards(data.subsystems);
  } catch (err) {
    Utils.toast(err.message || "Could not load machine overview.", "error");
    document.querySelectorAll('[data-field="param-list"]').forEach((el) => {
      el.innerHTML = Utils.errorBlock(err);
    });
  }
}

function populateKpis(machine) {
  const set = (id, text) => { const el = document.getElementById(id); if (el) el.textContent = text; };

  set("kpi-health-value", machine.overall_health);
  set("kpi-health-status", machine.overall_status);
  set("kpi-health-summary", machine.overall_summary);

  const ring = document.getElementById("kpi-health-ring");
  if (ring) {
    const circumference = 2 * Math.PI * 19;
    const filled = (machine.overall_health / 100) * circumference;
    ring.setAttribute("stroke-dasharray", `${filled.toFixed(1)} ${circumference.toFixed(1)}`);
    const color = machine.overall_health >= 80 ? "var(--status-healthy)" : machine.overall_health >= 60 ? "var(--status-warning)" : "var(--status-critical)";
    ring.setAttribute("stroke", color);
  }

  set("kpi-alerts-count", machine.active_alert_count);
  set("kpi-predicted-count", machine.predicted_issue_count);
  set("kpi-predicted-window", `In next ${machine.prediction_window_hours} hours`);
  set("kpi-mtbf", `${machine.mtbf_hours.toFixed(1)}h`);
  const deltaEl = document.getElementById("kpi-mtbf-delta");
  if (deltaEl) {
    const sign = machine.mtbf_delta_pct >= 0 ? "+" : "";
    deltaEl.textContent = `${sign}${machine.mtbf_delta_pct}% vs earlier this run`;
    deltaEl.classList.toggle("positive", machine.mtbf_delta_pct >= 0);
    deltaEl.classList.toggle("negative", machine.mtbf_delta_pct < 0);
  }

  const lastMaintDate = new Date(machine.last_maintenance);
  const daysAgo = Math.max(0, Math.round((Date.now() - lastMaintDate.getTime()) / 86400000));
  set("kpi-last-maintenance", daysAgo === 0 ? "Today" : `${daysAgo} day${daysAgo === 1 ? "" : "s"} ago`);
  set("kpi-last-maintenance-date", Utils.formatDate(lastMaintDate));
}

function populateSubsystemCards(subsystems) {
  subsystems.forEach((s) => {
    const card = document.querySelector(`.subsystem-card[data-subsystem="${s.id}"]`);
    if (!card) return;

    const badge = card.querySelector('[data-field="status-badge"]');
    if (badge) {
      badge.textContent = Utils.capitalize(s.status);
      badge.className = `status-badge status-${s.status}`;
    }

    const confidence = card.querySelector('[data-field="confidence"]');
    if (confidence) confidence.textContent = `Confidence ${(s.confidence * 100).toFixed(0)}%`;

    const trendIcon = card.querySelector('[data-field="trend-icon"]');
    if (trendIcon) {
      const name = s.trend_direction === "up" ? "trending-up" : s.trend_direction === "down" ? "trending-down" : "";
      trendIcon.innerHTML = name ? Icons.svg(name, "", 13) : "";
    }

    const diagnostic = card.querySelector('[data-field="diagnostic"]');
    if (diagnostic) diagnostic.textContent = s.diagnostic_text;

    const paramList = card.querySelector('[data-field="param-list"]');
    if (paramList) {
      paramList.innerHTML = s.params.map((p) => `
        <div class="param-row ${p.flag ? "flag" : ""}">
          <span class="param-label">${Utils.escapeHtml(p.label)}</span>
          <span class="param-value">${p.value}${Utils.escapeHtml(p.unit)}${p.flag ? Icons.svg(p.direction === "down" ? "trending-down" : "trending-up", "", 12) : ""}</span>
        </div>`).join("");
    }

    const canvas = card.querySelector('[data-field="sparkline"]');
    if (canvas) {
      const colorToken = s.status === "healthy" ? "healthy" : s.status === "warning" ? "warning" : s.status === "degrading" ? "degrading" : "critical";
      Charts.sparkline(canvas, s.sparkline, colorToken);
    }
  });
}

async function loadMaintenanceNeeds() {
  const body = document.getElementById("maintenance-needs-body");
  try {
    const data = await Api.getMaintenanceNeeds();
    if (!data.items.length) {
      body.innerHTML = `<tr><td colspan="6"><div class="empty-note">No predicted maintenance needs right now.</div></td></tr>`;
      return;
    }
    body.innerHTML = data.items.map((item) => `
      <tr>
        <td class="cell-strong">${Utils.escapeHtml(item.component)}</td>
        <td>${Utils.escapeHtml(item.issue)}</td>
        <td><span class="severity-dot-label severity-${item.severity}"><span class="status-dot"></span>${Utils.capitalize(item.severity)}</span></td>
        <td>${Utils.escapeHtml(item.prediction_window)}</td>
        <td>${Utils.escapeHtml(item.recommendation)}</td>
        <td>
          <div class="confidence-bar-wrap">
            <div class="confidence-bar"><div class="confidence-bar-fill severity-${item.severity}" style="width:${(item.confidence * 100).toFixed(0)}%"></div></div>
            <span class="confidence-pct">${(item.confidence * 100).toFixed(0)}%</span>
          </div>
        </td>
      </tr>`).join("");
  } catch (err) {
    body.innerHTML = `<tr><td colspan="6">${Utils.errorBlock(err)}</td></tr>`;
  }
}

async function loadAlerts() {
  const list = document.getElementById("alerts-list");
  try {
    const data = await Api.getAlerts();
    if (!data.alerts.length) {
      list.innerHTML = `<div class="empty-note">No active alerts.</div>`;
      return;
    }
    list.innerHTML = data.alerts.map((alert) => {
      const iconName = alert.subsystem === "heater" ? "flame" : alert.subsystem === "hydraulic" ? "droplet" : "alert-triangle";
      const tone = alert.severity === "high" ? "critical" : alert.severity === "medium" ? "warning" : "healthy";
      return `
        <div class="alert-row">
          <div class="alert-icon status-${tone}-soft" style="background: var(--status-${tone}-soft); color: var(--status-${tone});">${Icons.svg(iconName, "", 15)}</div>
          <div class="alert-body">
            <div class="alert-title">${Utils.escapeHtml(alert.title)}</div>
            <div class="alert-detail">${Utils.escapeHtml(alert.detail)}</div>
          </div>
          <span class="alert-time">${Utils.timeAgo(alert.timestamp)}</span>
        </div>`;
    }).join("");
  } catch (err) {
    list.innerHTML = Utils.errorBlock(err);
  }
}

let healthTrendChart = null;
async function loadHealthTrend() {

  const canvas =
    document.getElementById(
      "health-trend-chart"
    );

  if (!canvas) {
    console.error(
      "health-trend-chart canvas not found"
    );
    return;
  }

  try {

    const rangeSelect =
      document.getElementById(
        "health-trend-range"
      );

    const limit =
      parseInt(
        rangeSelect?.value || "20",
        10
      );

    const response =
      await Api.getTrends(limit);

    const trend =
      response.health_trend_7d;

    console.log(
      "Trend API response:",
      response
    );

    if (
      !trend ||
      !Array.isArray(trend.labels) ||
      !Array.isArray(trend.series) ||
      trend.labels.length === 0
    ) {
      console.warn(
        "No health trend data available"
      );
      return;
    }

    // ---------------------------------
    // IMPORTANT:
    // Destroy ANY Chart.js chart already
    // attached to this canvas.
    // ---------------------------------

    const existingChart =
      Chart.getChart(canvas);

    if (existingChart) {
      existingChart.destroy();
    }

    healthTrendChart = null;

    // ---------------------------------
    // Create fresh chart
    // ---------------------------------

    healthTrendChart =
      Charts.lineChart(
        canvas,
        {
          labels: trend.labels,
          data: trend.series,
          colorToken: "blue",
          unit: "%",
        }
      );

    console.log(
      "Health trend chart created:",
      healthTrendChart
    );

  } catch (err) {

    console.error(
      "Health trend failed:",
      err
    );
  }
}