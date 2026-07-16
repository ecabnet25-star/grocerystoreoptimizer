// Plan generation page (index.html)

let lastOptimizationPayload = null;
let lastOptimizationResult = null;
let lastLocationCurrency = "CAD";
let livePricingIntervalId = null;
let chefIsResponding = false;
let routeMap = null;
const storeChecklistState = new Map();
const PRESET_BREAKDOWNS = {
  balanced: {
    title: "Balanced split",
    values: { produce: 34, protein: 30, grains: 18, savings: 12, pantry: 6 },
  },
  budget: {
    title: "Budget saver split",
    values: { produce: 20, protein: 18, grains: 24, savings: 28, pantry: 10 },
  },
  protein: {
    title: "High protein split",
    values: { produce: 22, protein: 46, grains: 14, savings: 8, pantry: 10 },
  },
  fresh: {
    title: "Fresh produce split",
    values: { produce: 52, protein: 20, grains: 10, savings: 8, pantry: 10 },
  },
};

let currentLanguage = "en";

const UI_COPY = {
  en: {
    moreOptions: "More options",
    generatePlan: "Generate plan",
    print: "Print",
    exportCsv: "Export CSV",
    savePlan: "Save plan",
    refreshPrices: "Refresh prices",
    copyItems: "Copy items",
    mustHaveHint: "Enter the exact item name when possible, then add commas for multiple items.",
    routeTradeoffPrefix: "Travel tradeoff:",
    routeTradeoffDefault: "We only split stores when the savings beat the extra trip cost.",
    retailerCoverage: "Coverage priorities show which chains we price first and which sources back them.",
    mapEmpty: "Enter a postal code or street address to see stores on the map.",
  },
  fr: {
    moreOptions: "Plus d'options",
    generatePlan: "Générer le plan",
    print: "Imprimer",
    exportCsv: "Exporter CSV",
    savePlan: "Enregistrer le plan",
    refreshPrices: "Actualiser les prix",
    copyItems: "Copier les articles",
    mustHaveHint: "Saisissez si possible le nom exact de l'article, puis utilisez des virgules pour plusieurs articles.",
    routeTradeoffPrefix: "Compromis trajet :",
    routeTradeoffDefault: "Nous séparons les magasins seulement si l'économie dépasse le coût du trajet supplémentaire.",
    retailerCoverage: "Les priorités de couverture montrent quelles enseignes sont évaluées en premier et quelles sources les soutiennent.",
    mapEmpty: "Entrez un code postal ou une adresse pour voir les magasins sur la carte.",
  },
};

function getUiCopy() {
  return UI_COPY[currentLanguage] || UI_COPY.en;
}

function applyLanguage(language) {
  currentLanguage = language === "fr" ? "fr" : "en";
  document.documentElement.lang = currentLanguage;
  const copy = getUiCopy();
  document.title = currentLanguage === "fr" ? "unibite.click | Planification d'épicerie" : "unibite.click | Smart grocery planning";
  const prefsToggle = document.getElementById("prefsToggle");
  const generateBtn = document.getElementById("generateBtn");
  const printBtn = document.getElementById("printCurrentPlanBtn");
  const exportBtn = document.getElementById("exportCurrentPlanCsvBtn");
  const saveBtn = document.getElementById("savePlanBtn");
  const refreshBtn = document.getElementById("refreshPricingBtn");
  const copyBtn = document.getElementById("copyShoppingListBtn");
  const mustHave = document.getElementById("mustHaveItems");
  const mapEmpty = document.getElementById("storeMapEmpty");
  const languageLabel = document.querySelector(".nav-language-switcher span");
  const heroEyebrow = document.querySelector(".hero-copy .eyebrow");
  const heroTitle = document.querySelector(".hero-copy h1");
  const heroSubtitle = document.querySelector(".hero-copy .subtitle");
  const stepEyebrow = document.querySelector(".planner-toolbar .eyebrow");
  const stepTitle = document.querySelector(".planner-toolbar h2");
  const resultTitle = document.querySelector("#result h2");
  const insightsTitle = document.querySelector("#planInsights h3");
  const forecastEyebrow = document.querySelector("#priceForecast .eyebrow");
  const forecastTitle = document.getElementById("priceForecastTitle");
  const nearbyTitle = document.querySelector("#storeComparison h3");
  const retailerTitle = document.querySelector("#retailerIntelPanel h4");
  const routeTitle = document.querySelector("#routeInfo h3");
  const routeInfoLine = document.querySelector("#routeInfo .muted");
  const saveLabel = document.querySelector("#saveModal label");
  const saveConfirm = document.getElementById("saveModalConfirm");
  const saveCancel = document.getElementById("saveModalCancel");
  const chefTitle = document.querySelector("#chefWidget .chef-panel-header h3");
  const chefClose = document.getElementById("chefCloseBtn");
  const chefLauncher = document.querySelector(".chef-launch-text");
  const chefInput = document.getElementById("assistantInput");
  const tableHeaders = document.querySelectorAll("#result thead th");
  const actionTiles = document.querySelectorAll("#planActionBoard .action-tile");
  const promptButtons = document.querySelectorAll("#chefWidget .chef-prompt");
  const routeBadge = document.getElementById("mapRouteBadge");
  const openDirections = document.getElementById("openDirectionsLink");
  const routeTradeoff = document.getElementById("routeTradeoffText");

  if (languageLabel) languageLabel.textContent = currentLanguage === "fr" ? "Langue" : "Language";
  if (heroEyebrow) heroEyebrow.textContent = currentLanguage === "fr" ? "Budget malin · magasinage rapide" : "Budget smart · shop faster";
  if (heroTitle) heroTitle.textContent = currentLanguage === "fr" ? "Dépensez moins. Mangez bien. Sachez où magasiner." : "Spend less. Eat well. Know where to shop.";
  if (heroSubtitle) heroSubtitle.textContent = currentLanguage === "fr" ? "Équilibrez le coût, la nutrition, la fraîcheur, les estimations des magasins proches et le trajet en une seule étape." : "Balance cost, nutrition, freshness, nearby store estimates, and route planning in one pass.";
  if (stepEyebrow) stepEyebrow.textContent = currentLanguage === "fr" ? "Étape 1" : "Step 1";
  if (stepTitle) stepTitle.textContent = currentLanguage === "fr" ? "Définissez votre panier" : "Set your shopping target";
  if (prefsToggle) prefsToggle.textContent = copy.moreOptions;
  if (generateBtn) generateBtn.textContent = copy.generatePlan;
  if (printBtn) printBtn.textContent = copy.print;
  if (exportBtn) exportBtn.textContent = copy.exportCsv;
  if (saveBtn) saveBtn.textContent = copy.savePlan;
  if (refreshBtn) refreshBtn.textContent = copy.refreshPrices;
  if (copyBtn) copyBtn.textContent = copy.copyItems;
  if (mustHave) mustHave.placeholder = currentLanguage === "fr" ? "Poulet, pommes, avoine" : "Chicken breast, apples, oats";
  if (mapEmpty) mapEmpty.textContent = copy.mapEmpty;
  if (resultTitle) resultTitle.textContent = currentLanguage === "fr" ? "Votre plan optimisé" : "Your optimized plan";
  if (insightsTitle) insightsTitle.textContent = currentLanguage === "fr" ? "Aperçu du plan" : "Plan insights";
  if (forecastEyebrow) forecastEyebrow.textContent = currentLanguage === "fr" ? "Prévision des prix sur 7 jours" : "7-day price outlook";
  if (forecastTitle) forecastTitle.textContent = currentLanguage === "fr" ? "Meilleur moment pour magasiner" : "Best time to shop";
  if (nearbyTitle) nearbyTitle.textContent = currentLanguage === "fr" ? "Magasins proches" : "Nearby stores";
  if (retailerTitle) retailerTitle.textContent = currentLanguage === "fr" ? "Priorités de couverture" : "Coverage priorities";
  if (routeTitle) routeTitle.textContent = currentLanguage === "fr" ? "Itinéraire suggéré" : "Suggested route";
  if (routeInfoLine) routeInfoLine.innerHTML = currentLanguage === "fr" ? "<strong>De :</strong> <span id=\"routeOriginLabel\">-</span> &mdash; <strong>Total :</strong> <span id=\"routeTotalDistance\"></span> km" : "<strong>From:</strong> <span id=\"routeOriginLabel\">-</span> &mdash; <strong>Total:</strong> <span id=\"routeTotalDistance\"></span> km";
  if (saveLabel) saveLabel.textContent = currentLanguage === "fr" ? "Nommez votre plan" : "Name your plan";
  if (saveConfirm) saveConfirm.textContent = currentLanguage === "fr" ? "Enregistrer" : "Save";
  if (saveCancel) saveCancel.textContent = currentLanguage === "fr" ? "Annuler" : "Cancel";
  if (chefTitle) chefTitle.textContent = currentLanguage === "fr" ? "Le Chef" : "The Chef";
  if (chefClose) chefClose.textContent = currentLanguage === "fr" ? "Fermer" : "Close";
  if (chefLauncher) chefLauncher.textContent = currentLanguage === "fr" ? "Demander au Chef" : "Ask The Chef";
  if (chefInput) chefInput.placeholder = currentLanguage === "fr" ? "Demandez des idées de repas au Chef..." : "Ask The Chef for meal ideas...";
  if (tableHeaders.length === 6) {
    const labels = currentLanguage === "fr"
      ? ["Article", "Catégorie", "Qté", "Prix du magasin", "Économies", "Acheter à"]
      : ["Item", "Category", "Qty", "Store price", "Savings", "Buy at"];
    tableHeaders.forEach((header, index) => {
      header.textContent = labels[index] || header.textContent;
    });
  }
  actionTiles.forEach((tile, index) => {
    const titleEl = tile.querySelector("strong");
    const subtitleEl = tile.querySelector("span");
    const copyRows = currentLanguage === "fr"
      ? [["Dîners rapides", "Demander au Chef"], ["Préparation", "Créer l'horaire"], ["Liste d'épicerie", "Copier les articles"], ["Fraîcheur", "À utiliser en premier"], ["Mode offres", "Voir les offres"]]
      : [["Fast dinners", "Ask The Chef"], ["Meal prep", "Build schedule"], ["Shopping list", "Copy items"], ["Freshness", "Use first"], ["Sale mode", "Browse deals"]];
    const row = copyRows[index];
    if (row && subtitleEl) subtitleEl.textContent = row[0];
    if (row && titleEl) titleEl.textContent = row[1];
  });
  promptButtons.forEach((button, index) => {
    const labels = currentLanguage === "fr"
      ? ["Dîners rapides", "Préparation", "Utiliser les ingrédients frais d'abord"]
      : ["Fast dinners", "Meal prep", "Use fresh items first"];
    if (labels[index]) button.textContent = labels[index];
  });
  if (routeBadge && routeBadge.textContent === "Best value") routeBadge.textContent = currentLanguage === "fr" ? "Meilleure valeur" : "Best value";
  if (openDirections && openDirections.textContent === "Open directions") openDirections.textContent = currentLanguage === "fr" ? "Ouvrir l'itinéraire" : "Open directions";
  if (routeTradeoff && !routeTradeoff.textContent) routeTradeoff.textContent = currentLanguage === "fr" ? "Le compromis trajet s’affichera ici après génération du plan." : "Travel tradeoff will appear here after a plan is generated.";
}

