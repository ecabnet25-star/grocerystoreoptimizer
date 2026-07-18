// Account management page (account.html)

function updateAccountDisplay() {
  const displayUserId = document.getElementById("displayUserId");
  const displaySessionStatus = document.getElementById("displaySessionStatus");
  const createAccountForm = document.getElementById("createAccountForm");
  const loginForm = document.getElementById("loginForm");
  const sessionActions = document.getElementById("sessionActions");
  const welcomeCard = document.getElementById("welcomeCard");
  const welcomeName = document.getElementById("welcomeName");
  const copyAccountIdBtn = document.getElementById("copyAccountIdBtn");
  const preferencesForm = document.getElementById("preferencesForm");

  if (Session.isActive()) {
    displayUserId.textContent = Session.userId;
    displaySessionStatus.textContent = tr("Active", "Active");
    displaySessionStatus.style.color = "var(--brand)";
    if (copyAccountIdBtn) copyAccountIdBtn.disabled = false;
    showStatus(`${tr("Signed in as", "Connecte en tant que")} ${Session.userName || tr("user", "utilisateur")}.`, "success");

    // Show welcome card, hide auth forms
    if (welcomeCard) {
      welcomeCard.classList.remove("hidden");
      if (welcomeName) {
        welcomeName.textContent = `${tr("Welcome back", "Bon retour")}, ${Session.userName || tr("user", "utilisateur")}!`;
      }
    }
    if (createAccountForm) createAccountForm.classList.add("hidden");
    if (loginForm) loginForm.classList.add("hidden");
    if (sessionActions) sessionActions.classList.remove("hidden");
    if (preferencesForm) preferencesForm.classList.remove("hidden");
    void populatePreferencesForm();
  } else {
    displayUserId.textContent = tr("Not signed in", "Non connecte");
    displaySessionStatus.textContent = tr("Inactive", "Inactif");
    displaySessionStatus.style.color = "var(--muted)";
    if (copyAccountIdBtn) copyAccountIdBtn.disabled = true;
    showStatus(tr("Create an account or sign in to manage plans.", "Creez un compte ou connectez-vous pour gerer vos plans."), "info");

    // Hide welcome card and session actions, show auth forms
    if (welcomeCard) welcomeCard.classList.add("hidden");
    if (createAccountForm) createAccountForm.classList.remove("hidden");
    if (loginForm) loginForm.classList.remove("hidden");
    if (sessionActions) sessionActions.classList.add("hidden");
    if (preferencesForm) preferencesForm.classList.add("hidden");
  }
}

function accountSplitList(value) {
  return String(value || "").split(",").map((item) => item.trim()).filter(Boolean);
}

async function populatePreferencesForm() {
  if (!Session.isActive()) return;
  const result = await loadProfilePreferences();
  if (!result.ok) return;
  const preferences = result.data.preferences || {};
  document.getElementById("profileLikes").value = (preferences.likes || []).join(", ");
  document.getElementById("profileDislikes").value = (preferences.dislikes || []).join(", ");
  document.getElementById("profileGoals").value = (preferences.health_goals || []).join(", ");
  document.getElementById("profileExcluded").value = (preferences.excluded_categories || []).join(", ");
  document.getElementById("profileLanguage").value = preferences.preferred_language || "en";
}

document.getElementById("preferencesForm")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = document.getElementById("savePreferencesBtn");
  const payload = {
    likes: accountSplitList(document.getElementById("profileLikes").value),
    dislikes: accountSplitList(document.getElementById("profileDislikes").value),
    health_goals: accountSplitList(document.getElementById("profileGoals").value),
    excluded_categories: accountSplitList(document.getElementById("profileExcluded").value),
    preferred_language: document.getElementById("profileLanguage").value === "fr" ? "fr" : "en",
  };
  setButtonLoading(button, true, tr("Save preferences", "Enregistrer les preferences"));
  const result = await saveProfilePreferences(payload);
  setButtonLoading(button, false, tr("Save preferences", "Enregistrer les preferences"));
  if (!result.ok) {
    showStatus(result.data.detail || tr("Could not save preferences.", "Impossible d'enregistrer les preferences."), "error");
    return;
  }
  setCurrentLanguage(payload.preferred_language);
  document.getElementById("languageSelect").value = payload.preferred_language;
  showStatus(tr("Preferences saved and ready for your next plan.", "Preferences enregistrees pour votre prochain plan."), "success");
});

// Helper to set button loading state
function setButtonLoading(btn, loading, originalText) {
  if (!btn) return;
  btn.disabled = loading;
  btn.textContent = loading ? tr("Working...", "Traitement...") : originalText;
}

// Create account form
document.getElementById("createAccountForm").addEventListener("submit", async (event) => {
  event.preventDefault();

  const name = document.getElementById("createName").value.trim();
  const email = document.getElementById("createEmail").value.trim();
  const password = document.getElementById("createPassword").value;
  const btn = document.getElementById("createAccountBtn");

  if (!name || !email || !password) {
    showStatus(tr("Please enter name, email, and password.", "Veuillez entrer nom, courriel et mot de passe."), "error");
    return;
  }
  if (password.length < 8) {
    showStatus(tr("Password must be at least 8 characters.", "Le mot de passe doit contenir au moins 8 caracteres."), "error");
    return;
  }

  setButtonLoading(btn, true, tr("Create account", "Creer un compte"));
  showStatus(tr("Creating account...", "Creation du compte..."), "info");
  const result = await createUser(name, email, password);
  setButtonLoading(btn, false, tr("Create account", "Creer un compte"));

  if (result.ok) {
    updateAccountDisplay();
    document.getElementById("createAccountForm").reset();
  } else {
    showStatus(result.data.detail || tr("Account creation failed.", "La creation du compte a echoue."), "error");
  }
});

