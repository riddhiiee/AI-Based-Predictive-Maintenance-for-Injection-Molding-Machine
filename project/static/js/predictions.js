/**
 * Prediction Results page. Two modes:
 *  - Live (default): renders one card per subsystem from GET /predict/all,
 *    which runs the real trained models against a simulated live-feed replay
 *    of historical cycles (see models/inference.py) -- there is no live PLC
 *    connection in this prototype, only the model/SHAP layer is real.
 *  - Uploaded: after uploading a CSV/Excel file via POST /predict/upload,
 *    renders the same real models' predictions against the operator's own
 *    data, one group of subsystem cards per mold found in the file.
 */
document.addEventListener("DOMContentLoaded", () => {
  restorePredictionState();
  wireUpload();
  loadUploadRequirements();
  wirePredictionMachineSelector();
  setInterval(async () => {
    try {
      const saved = await Api.getCurrentUpload();
      if (!saved.has_upload) await loadPredictions(false);
    } catch (_) { /* keep last rendered state */ }
  }, 2000);
});

async function wirePredictionMachineSelector() {
  const select = document.getElementById("prediction-machine-profile");
  if (!select) return;
  try {
    const status = await Api.getLiveMachine();
    select.innerHTML = status.profiles.map((p) => `<option value="${Utils.escapeHtml(p.mold)}">${Utils.escapeHtml(p.material)} · ${p.cycle_seconds}s/cycle</option>`).join("");
    select.value = status.selected_mold;
    select.addEventListener("change", async () => {
      await Api.clearCurrentUpload();
      await Api.selectLiveMachine(select.value);
      await loadPredictions();
      const liveBtn = document.getElementById("predict-live-btn");
      if (liveBtn) liveBtn.style.display = "none";
    });
  } catch (err) { console.warn("Could not load live profiles", err); }
}

async function restorePredictionState() {
  const container = document.getElementById("prediction-cards");
  const modeIndicator = document.getElementById("mode-indicator");
  const liveBtn = document.getElementById("predict-live-btn");
  const status = document.getElementById("predict-upload-status");

  try {
    const saved = await Api.getCurrentUpload();

    if (saved.has_upload && saved.result) {
      renderUploadResults(
        container,
        saved.result,
        saved.filename
      );

      if (modeIndicator) {
        modeIndicator.textContent = "Uploaded Data";
      }

      if (liveBtn) {
        liveBtn.style.display = "";
      }

      if (status) {
        status.textContent =
          `Active dataset: "${saved.filename}"`;
      }

      return;
    }
  } catch (err) {
    console.warn("Could not restore uploaded dataset:", err);
  }

  loadPredictions();
}

async function loadPredictions(showLoading = true) {
  const container = document.getElementById("prediction-cards");
  const cycleMeta = document.getElementById("cycle-meta");
  const modeIndicator = document.getElementById("mode-indicator");

  if (showLoading) container.innerHTML = `<div class="loading-row"><span class="spinner"></span>Loading predictions…</div>`;
  try {
    const data = await Api.getPredictAll();
    if (modeIndicator) modeIndicator.textContent = "Simulated Live Feed";
    const liveBtn = document.getElementById("predict-live-btn");
    if (liveBtn) liveBtn.style.display = "none";

    if (cycleMeta) {
      cycleMeta.textContent = `Cycle ${data.cycle_id} \u00b7 ${data.mold} \u00b7 ${data.material} \u00b7 generated ${Utils.timeAgo(data.generated_at)}`;
    }

    if (!data.predictions.length) {
      container.innerHTML = Utils.stateBlock("", "No predictions available", "Run a cycle to generate predictions.");
      return;
    }

    container.innerHTML = data.predictions.map(renderPredictionCard).join("");
  } catch (err) {
    container.innerHTML = Utils.errorBlock(err);
    Utils.toast(err.message || "Could not load predictions.", "error");
  }
}

async function loadUploadRequirements() {
  const el = document.getElementById("upload-required-cols");
  if (!el) return;
  try {
    const data = await Api.getUploadRequirements();
    el.textContent = data.required_columns.join(", ");
  } catch (_err) {
    // Non-critical -- leave the placeholder text if this fails.
  }
}

