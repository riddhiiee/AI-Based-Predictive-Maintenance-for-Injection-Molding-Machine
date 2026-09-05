/**
 * Global chrome interactions shared by every page (sidebar + topbar).
 * Nav active-state highlighting is done server-side in _sidebar.html;
 * this file wires up the sidebar's live backend-status indicator and the
 * "Download Report" action available in the topbar on every page.
 */
document.addEventListener("DOMContentLoaded", () => {
  wireBackendStatus();

  const btn = document.getElementById("download-report-btn");
  if (!btn) return;

  btn.addEventListener("click", async () => {
    const original = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner"></span><span>Preparing\u2026</span>`;

    try {
      const [subsystems, predictions] = await Promise.all([
        Api.getSubsystems(),
        Api.getPredictAll(),
      ]);
      const report = buildTextReport(subsystems, predictions);
      downloadTextFile(`${subsystems.machine.id}_report_${new Date().toISOString().slice(0, 10)}.txt`, report);
      Utils.toast("Report exported.", "success");
    } catch (err) {
      Utils.toast(err.message || "Could not generate report.", "error");
    } finally {
      btn.disabled = false;
      btn.innerHTML = original;
    }
  });
});

/**
 * FUTURE INTEGRATION POINT: replace this plain-text export with a real
 * PDF/Excel report generator (e.g. via a dedicated /report endpoint that
 * renders a templated PDF) once one exists. This is a client-side mock so
 * the "Download Report" action in the UI is fully wired end to end.
 */
function buildTextReport(subsystems, predictions) {
  const lines = [];
  lines.push(`PREDICTIVE MAINTENANCE REPORT`);
  lines.push(`Machine: ${subsystems.machine.id} (${subsystems.machine.model})`);
  lines.push(`Location: ${subsystems.machine.location}`);
  lines.push(`Generated: ${new Date().toLocaleString()}`);
  lines.push(`Overall health: ${subsystems.machine.overall_health}/100 (${subsystems.machine.overall_status})`);
  lines.push("");
  lines.push("SUBSYSTEM PREDICTIONS");
  lines.push("-".repeat(60));
  predictions.predictions.forEach((p) => {
    lines.push(`${p.subsystem_name}: ${p.predicted_state} (confidence ${(p.confidence * 100).toFixed(0)}%)`);
    lines.push(`  Recommended action: ${p.recommended_action}`);
    lines.push(`  Prediction window: ${p.prediction_window}`);
    lines.push("");
  });
  lines.push("This report was generated from mock/simulated prediction data.");
  return lines.join("\n");
}

/**
 * Pings GET /health on a light interval and reflects real connectivity to
 * the FastAPI backend in the sidebar footer -- replaces the old static
 * "Machine / Online" card, which never actually reflected anything live.
 */
function wireBackendStatus() {
  const label = document.getElementById("backend-status-label");
  if (!label) return;
  const textEl = label.querySelector("span:last-child");

  async function check() {
    try {
      await Api.getHealth();
      label.className = "status-dot-label status-dot-healthy";
      textEl.textContent = "Backend connected";
    } catch (err) {
      label.className = "status-dot-label status-dot-critical";
      textEl.textContent = "Backend unreachable";
    }
  }

  check();
  setInterval(check, 20000);
}

function downloadTextFile(filename, content) {
  const blob = new Blob([content], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