function splitList(value) {
  return String(value || "")
    .split(",")
    .map((x) => x.trim())
    .filter((x) => x.length > 0);
}

// escapeHtml is defined in shared.js

function toKey(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "item";
}

function updateChecklistProgress(container) {
  if (!container) {
    return;
  }
  const checks = [...container.querySelectorAll("input.store-check-item")];
  const selected = checks.filter((c) => c.checked).length;
  const progress = container.querySelector(".checklist-progress");
  if (progress) {
    progress.textContent = `${selected}/${checks.length} selected`;
  }
}

function setBudgetCurrencyLabel(currency) {
  const budgetLabelText = document.getElementById("budgetLabelText");
  if (budgetLabelText) {
    budgetLabelText.textContent = `Budget (${currency || "CAD"})`;
  }
  updatePlanPreview();
}

function updatePlanPreview() {
  const pill = document.getElementById("planPreviewPill");
  if (!pill) {
    return;
  }

  const budget = Number(document.getElementById("budget")?.value || 0);
  const maxItems = Number(document.getElementById("maxItems")?.value || 0);
  const strategy = document.getElementById("strategy")?.value === "knapsack" ? "Best value" : "Quick pick";
  pill.textContent = `${formatCurrency(budget, lastLocationCurrency)} · ${maxItems || 0} items · ${strategy}`;
  updateHeroBreakdownTotal();
}

function updateHeroBreakdownTotal() {
  const total = document.getElementById("breakdownTotal");
  if (!total) {
    return;
  }
  const budget = Number(document.getElementById("budget")?.value || 0);
  total.textContent = formatCurrency(budget, lastLocationCurrency);
}

function updateHeroBreakdown(presetName) {
  const breakdown = PRESET_BREAKDOWNS[presetName] || PRESET_BREAKDOWNS.balanced;
  const board = document.getElementById("presetBreakdownBoard");
  const title = document.getElementById("breakdownTitle");
  if (title) {
    title.textContent = breakdown.title;
  }

  Object.entries(breakdown.values).forEach(([key, value]) => {
    const row = document.querySelector(`[data-breakdown="${key}"]`);
    if (!row) {
      return;
    }
    const bar = row.querySelector(".breakdown-track i");
    const label = row.querySelector("strong");
    if (bar) {
      bar.style.width = `${value}%`;
    }
    if (label) {
      label.textContent = `${value}%`;
    }
  });
  if (board) {
    board.classList.remove("board-pulse");
    void board.offsetWidth;
    board.classList.add("board-pulse");
  }
  updateHeroBreakdownTotal();
}

function setActivePreset(presetName) {
  document.querySelectorAll(".preset-chip").forEach((button) => {
    button.classList.toggle("active", button.dataset.preset === presetName);
  });
}

function applyPreset(presetName) {
  const presets = {
    balanced: {
      budget: 50,
      maxItems: 8,
      strategy: "knapsack",
      required: "produce,protein",
      excluded: "dairy",
      likes: "",
      dislikes: "",
      goals: "",
    },
    budget: {
      budget: 35,
      maxItems: 10,
      strategy: "knapsack",
      required: "grains,pantry,produce",
      excluded: "",
      likes: "rice,oats,beans",
      dislikes: "",
      goals: "budget staples",
    },
    protein: {
      budget: 65,
      maxItems: 9,
      strategy: "knapsack",
      required: "protein,produce",
      excluded: "",
      likes: "eggs,chicken,beans,yogurt",
      dislikes: "",
      goals: "muscle gain, high protein",
    },
    fresh: {
      budget: 55,
      maxItems: 9,
      strategy: "greedy",
      required: "produce,protein",
      excluded: "frozen",
      likes: "greens,berries,vegetables",
      dislikes: "",
      goals: "heart health, fiber",
    },
  };

  const preset = presets[presetName];
  if (!preset) {
    return;
  }

  document.getElementById("budget").value = preset.budget;
  document.getElementById("maxItems").value = preset.maxItems;
  document.getElementById("strategy").value = preset.strategy;
  document.getElementById("requiredCategories").value = preset.required;
  document.getElementById("excludedCategories").value = preset.excluded;
  document.getElementById("likes").value = preset.likes;
  document.getElementById("dislikes").value = preset.dislikes;
  document.getElementById("healthGoals").value = preset.goals;
  setActivePreset(presetName);
  updateHeroBreakdown(presetName);
  updatePlanPreview();
  showStatus(`${presetName === "balanced" ? "Balanced" : presetName.replace("-", " ")} preset loaded.`, "success");
}

