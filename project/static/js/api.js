/**
 * Browser client for the FastAPI backend.
 *
 * The Flask UI runs on :5000 and FastAPI runs on :8000.  On some Windows
 * machines `localhost` resolves to IPv6 (::1) while Uvicorn is listening on
 * 127.0.0.1, which makes an otherwise healthy backend look unreachable.
 * This client therefore prefers the explicit IPv4 loopback and transparently
 * falls back between 127.0.0.1 and localhost on connection errors.
 */
const Api = (() => {
  const configuredBase = (window.API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
  const candidates = Array.from(new Set([
    configuredBase,
    "http://127.0.0.1:8000",
    "http://localhost:8000",
  ]));
  let activeBase = configuredBase;

  class ApiError extends Error {
    constructor(message, status, cause) {
      super(message);
      this.name = "ApiError";
      this.status = status;
      this.cause = cause;
    }
  }

  async function fetchWithFallback(path, options = {}) {
    const orderedBases = [activeBase, ...candidates.filter((b) => b !== activeBase)];
    let lastNetworkError = null;

    for (const base of orderedBases) {
      try {
        const response = await fetch(`${base}${path}`, options);
        activeBase = base;
        return response;
      } catch (err) {
        lastNetworkError = err;
      }
    }

    throw new ApiError(
      `Could not reach the FastAPI backend on port 8000. Start it with: python -m uvicorn api.main:app --host 127.0.0.1 --port 8000`,
      0,
      lastNetworkError
    );
  }

  async function request(path, options = {}) {
    const res = await fetchWithFallback(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });

    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        detail = body.detail || detail;
      } catch (_) {
        /* ignore parse failure */
      }
      throw new ApiError(detail, res.status);
    }
    if (res.status === 204) return null;
    return res.json();
  }

  async function multipart(path, form) {
    const res = await fetchWithFallback(path, { method: "POST", body: form });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        detail = body.detail || detail;
      } catch (_) { /* ignore */ }
      throw new ApiError(detail, res.status);
    }
    return res.json();
  }

  return {
    ApiError,
    getBase: () => activeBase,
    get: (path) => request(path, { method: "GET" }),
    post: (path, body) => request(path, { method: "POST", body: JSON.stringify(body) }),

    getHealth: () => request("/health"),
    getSubsystems: () => request("/subsystems"),
    getPredictAll: () => request("/predict/all"),
    getLiveMachine: () => request("/live-machine"),
    selectLiveMachine: (moldName) => request("/live-machine/select", { method: "POST", body: JSON.stringify({ mold_name: moldName }) }),
    getPredictOne: (subsystem) => request(`/predict/${subsystem}`),
    getUploadRequirements: () => request("/predict/upload-requirements"),
    getCurrentUpload: () => request("/predict/current-upload"),
    clearCurrentUpload: () => request("/predict/clear-upload", { method: "POST", body: JSON.stringify({}) }),
    postPredictUpload: async (file) => {
      const form = new FormData();
      form.append("file", file);
      return multipart("/predict/upload", form);
    },
    getExplain: (subsystem) => request(`/explain/${subsystem}`),
    getMaintenanceNeeds: () => request("/maintenance-needs"),
    getTrends: (limit = 50) =>
      request(`/trends?limit=${encodeURIComponent(limit)}`),
    getAlerts: () => request("/alerts"),
    getSuggestedPrompts: () => request("/assistant/suggested-prompts"),
    postAssistantChat: (message, subsystemHint) =>
      request("/assistant/chat", { method: "POST", body: JSON.stringify({ message, subsystem_hint: subsystemHint || null }) }),
    getDocuments: () => request("/rag/documents"),
    postUploadDocument: (filename, subsystem, docType) =>
      request("/rag/upload", { method: "POST", body: JSON.stringify({ filename, subsystem, doc_type: docType }) }),
    postUploadDocumentFile: async (file, subsystem, docType) => {
      const form = new FormData();
      form.append("file", file);
      if (subsystem) form.append("subsystem", subsystem);
      if (docType) form.append("doc_type", docType);
      return multipart("/rag/upload-file", form);
    },
    postQueryKnowledgeBase: (query, subsystemFilter) =>
      request("/rag/query", { method: "POST", body: JSON.stringify({ query, subsystem_filter: subsystemFilter || null }) }),
    getHistory: (params = {}) => {
      const qs = new URLSearchParams(params).toString();
      return request(`/history${qs ? `?${qs}` : ""}`);
    },
  };
})();
