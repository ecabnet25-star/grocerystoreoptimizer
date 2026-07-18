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

const LANGUAGE_STORAGE_KEY = "grocery_lang";

function getCurrentLanguage() {
  const stored = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
  return stored === "fr" ? "fr" : "en";
}

function setCurrentLanguage(language) {
  const normalized = language === "fr" ? "fr" : "en";
  window.localStorage.setItem(LANGUAGE_STORAGE_KEY, normalized);
  document.documentElement.lang = normalized;
  return normalized;
}

function tr(english, french) {
  return getCurrentLanguage() === "fr" ? french : english;
}

window.getCurrentLanguage = getCurrentLanguage;
window.setCurrentLanguage = setCurrentLanguage;
window.tr = tr;

function applyGlobalPageLanguage(language) {
  const lang = setCurrentLanguage(language);
  const select = document.getElementById("languageSelect");
  if (select && select.value !== lang) {
    select.value = lang;
  }

  const languageLabel = document.querySelector(".nav-language-switcher span");
  if (languageLabel) {
    languageLabel.textContent = lang === "fr" ? "Langue" : "Language";
  }

  const page = (window.location.pathname.split("/").pop() || "index.html").toLowerCase();
  if (page === "index.html" || page === "") {
    return;
  }

  const copyByPage = {
    "about.html": [
      ["title", "About | unibite.click", "A propos | unibite.click"],
      [".nav-links a[href='about.html']", "About", "A propos"],
      [".nav-links a[href='index.html']", "Plan", "Planifier"],
      [".nav-links a[href='saved.html']", "Saved Plans", "Plans sauvegardes"],
      [".nav-links a[href='account.html']", "Account", "Compte"],
      [".about-hero-v2 .eyebrow", "Built in Montreal", "Construit a Montreal"],
      [".about-hero-v2 h1", "Make every grocery dollar work harder.", "Faites travailler chaque dollar d'epicerie."],
      [".about-hero-v2 .subtitle", "unibite.click turns your budget, food needs, nearby prices, and travel time into one clear shopping plan.", "unibite.click transforme votre budget, vos besoins, les prix proches et le temps de trajet en un plan clair."],
      [".about-hero-v2 .button-link", "Start a plan", "Commencer un plan"],
      [".purpose-band div:nth-child(1) h2", "Plan", "Planifier"],
      [".purpose-band div:nth-child(1) p", "Set a budget, location, and the foods you cannot leave without.", "Definissez un budget, une zone et les aliments indispensables."],
      [".purpose-band div:nth-child(2) h2", "Compare", "Comparer"],
      [".purpose-band div:nth-child(2) p", "See nearby stores, estimated totals, and the strongest per-item deals.", "Comparez les magasins proches, les totaux estimes et les meilleurs rabais."],
      [".purpose-band div:nth-child(3) h2", "Go", "Y aller"],
      [".purpose-band div:nth-child(3) p", "Follow a practical road route only when another stop is worth the trip.", "Suivez un trajet pratique seulement si l'arret supplementaire vaut le coup."],
      [".mission-band .eyebrow", "Our purpose", "Notre mission"],
      [".mission-band h2", "Clearer choices before checkout.", "Des choix plus clairs avant de payer."],
      [".mission-band p:last-child", "Food costs are hard enough without juggling flyers, maps, nutrition goals, and five open tabs. We built unibite.click to do that comparison work quickly and explain the result plainly. Price forecasts and store totals are estimates, so the app shows confidence and favors practical guidance over false certainty.", "Le cout alimentaire est deja difficile sans jongler entre circulaires, cartes, objectifs nutritionnels et onglets. Nous avons cree unibite.click pour comparer rapidement et expliquer clairement. Les previsions et totaux restent des estimations; l'app affiche la confiance et privilegie des conseils pratiques."],
    ],
    "account.html": [
      ["title", "Your Account | unibite.click", "Votre compte | unibite.click"],
      [".nav-links a[href='about.html']", "About", "A propos"],
      [".nav-links a[href='index.html']", "Plan", "Planifier"],
      [".nav-links a[href='saved.html']", "Saved Plans", "Plans sauvegardes"],
      [".nav-links a[href='account.html']", "Account", "Compte"],
      [".account-hero .eyebrow", "Plan across sessions", "Planifiez sur plusieurs sessions"],
      [".account-hero h1", "Your account", "Votre compte"],
      [".account-hero .subtitle", "Sign in to save plans, reuse shopping targets, and keep your grocery workflow moving.", "Connectez-vous pour sauvegarder vos plans et reutiliser vos objectifs de courses."],
      ["#accountInfo h2", "Current session", "Session actuelle"],
      ["#accountInfo .muted", "Your session is stored only for this browser tab. Closing the tab signs you out locally.", "Votre session est conservee seulement dans cet onglet. Fermer l'onglet vous deconnecte."],
      ["#createAccountForm .eyebrow", "New here", "Nouveau ici"],
      ["#createAccountForm h2", "Create new account", "Creer un compte"],
      ["#loginForm .eyebrow", "Welcome back", "Bon retour"],
      ["#loginForm h2", "Sign in", "Se connecter"],
      ["#sessionActions h2", "Session management", "Gestion de session"],
      ["#preferencesForm .eyebrow", "Your defaults", "Vos reglages"],
      ["#preferencesForm h2", "Food preferences", "Preferences alimentaires"],
      ["#preferencesForm .muted", "These are applied automatically whenever you generate a plan while signed in.", "Ces reglages sont appliques automatiquement a chaque plan lorsque vous etes connecte."],
      ["#savePreferencesBtn", "Save preferences", "Enregistrer les preferences"],
    ],
    "saved.html": [
      ["title", "Saved Plans | unibite.click", "Plans sauvegardes | unibite.click"],
      [".nav-links a[href='about.html']", "About", "A propos"],
      [".nav-links a[href='index.html']", "Plan", "Planifier"],
      [".nav-links a[href='saved.html']", "Saved Plans", "Plans sauvegardes"],
      [".nav-links a[href='account.html']", "Account", "Compte"],
      [".saved-hero .eyebrow", "Your grocery vault", "Votre coffre d'epicerie"],
      [".saved-hero h1", "Your saved plans", "Vos plans sauvegardes"],
      [".saved-hero .subtitle", "Browse, reuse, export, or tune grocery plans you already like.", "Parcourez, reutilisez, exportez ou ajustez vos plans preferes."],
      ["#savedSignedOutState .eyebrow", "Keep plans across visits", "Conservez vos plans entre les visites"],
      ["#savedSignedOutState h2", "Sign in to open your plan library.", "Connectez-vous pour ouvrir votre bibliotheque de plans."],
      ["#savedSignedOutState .muted", "Create an account once, then save, reuse, rename, print, and export your grocery plans here.", "Creez un compte, puis sauvegardez, reutilisez, renommez, imprimez et exportez vos plans ici."],
      ["#savedSignedOutState .button-link", "Sign in or create account", "Se connecter ou creer un compte"],
      ["#plansList .section-heading .eyebrow", "Library", "Bibliotheque"],
      ["#plansList .section-heading h2", "Saved grocery plans", "Plans d'epicerie sauvegardes"],
      ["#planDetail .eyebrow", "Plan detail", "Detail du plan"],
      ["#planDetail h2", "Review and reuse", "Revoir et reutiliser"],
    ],
  };

  const rows = copyByPage[page] || [];
  rows.forEach(([selector, en, fr]) => {
    if (selector === "title") {
      document.title = lang === "fr" ? fr : en;
      return;
    }
    const node = document.querySelector(selector);
    if (!node) return;
    node.textContent = lang === "fr" ? fr : en;
  });
}