function renderStoreMapSvg(mapEl, points, route) {
  mapEl.classList.add("fallback-map");
  const width = Math.max(mapEl.clientWidth || 700, 420);
  const height = 320;
  const padding = 24;

  const coords = points.map((p) => [Number(p.latitude), Number(p.longitude)]);
  if (route && route.origin && Number.isFinite(Number(route.origin.latitude)) && Number.isFinite(Number(route.origin.longitude))) {
    coords.push([Number(route.origin.latitude), Number(route.origin.longitude)]);
  }

  if (!coords.length) {
    mapEl.innerHTML = "";
    return;
  }

  const lats = coords.map((c) => c[0]);
  const lons = coords.map((c) => c[1]);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const minLon = Math.min(...lons);
  const maxLon = Math.max(...lons);
  const rawLatSpan = maxLat - minLat;
  const rawLonSpan = maxLon - minLon;
  const latSpan = Math.max(rawLatSpan, 0.0001);
  const lonSpan = Math.max(rawLonSpan, 0.0001);

  const project = (lat, lon) => {
    const x = rawLonSpan === 0
      ? width / 2
      : padding + ((lon - minLon) / lonSpan) * (width - 2 * padding);
    const y = rawLatSpan === 0
      ? height / 2
      : height - padding - ((lat - minLat) / latSpan) * (height - 2 * padding);
    return [x, y];
  };

  const pointByStoreId = new Map();
  points.forEach((store) => {
    pointByStoreId.set(store.store_id, project(Number(store.latitude), Number(store.longitude)));
  });

  const routeStops = Array.isArray(route?.stops) ? route.stops : [];
  const routePoints = [];
  if (route && route.origin && Number.isFinite(Number(route.origin.latitude)) && Number.isFinite(Number(route.origin.longitude))) {
    routePoints.push(project(Number(route.origin.latitude), Number(route.origin.longitude)));
  }
  routeStops.forEach((stop) => {
    const p = pointByStoreId.get(stop.store_id);
    if (p) routePoints.push(p);
  });

  const routePath = routePoints
    .map((p, idx) => `${idx === 0 ? "M" : "L"} ${p[0].toFixed(1)} ${p[1].toFixed(1)}`)
    .join(" ");

  const routeStoreIds = new Set(routeStops.map((stop) => String(stop.store_id || "")));
  const markers = points
    .map((store) => {
      const [x, y] = project(Number(store.latitude), Number(store.longitude));
      const isRouteStop = routeStoreIds.has(String(store.store_id || ""));
      const fill = isRouteStop ? "#ed1b2f" : "#64748b";
      const radius = isRouteStop ? 8 : 5;
      const label = isRouteStop
        ? `<text x="${(x + 12).toFixed(1)}" y="${(y - 10).toFixed(1)}" class="map-label">${escapeHtml(store.name)}</text>`
        : "";
      return `
        <g class="${isRouteStop ? "map-marker route-marker" : "map-marker"}">
          <circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${radius}" fill="${fill}"><title>${escapeHtml(store.name)}</title></circle>
          ${label}
        </g>
      `;
    })
    .join("");

  let originMarker = "";
  if (route && route.origin && Number.isFinite(Number(route.origin.latitude)) && Number.isFinite(Number(route.origin.longitude))) {
    const [ox, oy] = project(Number(route.origin.latitude), Number(route.origin.longitude));
    originMarker = `<rect x="${(ox - 5).toFixed(1)}" y="${(oy - 5).toFixed(1)}" width="10" height="10" fill="#111827"><title>Start</title></rect>`;
  }

  mapEl.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" width="100%" height="${height}" role="img" aria-label="Store map">
      <defs>
        <linearGradient id="mapBg" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0" stop-color="#fff5f5" />
          <stop offset="0.52" stop-color="#f8fafc" />
          <stop offset="1" stop-color="#ffffff" />
        </linearGradient>
      </defs>
      <rect x="0" y="0" width="${width}" height="${height}" rx="18" fill="url(#mapBg)" />
      <path d="M 28 ${height - 52} C ${width * 0.25} ${height - 118}, ${width * 0.42} ${height - 16}, ${width - 30} 54" stroke="#ffe3e6" stroke-width="20" fill="none" opacity="0.75" />
      <path d="M 46 58 C ${width * 0.28} 24, ${width * 0.62} 124, ${width - 42} 98" stroke="#dbeafe" stroke-width="16" fill="none" opacity="0.78" />
      ${routePath ? `<path class="map-route-line" d="${routePath}" stroke="#ed1b2f" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" fill="none" />` : ""}
      ${markers}
      ${originMarker}
    </svg>
  `;
}

function buildDirectionsUrl(route) {
  const origin = route?.origin;
  const stops = Array.isArray(route?.stops) ? route.stops : [];
  if (!origin || !stops.length) {
    return "";
  }

  const originText = `${origin.latitude},${origin.longitude}`;
  const destination = stops[stops.length - 1];
  const destinationText = `${destination.latitude},${destination.longitude}`;
  const waypoints = stops.slice(0, -1).map((stop) => `${stop.latitude},${stop.longitude}`).join("|");
  const params = new URLSearchParams({
    api: "1",
    origin: originText,
    destination: destinationText,
    travelmode: "driving",
  });
  if (waypoints) {
    params.set("waypoints", waypoints);
  }
  return `https://www.google.com/maps/dir/?${params.toString()}`;
}

function updateDirectionsLink(route) {
  const link = document.getElementById("openDirectionsLink");
  if (!link) {
    return;
  }
  const url = buildDirectionsUrl(route);
  if (!url) {
    link.classList.add("hidden");
    link.removeAttribute("href");
    return;
  }
  link.href = url;
  link.classList.remove("hidden");
}

function setRoadRouteStatus(message, type = "info") {
  const status = document.getElementById("roadRouteStatus");
  if (!status) {
    return;
  }
  if (!message) {
    status.classList.add("hidden");
    status.textContent = "";
    return;
  }
  status.textContent = message;
  status.className = `map-note map-note-${type}`;
}

async function fetchRoadRouteLatLngs(routeLine) {
  if (!Array.isArray(routeLine) || routeLine.length < 2) {
    return [];
  }

  const result = await apiRequest("/route/road", {
    method: "POST",
    body: JSON.stringify({
      points: routeLine.map(([lat, lon]) => ({
        latitude: Number(lat),
        longitude: Number(lon),
      })),
    }),
  });

  if (!result.ok) {
    return [];
  }

  const routeCoords = result.data?.route?.coordinates;
  if (!Array.isArray(routeCoords)) {
    return [];
  }

  return routeCoords
    .map((coord) => [Number(coord.latitude), Number(coord.longitude)])
    .filter(([lat, lon]) => Number.isFinite(lat) && Number.isFinite(lon));
}

