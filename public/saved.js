// Saved plans page (saved.html)

let currentOffset = 0;
const PAGE_SIZE = 20;
let currentPlanDetail = null;

function getPlanSearchTerm() {
  return (document.getElementById("planSearch")?.value || "").trim().toLowerCase();
}

function applyPlanSearchFilter() {
  const term = getPlanSearchTerm();
  const cards = Array.from(document.querySelectorAll("#savedPlansList .saved-plan"));
  const emptySearch = document.getElementById("savedPlansSearchEmpty");
  let visibleCount = 0;

  cards.forEach((card) => {
    const matches = !term || card.textContent.toLowerCase().includes(term);
    card.classList.toggle("hidden-by-search", !matches);
    if (matches) visibleCount += 1;
  });

  if (emptySearch) {
    emptySearch.classList.toggle("hidden", !term || visibleCount > 0);
  }
}

function renderPlansList(data) {
  const plans = Array.isArray(data.plans) ? data.plans : [];
  const pagination = data.pagination || {};
  const savedPlansList = document.getElementById("savedPlansList");
  const plansList = document.getElementById("plansList");
  const paginationInfo = document.getElementById("paginationInfo");
  const loadMoreBtn = document.getElementById("loadMoreBtn");

  if (!plans.length && currentOffset === 0) {
    savedPlansList.innerHTML = `
      <div class="empty-state">
        <strong>${tr("No saved plans yet", "Aucun plan sauvegarde")}</strong>
        <p class="muted">${tr("Generate a grocery plan, save it, then come back here to reuse, print, or export it.", "Generez un plan d'epicerie, sauvegardez-le, puis revenez pour le reutiliser, imprimer ou exporter.")}</p>
        <a class="button-link" href="index.html">${tr("Build a plan", "Creer un plan")}</a>
      </div>
    `;
    plansList.classList.remove("hidden");
    paginationInfo.textContent = "";
    loadMoreBtn.classList.add("hidden");
    return;
  }

  if (currentOffset === 0) {
    savedPlansList.innerHTML = `<div id="savedPlansSearchEmpty" class="empty-state hidden"><strong>${tr("No matching plans", "Aucun plan correspondant")}</strong><p class="muted">${tr("Try a different plan name, category, or cost detail.", "Essayez un autre nom de plan, categorie ou detail de cout.")}</p></div>`;
  }

  savedPlansList.insertAdjacentHTML(
    "beforeend",
    plans
      .map((plan) => {
        const totalCost = plan.result?.summary?.total_cost;
        const itemCount = plan.result?.summary?.total_units || 0;
        const currency = plan.result?.location?.currency || plan.result?.insights?.currency || "CAD";
        const budgetUsed = Number(plan.result?.insights?.budget_used_percent || 0).toFixed(1);
        const safeLabel = escapeHtml(plan.label || "Untitled plan");
        const safeId = escapeHtml(plan.id);
        return `
          <article class="saved-plan" data-plan-id="${safeId}">
            <div class="saved-plan-topline">
              <strong class="plan-label-text">${safeLabel}</strong>
              <span class="preview-pill">${budgetUsed}% ${tr("budget", "budget")}</span>
            </div>
            <p class="muted">${tr("Created:", "Cree le:")} ${escapeHtml(formatDate(plan.created_at))}</p>
            <p class="muted">${tr("Cost:", "Cout:")} ${escapeHtml(formatCurrency(totalCost, currency))} &bull; ${tr("Items:", "Articles:")} ${itemCount}</p>
            <div class="plan-actions">
              <button class="secondary btn-sm" data-action="open" data-plan-id="${safeId}">${tr("Open", "Ouvrir")}</button>
              <button class="secondary btn-sm" data-action="reuse" data-plan-id="${safeId}">${tr("Reuse", "Reutiliser")}</button>
              <button class="secondary btn-sm" data-action="rename" data-plan-id="${safeId}" data-current-label="${escapeHtml(plan.label || "")}">${tr("Rename", "Renommer")}</button>
              <button class="danger btn-sm" data-action="delete" data-plan-id="${safeId}">${tr("Delete", "Supprimer")}</button>
            </div>
          </article>
        `;
      })
      .join("")
  );

  plansList.classList.remove("hidden");

  const total = pagination.total || 0;
  const loaded = currentOffset + plans.length;
  paginationInfo.textContent = `${tr("Showing", "Affichage")} ${loaded} ${tr("of", "sur")} ${total} ${tr("plan(s).", "plan(s).")}`;

  if (loaded < total) {
    loadMoreBtn.classList.remove("hidden");
  } else {
    loadMoreBtn.classList.add("hidden");
  }

  applyPlanSearchFilter();
}

