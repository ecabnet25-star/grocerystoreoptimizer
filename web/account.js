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

  if (Session.isActive()) {
    displayUserId.textContent = Session.userId;
    displaySessionStatus.textContent = "Active";
    displaySessionStatus.style.color = "var(--brand)";
    if (copyAccountIdBtn) copyAccountIdBtn.disabled = false;
    showStatus(`Signed in as ${Session.userName || "user"}.`, "success");

    // Show welcome card, hide auth forms
    if (welcomeCard) {
      welcomeCard.classList.remove("hidden");
      if (welcomeName) {
        welcomeName.textContent = `Welcome back, ${Session.userName || "user"}!`;
      }
    }
    if (createAccountForm) createAccountForm.classList.add("hidden");
    if (loginForm) loginForm.classList.add("hidden");
    if (sessionActions) sessionActions.classList.remove("hidden");
  } else {
    displayUserId.textContent = "Not signed in";
    displaySessionStatus.textContent = "Inactive";
    displaySessionStatus.style.color = "var(--muted)";
    if (copyAccountIdBtn) copyAccountIdBtn.disabled = true;
    showStatus("Create an account or sign in to manage plans.", "info");

    // Hide welcome card and session actions, show auth forms
    if (welcomeCard) welcomeCard.classList.add("hidden");
    if (createAccountForm) createAccountForm.classList.remove("hidden");
    if (loginForm) loginForm.classList.remove("hidden");
    if (sessionActions) sessionActions.classList.add("hidden");
  }
}

// Helper to set button loading state
function setButtonLoading(btn, loading, originalText) {
  if (!btn) return;
  btn.disabled = loading;
  btn.textContent = loading ? "Working..." : originalText;
}

// Create account form
document.getElementById("createAccountForm").addEventListener("submit", async (event) => {
  event.preventDefault();

  const name = document.getElementById("createName").value.trim();
  const email = document.getElementById("createEmail").value.trim();
  const password = document.getElementById("createPassword").value;
  const btn = document.getElementById("createAccountBtn");

  if (!name || !email || !password) {
    showStatus("Please enter name, email, and password.", "error");
    return;
  }
  if (password.length < 8) {
    showStatus("Password must be at least 8 characters.", "error");
    return;
  }

  setButtonLoading(btn, true, "Create account");
  showStatus("Creating account...", "info");
  const result = await createUser(name, email, password);
  setButtonLoading(btn, false, "Create account");

  if (result.ok) {
    updateAccountDisplay();
    document.getElementById("createAccountForm").reset();
  } else {
    showStatus(result.data.detail || "Account creation failed.", "error");
  }
});

// Login form
document.getElementById("loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();

  const email = document.getElementById("loginEmail").value.trim();
  const password = document.getElementById("loginPassword").value;
  const btn = document.getElementById("loginBtn");

  if (!email || !password) {
    showStatus("Please enter your email and password.", "error");
    return;
  }

  setButtonLoading(btn, true, "Sign in");
  showStatus("Signing in...", "info");
  const result = await loginUser(email, password);
  setButtonLoading(btn, false, "Sign in");

  if (result.ok) {
    updateAccountDisplay();
    document.getElementById("loginForm").reset();
  } else {
    showStatus(result.data.detail || "Sign in failed.", "error");
  }
});

// Refresh token button
document.getElementById("refreshTokenBtn").addEventListener("click", async () => {
  if (!Session.isActive()) {
    showStatus("Please sign in first.", "error");
    return;
  }

  const btn = document.getElementById("refreshTokenBtn");
  setButtonLoading(btn, true, "Refresh session");
  showStatus("Refreshing session...", "info");
  const result = await refreshToken();
  setButtonLoading(btn, false, "Refresh session");

  if (result.ok) {
    showStatus("Session refreshed successfully.", "success");
  } else {
    showStatus(result.data.detail || "Could not refresh session.", "error");
  }
});

// Logout button
document.getElementById("logoutBtn").addEventListener("click", async () => {
  if (!Session.isActive()) {
    showStatus("You are already signed out.", "info");
    return;
  }

  const btn = document.getElementById("logoutBtn");
  setButtonLoading(btn, true, "Sign out");
  showStatus("Signing out...", "info");
  const result = await logoutUser();
  setButtonLoading(btn, false, "Sign out");

  if (result.ok) {
    updateAccountDisplay();
  } else {
    showStatus(result.data.detail || "Sign out failed.", "error");
  }
});

// Logout all button
document.getElementById("logoutAllBtn").addEventListener("click", async () => {
  if (!Session.isActive()) {
    showStatus("You are already signed out.", "info");
    return;
  }

  // Inline confirmation pattern: first click asks, second click confirms
  const btn = document.getElementById("logoutAllBtn");
  if (btn.dataset.confirming === "true") {
    btn.dataset.confirming = "";
    btn.textContent = "Sign out all devices";
    btn.classList.remove("danger-confirm");
    btn.classList.add("danger");

    setButtonLoading(btn, true, "Sign out all devices");
    showStatus("Signing out from all devices...", "info");
    const result = await logoutAllSessions();
    setButtonLoading(btn, false, "Sign out all devices");

    if (result.ok) {
      updateAccountDisplay();
      showStatus("Signed out from all devices.", "success");
    } else {
      showStatus(result.data.detail || "Sign out failed.", "error");
    }
    return;
  }

  // First click — show confirmation state
  btn.dataset.confirming = "true";
  btn.textContent = "Click again to confirm";
  btn.classList.remove("danger");
  btn.classList.add("danger-confirm");

  // Auto-reset after 4 seconds
  setTimeout(() => {
    if (btn.dataset.confirming === "true") {
      btn.dataset.confirming = "";
      btn.textContent = "Sign out all devices";
      btn.classList.remove("danger-confirm");
      btn.classList.add("danger");
    }
  }, 4000);
});

document.getElementById("copyAccountIdBtn")?.addEventListener("click", async () => {
  if (!Session.isActive()) {
    showStatus("Sign in before copying your account ID.", "error");
    return;
  }

  try {
    await navigator.clipboard.writeText(Session.userId);
    showStatus("Account ID copied.", "success");
  } catch {
    showStatus("Could not copy automatically. Select the account ID manually.", "error");
  }
});

// Initial display
updateAccountDisplay();
