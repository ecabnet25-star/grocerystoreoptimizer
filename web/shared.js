// Shared utilities and state management for all pages

// API base URL — auto-detect based on environment
const API_BASE = (function() {
  // If served from a dev server on port 8080, proxy to the API on 8000
  if (window.location.port === "8080") {
    return "http://127.0.0.1:8000";
  }
  // If served from the API itself (same origin), use relative URLs
  if (window.location.port === "8000") {
    return "";
  }
  // For file:// protocol or other dev scenarios, default to localhost API
  if (window.location.protocol === "file:") {
    return "http://127.0.0.1:8000";
  }
  // Otherwise, assume same origin
  return window.location.origin;
})();

// HTML escaping — MUST be used for ALL user data rendered into HTML
function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

const sessionStore = window.sessionStorage;
const legacyLocalStore = window.localStorage;

function getSessionValue(key) {
  const value = sessionStore.getItem(key);
  if (value) {
    return value;
  }
  const legacyValue = legacyLocalStore.getItem(key) || "";
  if (legacyValue) {
    sessionStore.setItem(key, legacyValue);
    legacyLocalStore.removeItem(key);
  }
  return legacyValue;
}

function setSessionValue(key, value) {
  if (value) {
    sessionStore.setItem(key, value);
  } else {
    sessionStore.removeItem(key);
  }
  legacyLocalStore.removeItem(key);
}

// Session state (kept in sessionStorage so tokens are cleared when the tab closes)
const Session = {
  get userId() {
    return getSessionValue("grocery_user_id");
  },
  set userId(value) {
    setSessionValue("grocery_user_id", value);
  },
  get authToken() {
    return getSessionValue("grocery_auth_token");
  },
  set authToken(value) {
    setSessionValue("grocery_auth_token", value);
  },
  get userName() {
    return getSessionValue("grocery_user_name");
  },
  set userName(value) {
    setSessionValue("grocery_user_name", value);
  },
  clear() {
    this.userId = "";
    this.authToken = "";
    this.userName = "";
  },
  isActive() {
    return !!(this.userId && this.authToken);
  },
};

// Toast notification system
function showToast(message, type = "info", duration = 4000) {
  const container = document.getElementById("toastContainer");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      toast.classList.add("toast-visible");
    });
  });
  setTimeout(() => {
    toast.classList.remove("toast-visible");
    toast.addEventListener("transitionend", () => toast.remove());
    // Fallback removal if transitionend doesn't fire
    setTimeout(() => {
      if (toast.parentNode) toast.remove();
    }, 500);
  }, duration);
}

// Status banner utilities
function showStatus(message, type = "info") {
  const banner = document.getElementById("statusBanner");
  if (banner) {
    banner.className = `status ${type}`;
    banner.textContent = message;
  }
  // Also show ephemeral toast for error and success messages
  if (type === "error") {
    showToast(message, "error", 5000);
  } else if (type === "success") {
    showToast(message, "success", 3000);
  }
}

// Formatting helpers
function formatCurrency(value, currency = "CAD") {
  const amount = Number(value || 0);
  return amount.toLocaleString("en-CA", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  });
}

function prettyCategory(name) {
  if (!name) return "-";
  return name[0].toUpperCase() + name.slice(1);
}

function formatDate(isoString) {
  if (!isoString) return "Unknown";
  const date = new Date(isoString);
  return date.toLocaleDateString("en-CA", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// API helpers
async function apiRequest(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
    });
    const raw = await response.text();
    let data = {};
    if (raw) {
      try {
        data = JSON.parse(raw);
      } catch {
        data = { detail: raw };
      }
    }
    return { ok: response.ok, status: response.status, data };
  } catch (error) {
    return { ok: false, status: 0, data: { detail: error.message } };
  }
}

async function createUser(name, email, password) {
  const result = await apiRequest("/users", {
    method: "POST",
    body: JSON.stringify({ name, email, password }),
  });

  if (result.ok) {
    Session.userId = result.data.user.id;
    Session.authToken = result.data.auth_token;
    Session.userName = result.data.user.name;
  }

  return result;
}

async function loginUser(email, password) {
  const result = await apiRequest("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });

  if (result.ok) {
    Session.userId = result.data.user.id;
    Session.authToken = result.data.auth_token;
    Session.userName = result.data.user.name;
  }

  return result;
}

async function refreshToken() {
  if (!Session.isActive()) {
    return { ok: false, data: { detail: "Not signed in" } };
  }

  const result = await apiRequest("/auth/refresh", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${Session.authToken}`,
    },
    body: JSON.stringify({
      user_id: Session.userId,
    }),
  });

  if (result.ok) {
    Session.authToken = result.data.auth_token;
  }

  return result;
}

async function logoutUser() {
  if (!Session.isActive()) {
    return { ok: false, data: { detail: "Not signed in" } };
  }

  const result = await apiRequest("/auth/logout", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${Session.authToken}`,
    },
    body: JSON.stringify({
      user_id: Session.userId,
    }),
  });

  if (result.ok) {
    Session.clear();
  }

  return result;
}

