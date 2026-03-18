// ── Sprite URL ────────────────────────────────────────────────────
function spriteUrl(id) {
  return `https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/${id}.png`;
}

// ── Collect button ────────────────────────────────────────────────
function makeCollectBtn(key, onToggle) {
  const btn = document.createElement("button");
  btn.className = "collect-btn" + (state[key].collected ? " active" : "");
  btn.title = "Mark as caught";
  btn.innerHTML = `<span class="check-icon">✓</span><span class="empty-icon">○</span>`;
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    state[key].collected = !state[key].collected;
    btn.className = "collect-btn" + (state[key].collected ? " active" : "");
    if (onToggle) onToggle();
    updateStats();
  });
  return btn;
}

// ── Form sub-row ──────────────────────────────────────────────────
function renderFormRow(form, parentId) {
  const tr = document.createElement("tr");
  tr.className =
    "form-row" + (state[form.formId].collected ? " collected" : "");
  tr.dataset.formId = form.formId;
  tr.dataset.parentId = parentId;

  const typeHtml = form.types
    .map((t) => `<span class="type-badge type-${t}">${t}</span>`)
    .join("");
  const parentName = (POKEMON.find((p) => p.id === parentId) || {}).name || "";

  const nameTd = document.createElement("td");
  nameTd.className = "name-cell";
  nameTd.innerHTML = `
    <div class="pokemon-entry" style="padding-left:36px;">
      <div class="sprite-wrap" style="width:36px;height:36px;">
        <img src="${spriteUrl(form.spriteId)}" alt="${form.name}" loading="lazy" style="width:36px;height:36px;">
      </div>
      <div>
        <div class="pokemon-name" style="font-size:13px;">${form.name} ${parentName}</div>
        <div class="pokemon-type">${typeHtml}</div>
      </div>
    </div>`;

  const emptyTd = () => document.createElement("td");
  const collectTd = document.createElement("td");
  collectTd.appendChild(
    makeCollectBtn(form.formId, () => {
      tr.className =
        "form-row" + (state[form.formId].collected ? " collected" : "");
    }),
  );

  tr.appendChild(nameTd);
  tr.appendChild(emptyTd()); // gender
  tr.appendChild(emptyTd()); // lucky
  tr.appendChild(emptyTd()); // shiny
  tr.appendChild(collectTd);
  tr.appendChild(emptyTd()); // check-all
  tr.appendChild(emptyTd()); // remove-all

  tr.addEventListener("click", () => {
    state[form.formId].collected = !state[form.formId].collected;
    tr.className =
      "form-row" + (state[form.formId].collected ? " collected" : "");
    tr.querySelector(".collect-btn").className =
      "collect-btn" + (state[form.formId].collected ? " active" : "");
    updateStats();
  });

  return tr;
}