function initGlobalLanguage() {
  const select = document.getElementById("languageSelect");
  const language = getCurrentLanguage();
  applyGlobalPageLanguage(language);
  if (!select) {
    return;
  }
  select.value = language;
  select.addEventListener("change", (event) => {
    const chosen = event.target.value === "fr" ? "fr" : "en";
    applyGlobalPageLanguage(chosen);
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initGlobalLanguage);
} else {
  initGlobalLanguage();
}

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
  if (getCurrentLanguage() === "fr") {
    const translated = { produce: "Fruits et legumes", protein: "Proteines", dairy: "Produits laitiers", grains: "Cereales", pantry: "Garde-manger" };
    if (translated[name.toLowerCase()]) return translated[name.toLowerCase()];
  }
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
  const authenticatedPayload = Session.isActive()
    ? { ...payload, user_id: Session.userId }
    : payload;
  return await apiRequest("/optimize", {
    method: "POST",
    headers: Session.isActive() ? { Authorization: `Bearer ${Session.authToken}` } : {},
    body: JSON.stringify(authenticatedPayload),
  });
}

async function loadProfilePreferences() {
  if (!Session.isActive()) {
    return { ok: false, data: { detail: "Not signed in" } };
  }
  return await apiRequest(`/users/${Session.userId}/profile`, {
    headers: { Authorization: `Bearer ${Session.authToken}` },
  });
}

async function saveProfilePreferences(preferences) {
  if (!Session.isActive()) {
    return { ok: false, data: { detail: "Not signed in" } };
  }
  return await apiRequest(`/users/${Session.userId}/profile`, {
    method: "PATCH",
    headers: { Authorization: `Bearer ${Session.authToken}` },
    body: JSON.stringify(preferences),
  });
}

async function loadCurrentDeals(filters = {}) {
  const params = new URLSearchParams();
  params.set("postal_code", filters.postal_code || "H3A1A1");
  if (filters.category) params.set("category", filters.category);
  if (filters.chain) params.set("chain", filters.chain);
  if (filters.q) params.set("q", filters.q);
  params.set("sort_by", filters.sort_by || "savings");
  params.set("sale_only", filters.sale_only === false ? "false" : "true");
  return await apiRequest(`/deals?${params.toString()}`);
}

async function savePlan(label, optimizeRequest, optimizationResult = null) {
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
      optimization_result: optimizationResult,
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
  const rows = [["Item", "Category", "Quantity", "Purchase Price", "Unit Price", "Savings", "Currency", "Recommended Store", "Store Address"]];
  items.forEach((item) => {
    rows.push([
      item.name || "",
      item.category || "",
      String(item.quantity ?? ""),
      String(item.purchase_price ?? item.total_cost ?? ""),
      String(item.recommended_store_unit_price ?? ""),
      String(item.store_savings ?? ""),
      currency,
      item.recommended_store || "",
      item.recommended_store_address || "",
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
  params.set("transportation_mode", payload.transportation_mode || "transit");
  params.set("country_hint", payload.country_hint || "");

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
