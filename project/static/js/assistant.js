/**
 * Full AI Assistant chat page. Talks to POST /assistant/chat (mock;
 * see services/mock_assistant_service.py for the future LLM+SHAP+RAG
 * orchestration seam) and renders the future-ready response shape:
 * subsystem, predicted_state, confidence, top_features,
 * explanation_summary, maintenance_actions, severity, source_documents,
 * retrieved_manual_chunks.
 */
const CHAT_STORAGE_KEY = "moldguard_chat_thread_v1";
const SOURCE_STORAGE_KEY = "moldguard_chat_sources_v1";

document.addEventListener("DOMContentLoaded", () => {
  restoreChat();
  loadSuggestedPrompts();

  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");

  if (form && input) {
    form.addEventListener("submit", (e) => {
      e.preventDefault();

      const message = input.value.trim();

      if (!message) return;

      input.value = "";
      sendMessage(message);
    });
  }

  // Clear Chat button
  const clearBtn = document.getElementById("clear-chat-btn");

  if (clearBtn) {
    clearBtn.addEventListener("click", clearChat);
  }
});

function saveChat() {
  const thread = document.getElementById("chat-thread");
  const sources = document.getElementById("sources-list");

  if (thread) {
    localStorage.setItem(
      CHAT_STORAGE_KEY,
      thread.innerHTML
    );
  }

  if (sources) {
    localStorage.setItem(
      SOURCE_STORAGE_KEY,
      sources.innerHTML
    );
  }
}


function restoreChat() {
  const thread = document.getElementById("chat-thread");
  const sources = document.getElementById("sources-list");

  const savedThread =
    localStorage.getItem(CHAT_STORAGE_KEY);

  const savedSources =
    localStorage.getItem(SOURCE_STORAGE_KEY);

  if (thread && savedThread) {
    thread.innerHTML = savedThread;
  }

  if (sources && savedSources) {
    sources.innerHTML = savedSources;
  }
}


function clearChat() {
  localStorage.removeItem(CHAT_STORAGE_KEY);
  localStorage.removeItem(SOURCE_STORAGE_KEY);

  window.location.reload();
}
async function loadSuggestedPrompts() {
  const row = document.getElementById("suggested-prompts");
  try {
    const data = await Api.getSuggestedPrompts();
    row.innerHTML = data.prompts.map((p) => `<button type="button" class="prompt-chip" data-prompt="${Utils.escapeHtml(p)}">${Utils.escapeHtml(p)}</button>`).join("");
    row.querySelectorAll(".prompt-chip").forEach((chip) => {
      chip.addEventListener("click", () => sendMessage(chip.dataset.prompt));
    });
  } catch (err) {
    row.innerHTML = `<span class="empty-note">${Utils.escapeHtml(err.message || "Could not load suggested prompts.")}</span>`;
  }
}

async function sendMessage(message) {
  const thread = document.getElementById("chat-thread");
  const sendBtn = document.getElementById("chat-send-btn");

  thread.insertAdjacentHTML("beforeend", renderUserMessage(message));
  const thinkingId = `thinking-${Date.now()}`;
  thread.insertAdjacentHTML("beforeend", renderThinkingMessage(thinkingId));
  thread.scrollTop = thread.scrollHeight;
  if (sendBtn) sendBtn.disabled = true;

  try {
    const response = await Api.postAssistantChat(message);
    document.getElementById(thinkingId).outerHTML = renderAssistantMessage(response);
    updateSourcesRail(response);
    saveChat();
  } catch (err) {
    document.getElementById(thinkingId).outerHTML = renderAssistantErrorMessage(err);
    saveChat();

  } finally {
    if (sendBtn) sendBtn.disabled = false;
    thread.scrollTop = thread.scrollHeight;
  }
}

function renderUserMessage(text) {
  return `
    <div class="chat-msg from-user">
      <div class="chat-avatar avatar-user">YOU</div>
      <div class="chat-bubble">${Utils.escapeHtml(text)}</div>
    </div>`;
}

function renderThinkingMessage(id) {
  return `
    <div class="chat-msg from-ai" id="${id}">
      <div class="chat-avatar avatar-ai">${Icons.svg("network", "", 16)}</div>
      <div class="chat-bubble"><div class="loading-row"><span class="spinner"></span>Analyzing prediction, explanation, and manuals\u2026</div></div>
    </div>`;
}