function renderStoreMapLeaflet(mapEl, points, route) {
  if (!window.L) {
    return false;
  }

  if (routeMap) {
    routeMap.remove();
    routeMap = null;
  }

  mapEl.classList.remove("fallback-map");
  mapEl.innerHTML = "";
  const L = window.L;
  routeMap = L.map(mapEl, {
    scrollWheelZoom: false,
    tap: true,
  });

  const tileLayer = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  });
  tileLayer.on("tileerror", () => {
    const mapEmpty = document.getElementById("storeMapEmpty");
    if (mapEmpty) {
      mapEmpty.textContent = "Map tiles are blocked or unavailable, but route markers and directions are still shown.";
      mapEmpty.classList.remove("hidden");
    }
  });
  tileLayer.addTo(routeMap);

  const routeStops = Array.isArray(route?.stops) ? route.stops : [];
  const routeStoreIds = new Set(routeStops.map((stop) => String(stop.store_id || "")));
  const bounds = [];

  if (route?.origin && Number.isFinite(Number(route.origin.latitude)) && Number.isFinite(Number(route.origin.longitude))) {
    const originLatLng = [Number(route.origin.latitude), Number(route.origin.longitude)];
    bounds.push(originLatLng);
    L.marker(originLatLng, {
      title: "Start",
      icon: L.divIcon({
        className: "leaflet-start-marker",
        html: "<span>Start</span>",
        iconSize: [44, 28],
        iconAnchor: [22, 14],
      }),
    }).addTo(routeMap).bindPopup(`<strong>Start</strong><br>${escapeHtml(route.origin.display_name || route.origin.postal_code || "Origin")}`);
  }

  points.forEach((store) => {
    const latLng = [Number(store.latitude), Number(store.longitude)];
    bounds.push(latLng);
    const isRouteStop = routeStoreIds.has(String(store.store_id || ""));
    L.marker(latLng, {
      title: store.name,
      icon: L.divIcon({
        className: isRouteStop ? "leaflet-store-marker route-stop-marker" : "leaflet-store-marker",
        html: `<span>${isRouteStop ? String(routeStops.findIndex((stop) => String(stop.store_id) === String(store.store_id)) + 1) : ""}</span>`,
        iconSize: [48, 28],
        iconAnchor: [24, 14],
      }),
    }).addTo(routeMap).bindPopup(`
      <strong>${escapeHtml(store.name)}</strong><br>
      ${escapeHtml(store.chain || "")}<br>
      ${escapeHtml(String(store.distance_km || "-"))} km away
    `);
  });

  const routeLine = [];
  if (route?.origin && Number.isFinite(Number(route.origin.latitude)) && Number.isFinite(Number(route.origin.longitude))) {
    routeLine.push([Number(route.origin.latitude), Number(route.origin.longitude)]);
  }
  routeStops.forEach((stop) => {
    if (Number.isFinite(Number(stop.latitude)) && Number.isFinite(Number(stop.longitude))) {
      routeLine.push([Number(stop.latitude), Number(stop.longitude)]);
    }
  });
  if (bounds.length) {
    routeMap.fitBounds(bounds, { padding: [36, 36], maxZoom: 14 });
  }
  setTimeout(() => routeMap?.invalidateSize(), 120);

  if (routeLine.length >= 2) {
    setRoadRouteStatus("Loading road-following route...", "info");
    fetchRoadRouteLatLngs(routeLine).then((roadRoute) => {
      if (!routeMap) {
        return;
      }
      if (roadRoute.length >= 2) {
        L.polyline(roadRoute, {
          className: "road-route-line",
          color: "#ed1b2f",
          weight: 6,
          opacity: 0.92,
          lineCap: "round",
          lineJoin: "round",
        }).addTo(routeMap);
        routeMap.fitBounds(roadRoute, { padding: [38, 38], maxZoom: 15 });
        setRoadRouteStatus("Showing the recommended driving route on roads.", "success");
        return;
      }

      L.polyline(routeLine, {
        className: "approx-route-line",
        color: "#f59e0b",
        weight: 4,
        opacity: 0.82,
        dashArray: "10 8",
      }).addTo(routeMap);
      setRoadRouteStatus("Road route is unavailable right now, so this is an approximate line.", "warning");
    });
  } else {
    setRoadRouteStatus("");
  }
  return true;
}

function renderStoreMap(nearbyStores, route) {
  const mapEl = document.getElementById("storeMap");
  const mapEmpty = document.getElementById("storeMapEmpty");
  if (!mapEl || !mapEmpty) {
    return;
  }

  const points = (Array.isArray(nearbyStores) ? nearbyStores : [])
    .filter((s) => Number.isFinite(Number(s.latitude)) && Number.isFinite(Number(s.longitude)));

  if (!points.length) {
    mapEl.classList.add("hidden");
    updateDirectionsLink(null);
    setRoadRouteStatus("");
    mapEmpty.classList.remove("hidden");
    mapEmpty.textContent = "No coordinates available for nearby stores.";
    return;
  }

  mapEl.classList.remove("hidden");
  mapEmpty.classList.add("hidden");
  updateDirectionsLink(route);
  const renderedLeaflet = renderStoreMapLeaflet(mapEl, points, route);
  if (!renderedLeaflet) {
    renderStoreMapSvg(mapEl, points, route);
  }
}

function renderSavingsCelebration(insights, currency) {
  const panel = document.getElementById("savingsCelebration");
  const title = document.getElementById("savingsCelebrationTitle");
  const text = document.getElementById("savingsCelebrationText");
  if (!panel || !title || !text) {
    return;
  }

  const routeSavings = Number(insights?.net_route_savings || 0);
  const savings = routeSavings > 0 ? routeSavings : Number(insights?.estimated_store_savings || 0);
  const bestStore = insights?.best_store?.name || "the lowest estimated store";
  const liveCoverage = Number(insights?.live_quote_coverage_percent || 0);
  const pricingMode = String(insights?.pricing_mode || "");
  const hasVerifiedPricing = pricingMode.includes("live") || liveCoverage >= 50 || Number(insights?.live_quotes || 0) > 0;
  if (savings <= 0 || !hasVerifiedPricing) {
    panel.classList.add("hidden");
    return;
  }

  title.textContent = routeSavings > 0 ? "Verified route savings found" : "Verified savings found";
  text.textContent = routeSavings > 0
    ? `This route may net about ${formatCurrency(routeSavings, currency)} after estimated extra travel by splitting items across the best deal stops.`
    : `This plan may save you up to ${formatCurrency(savings, currency)} versus the highest nearby store estimate. Start with ${bestStore} to keep the most money in your pocket.`;
  panel.classList.remove("hidden");
  panel.classList.add("celebrate-pop");
  setTimeout(() => panel.classList.remove("celebrate-pop"), 900);
}

function applyReusePlanPrefill() {
  const raw = sessionStorage.getItem("reuse_plan_request");
  if (!raw) {
    return;
  }

  try {
    const req = JSON.parse(raw);
    if (req.budget != null) {
      document.getElementById("budget").value = Number(req.budget);
    }
    if (req.max_items != null) {
      document.getElementById("maxItems").value = Number(req.max_items);
    }
    if (req.strategy) {
      document.getElementById("strategy").value = String(req.strategy);
    }
    if (req.location) {
      document.getElementById("location").value = String(req.location);
    }
    if (req.postal_code) {
      document.getElementById("postalCode").value = String(req.postal_code);
    }
    if (req.address) {
      document.getElementById("address").value = String(req.address);
    }
    if (req.transportation_mode) {
      document.getElementById("travelMode").value = String(req.transportation_mode);
    }
    if (req.country_hint != null) {
      document.getElementById("countryHint").value = String(req.country_hint);
    }
    if (Array.isArray(req.required_categories)) {
      document.getElementById("requiredCategories").value = req.required_categories.join(",");
    }
    if (Array.isArray(req.must_have_items)) {
      document.getElementById("mustHaveItems").value = req.must_have_items.join(",");
    }
    if (Array.isArray(req.excluded_categories)) {
      document.getElementById("excludedCategories").value = req.excluded_categories.join(",");
    }
    if (Array.isArray(req.likes)) {
      document.getElementById("likes").value = req.likes.join(",");
    }
    if (Array.isArray(req.dislikes)) {
      document.getElementById("dislikes").value = req.dislikes.join(",");
    }
    if (Array.isArray(req.health_goals)) {
      document.getElementById("healthGoals").value = req.health_goals.join(",");
    }

    showStatus("Loaded a saved plan. Review and click 'Generate plan'.", "success");
  } catch {
    showStatus("Could not load reused plan data. Fill the form manually.", "error");
  } finally {
    sessionStorage.removeItem("reuse_plan_request");
  }
}

async function checkApiReady() {
  const result = await apiRequest("/health");
  if (!result.ok) {
    showStatus("API is offline. Start local servers before using buttons.", "error");
    return false;
  }
  return true;
}

function getTierBadgeClass(tier) {
  const t = String(tier || "").toLowerCase().replace(/[\s_-]+/g, "-");
  if (t.includes("budget")) return "tier-badge tier-badge-budget";
  if (t.includes("premium")) return "tier-badge tier-badge-premium";
  return "tier-badge tier-badge-mid";
}

