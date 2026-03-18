// ── Trainer display ───────────────────────────────────────────────
function setTrainerDisplay(id) {
  const el = document.getElementById("sidebar-trainer-name");
  if (el) el.textContent = id;
}

// ── Switch active user and re-render table ────────────────────────
function switchToUser(userId) {
  saveUserId(userId);
  setTrainerDisplay(userId);
  _cookieData = loadCookieForUser(userId);
  renderTable();
}

// ── First-visit user ID prompt ────────────────────────────────────
function showUserIdPrompt() {
  return new Promise((resolve) => {
    const overlay = document.getElementById("userid-overlay");
    const input = document.getElementById("userid-input");
    const btn = document.getElementById("userid-confirm");
    const error = document.getElementById("userid-error");

    input.value = "";
    error.style.display = "none";
    overlay.classList.add("visible");
    setTimeout(() => input.focus(), 50);

    function confirm() {
      const val = input.value.trim();
      if (!val) {
        error.textContent = "Please enter an ID to continue.";
        error.style.display = "block";
        input.focus();
        return;
      }
      saveUserId(val);
      overlay.classList.remove("visible");
      setTrainerDisplay(val);
      resolve(val);
    }

    const freshBtn = btn.cloneNode(true);
    btn.replaceWith(freshBtn);
    freshBtn.addEventListener("click", confirm);
    input.addEventListener("keydown", function onKey(e) {
      if (e.key === "Enter") {
        confirm();
        input.removeEventListener("keydown", onKey);
      }
    });
  });
}