// ── Main Pokémon row ──────────────────────────────────────────────
function renderRow(p) {
  const s = state[p.id];
  const hasForms = !!(p.forms && p.forms.length);
  const tr = document.createElement("tr");
  tr.dataset.id = p.id;
  if (s.collected) tr.classList.add("collected");

  const typeHtml = p.types
    .map((t) => `<span class="type-badge type-${t}">${t}</span>`)
    .join("");

  // Name cell
  const nameTd = document.createElement("td");
  nameTd.className = "name-cell";
  const expandBtn = hasForms
    ? `<button class="expand-btn ${s.expanded ? "open" : ""}" data-id="${p.id}" title="Toggle forms">&#9660;</button>`
    : `<span style="display:inline-block;width:28px;flex-shrink:0;"></span>`;

  nameTd.innerHTML = `
    <div class="pokemon-entry">
      ${expandBtn}
      <span class="dex-num">#${String(p.id).padStart(3, "0")}</span>
      <div class="sprite-wrap">
        <img src="${spriteUrl(p.spriteId)}" alt="${p.name}" loading="lazy">
      </div>
      <div>
        <div class="pokemon-name">${p.name}</div>
        <div class="pokemon-type">${typeHtml}</div>
      </div>
    </div>`;

  // Gender cell
  const genderTd = document.createElement("td");
  if (p.gender === "none") {
    const btn = document.createElement("button");
    btn.className = "gender-btn" + (s.genderless ? " active" : "");
    btn.dataset.gender = "none";
    btn.title = "Genderless";
    btn.textContent = "—";
    btn.style.cssText = "font-size:14px;font-weight:700;";
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      state[p.id].genderless = !state[p.id].genderless;
      btn.className = "gender-btn" + (state[p.id].genderless ? " active" : "");
      if (state[p.id].genderless) autoCollect();
      else syncCheckAllBtn();
      updateStats();
    });
    const group = document.createElement("div");
    group.className = "gender-group";
    group.appendChild(btn);
    genderTd.appendChild(group);
  } else {
    const group = document.createElement("div");
    group.className = "gender-group";
    ["male", "female"].forEach((g) => {
      const btn = document.createElement("button");
      btn.className = "gender-btn" + (s[g] ? " active" : "");
      btn.dataset.gender = g;
      btn.title = g.charAt(0).toUpperCase() + g.slice(1);
      btn.textContent = g === "male" ? "♂" : "♀";
      group.appendChild(btn);
    });
    genderTd.appendChild(group);
  }

  // Lucky / Shiny cells
  const luckyTd = document.createElement("td");
  const luckyBtn = document.createElement("button");
  luckyBtn.className = "toggle-btn lucky" + (s.lucky ? " active" : "");
  luckyBtn.title = "Lucky";
  luckyBtn.textContent = "🍀";
  luckyTd.appendChild(luckyBtn);

  const shinyTd = document.createElement("td");
  const shinyBtn = document.createElement("button");
  shinyBtn.className = "toggle-btn shiny" + (s.shiny ? " active" : "");
  shinyBtn.title = "Shiny";
  shinyBtn.textContent = "✨";
  shinyTd.appendChild(shinyBtn);

  // Collect cell
  const collectTd = document.createElement("td");
  const collectBtn = makeCollectBtn(p.id, () => {
    tr.className = state[p.id].collected ? "collected" : "";
    syncCheckAllBtn();
  });
  collectTd.appendChild(collectBtn);

  // ── Check-all cell ────────────────────────────────────────────
  const checkAllTd = document.createElement("td");
  const checkAllBtn = document.createElement("button");
  checkAllBtn.className = "row-check-all-btn";
  checkAllBtn.title = "Check all boxes for this Pokémon";

  function isAllChecked() {
    const keys = ["male", "female", "genderless", "lucky", "shiny"].filter(
      (k) => k in state[p.id],
    );
    return state[p.id].collected && keys.every((k) => state[p.id][k]);
  }

  function syncCheckAllBtn() {
    const allDone = isAllChecked();
    checkAllBtn.textContent = allDone ? "✓ All" : "+ All";
    checkAllBtn.classList.toggle("all-checked", allDone);
  }
  syncCheckAllBtn();

  function setFormStates(newVal) {
    if (!p.forms) return;
    p.forms.forEach((f) => {
      state[f.formId].collected = newVal;
      const ftr = document.querySelector(`tr[data-form-id="${f.formId}"]`);
      if (ftr) {
        ftr.className = "form-row" + (newVal ? " collected" : "");
        const cb = ftr.querySelector(".collect-btn");
        if (cb) cb.className = "collect-btn" + (newVal ? " active" : "");
      }
    });
  }

  checkAllBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    const newVal = !isAllChecked();

    state[p.id].collected = newVal;
    tr.className = newVal ? "collected" : "";
    collectBtn.className = "collect-btn" + (newVal ? " active" : "");

    if (p.gender === "none") {
      state[p.id].genderless = newVal;
      const gb = genderTd.querySelector(".gender-btn");
      if (gb) gb.className = "gender-btn" + (newVal ? " active" : "");
    } else {
      ["male", "female"].forEach((g) => {
        state[p.id][g] = newVal;
        const gb = genderTd.querySelector(`.gender-btn[data-gender="${g}"]`);
        if (gb) gb.className = "gender-btn" + (newVal ? " active" : "");
      });
    }

    state[p.id].lucky = newVal;
    luckyBtn.className = "toggle-btn lucky" + (newVal ? " active" : "");
    state[p.id].shiny = newVal;
    shinyBtn.className = "toggle-btn shiny" + (newVal ? " active" : "");

    setFormStates(newVal);
    syncCheckAllBtn();
    updateStats();
  });
  checkAllTd.appendChild(checkAllBtn);

  // ── Remove-all cell ───────────────────────────────────────────
  const removeAllTd = document.createElement("td");
  const removeAllBtn = document.createElement("button");
  removeAllBtn.className = "row-remove-all-btn";
  removeAllBtn.textContent = "✕ Clear";
  removeAllBtn.title = "Clear all boxes for this Pokémon";
  removeAllBtn.addEventListener("click", (e) => {
    e.stopPropagation();

    state[p.id].collected = false;
    tr.className = "";
    collectBtn.className = "collect-btn";

    if (p.gender === "none") {
      state[p.id].genderless = false;
      const gb = genderTd.querySelector(".gender-btn");
      if (gb) gb.className = "gender-btn";
    } else {
      ["male", "female"].forEach((g) => {
        state[p.id][g] = false;
        const gb = genderTd.querySelector(`.gender-btn[data-gender="${g}"]`);
        if (gb) gb.className = "gender-btn";
      });
    }

    state[p.id].lucky = false;
    luckyBtn.className = "toggle-btn lucky";
    state[p.id].shiny = false;
    shinyBtn.className = "toggle-btn shiny";

    setFormStates(false);
    syncCheckAllBtn();
    updateStats();
  });
  removeAllTd.appendChild(removeAllBtn);

  tr.appendChild(nameTd);
  tr.appendChild(genderTd);
  tr.appendChild(luckyTd);
  tr.appendChild(shinyTd);
  tr.appendChild(collectTd);
  tr.appendChild(checkAllTd);
  tr.appendChild(removeAllTd);

  // ── Auto-collect when any box is checked ──────────────────────
  function autoCollect() {
    if (!state[p.id].collected) {
      state[p.id].collected = true;
      tr.classList.add("collected");
      collectBtn.className = "collect-btn active";
      updateStats();
    }
    syncCheckAllBtn();
  }

  // ── Events ────────────────────────────────────────────────────
  if (hasForms) {
    nameTd.querySelector(".expand-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      state[p.id].expanded = !state[p.id].expanded;
      toggleFormRows(p);
      nameTd
        .querySelector(".expand-btn")
        .classList.toggle("open", state[p.id].expanded);
    });
  }

  genderTd.querySelectorAll(".gender-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const g = btn.dataset.gender;
      if (g === "none") return;
      state[p.id][g] = !state[p.id][g];
      btn.className = "gender-btn" + (state[p.id][g] ? " active" : "");
      if (state[p.id][g]) autoCollect();
      else syncCheckAllBtn();
      updateStats();
    });
  });

  luckyBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    state[p.id].lucky = !state[p.id].lucky;
    luckyBtn.className =
      "toggle-btn lucky" + (state[p.id].lucky ? " active" : "");
    if (state[p.id].lucky) autoCollect();
    else syncCheckAllBtn();
    updateStats();
  });

  shinyBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    state[p.id].shiny = !state[p.id].shiny;
    shinyBtn.className =
      "toggle-btn shiny" + (state[p.id].shiny ? " active" : "");
    if (state[p.id].shiny) autoCollect();
    else syncCheckAllBtn();
    updateStats();
  });

  if (!hasForms) {
    tr.addEventListener("click", () => {
      state[p.id].collected = !state[p.id].collected;
      tr.className = state[p.id].collected ? "collected" : "";
      collectBtn.className =
        "collect-btn" + (state[p.id].collected ? " active" : "");
      syncCheckAllBtn();
      updateStats();
    });
  }

  return tr;
}