function renderStoreCards(stores, itemQuotes, currency, route) {
  const container = document.getElementById("storeCards");
  const meta = document.getElementById("storeComparisonMeta");
  if (!container || !meta) {
    return;
  }

  const quotesByStore = new Map();
  (Array.isArray(itemQuotes) ? itemQuotes : []).forEach((quote) => {
    const key = `${quote.store_id || quote.store_name || ""}`;
    if (!quotesByStore.has(key)) {
      quotesByStore.set(key, []);
    }
    quotesByStore.get(key).push(quote);
  });

  const sortedStores = [...(Array.isArray(stores) ? stores : [])].sort((a, b) => {
    const distanceDelta = Number(a.distance_km || 0) - Number(b.distance_km || 0);
    if (Math.abs(distanceDelta) > 0.001) {
      return distanceDelta;
    }
    return Number(a.estimated_total || 0) - Number(b.estimated_total || 0);
  });

  const displayed = sortedStores;
  const routeIds = new Set((route?.stops || []).map((stop) => String(stop.store_id || "")));
  meta.textContent = `${displayed.length} nearby stores found. Ordered by distance first, then estimated price. Open each card to compare branch-specific prices and pickup details.`;

  if (!displayed.length) {
    container.innerHTML = '<p class="muted">No nearby store pricing available yet.</p>';
    return;
  }

  container.innerHTML = displayed
    .map((store, idx) => {
      const rows = quotesByStore.get(store.name) || [];
      const storeKey = toKey(store.store_id || store.name || idx);

      const checklistByItem = new Map();
      rows.forEach((row) => {
        const itemKey = toKey(row.item_name);
        const existing = checklistByItem.get(itemKey);
        if (!existing || Number(row.line_total || 0) < Number(existing.line_total || 0)) {
          checklistByItem.set(itemKey, row);
        }
      });
      const checklistItems = [...checklistByItem.values()].slice(0, 40);
      const selectedCount = checklistItems.filter((row) => storeChecklistState.get(`${storeKey}::${toKey(row.item_name)}`)).length;
      const storeAddress = [store.address, store.distance_km != null ? `${store.distance_km} km away` : ""].filter(Boolean).join(" · ");

      const checklistPanel = checklistItems.length
        ? `
          <div class="store-checklist">
            <div class="checklist-toolbar">
              <button type="button" class="secondary btn-sm checklist-select-all" data-store-key="${storeKey}">Select all</button>
              <button type="button" class="secondary btn-sm checklist-clear" data-store-key="${storeKey}">Clear</button>
              <span class="muted checklist-progress">${selectedCount}/${checklistItems.length} selected</span>
            </div>
            <div class="checklist-items">
              ${checklistItems
                .map((row) => {
                  const itemKey = toKey(row.item_name);
                  const stateKey = `${storeKey}::${itemKey}`;
                  const checked = storeChecklistState.get(stateKey) ? "checked" : "";
                  return `
                    <label class="checklist-item">
                      <input
                        type="checkbox"
                        class="store-check-item"
                        data-store-key="${storeKey}"
                        data-item-key="${itemKey}"
                        ${checked}
                      />
                      <span>${escapeHtml(row.item_name)} x${row.quantity} &mdash; ${formatCurrency(row.line_total, row.currency || currency)}${Number(row.unit_price || 0) > 0 ? ` (${formatCurrency(row.unit_price, row.currency || currency)} / unit)` : ""}</span>
                    </label>
                  `;
                })
                .join("")}
            </div>
          </div>
        `
        : '<p class="muted">No items available for this store yet.</p>';

      const tierBadgeClass = getTierBadgeClass(store.price_tier);

      return `
        <article class="store-card simple-store-card ${routeIds.has(String(store.store_id || "")) ? "recommended-store" : ""}">
          <div class="store-card-heading">
            <div><strong>${escapeHtml(store.name)}</strong><small>${escapeHtml(store.chain)}</small></div>
            ${routeIds.has(String(store.store_id || "")) ? '<span class="route-badge">Route stop</span>' : ""}
          </div>
          <p class="store-address-line">${escapeHtml(storeAddress)}</p>
          <div class="store-facts"><span>${store.distance_km} km</span><span>${formatCurrency(store.estimated_total, currency)}</span><span class="${tierBadgeClass}">${escapeHtml(store.price_tier)}</span></div>
          <p class="muted">Quality ${store.quality_rating}/5</p>
          <details class="item-checklist-details"><summary>View item prices</summary>${checklistPanel}</details>
        </article>
      `;
    })
    .join("");
}

function renderRetailerIntel(research) {
  const panel = document.getElementById("retailerIntelPanel");
  const summary = document.getElementById("retailerIntelSummary");
  const chips = document.getElementById("retailerIntelChips");
  if (!panel || !summary || !chips) {
    return;
  }

  const topRetailers = Array.isArray(research?.top_priority_retailers) ? research.top_priority_retailers : [];
  const tiers = Array.isArray(research?.acquisition_tiers) ? research.acquisition_tiers : [];
  if (!topRetailers.length && !tiers.length) {
    panel.classList.add("hidden");
    return;
  }

  const tierOne = tiers.find((tier) => String(tier.tier || "").includes("tier_1"));
  const tierTwo = tiers.find((tier) => String(tier.tier || "").includes("tier_2"));
  const seedCount = Number(research?.verified_seed_count || 0);
  const copy = getUiCopy();
  summary.textContent = [
    copy.retailerCoverage,
    tierOne?.label ? `${tierOne.label}: ${(tierOne.retailers || []).slice(0, 6).join(", ")}` : "",
    tierTwo?.label ? `${tierTwo.label}: ${(tierTwo.retailers || []).slice(0, 5).join(", ")}` : "",
    seedCount ? `${seedCount} verified specialty-store seed(s) added from research` : "",
  ].filter(Boolean).join(" · ");

  chips.innerHTML = topRetailers.slice(0, 8).map((retailer) => `
    <span class="retailer-chip">
      <strong>${escapeHtml(retailer.retailer || "Retailer")}</strong>
      <small>Tier ${escapeHtml(retailer.tier || "-")} · score ${escapeHtml(retailer.weighted_score || "-")}</small>
    </span>
  `).join("");
  panel.classList.remove("hidden");
}

function buildItemStorePlan(items, itemQuotes, routeAssignments = [], storeComparison = []) {
  const storeById = new Map();
  (Array.isArray(storeComparison) ? storeComparison : []).forEach((store) => {
    const key = String(store.store_id || "");
    if (key) {
      storeById.set(key, store);
    }
  });

  const routeStoreByItem = new Map();
  (Array.isArray(routeAssignments) ? routeAssignments : []).forEach((assignment) => {
    const key = String(assignment.item_name || "").toLowerCase();
    if (key) {
      routeStoreByItem.set(key, assignment);
    }
  });

  const quotesByItem = new Map();
  (Array.isArray(itemQuotes) ? itemQuotes : []).forEach((quote) => {
    const key = String(quote.item_name || "").toLowerCase();
    if (!quotesByItem.has(key)) {
      quotesByItem.set(key, []);
    }
    quotesByItem.get(key).push(quote);
  });

  return (Array.isArray(items) ? items : []).map((item) => {
    const key = String(item.name || "").toLowerCase();
    const routeBest = routeStoreByItem.get(key);
    const itemQuotesForStore = (quotesByItem.get(key) || []).sort((left, right) => Number(left.line_total || 0) - Number(right.line_total || 0));
    const best = routeBest || itemQuotesForStore[0] || null;
    const storeId = String(best?.store_id || item.recommended_store_id || "");
    const storeInfo = storeById.get(storeId) || {};
    const purchasePrice = Number(best?.line_total ?? item.store_line_total ?? item.total_cost ?? 0);
    const savings = Number(best?.gross_savings ?? item.store_savings ?? 0);
    const unitPrice = Number(best?.unit_price ?? item.recommended_store_unit_price ?? item.price ?? 0);
    const storeName = String(best?.store_name || storeInfo.name || item.recommended_store || "-");
    const storeAddress = String(storeInfo.address || item.recommended_store_address || "");
    const priceOptions = itemQuotesForStore.slice(0, 3).map((quote) => {
      const optionStore = storeById.get(String(quote.store_id || "")) || {};
      return {
        store_id: String(quote.store_id || ""),
        store_name: String(quote.store_name || optionStore.name || "Store"),
        store_address: String(optionStore.address || ""),
        line_total: Number(quote.line_total || 0),
        unit_price: Number(quote.unit_price || 0),
        distance_km: optionStore.distance_km,
      };
    });

    return {
      ...item,
      recommended_store: storeName || "-",
      recommended_store_id: storeId,
      recommended_store_address: storeAddress,
      recommended_store_distance_km: storeInfo.distance_km,
      recommended_store_unit_price: unitPrice,
      purchase_price: purchasePrice,
      store_line_total: purchasePrice,
      store_savings: savings,
      price_options: priceOptions,
    };
  });
}