function wireUpload() {
  const btn = document.getElementById("predict-upload-btn");
  const liveBtn = document.getElementById("predict-live-btn");
  const input = document.getElementById("predict-upload-input");
  const status = document.getElementById("predict-upload-status");
  if (!btn || !input) return;

  btn.addEventListener("click", () => input.click());
  liveBtn.addEventListener("click", async () => {
    try {
      await Api.clearCurrentUpload();

      document.getElementById("cycle-meta").textContent =
        "Loading cycle details…";

      status.textContent = "";

      await loadPredictions();

      Utils.toast(
        "Uploaded dataset cleared. Returned to live feed.",
        "success"
      );
    } catch (err) {
      Utils.toast(
        err.message || "Could not return to live feed.",
        "error"
      );
    }
  });

  input.addEventListener("change", async () => {
    const file = input.files && input.files[0];
    input.value = "";
    if (!file) return;

    status.textContent = `Processing "${file.name}"…`;
    const container = document.getElementById("prediction-cards");
    container.innerHTML = `<div class="loading-row"><span class="spinner"></span>Running trained models on your data…</div>`;

    try {
      const data = await Api.postPredictUpload(file);
      renderUploadResults(container, data, file.name);
      status.textContent = `Loaded "${file.name}" \u00b7 ${data.molds.length} mold(s)`;
      document.getElementById("mode-indicator").textContent = "Uploaded Data";
      liveBtn.style.display = "";
      Utils.toast(`Ran real models against "${file.name}".`, "success");
    } catch (err) {
      container.innerHTML = Utils.errorBlock(err);
      status.textContent = "";
      Utils.toast(err.message || "Could not process the uploaded file.", "error");
    }
  });
}

function renderUploadResults(container, data, filename) {
  const cycleMeta = document.getElementById("cycle-meta");
  if (cycleMeta) {
    const total = data.molds.length;
    cycleMeta.textContent = `${filename} \u00b7 ${total} mold${total === 1 ? "" : "s"} \u00b7 generated ${Utils.timeAgo(data.generated_at)}`;
  }

  if (!data.molds.length) {
    container.innerHTML = Utils.stateBlock("", "No predictions available", "The uploaded file produced no usable rows.");
    return;
  }

  container.innerHTML = data.molds.map((m) => `
    <div class="doc-card" style="grid-column: 1 / -1;">
      <div class="doc-card-head">
        <span class="doc-title">${Utils.escapeHtml(m.mold)}${m.recognized_mold ? "" : " (unrecognized mold \u2014 falls back to no mold-match encoding, may reduce accuracy)"}</span>
        <span class="kpi-sub">${m.rows_used} cycle(s) used \u00b7 latest ${Utils.escapeHtml(m.cycle_id)}</span>
      </div>
      <div class="grid-subsystems" style="margin-top: var(--space-2);">
        ${m.predictions.map(renderPredictionCard).join("")}
      </div>
    </div>`).join("");
}

function statusClass(predictedState) {
  return predictedState.toLowerCase();
}

function renderPredictionCard(p) {
  const cls = statusClass(p.predicted_state);
  const max = Math.max(...p.top_features.map((f) => f.impact), 0.01);

  return `
    <div class="prediction-card">
      <div class="prediction-card-head">
        <span class="subsystem-name">${Utils.escapeHtml(p.subsystem_name)}</span>
        <span class="status-badge status-${cls}">${Utils.escapeHtml(p.predicted_state)}</span>
      </div>
      <div class="kpi-sub">Confidence <span class="cell-mono" style="font-family:var(--font-mono); color:var(--text-primary);">${(p.confidence * 100).toFixed(0)}%</span></div>

      <div>
        <div class="response-section-label">Top Feature Impacts</div>
        ${p.top_features.slice(0, 3).map((f) => `
          <div class="feature-impact-row">
            <span class="feature-name">${Utils.escapeHtml(f.feature)}</span>
            <div class="feature-impact-bar"><div class="feature-impact-bar-fill" style="width:${((f.impact / max) * 100).toFixed(0)}%"></div></div>
          </div>`).join("")}
      </div>

      <div class="recommended-action-box">
        ${Icons.svg("wrench", "", 15)}
        <span>${Utils.escapeHtml(p.recommended_action)}</span>
      </div>

      <div class="kpi-sub">Prediction window: ${Utils.escapeHtml(p.prediction_window)}</div>
    </div>`;
}