function renderPlanDetail(planData) {
  currentPlanDetail = planData;
  const plan = planData.plan || {};
  const result = plan.result || {};
  const summary = result.summary || {};
  const insights = result.insights || {};
  const items = Array.isArray(result.items) ? result.items : [];
  const currency = result.location?.currency || insights.currency || "CAD";
  const categories = Array.isArray(insights.category_breakdown) ? insights.category_breakdown : [];
  const actions = Array.isArray(insights.next_actions) ? insights.next_actions : [];

  const planDetailContent = document.getElementById("planDetailContent");
  const planDetail = document.getElementById("planDetail");
  const plansList = document.getElementById("plansList");

  const cards = [
    [tr("Total cost", "Cout total"), formatCurrency(summary.total_cost, currency)],
    [tr("Budget left", "Budget restant"), formatCurrency(summary.budget_remaining, currency)],
    [tr("Items", "Articles"), String(summary.total_units || 0)],
  ];

  planDetailContent.innerHTML = `
    <h3>${escapeHtml(plan.label || tr("Untitled plan", "Plan sans titre"))}</h3>
    <p class="muted">${tr("Created:", "Cree le:")} ${escapeHtml(formatDate(plan.created_at))}</p>

    <div class="summary-grid mt-sm">
      ${cards.map(([label, value]) => `
        <article class="summary-card">
          <span class="label">${escapeHtml(label)}</span>
          <span class="value">${escapeHtml(value)}</span>
        </article>
      `).join("")}
    </div>

    <section class="insights-panel mt-section">
      <div>
        <h4>${tr("Plan insights", "Apercus du plan")}</h4>
        <p class="muted">${escapeHtml(Number(insights.budget_used_percent || 0).toFixed(1))}% ${tr("of budget used", "du budget utilise")}${insights.best_store?.name ? ` · ${tr("Lowest estimate:", "Estimation la plus basse:")} ${escapeHtml(insights.best_store.name)}` : ""}</p>
      </div>
      <div class="category-breakdown">
        ${categories.length ? categories.slice(0, 6).map((row) => `
          <div class="category-pill">
            <span>${escapeHtml(prettyCategory(row.category))}</span>
            <strong>${escapeHtml(formatCurrency(row.cost, currency))}</strong>
          </div>
        `).join("") : `<p class="muted">${tr("No category spending data available.", "Aucune depense par categorie disponible.")}</p>`}
      </div>
      <ul class="insight-actions">
        ${actions.length ? actions.map((action) => `<li>${escapeHtml(action)}</li>`).join("") : `<li>${tr("Review your list before shopping.", "Revisez votre liste avant d'aller en magasin.")}</li>`}
      </ul>
    </section>

    <h4 class="mt-section">${tr("Shopping list", "Liste d'achats")}</h4>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>${tr("Item", "Article")}</th>
            <th>${tr("Category", "Categorie")}</th>
            <th>${tr("Qty", "Qt")}</th>
            <th>${tr("Cost", "Cout")}</th>
          </tr>
        </thead>
        <tbody>
          ${items.map(item => `
            <tr>
              <td>${escapeHtml(item.name)}</td>
              <td>${escapeHtml(prettyCategory(item.category))}</td>
              <td>${item.quantity}</td>
              <td>${escapeHtml(formatCurrency(item.total_cost, currency))}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;

  // Hide list, show detail
  plansList.classList.add("hidden");
  planDetail.classList.remove("hidden");

  setTimeout(() => {
    planDetail.scrollIntoView({ behavior: "smooth", block: "start" });
  }, 100);
}