function renderPlanInsights(insights, currency) {
  const panel = document.getElementById("planInsights");
  const overview = document.getElementById("insightsOverview");
  const categoryBreakdown = document.getElementById("categoryBreakdown");
  const nextActions = document.getElementById("nextActions");
  if (!panel || !overview || !categoryBreakdown || !nextActions) {
    return;
  }

  const data = insights || {};
  const bestStore = data.best_store || null;
  const savings = Number(data.estimated_store_savings || 0);
  const routeDistance = data.route_distance_km;
  const budgetUsed = Number(data.budget_used_percent || 0);
  const overviewParts = [`${budgetUsed.toFixed(1)}% of budget used`];
  if (bestStore && bestStore.name) {
    overviewParts.push(`lowest estimate: ${bestStore.name}`);
  }
  if (savings > 0) {
    overviewParts.push(`possible store spread: ${formatCurrency(savings, currency)}`);
  }
  if (Number(data.net_route_savings || 0) > 0) {
    overviewParts.push(`route net savings: ${formatCurrency(data.net_route_savings, currency)}`);
  }
  if (routeDistance != null) {
    overviewParts.push(`route: ${routeDistance} km`);
  }
  overview.textContent = overviewParts.join(" · ");

  const categories = Array.isArray(data.category_breakdown) ? data.category_breakdown : [];
  categoryBreakdown.innerHTML = categories.length
    ? categories
      .slice(0, 6)
      .map((row) => {
        const cost = Number(row.cost || 0);
        return `
          <div class="category-pill">
            <span>${escapeHtml(prettyCategory(row.category))}</span>
            <strong>${formatCurrency(cost, currency)}</strong>
          </div>
        `;
      })
      .join("")
    : '<p class="muted">No category spending data available.</p>';

  const actions = Array.isArray(data.next_actions) ? data.next_actions : [];
  nextActions.innerHTML = actions.length
    ? actions.map((action) => `<li>${escapeHtml(action)}</li>`).join("")
    : "<li>Review your list before shopping.</li>";
  panel.classList.remove("hidden");
}

function renderPriceForecast(forecast, currency) {
  const panel = document.getElementById("priceForecast");
  const title = document.getElementById("priceForecastTitle");
  const text = document.getElementById("priceForecastText");
  const drops = document.getElementById("priceForecastDrops");
  const disclaimer = document.getElementById("priceForecastDisclaimer");
  if (!panel || !title || !text || !drops || !disclaimer) return;
  const data = forecast || {};
  title.textContent = data.action === "wait" ? "A short wait may pay off" : "Today is a reasonable day to shop";
  text.textContent = data.recommendation || "Use current nearby-store estimates before shopping.";
  const candidates = Array.isArray(data.drops) ? data.drops : [];
  drops.innerHTML = candidates.map((row) => `
    <span><strong>${escapeHtml(row.item_name)}</strong> ${formatCurrency(row.current_price, currency)} &rarr; ${formatCurrency(row.predicted_price, currency)} <small>${escapeHtml(row.change_percent)}%</small></span>
  `).join("");
  disclaimer.textContent = data.disclaimer || "Price timing is an estimate based on observed data.";
  panel.classList.remove("hidden");
}

function renderOptimizationResult(data, caption = "Plan generated.") {
  const summary = data.summary || {};
  const items = Array.isArray(data.items) ? data.items : [];
  const stores = data.stores || {};
  const route = data.route;
  const location = data.location || {};

  lastLocationCurrency = location.currency || "CAD";
  setBudgetCurrencyLabel(lastLocationCurrency);

  const resultSection = document.getElementById("result");
  const summaryCards = document.getElementById("summaryCards");
  const resultItemsBody = document.getElementById("resultItemsBody");
  const resultText = document.getElementById("resultText");
  const storeComparisonData = Array.isArray(stores.comparison) ? stores.comparison : [];
  const savingsValue = Number(data.insights?.net_route_savings || data.insights?.estimated_store_savings || 0);

  const cards = [
    ["Total cost", formatCurrency(summary.total_cost, lastLocationCurrency)],
    ["Budget left", formatCurrency(summary.budget_remaining, lastLocationCurrency)],
    ["Items", String(summary.total_units || items.reduce((acc, item) => acc + (Number(item.quantity) || 0), 0))],
    ["Savings", formatCurrency(Math.max(0, savingsValue), lastLocationCurrency)],
  ];

  summaryCards.innerHTML = cards
    .map(
      ([label, value]) => `
      <article class="summary-card">
        <span class="label">${escapeHtml(label)}</span>
        <span class="value">${escapeHtml(value)}</span>
      </article>
    `
    )
    .join("");

  renderPlanInsights(data.insights || {}, lastLocationCurrency);
  renderSavingsCelebration({ ...(data.insights || {}), pricing_mode: stores.pricing_mode, live_quote_coverage_percent: stores.live_quote_coverage_percent, live_quotes: stores.live_quotes }, lastLocationCurrency);
  renderPriceForecast(data.price_forecast || {}, lastLocationCurrency);

  const plannedItems = buildItemStorePlan(items, stores.item_quotes || [], route?.item_assignments || [], storeComparisonData);
  resultItemsBody.innerHTML = plannedItems
    .map(
      (item) => `
      <tr>
        <td>${escapeHtml(item.name)}</td>
        <td>${escapeHtml(prettyCategory(item.category))}</td>
        <td>${item.quantity}</td>
        <td>${formatCurrency(item.purchase_price ?? item.total_cost, lastLocationCurrency)}</td>
        <td>${Number(item.store_savings || 0) > 0 ? formatCurrency(item.store_savings, lastLocationCurrency) : "-"}</td>
        <td>
          <div class="item-store-cell">
            <strong>${escapeHtml(item.recommended_store || "-")}</strong>
            ${item.recommended_store_address ? `<small>${escapeHtml(item.recommended_store_address)}${item.recommended_store_distance_km != null ? ` · ${item.recommended_store_distance_km} km` : ""}</small>` : ""}
            ${Number(item.recommended_store_unit_price || 0) > 0 ? `<small>${formatCurrency(item.recommended_store_unit_price, lastLocationCurrency)} / unit</small>` : ""}
            ${Array.isArray(item.price_options) && item.price_options.length > 1 ? `
              <span class="item-store-options-label">Other options</span>
              <span class="item-store-options">
                ${item.price_options.slice(0, 3).map((option) => `<span>${escapeHtml(option.store_name)} ${formatCurrency(option.line_total, lastLocationCurrency)}</span>`).join("")}
              </span>
            ` : ""}
          </div>
        </td>
      </tr>
    `
    )
    .join("");

  const storeDataSource = document.getElementById("storeDataSource");
  const storeComparison = document.getElementById("storeComparison");
  storeComparison.classList.remove("hidden");

  renderRetailerIntel(stores.retailer_research || {});

  // Hidden data holders (kept for compatibility)
  storeDataSource.textContent = stores.data_source || "N/A";
  const livePricingStatus = document.getElementById("livePricingStatus");
  livePricingStatus.textContent = stores.last_updated_utc || "";

  renderStoreMap(stores.nearby || [], route);
  const mapRouteTitle = document.getElementById("mapRouteTitle");
  const mapRouteBadge = document.getElementById("mapRouteBadge");
  if (mapRouteTitle && mapRouteBadge) {
    mapRouteTitle.textContent = `${stores.nearby?.length || 0} nearby stores · ${route?.stops?.length || 0} recommended stop(s)`;
    mapRouteBadge.textContent = route?.skipped_store_count
      ? `${route.skipped_store_count} store(s) skipped`
      : "Best value";
  }

  if (route && Array.isArray(route.stops) && route.stops.length > 0) {
    const routeStops = document.getElementById("routeStops");
    const routeTotalDistance = document.getElementById("routeTotalDistance");
    const routeOriginLabel = document.getElementById("routeOriginLabel");

    routeStops.innerHTML = route.stops
      .map(
        (stop) => `
        <div class="route-stop">
          <strong>Stop ${stop.order}: ${escapeHtml(stop.name)}</strong><br/>
          <small class="muted">
            ${stop.distance_from_previous_km} km from previous stop
            ${stop.estimated_total != null ? ` · estimate ${formatCurrency(stop.estimated_total, lastLocationCurrency)}` : ""}
            ${Number(stop.deal_savings || 0) > 0 ? ` · item deals ${formatCurrency(stop.deal_savings, lastLocationCurrency)}` : ""}
            ${Number(stop.assigned_item_count || 0) > 0 ? ` · ${stop.assigned_item_count} assigned item(s)` : ""}
          </small>
          ${Array.isArray(stop.assigned_items) && stop.assigned_items.length ? `
            <div class="route-stop-items">
              ${stop.assigned_items.slice(0, 5).map((item) => `
                <span>${escapeHtml(item.item_name)} ${formatCurrency(item.line_total, lastLocationCurrency)}</span>
              `).join("")}
            </div>
          ` : ""}
        </div>
      `
      )
      .join("");

    routeTotalDistance.textContent = route.total_distance_km;
    if (routeOriginLabel) {
      routeOriginLabel.textContent = route.origin?.display_name || route.origin?.postal_code || "-";
    }
    const routeTradeoffText = document.getElementById("routeTradeoffText");
    if (routeTradeoffText) {
      const copy = getUiCopy();
      const threshold = Number(route.savings_threshold || 0);
      const travelCost = Number(route.travel_cost_per_km || 0);
      routeTradeoffText.textContent = `${copy.routeTradeoffPrefix} ${route.selection_reason || copy.routeTradeoffDefault}${threshold > 0 ? ` (${formatCurrency(threshold, lastLocationCurrency)} threshold, ${formatCurrency(travelCost, lastLocationCurrency)} / km)` : ""}`;
    }
    document.getElementById("routeInfo").classList.remove("hidden");
  } else {
    document.getElementById("routeInfo").classList.add("hidden");
  }

  resultText.textContent = JSON.stringify(data, null, 2);
  resultSection.classList.remove("hidden");
  document.getElementById("chefWidget")?.classList.remove("hidden");
  showStatus(caption, "success");
}