// ── Sidebar + Settings panel ──────────────────────────────────────
function initSidebar() {
  const sidebar = document.getElementById("left-sidebar");
  const toggleBtn = document.getElementById("sidebar-toggle");
  const settingsBtn = document.getElementById("sidebar-settings-btn");
  const settingsOverlay = document.getElementById("settings-overlay");
  const settingsCloseBtn = document.getElementById("settings-close-btn");
  const userList = document.getElementById("settings-user-list");
  const formLabel = document.getElementById("settings-form-label");
  const input = document.getElementById("settings-userid-input");
  const confirmBtn = document.getElementById("settings-confirm-btn");
  const errorEl = document.getElementById("settings-userid-error");

  let editingUser = null;

  toggleBtn.addEventListener("click", () => sidebar.classList.toggle("open"));

  function closeSettings() {
    settingsOverlay.classList.remove("visible");
    editingUser = null;
    input.value = "";
    errorEl.style.display = "none";
    formLabel.textContent = "Add New Trainer";
    confirmBtn.textContent = "Save";
  }

  settingsBtn.addEventListener("click", () => {
    renderUserList();
    settingsOverlay.classList.add("visible");
    setTimeout(() => input.focus(), 50);
  });

  settingsCloseBtn.addEventListener("click", closeSettings);
  settingsOverlay.addEventListener("click", (e) => {
    if (e.target === settingsOverlay) closeSettings();
  });

  function renderUserList() {
    const users = loadAllUsers();
    const activeId = loadUserId();
    userList.innerHTML = "";

    if (users.length === 0) {
      userList.innerHTML =
        '<p style="color:var(--text-dim);font-size:12px;text-align:center;padding:8px 0">No saved trainers yet.</p>';
      return;
    }

    users.forEach((uid) => {
      const row = document.createElement("div");
      row.className = "settings-user-row" + (uid === activeId ? " active" : "");

      const nameEl = document.createElement("span");
      nameEl.className = "settings-user-name";
      nameEl.textContent = uid;
      if (uid === activeId) {
        const badge = document.createElement("span");
        badge.className = "settings-active-badge";
        badge.textContent = "Active";
        nameEl.appendChild(badge);
      }

      const actions = document.createElement("div");
      actions.className = "settings-user-actions";

      if (uid !== activeId) {
        const switchBtn = document.createElement("button");
        switchBtn.className = "settings-action-btn switch";
        switchBtn.title = "Switch to this trainer";
        switchBtn.textContent = "⇄";
        switchBtn.addEventListener("click", () => {
          switchToUser(uid);
          closeSettings();
        });
        actions.appendChild(switchBtn);
      }

      const exportBtn = document.createElement("button");
      exportBtn.className = "settings-action-btn export";
      exportBtn.title = "Export this trainer's data";
      exportBtn.textContent = "⬇";
      exportBtn.addEventListener("click", () => exportUserData(uid));
      actions.appendChild(exportBtn);

      const renameBtn = document.createElement("button");
      renameBtn.className = "settings-action-btn rename";
      renameBtn.title = "Rename";
      renameBtn.textContent = "✎";
      renameBtn.addEventListener("click", () => {
        editingUser = uid;
        input.value = uid;
        formLabel.textContent = `Rename "${uid}"`;
        confirmBtn.textContent = "Rename";
        errorEl.style.display = "none";
        input.focus();
        input.select();
      });
      actions.appendChild(renameBtn);

      const delBtn = document.createElement("button");
      delBtn.className = "settings-action-btn delete";
      delBtn.title = "Delete trainer";
      delBtn.textContent = "✕";
      delBtn.addEventListener("click", () => {
        if (
          !confirm(
            `Delete trainer "${uid}" and all their data? This cannot be undone.`,
          )
        )
          return;
        deleteUser(uid);
        const remaining = loadAllUsers();
        if (uid === activeId) {
          if (remaining.length > 0) {
            switchToUser(remaining[0]);
          } else {
            closeSettings();
            showUserIdPrompt().then((newId) => switchToUser(newId));
            return;
          }
        }
        renderUserList();
      });
      actions.appendChild(delBtn);

      row.appendChild(nameEl);
      row.appendChild(actions);
      userList.appendChild(row);
    });
  }

  function handleConfirm() {
    const val = input.value.trim();
    if (!val) {
      errorEl.textContent = "Please enter a Trainer ID.";
      errorEl.style.display = "block";
      input.focus();
      return;
    }
    const users = loadAllUsers();
    if (editingUser) {
      if (val !== editingUser && users.includes(val)) {
        errorEl.textContent = `Trainer "${val}" already exists.`;
        errorEl.style.display = "block";
        return;
      }
      renameUser(editingUser, val);
      if (loadUserId() === val) setTrainerDisplay(val);
      editingUser = null;
      formLabel.textContent = "Add New Trainer";
      confirmBtn.textContent = "Save";
    } else {
      if (users.includes(val)) {
        errorEl.textContent = `Trainer "${val}" already exists.`;
        errorEl.style.display = "block";
        return;
      }
      saveUserId(val);
      switchToUser(val);
      closeSettings();
      return;
    }
    input.value = "";
    errorEl.style.display = "none";
    renderUserList();
  }

  confirmBtn.addEventListener("click", handleConfirm);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") handleConfirm();
  });

  // Import
  const importInput = document.getElementById("settings-import-input");
  const importMsg = document.getElementById("settings-import-error");

  function showImportMsg(text, isSuccess = false) {
    importMsg.style.cssText = `display:block;color:${isSuccess ? "var(--collected)" : "#ff6b6b"}`;
    importMsg.textContent = text;
    if (isSuccess)
      setTimeout(() => {
        importMsg.style.display = "none";
      }, 4000);
  }

  importInput.addEventListener("change", () => {
    const file = importInput.files[0];
    if (!file) return;
    importMsg.style.display = "none";
    importInput.value = "";

    parseImportFile(file, (err, result) => {
      if (err) {
        showImportMsg(err);
        return;
      }
      const { uid, data, exists } = result;

      if (exists) {
        importMsg.style.cssText = "display:block;color:#ffd43b";
        importMsg.innerHTML = `Trainer <strong style="color:var(--text)">${uid}</strong> already exists. Overwrite their data?
          <span style="display:inline-flex;gap:6px;margin-left:8px;">
            <button id="import-overwrite-yes" style="font-family:Nunito,sans-serif;font-weight:800;font-size:11px;padding:3px 10px;border-radius:6px;border:1px solid #ffd43b;background:rgba(255,211,67,0.15);color:#ffd43b;cursor:pointer;">Yes</button>
            <button id="import-overwrite-no"  style="font-family:Nunito,sans-serif;font-weight:800;font-size:11px;padding:3px 10px;border-radius:6px;border:1px solid var(--border);background:transparent;color:var(--text-dim);cursor:pointer;">Cancel</button>
          </span>`;
        document
          .getElementById("import-overwrite-yes")
          .addEventListener("click", () => {
            applyImport(uid, data);
            renderUserList();
            switchToUser(uid);
            showImportMsg(`✓ Trainer "${uid}" imported successfully!`, true);
          });
        document
          .getElementById("import-overwrite-no")
          .addEventListener("click", () => {
            importMsg.style.display = "none";
          });
      } else {
        applyImport(uid, data);
        renderUserList();
        switchToUser(uid);
        showImportMsg(`✓ Trainer "${uid}" imported successfully!`, true);
      }
    });
  });
}
