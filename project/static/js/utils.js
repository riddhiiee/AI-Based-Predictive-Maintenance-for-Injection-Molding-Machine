/**
 * Shared helpers used across pages: live clock, toast notifications,
 * formatting, and small DOM utilities. No framework, no build step.
 */
const Utils = (() => {
  function escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function capitalize(str) {
    if (!str) return "";
    return str.charAt(0).toUpperCase() + str.slice(1);
  }

  function formatTime(isoOrDate) {
    const d = isoOrDate instanceof Date ? isoOrDate : new Date(isoOrDate);
    if (isNaN(d.getTime())) return "";
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function formatDate(isoOrDate) {
    const d = isoOrDate instanceof Date ? isoOrDate : new Date(isoOrDate);
    if (isNaN(d.getTime())) return "";
    return d.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
  }

  function timeAgo(iso) {
    const then = new Date(iso).getTime();
    if (isNaN(then)) return "";
    const diffMs = Date.now() - then;
    const mins = Math.round(diffMs / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.round(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.round(hrs / 24);
    return `${days}d ago`;
  }

  function startClock(dateElId, timeElId) {
    const dateEl = document.getElementById(dateElId);
    const timeEl = document.getElementById(timeElId);
    if (!dateEl || !timeEl) return;
    function tick() {
      const now = new Date();
      dateEl.textContent = formatDate(now);
      timeEl.textContent = formatTime(now);
    }
    tick();
    setInterval(tick, 30000);
  }

  let lastToastMessage = "";
  let lastToastAt = 0;

  function toast(message, variant = "info") {
    const root = document.getElementById("toast-root");
    if (!root) return;

    // Several dashboard panels load in parallel. If the backend is offline they
    // may fail together; show one useful connection message instead of stacking
    // duplicate red toasts.
    const now = Date.now();
    if (message === lastToastMessage && now - lastToastAt < 2500) return;
    lastToastMessage = message;
    lastToastAt = now;

    const el = document.createElement("div");
    el.className = `toast ${variant === "error" ? "toast-error" : variant === "success" ? "toast-success" : ""}`;
    el.textContent = message;
    root.appendChild(el);
    setTimeout(() => el.remove(), 5000);
  }

  function loadingRow(label = "Loading\u2026") {
    return `<div class="loading-row"><span class="spinner"></span>${escapeHtml(label)}</div>`;
  }

  function stateBlock(iconSvgMarkup, title, subtitle) {
    return `<div class="state-block">${iconSvgMarkup || ""}<h3>${escapeHtml(title)}</h3>${subtitle ? `<p>${escapeHtml(subtitle)}</p>` : ""}</div>`;
  }

  function errorBlock(err, retryLabel = "Retry") {
    const message = err instanceof Error ? err.message : String(err);
    const title = err && err.status === 0 ? "Backend connection unavailable" : "API request failed";
    return `<div class="state-block">
      <h3>${escapeHtml(title)}</h3>
      <p>${escapeHtml(message)}</p>
    </div>`;
  }

  return { escapeHtml, capitalize, formatTime, formatDate, timeAgo, startClock, toast, loadingRow, stateBlock, errorBlock };
})();

document.addEventListener("DOMContentLoaded", () => {
  Utils.startClock("topbar-date", "topbar-time");
});