async function logoutAllSessions() {
  if (!Session.isActive()) {
    return { ok: false, data: { detail: "Not signed in" } };
  }

  const result = await apiRequest("/auth/logout-all", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${Session.authToken}`,
    },
    body: JSON.stringify({
      user_id: Session.userId,
    }),
  });

  if (result.ok) {
    Session.clear();
  }

  return result;
}

async function optimizePlan(payload) {
  return await apiRequest("/optimize", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

async function savePlan(label, optimizeRequest) {
  if (!Session.isActive()) {
    return { ok: false, data: { detail: "Not signed in" } };
  }

  return await apiRequest(`/users/${Session.userId}/plans`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${Session.authToken}`,
    },
    body: JSON.stringify({
      label,
      optimize_request: optimizeRequest,
    }),
  });
}

async function listPlans(limit = 20, offset = 0) {
  if (!Session.isActive()) {
    return { ok: false, data: { detail: "Not signed in" } };
  }

  return await apiRequest(`/users/${Session.userId}/plans?limit=${limit}&offset=${offset}`, {
    headers: {
      Authorization: `Bearer ${Session.authToken}`,
    },
  });
}

function buildPlanCsvRows(plan) {
  const result = plan?.result || plan || {};
  const location = result.location || {};
  const currency = location.currency || result.insights?.currency || "CAD";
  const items = Array.isArray(result.items) ? result.items : [];
  const rows = [["Item", "Category", "Quantity", "Cost", "Currency", "Recommended Store"]];
  items.forEach((item) => {
    rows.push([
      item.name || "",
      item.category || "",
      String(item.quantity ?? ""),
      String(item.total_cost ?? ""),
      currency,
      item.recommended_store || "",
    ]);
  });
  return rows;
}

function downloadCsv(filename, rows) {
  const csv = rows
    .map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(","))
    .join("\r\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function printPlanView() {
  window.print();
}

async function getPlan(planId) {
  if (!Session.isActive()) {
    return { ok: false, data: { detail: "Not signed in" } };
  }

  return await apiRequest(`/users/${Session.userId}/plans/${planId}`, {
    headers: {
      Authorization: `Bearer ${Session.authToken}`,
    },
  });
}

async function renamePlan(planId, label) {
  if (!Session.isActive()) {
    return { ok: false, data: { detail: "Not signed in" } };
  }

  return await apiRequest(`/users/${Session.userId}/plans/${planId}`, {
    method: "PATCH",
    headers: {
      Authorization: `Bearer ${Session.authToken}`,
    },
    body: JSON.stringify({ label }),
  });
}

async function deletePlan(planId) {
  if (!Session.isActive()) {
    return { ok: false, data: { detail: "Not signed in" } };
  }

  return await apiRequest(`/users/${Session.userId}/plans/${planId}`, {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${Session.authToken}`,
    },
  });
}

async function loadLocations() {
  const result = await apiRequest("/locations");
  if (result.ok && result.data.locations) {
    return result.data.locations;
  }
  return [];
}

async function loadStores(postalCode = "", location = "") {
  const params = new URLSearchParams();
  if (postalCode) params.set("postal_code", postalCode);
  if (location) params.set("location", location);

  const result = await apiRequest(`/stores?${params}`);
  if (result.ok) {
    return result.data;
  }
  return null;
}

async function loadPostalCodes(country = "") {
  const params = new URLSearchParams();
  if (country) params.set("country", country);

  const result = await apiRequest(`/postal-codes?${params}`);
  if (result.ok) {
    return result.data;
  }
  return null;
}

async function loadLivePricing(payload) {
  const params = new URLSearchParams();
  params.set("location", payload.location || "montreal");
  params.set("postal_code", payload.postal_code || "");
  params.set("address", payload.address || "");
  params.set("budget", String(payload.budget ?? 50));
  params.set("max_items", String(payload.max_items ?? 8));
  params.set("strategy", payload.strategy || "knapsack");

  const result = await apiRequest(`/pricing/live?${params.toString()}`);
  if (result.ok) {
    return result.data;
  }
  return null;
}

async function askMealAssistant(payload) {
  return await apiRequest("/assistant/chat", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