// --- Actions ---

async function openPlan(planId) {
  showStatus(tr("Opening plan...", "Ouverture du plan..."), "info");
  const result = await getPlan(planId);
  if (result.ok) {
    renderPlanDetail(result.data);
    showStatus(`${tr("Opened:", "Ouvert:")} ${escapeHtml(result.data.plan?.label || planId)}`, "success");
  } else {
    showStatus(result.data.detail || tr("Could not open this plan.", "Impossible d'ouvrir ce plan."), "error");
  }
}

async function reusePlan(planId) {
  showStatus(tr("Loading plan for reuse...", "Chargement du plan pour reutilisation..."), "info");
  const result = await getPlan(planId);
  if (result.ok && result.data.plan && result.data.plan.request) {
    const request = result.data.plan.request.optimize_request || {};
    sessionStorage.setItem("reuse_plan_request", JSON.stringify(request));
    window.location.href = "index.html";
  } else {
    showStatus(tr("Could not load plan for reuse.", "Impossible de charger le plan pour reutilisation."), "error");
  }
}

// Inline rename — replaces prompt()
function startInlineRename(triggerBtn, planId, currentLabel) {
  const article = triggerBtn.closest(".saved-plan");
  if (!article) return;

  const labelEl = article.querySelector(".plan-label-text");
  if (!labelEl) return;

  if (article.querySelector(".inline-rename-input")) return;

  const originalText = labelEl.textContent;
  const input = document.createElement("input");
  input.type = "text";
  input.className = "inline-rename-input";
  input.value = currentLabel;

  labelEl.textContent = "";
  labelEl.appendChild(input);
  input.focus();
  input.select();

  const finishRename = async () => {
    const newLabel = input.value.trim();
    if (!newLabel || newLabel === currentLabel) {
      labelEl.textContent = originalText;
      return;
    }

    labelEl.textContent = tr("Saving...", "Enregistrement...");
    const result = await renamePlan(planId, newLabel);

    if (result.ok) {
      showStatus(tr("Plan renamed.", "Plan renomme."), "success");
      loadAllPlans();
    } else {
      showStatus(result.data.detail || tr("Rename failed.", "Echec du renommage."), "error");
      labelEl.textContent = originalText;
    }
  };

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      finishRename();
    }
    if (e.key === "Escape") {
      labelEl.textContent = originalText;
    }
  });

  input.addEventListener("blur", () => {
    setTimeout(() => {
      if (labelEl.contains(input)) {
        labelEl.textContent = originalText;
      }
    }, 150);
  });
}

// Delete confirmation — replaces confirm()
function startDeleteConfirm(triggerBtn, planId) {
  const actionsDiv = triggerBtn.closest(".plan-actions");
  if (!actionsDiv) return;

  const group = document.createElement("span");
  group.className = "delete-confirm-group";
  group.innerHTML = `
    <button class="danger-confirm btn-sm" data-action="confirm-delete" data-plan-id="${escapeHtml(planId)}">${tr("Yes, delete", "Oui, supprimer")}</button>
    <button class="secondary btn-sm" data-action="cancel-delete">${tr("Cancel", "Annuler")}</button>
  `;

  triggerBtn.replaceWith(group);

  const timerId = setTimeout(() => {
    cancelDeleteConfirm(group.querySelector("[data-action='cancel-delete']"));
  }, 5000);

  group.dataset.timerId = String(timerId);
}

function cancelDeleteConfirm(cancelBtn) {
  if (!cancelBtn) return;
  const group = cancelBtn.closest(".delete-confirm-group");
  if (!group) return;

  if (group.dataset.timerId) {
    clearTimeout(Number(group.dataset.timerId));
  }

  const planId = group.querySelector("[data-action='confirm-delete']")?.dataset?.planId || "";
  const newBtn = document.createElement("button");
  newBtn.className = "danger btn-sm";
  newBtn.dataset.action = "delete";
  newBtn.dataset.planId = planId;
  newBtn.textContent = tr("Delete", "Supprimer");
  group.replaceWith(newBtn);
}

