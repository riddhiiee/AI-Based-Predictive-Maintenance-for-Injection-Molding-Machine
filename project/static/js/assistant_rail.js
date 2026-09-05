/**
 * Behavior for the compact, docked AI Assistant rail (partials/_assistant_rail.html).
 * Shown on the Dashboard and Predictions pages.
 */
document.addEventListener("DOMContentLoaded", () => {
  const feed = document.getElementById("assistant-rail-feed");
  const form = document.getElementById("assistant-rail-form");
  const input = document.getElementById("assistant-rail-text");
  if (!feed || !form || !input) return;

  loadInitialInsights();

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const message = input.value.trim();
    if (!message) return;
    input.value = "";
    appendThinkingCard();

    try {
      const response = await Api.postAssistantChat(message);
      replaceThinkingCard(renderAssistantResponseCard(response));
    } catch (err) {
      replaceThinkingCard(renderErrorCard(err));
    }
  });

  async function loadInitialInsights() {
    try {
      const [alertsData, predictionsData] = await Promise.all([Api.getAlerts(), Api.getPredictAll()]);
      feed.innerHTML = "";

      alertsData.alerts.slice(0, 2).forEach((alert) => {
        feed.insertAdjacentHTML("beforeend", renderAlertCard(alert));
      });

      const topPrediction = [...predictionsData.predictions].sort((a, b) => sevRank(b.severity) - sevRank(a.severity))[0];
      if (topPrediction) {
        feed.insertAdjacentHTML("beforeend", renderRecommendationCard(topPrediction));
      }

      if (!feed.children.length) {
        feed.innerHTML = `<p class="empty-note">No active insights right now.</p>`;
      }
    } catch (err) {
      feed.innerHTML = `<p class="empty-note">${Utils.escapeHtml(err.message || "Could not load insights.")}</p>`;
    }
  }

  function sevRank(sev) {
    return { high: 3, medium: 2, low: 1 }[sev] || 0;
  }

  function renderAlertCard(alert) {
    const tone = alert.severity === "high" ? "critical" : alert.severity === "medium" ? "warning" : "info";
    const iconName = alert.subsystem === "heater" ? "flame" : alert.subsystem === "hydraulic" ? "droplet" : "alert-triangle";
    return `
      <div class="insight-card tone-${tone}">
        <div class="insight-card-head">${Icons.svg(iconName, "", 15)}<span>${Utils.escapeHtml(alert.title)}</span></div>
        <div class="insight-card-body">
          <p>${Utils.escapeHtml(alert.detail)}</p>
        </div>
        <span class="insight-card-time">${Utils.timeAgo(alert.timestamp)}</span>
      </div>`;
  }

  function renderRecommendationCard(prediction) {
    return `
      <div class="insight-card tone-action">
        <div class="insight-card-head">${Icons.svg("wrench", "", 15)}<span>Recommend: ${Utils.escapeHtml(prediction.subsystem_name)}</span></div>
        <div class="insight-card-body">
          <p>${Utils.escapeHtml(prediction.recommended_action)}</p>
        </div>
        <span class="insight-card-time">${Utils.escapeHtml(prediction.prediction_window)}</span>
      </div>`;
  }

  function appendThinkingCard() {
    feed.insertAdjacentHTML("beforeend", `<div class="insight-card tone-info" id="thinking-card"><div class="loading-row"><span class="spinner"></span>Thinking\u2026</div></div>`);
    feed.scrollTop = feed.scrollHeight;
  }

  function replaceThinkingCard(html) {
    const el = document.getElementById("thinking-card");
    if (el) el.outerHTML = html;
    feed.scrollTop = feed.scrollHeight;
  }

  function renderAssistantResponseCard(r) {
    return `
      <div class="insight-card tone-action">
        <div class="insight-card-head">${Icons.svg("message-square", "", 15)}<span>${Utils.escapeHtml(Utils.capitalize(r.subsystem))} \u2014 ${Utils.escapeHtml(r.predicted_state)}</span></div>
        <div class="insight-card-body">
          <p style="white-space:pre-line;">${Utils.escapeHtml(r.explanation_summary)}</p>
        </div>
        <span class="insight-card-time">Confidence ${(r.confidence * 100).toFixed(0)}%</span>
      </div>`;
  }

  function renderErrorCard(err) {
    return `<div class="insight-card tone-critical"><div class="insight-card-head">${Icons.svg("alert-triangle", "", 15)}<span>Couldn't reach assistant</span></div><div class="insight-card-body"><p>${Utils.escapeHtml(err.message || "Unknown error")}</p></div></div>`;
  }
});