// ── Form row toggle ───────────────────────────────────────────────
function toggleFormRows(p) {
  const tbody = document.getElementById("pokemon-tbody");
  const parentTr = tbody.querySelector(`tr[data-id="${p.id}"]`);

  if (state[p.id].expanded) {
    let ref = parentTr.nextSibling;
    p.forms.forEach((f) => {
      tbody.insertBefore(renderFormRow(f, p.id), ref);
    });
  } else {
    tbody
      .querySelectorAll(`tr[data-parent-id="${p.id}"]`)
      .forEach((r) => r.remove());
  }
}

// ── Stats + save ──────────────────────────────────────────────────
function updateStats() {
  let collected = 0,
    shiny = 0,
    lucky = 0,
    total = 0;

  POKEMON.forEach((p) => {
    if (p.forms) {
      p.forms.forEach((f) => {
        total++;
        if (state[f.formId].collected) collected++;
      });
      if (state[p.id].shiny) shiny++;
      if (state[p.id].lucky) lucky++;
    } else {
      total++;
      if (state[p.id].collected) collected++;
      if (state[p.id].shiny) shiny++;
      if (state[p.id].lucky) lucky++;
    }
  });

  document.getElementById("stat-collected").textContent = collected;
  document.getElementById("stat-shiny").textContent = shiny;
  document.getElementById("stat-lucky").textContent = lucky;
  document.getElementById("progress-text").textContent =
    `${collected} / ${total}`;
  document.getElementById("progress-fill").style.width =
    `${(collected / total) * 100}%`;

  saveCookie();
}