async function executeDelete(planId) {
  const result = await deletePlan(planId);
  if (result.ok) {
    showStatus(tr("Plan deleted.", "Plan supprime."), "success");
    loadAllPlans();
  } else {
    showStatus(result.data.detail || tr("Delete failed.", "Echec de suppression."), "error");
  }
}

// --- Event Delegation ---

document.getElementById("savedPlansList").addEventListener("click", (event) => {
  const btn = event.target.closest("button[data-action]");
  if (!btn) return;

  const action = btn.dataset.action;
  const planId = btn.dataset.planId;

  switch (action) {
    case "open":
      openPlan(planId);
      break;
    case "reuse":
      reusePlan(planId);
      break;
    case "rename":
      startInlineRename(btn, planId, btn.dataset.currentLabel || "");
      break;
    case "delete":
      startDeleteConfirm(btn, planId);
      break;
    case "confirm-delete":
      executeDelete(planId);
      break;
    case "cancel-delete":
      cancelDeleteConfirm(btn);
      break;
  }
});

// --- Back to list ---

document.getElementById("backToListBtn").addEventListener("click", () => {
  document.getElementById("planDetail").classList.add("hidden");
  document.getElementById("plansList").classList.remove("hidden");
});

document.getElementById("printPlanBtn").addEventListener("click", () => {
  if (!currentPlanDetail) {
    showStatus(tr("Open a plan before printing.", "Ouvrez un plan avant d'imprimer."), "error");
    return;
  }
  printPlanView();
});

document.getElementById("exportPlanCsvBtn").addEventListener("click", () => {
  if (!currentPlanDetail) {
    showStatus(tr("Open a plan before exporting.", "Ouvrez un plan avant d'exporter."), "error");
    return;
  }
  const label = currentPlanDetail.plan?.label || "saved-plan";
  const safeLabel = String(label).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "saved-plan";
  downloadCsv(`${safeLabel}.csv`, buildPlanCsvRows(currentPlanDetail.plan));
  showStatus(tr("CSV exported.", "CSV exporte."), "success");
});

// --- Load more ---

document.getElementById("loadMoreBtn").addEventListener("click", async () => {
  currentOffset += PAGE_SIZE;
  showStatus(tr("Loading more plans...", "Chargement de plus de plans..."), "info");
  const result = await listPlans(PAGE_SIZE, currentOffset);
  if (result.ok) {
    renderPlansList(result.data);
    showStatus(tr("Plans loaded.", "Plans charges."), "success");
  } else {
    showStatus(result.data.detail || tr("Could not load more plans.", "Impossible de charger plus de plans."), "error");
  }
});

document.getElementById("planSearch")?.addEventListener("input", () => {
  applyPlanSearchFilter();
});

// --- Initial load helper ---

async function loadAllPlans() {
  currentOffset = 0;
  showStatus(tr("Loading your saved plans...", "Chargement de vos plans sauvegardes..."), "info");
  const result = await listPlans(PAGE_SIZE, 0);
  if (result.ok) {
    renderPlansList(result.data);
    showStatus(tr("Saved plans loaded.", "Plans sauvegardes charges."), "success");
  } else {
    showStatus(result.data.detail || tr("Could not load saved plans.", "Impossible de charger les plans sauvegardes."), "error");
  }
}

// --- Hidden backward-compat elements (wired up so old code paths don't throw) ---

document.getElementById("loadPlansBtn").addEventListener("click", () => loadAllPlans());
document.getElementById("fetchPlanBtn").addEventListener("click", () => {
  const planId = document.getElementById("planIdToFetch").value.trim();
  if (planId) openPlan(planId);
});

// --- Auto-load on page visit ---

if (Session.isActive()) {
  document.getElementById("savedSignedOutState")?.classList.add("hidden");
  loadAllPlans();
} else {
  document.getElementById("savedSignedOutState")?.classList.remove("hidden");
  showStatus(tr("Sign in to see your saved plans.", "Connectez-vous pour voir vos plans sauvegardes."), "info");
}
