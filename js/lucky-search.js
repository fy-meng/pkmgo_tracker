// ── Lucky data queries ────────────────────────────────────────────
function getLuckyIdsForUser(uid) {
  const data = loadCookieForUser(uid);
  const luckyIds = new Set();
  POKEMON.forEach((p) => {
    const entry = data[p.id] || {};
    if (entry.l) luckyIds.add(p.id);
  });
  return luckyIds;
}

function buildLuckyResults(selectedUsers) {
  const allIds = POKEMON.map((p) => p.id);
  const userSets = {};
  selectedUsers.forEach((uid) => {
    userSets[uid] = getLuckyIdsForUser(uid);
  });

  const allHave = allIds.filter((id) =>
    selectedUsers.every((uid) => userSets[uid].has(id)),
  );
  const noneHave = allIds.filter((id) =>
    selectedUsers.every((uid) => !userSets[uid].has(id)),
  );
  const perUserMissing = {};
  selectedUsers.forEach((uid) => {
    perUserMissing[uid] = allIds.filter((id) => !userSets[uid].has(id));
  });

  return { allHave, noneHave, perUserMissing };
}

// ── Range compression ─────────────────────────────────────────────
// Runs of 3+ consecutive IDs become "start-end"; shorter runs stay as "a,b"
function toRangeString(ids) {
  if (ids.length === 0) return "";
  const sorted = [...ids].sort((a, b) => a - b);
  const parts = [];
  let start = sorted[0],
    end = sorted[0];

  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i] === end + 1) {
      end = sorted[i];
    } else {
      parts.push(
        end - start >= 2
          ? `${start}-${end}`
          : start === end
            ? `${start}`
            : `${start},${end}`,
      );
      start = end = sorted[i];
    }
  }
  parts.push(
    end - start >= 2
      ? `${start}-${end}`
      : start === end
        ? `${start}`
        : `${start},${end}`,
  );
  return parts.join(",");
}

// ── Result block UI ───────────────────────────────────────────────
function makeCopyBlock(label, ids, sublabel, excludeSuffix = "") {
  const wrapper = document.createElement("div");
  wrapper.className = "lucky-result-block";

  const header = document.createElement("div");
  header.className = "lucky-result-header";

  const title = document.createElement("span");
  title.className = "lucky-result-title";
  title.textContent = label;
  header.appendChild(title);

  if (sublabel) {
    const sub = document.createElement("span");
    sub.className = "lucky-result-sublabel";
    sub.textContent = sublabel;
    header.appendChild(sub);
  }

  const rangeStr = toRangeString(ids);
  const fullStr = ids.length > 0 ? rangeStr + excludeSuffix : "";

  const copyBtn = document.createElement("button");
  copyBtn.className = "lucky-copy-btn";
  copyBtn.textContent = "Copy";
  copyBtn.addEventListener("click", () => {
    navigator.clipboard.writeText(fullStr).then(() => {
      copyBtn.textContent = "✓ Copied";
      copyBtn.classList.add("copied");
      setTimeout(() => {
        copyBtn.textContent = "Copy";
        copyBtn.classList.remove("copied");
      }, 2000);
    });
  });
  header.appendChild(copyBtn);

  wrapper.appendChild(header);

  const textbox = document.createElement("div");
  textbox.className = "lucky-result-text" + (ids.length === 0 ? " empty" : "");
  textbox.textContent = ids.length > 0 ? fullStr : "(none)";
  wrapper.appendChild(textbox);

  return wrapper;
}

// ── Modal init ────────────────────────────────────────────────────
function initLuckySearch() {
  const openBtn = document.getElementById("lucky-search-open-btn");
  const overlay = document.getElementById("lucky-search-overlay");
  const closeBtn = document.getElementById("lucky-search-close-btn");
  const checklist = document.getElementById("lucky-user-checklist");
  const generateBtn = document.getElementById("lucky-generate-btn");
  const selectError = document.getElementById("lucky-select-error");
  const stepSelect = document.getElementById("lucky-step-select");
  const stepResults = document.getElementById("lucky-step-results");
  const resultsBody = document.getElementById("lucky-results-body");
  const backBtn = document.getElementById("lucky-back-btn");
  const resultClose = document.getElementById("lucky-results-close-btn");

  function close() {
    overlay.classList.remove("visible");
  }

  function showStep(step) {
    stepSelect.style.display = step === "select" ? "" : "none";
    stepResults.style.display = step === "results" ? "" : "none";
  }

  function syncGenerateBtn() {
    const count = checklist.querySelectorAll(
      ".lucky-user-checkbox:checked",
    ).length;
    generateBtn.disabled = count < 2;
    generateBtn.style.opacity = count < 2 ? "0.4" : "1";
    generateBtn.style.cursor = count < 2 ? "not-allowed" : "pointer";
  }

  openBtn.addEventListener("click", () => {
    const users = loadAllUsers();
    const activeId = loadUserId();
    checklist.innerHTML = "";
    selectError.style.display = "none";
    showStep("select");
    overlay.classList.add("visible");

    users.forEach((uid) => {
      const row = document.createElement("label");
      row.className = "lucky-user-check-row";

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.value = uid;
      cb.checked = uid === activeId;
      cb.className = "lucky-user-checkbox";
      cb.addEventListener("change", syncGenerateBtn);

      const name = document.createElement("span");
      name.textContent = uid;
      if (uid === activeId) {
        const badge = document.createElement("span");
        badge.className = "settings-active-badge";
        badge.textContent = "Active";
        name.appendChild(badge);
      }

      row.appendChild(cb);
      row.appendChild(name);
      checklist.appendChild(row);
    });

    syncGenerateBtn();
  });

  closeBtn.addEventListener("click", close);
  resultClose.addEventListener("click", close);
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) close();
  });
  backBtn.addEventListener("click", () => showStep("select"));

  generateBtn.addEventListener("click", () => {
    const selected = [
      ...checklist.querySelectorAll(".lucky-user-checkbox:checked"),
    ].map((cb) => cb.value);
    if (selected.length < 2) return;
    selectError.style.display = "none";

    const excludeSuffix = [
      ...document.querySelectorAll(".lucky-exclude-cb:checked"),
    ]
      .map((cb) => cb.value)
      .join("");

    const { allHave, noneHave, perUserMissing } = buildLuckyResults(selected);

    resultsBody.innerHTML = "";

    const desc = document.createElement("p");
    desc.className = "lucky-results-desc";
    desc.textContent = `Comparing: ${selected.join(", ")}`;
    resultsBody.appendChild(desc);

    resultsBody.appendChild(
      makeCopyBlock(
        "All trainers have 🍀",
        allHave,
        `${allHave.length} Pokémon`,
        excludeSuffix,
      ),
    );
    resultsBody.appendChild(
      makeCopyBlock(
        "No trainer has 🍀",
        noneHave,
        `${noneHave.length} Pokémon`,
        excludeSuffix,
      ),
    );

    selected.forEach((uid) => {
      const missing = perUserMissing[uid];
      resultsBody.appendChild(
        makeCopyBlock(
          `${uid} — missing 🍀`,
          missing,
          `${missing.length} Pokémon`,
          excludeSuffix,
        ),
      );
    });

    showStep("results");
  });
}