function renderAssistantErrorMessage(err) {
  return `
    <div class="chat-msg from-ai">
      <div class="chat-avatar avatar-ai">${Icons.svg("network", "", 16)}</div>
      <div class="chat-bubble">${Utils.escapeHtml(err.message || "Something went wrong reaching the assistant.")}</div>
    </div>`;
}
function formatAssistantText(text) {
  if (!text) return "";

  // Escape HTML first for safety
  let safe = Utils.escapeHtml(text);

  // Remove markdown heading symbols
  safe = safe.replace(/^#{1,6}\s+/gm, "");

  // Convert **bold** into real bold HTML
  safe = safe.replace(
    /\*\*(.*?)\*\*/g,
    "<strong>$1</strong>"
  );

  // Convert *text* into emphasis
  safe = safe.replace(
    /(?<!\*)\*([^*\n]+)\*(?!\*)/g,
    "<strong>$1</strong>"
  );

  // Clean escaped / malformed markdown bullets
  safe = safe.replace(/^[\\]*[-*]\s+/gm, "• ");

  // Convert numbered items
  safe = safe.replace(
    /^(\d+)\.\s+/gm,
    "<strong>$1.</strong> "
  );

  // Convert line breaks
  safe = safe.replace(/\n/g, "<br>");

  return safe;
}
function renderAssistantMessage(r) {
  const max = Math.max(...(r.top_features || []).map((f) => f.impact), 0.01);
  const featuresHtml = (r.top_features || []).length
    ? r.top_features.map((f) => `
        <div class="feature-impact-row">
          <span class="feature-name">${Utils.escapeHtml(f.feature)}</span>
          <div class="feature-impact-bar"><div class="feature-impact-bar-fill" style="width:${((f.impact / max) * 100).toFixed(0)}%"></div></div>
        </div>`).join("")
    : "";

  const actionsHtml = (r.maintenance_actions || []).map((a) => `<li>${Icons.svg("check-circle", "", 14)}<span>${Utils.escapeHtml(a)}</span></li>`).join("");

  const citationsHtml = (r.source_documents || []).length
    ? `<div class="citation-chip-row">${r.source_documents.map((docId) => `<span class="citation-chip">${Icons.svg("file-text", "", 12)}${Utils.escapeHtml(docId)}</span>`).join("")}</div>`
    : `<span class="empty-note" style="padding:0;">No manual passage closely matched this question.</span>`;

  return `
    <div class="chat-msg from-ai">
      <div class="chat-avatar avatar-ai">${Icons.svg("network", "", 16)}</div>
      <div class="response-card">
        <div class="response-card-head">
          <span class="subsystem-name">${Utils.escapeHtml(Utils.capitalize(r.subsystem))} \u2014 ${Utils.escapeHtml(r.predicted_state)}</span>
          <span class="status-badge status-${r.predicted_state.toLowerCase()}">${(r.confidence * 100).toFixed(0)}% confidence</span>
        </div>

        <div class="assistant-answer">
          ${formatAssistantText(r.explanation_summary)}
        </div>
        ${featuresHtml ? `<div><div class="response-section-label">Top Contributing Factors</div>${featuresHtml}</div>` : ""}

        ${actionsHtml ? `<div><div class="response-section-label">Maintenance Actions</div><ul class="maintenance-action-list">${actionsHtml}</ul></div>` : ""}

        <div>
          <div class="response-section-label">Sources</div>
          ${citationsHtml}
        </div>
      </div>
    </div>`;
}

function updateSourcesRail(r) {
  const list = document.getElementById("sources-list");
  if (!list) return;

  if (!r.retrieved_manual_chunks || !r.retrieved_manual_chunks.length) {
    list.innerHTML = `<p class="empty-note">No manual passage closely matched this question. Try mentioning a subsystem or symptom directly.</p>`;
    return;
  }

  list.innerHTML = r.retrieved_manual_chunks.map((chunk) => `
    <div class="source-doc-card">
      <div class="doc-title">${Icons.svg("file-text", "", 13)} ${Utils.escapeHtml(chunk.document_title)}</div>
      <div class="doc-snippet">${Utils.escapeHtml(chunk.snippet)}</div>
    </div>`).join("");
}