// Login form
document.getElementById("loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();

  const email = document.getElementById("loginEmail").value.trim();
  const password = document.getElementById("loginPassword").value;
  const btn = document.getElementById("loginBtn");

  if (!email || !password) {
    showStatus(tr("Please enter your email and password.", "Veuillez entrer votre courriel et mot de passe."), "error");
    return;
  }

  setButtonLoading(btn, true, tr("Sign in", "Se connecter"));
  showStatus(tr("Signing in...", "Connexion..."), "info");
  const result = await loginUser(email, password);
  setButtonLoading(btn, false, tr("Sign in", "Se connecter"));

  if (result.ok) {
    updateAccountDisplay();
    document.getElementById("loginForm").reset();
  } else {
    showStatus(result.data.detail || tr("Sign in failed.", "Echec de connexion."), "error");
  }
});

// Refresh token button
document.getElementById("refreshTokenBtn").addEventListener("click", async () => {
  if (!Session.isActive()) {
    showStatus(tr("Please sign in first.", "Veuillez d'abord vous connecter."), "error");
    return;
  }

  const btn = document.getElementById("refreshTokenBtn");
  setButtonLoading(btn, true, tr("Refresh session", "Actualiser la session"));
  showStatus(tr("Refreshing session...", "Actualisation de la session..."), "info");
  const result = await refreshToken();
  setButtonLoading(btn, false, tr("Refresh session", "Actualiser la session"));

  if (result.ok) {
    showStatus(tr("Session refreshed successfully.", "Session actualisee avec succes."), "success");
  } else {
    showStatus(result.data.detail || tr("Could not refresh session.", "Impossible d'actualiser la session."), "error");
  }
});

// Logout button
document.getElementById("logoutBtn").addEventListener("click", async () => {
  if (!Session.isActive()) {
    showStatus(tr("You are already signed out.", "Vous etes deja deconnecte."), "info");
    return;
  }

  const btn = document.getElementById("logoutBtn");
  setButtonLoading(btn, true, tr("Sign out", "Se deconnecter"));
  showStatus(tr("Signing out...", "Deconnexion..."), "info");
  const result = await logoutUser();
  setButtonLoading(btn, false, tr("Sign out", "Se deconnecter"));

  if (result.ok) {
    updateAccountDisplay();
  } else {
    showStatus(result.data.detail || tr("Sign out failed.", "Echec de deconnexion."), "error");
  }
});

// Logout all button
document.getElementById("logoutAllBtn").addEventListener("click", async () => {
  if (!Session.isActive()) {
    showStatus(tr("You are already signed out.", "Vous etes deja deconnecte."), "info");
    return;
  }

  // Inline confirmation pattern: first click asks, second click confirms
  const btn = document.getElementById("logoutAllBtn");
  if (btn.dataset.confirming === "true") {
    btn.dataset.confirming = "";
    btn.textContent = tr("Sign out all devices", "Deconnecter tous les appareils");
    btn.classList.remove("danger-confirm");
    btn.classList.add("danger");

    setButtonLoading(btn, true, tr("Sign out all devices", "Deconnecter tous les appareils"));
    showStatus(tr("Signing out from all devices...", "Deconnexion de tous les appareils..."), "info");
    const result = await logoutAllSessions();
    setButtonLoading(btn, false, tr("Sign out all devices", "Deconnecter tous les appareils"));

    if (result.ok) {
      updateAccountDisplay();
      showStatus(tr("Signed out from all devices.", "Deconnecte de tous les appareils."), "success");
    } else {
      showStatus(result.data.detail || tr("Sign out failed.", "Echec de deconnexion."), "error");
    }
    return;
  }

  // First click — show confirmation state
  btn.dataset.confirming = "true";
  btn.textContent = tr("Click again to confirm", "Cliquez encore pour confirmer");
  btn.classList.remove("danger");
  btn.classList.add("danger-confirm");

  // Auto-reset after 4 seconds
  setTimeout(() => {
    if (btn.dataset.confirming === "true") {
      btn.dataset.confirming = "";
      btn.textContent = tr("Sign out all devices", "Deconnecter tous les appareils");
      btn.classList.remove("danger-confirm");
      btn.classList.add("danger");
    }
  }, 4000);
});

document.getElementById("copyAccountIdBtn")?.addEventListener("click", async () => {
  if (!Session.isActive()) {
    showStatus(tr("Sign in before copying your account ID.", "Connectez-vous avant de copier votre identifiant."), "error");
    return;
  }

  try {
    await navigator.clipboard.writeText(Session.userId);
    showStatus(tr("Account ID copied.", "Identifiant copie."), "success");
  } catch {
    showStatus(tr("Could not copy automatically. Select the account ID manually.", "Copie automatique impossible. Selectionnez l'identifiant manuellement."), "error");
  }
});

// Initial display
updateAccountDisplay();