// ── Region separators ─────────────────────────────────────────────
const REGION_COLORS = {
  Kanto: "#e03131",
  Johto: "#f59f00",
  Hoenn: "#2f9e44",
  Sinnoh: "#1971c2",
  Unova: "#868e96",
  Kalos: "#ae3ec9",
  Alola: "#f76707",
  Galar: "#9c36b5",
  Paldea: "#c2255c",
};

function renderRegionSeparator(region, count) {
  const tr = document.createElement("tr");
  tr.className = "region-separator";
  tr.id = `region-${region.toLowerCase()}`;
  const td = document.createElement("td");
  td.colSpan = 7;
  const color = REGION_COLORS[region] || "#ffcb05";
  td.innerHTML = `
    <div class="region-banner" style="--region-color:${color}">
      <span class="region-banner-name">${region}</span>
      <div class="region-banner-line"></div>
      <span class="region-banner-count">${count} Pokémon</span>
    </div>`;
  tr.appendChild(td);
  return tr;
}

// ── TOC sidebar ───────────────────────────────────────────────────
function buildTOC(regions) {
  const sidebar = document.getElementById("toc-sidebar");
  sidebar.innerHTML = "";

  regions.forEach(({ name }) => {
    const color = REGION_COLORS[name] || "#ffcb05";
    const item = document.createElement("div");
    item.className = "toc-item";
    item.style.setProperty("--region-color", color);
    item.innerHTML = `<span class="toc-label">${name}</span><div class="toc-dot"></div>`;
    item.addEventListener("click", () => {
      document
        .getElementById(`region-${name.toLowerCase()}`)
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    sidebar.appendChild(item);
  });

  function updateActiveTOC() {
    const items = [...sidebar.querySelectorAll(".toc-item")];
    let activeIndex = -1;
    regions.forEach(({ name }, i) => {
      const el = document.getElementById(`region-${name.toLowerCase()}`);
      if (el && el.getBoundingClientRect().top <= 80) activeIndex = i;
    });
    items.forEach((item, i) =>
      item.classList.toggle("active", i === activeIndex),
    );
  }

  window.addEventListener("scroll", updateActiveTOC, { passive: true });
  updateActiveTOC();
}

// ── Render table for a given pokemon list ─────────────────────────
function renderTable() {
  const tbody = document.getElementById("pokemon-tbody");
  tbody.innerHTML = "";

  const regionOrder = [];
  const regionCounts = {};
  POKEMON.forEach((p) => {
    const r = p.region || "Unknown";
    if (!regionCounts[r]) {
      regionCounts[r] = 0;
      regionOrder.push(r);
    }
    regionCounts[r]++;
  });

  let currentRegion = null;
  POKEMON.forEach((p) => {
    const r = p.region || "Unknown";
    if (r !== currentRegion) {
      currentRegion = r;
      tbody.appendChild(renderRegionSeparator(r, regionCounts[r]));
    }
    initState(p);
    tbody.appendChild(renderRow(p));
  });

  buildTOC(regionOrder.map((name) => ({ name, count: regionCounts[name] })));
  updateStats();
}