async function refreshLivePricing() {
  if (!lastOptimizationPayload) {
    showStatus("Generate a plan first to enable live pricing refresh.", "info");
    return;
  }

  if (!lastOptimizationPayload.postal_code && !lastOptimizationPayload.address) {
    showStatus("Add a postal code or address to load nearby live store pricing.", "error");
    return;
  }

  const snapshot = await loadLivePricing(lastOptimizationPayload);
  if (!snapshot) {
    showStatus("Live pricing refresh failed. API may be unavailable.", "error");
    return;
  }

  const merged = {
    ...lastOptimizationResult,
    location: snapshot.location || lastOptimizationResult.location,
    summary: snapshot.summary || lastOptimizationResult.summary,
    stores: snapshot.stores || lastOptimizationResult.stores,
    route: snapshot.route || lastOptimizationResult.route,
  };
  lastOptimizationResult = merged;
  renderOptimizationResult(merged, "Live pricing refreshed.");
}

function addAssistantMessage(role, text) {
  const box = document.getElementById("assistantMessages");
  if (!box) {
    return;
  }
  const el = document.createElement("div");
  el.className = `assistant-message ${role}`;
  el.textContent = text;
  box.appendChild(el);
  box.scrollTop = box.scrollHeight;
  return el;
}

function buildShoppingListText() {
  if (!lastOptimizationResult) {
    return "";
  }

  const items = Array.isArray(lastOptimizationResult.items) ? lastOptimizationResult.items : [];
  const stores = lastOptimizationResult.stores || {};
  const plannedItems = buildItemStorePlan(items, stores.item_quotes || [], lastOptimizationResult.route?.item_assignments || [], Array.isArray(stores.comparison) ? stores.comparison : []);
  return plannedItems
    .map((item) => {
      const qty = Number(item.quantity || 0);
      const cost = formatCurrency(item.purchase_price ?? item.total_cost, lastLocationCurrency);
      const store = item.recommended_store && item.recommended_store !== "-" ? ` at ${item.recommended_store}` : "";
      const savings = Number(item.store_savings || 0) > 0 ? `, save ${formatCurrency(item.store_savings, lastLocationCurrency)}` : "";
      const unitPrice = Number(item.recommended_store_unit_price || 0) > 0 ? `, ${formatCurrency(item.recommended_store_unit_price, lastLocationCurrency)} / unit` : "";
      return `- ${item.name} x${qty} (${prettyCategory(item.category)}, ${cost}${store}${savings}${unitPrice})`;
    })
    .join("\n");
}

async function copyShoppingList() {
  const text = buildShoppingListText();
  if (!text) {
    showStatus("Generate a plan before copying the shopping list.", "error");
    return;
  }

  try {
    await navigator.clipboard.writeText(text);
    showStatus("Shopping list copied.", "success");
  } catch {
    showStatus("Could not copy automatically. Use Export CSV or Print instead.", "error");
  }
}

function toggleChefPanel(forceOpen = null) {
  const widget = document.getElementById("chefWidget");
  const panel = document.getElementById("chefPanel");
  const launcher = document.getElementById("chefLauncher");
  if (!widget || !panel || !launcher) {
    return;
  }
  if (widget.classList.contains("hidden")) {
    showStatus("Generate a plan first so The Chef can use your groceries.", "info");
    return;
  }

  const shouldOpen = forceOpen === null ? panel.classList.contains("hidden") : forceOpen;
  panel.classList.toggle("hidden", !shouldOpen);
  launcher.setAttribute("aria-expanded", String(shouldOpen));
  if (shouldOpen) {
    const input = document.getElementById("assistantInput");
    if (input) {
      input.focus();
    }
  }
}

function setChefLoading(loading) {
  chefIsResponding = loading;
  const sendBtn = document.getElementById("assistantSendBtn");
  const input = document.getElementById("assistantInput");
  if (sendBtn) {
    sendBtn.disabled = loading;
    sendBtn.textContent = loading ? "Thinking..." : "Send";
  }
  if (input) {
    input.disabled = loading;
  }
}

async function sendAssistantPrompt(messageOverride = "") {
  if (!lastOptimizationResult) {
    showStatus("Generate a plan first so The Chef can use your items.", "error");
    return;
  }
  if (chefIsResponding) {
    return;
  }

  const input = document.getElementById("assistantInput");
  const message = String(messageOverride || input.value || "").trim();
  if (!message) {
    return;
  }

  if (input) {
    input.value = "";
  }
  toggleChefPanel(true);
  addAssistantMessage("user", message);
  const pending = addAssistantMessage("assistant", "The Chef is checking your grocery list...");
  setChefLoading(true);

  const payload = {
    message,
    plan_items: lastOptimizationResult.items || [],
    likes: lastOptimizationPayload?.likes || [],
    dislikes: lastOptimizationPayload?.dislikes || [],
    health_goals: lastOptimizationPayload?.health_goals || [],
  };

  const result = await askMealAssistant(payload);
  setChefLoading(false);
  if (pending) {
    pending.remove();
  }
  if (!result.ok) {
    addAssistantMessage("assistant", result.data.detail || "The Chef is unavailable right now.");
    return;
  }

  const responseText = String(result.data.response || "");
  addAssistantMessage("assistant", responseText.trim());
}

// Loading state helpers
function setFormLoading(loading) {
  const overlay = document.getElementById("formLoadingOverlay");
  const generateBtn = document.getElementById("generateBtn");

  if (overlay) {
    if (loading) {
      overlay.classList.add("active");
    } else {
      overlay.classList.remove("active");
    }
  }

  if (generateBtn) {
    generateBtn.disabled = loading;
    generateBtn.textContent = loading ? "Generating..." : "Generate plan";
  }
}

document.querySelectorAll(".preset-chip").forEach((button) => {
  button.addEventListener("click", () => {
    applyPreset(button.dataset.preset || "balanced");
  });
});

document.getElementById("chefLauncher")?.addEventListener("click", () => toggleChefPanel());
document.getElementById("chefCloseBtn")?.addEventListener("click", () => toggleChefPanel(false));
document.querySelectorAll(".chef-prompt").forEach((button) => {
  button.addEventListener("click", () => {
    sendAssistantPrompt(button.dataset.prompt || "");
  });
});

document.querySelectorAll("[data-chef-auto]").forEach((button) => {
  button.addEventListener("click", () => {
    sendAssistantPrompt(button.dataset.chefAuto || "");
  });
});

["budget", "maxItems", "strategy"].forEach((id) => {
  const control = document.getElementById(id);
  if (control) {
    control.addEventListener("input", updatePlanPreview);
    control.addEventListener("change", updatePlanPreview);
  }
});

// Initialize locations
(async function initLocations() {
  const apiOk = await checkApiReady();
  if (!apiOk) return;

  const select = document.getElementById("location");
  const locations = await loadLocations();

  if (Array.isArray(locations) && locations.length > 0) {
    select.innerHTML = locations
      .map((loc) => `<option value="${escapeHtml(loc.location_id)}">${escapeHtml(loc.display_name)}</option>`)
      .join("");

    const montreal = locations.find((l) => l.location_id === "montreal");
    if (montreal) {
      select.value = "montreal";
      setBudgetCurrencyLabel(montreal.currency || "CAD");
    } else {
      setBudgetCurrencyLabel(locations[0].currency || "CAD");
    }

    applyReusePlanPrefill();
  } else {
    showStatus("Could not load locations. Check that API is running on port 8000.", "error");
  }
})();

document.getElementById("location").addEventListener("change", async (event) => {
  const value = event.target.value;
  const locations = await loadLocations();
  const selected = locations.find((loc) => loc.location_id === value);
  setBudgetCurrencyLabel((selected && selected.currency) || "CAD");
});

// Optimize form submission
document.getElementById("optForm").addEventListener("submit", async (event) => {
  event.preventDefault();

  const budgetInput = document.getElementById("budget");
  if (!budgetInput) {
    showStatus("Budget input is missing in the page. Hard refresh with Ctrl+F5.", "error");
    return;
  }

  const budgetValue = Number(budgetInput.value);
  if (!Number.isFinite(budgetValue) || budgetValue <= 0) {
    showStatus("Enter a valid budget amount greater than 0.", "error");
    budgetInput.focus();
    return;
  }

  const payload = {
    budget: budgetValue,
    max_items: Number(document.getElementById("maxItems").value),
    strategy: document.getElementById("strategy").value,
    location: document.getElementById("location").value,
    postal_code: document.getElementById("postalCode").value.trim().replace(/\s+/g, ""),
    address: document.getElementById("address").value.trim(),
    transportation_mode: document.getElementById("travelMode").value,
    country_hint: document.getElementById("countryHint").value,
    required_categories: splitList(document.getElementById("requiredCategories").value),
    must_have_items: splitList(document.getElementById("mustHaveItems").value),
    excluded_categories: splitList(document.getElementById("excludedCategories").value),
    likes: splitList(document.getElementById("likes").value),
    dislikes: splitList(document.getElementById("dislikes").value),
    health_goals: splitList(document.getElementById("healthGoals").value),
  };

  lastOptimizationPayload = payload;
  setFormLoading(true);
  showStatus("Generating optimized plan...", "info");

  const result = await optimizePlan(payload);

  // Hide loading state
  setFormLoading(false);
  if (result.ok) {
    lastOptimizationResult = result.data;
    renderOptimizationResult(result.data, "Plan ready. You can save it if you like it.");

    // Smooth scroll to results
    const resultSection = document.getElementById("result");
    if (resultSection) {
      setTimeout(() => {
        resultSection.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 100);
    }

    if (livePricingIntervalId) {
      clearInterval(livePricingIntervalId);
      livePricingIntervalId = null;
    }
    if (payload.postal_code || payload.address) {
      livePricingIntervalId = setInterval(() => {
        const autoRefresh = document.getElementById("autoRefreshPricing");
        if (autoRefresh && autoRefresh.checked) {
          refreshLivePricing();
        }
      }, 60000);
    }
  } else {
    document.getElementById("result").classList.remove("hidden");
    const detail = result?.data?.detail || "Unknown error";
    document.getElementById("resultText").textContent = `Request failed: ${detail}`;
    showStatus(`Could not generate a plan: ${detail}`, "error");
  }
});

document.getElementById("refreshPricingBtn").addEventListener("click", async () => {
  showStatus("Refreshing nearby store pricing...", "info");
  await refreshLivePricing();
});

document.getElementById("printCurrentPlanBtn").addEventListener("click", () => {
  if (!lastOptimizationResult) {
    showStatus("Generate a plan before printing.", "error");
    return;
  }
  printPlanView();
});

document.getElementById("exportCurrentPlanCsvBtn").addEventListener("click", () => {
  if (!lastOptimizationResult) {
    showStatus("Generate a plan before exporting.", "error");
    return;
  }
  downloadCsv("grocery-plan.csv", buildPlanCsvRows(lastOptimizationResult));
  showStatus("CSV exported.", "success");
});

document.getElementById("copyShoppingListBtn")?.addEventListener("click", copyShoppingList);
document.getElementById("dismissSavingsBtn")?.addEventListener("click", () => {
  document.getElementById("savingsCelebration")?.classList.add("hidden");
});
document.getElementById("assistantSendBtn").addEventListener("click", () => sendAssistantPrompt());
document.getElementById("assistantInput").addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    sendAssistantPrompt();
  }
});

// Nearby store card checklist interactions removed with card UI.

// Save plan button — show inline modal instead of prompt()
document.getElementById("savePlanBtn").addEventListener("click", async () => {
  if (!Session.isActive()) {
    showStatus("Create an account or sign in first.", "error");
    return;
  }

  if (!lastOptimizationPayload || !lastOptimizationResult) {
    showStatus("Generate a plan before saving.", "error");
    return;
  }

  // Show the inline save modal
  const modal = document.getElementById("saveModal");
  const nameInput = document.getElementById("savePlanName");
  if (modal && nameInput) {
    modal.classList.add("active");
    nameInput.value = "My grocery plan";
    nameInput.focus();
    nameInput.select();
  }
});

// Save modal confirm button
document.getElementById("saveModalConfirm").addEventListener("click", async () => {
  const nameInput = document.getElementById("savePlanName");
  const modal = document.getElementById("saveModal");
  const label = nameInput ? nameInput.value.trim() : "";

  if (!label) {
    showToast("Please enter a plan name.", "error");
    return;
  }

  const result = await savePlan(label, lastOptimizationPayload);

  if (result.ok) {
    showStatus(`Plan saved: ${escapeHtml(result.data.saved.id)}`, "success");
    if (modal) modal.classList.remove("active");
  } else {
    showStatus(result.data.detail || "Could not save this plan.", "error");
  }
});

// Save modal cancel button
document.getElementById("saveModalCancel").addEventListener("click", () => {
  const modal = document.getElementById("saveModal");
  if (modal) modal.classList.remove("active");
});

// Allow Enter in save modal name input to confirm
document.getElementById("savePlanName").addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    document.getElementById("saveModalConfirm").click();
  }
  if (event.key === "Escape") {
    document.getElementById("saveModalCancel").click();
  }
});

// Initial status
updateHeroBreakdown("balanced");
updatePlanPreview();
applyLanguage(document.getElementById("languageSelect")?.value || "en");
document.getElementById("languageSelect")?.addEventListener("change", (event) => {
  applyLanguage(event.target.value);
});
showStatus("Set your budget, add postal code or address, choose a travel mode, and click 'Generate plan'.", "info");
