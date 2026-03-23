// ── Entry point ───────────────────────────────────────────────────
// Load order: storage.js → state.js → table.js → sidebar.js → lucky-search.js → main.js

async function loadTabData() {
  const sources = {
    pokemon: "data/pokemon-data.json",
    mega: "data/pokemon-data-mega.json",
    gmax: "data/pokemon-data-gmax.json",
  };

  const results = await Promise.allSettled(
    Object.entries(sources).map(([tab, url]) =>
      fetch(url)
        .then((r) => r.json())
        .then((data) => ({ tab, data })),
    ),
  );

  results.forEach((r) => {
    if (r.status === "fulfilled") {
      TAB_DATA[r.value.tab] = r.value.data;
    }
  });

  if (!TAB_DATA.pokemon) throw new Error("Could not load pokemon-data.json.");
}

function switchTab(tab) {
  activeTab = tab;
  POKEMON = TAB_DATA[tab] || [];

  // Update tab button styles
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tab);
  });

  // Re-init state from cookie and re-render
  _cookieData = loadCookie();
  renderTable();
}

function initTabs() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });
}

async function init() {
  try {
    await loadTabData();
  } catch (err) {
    document.querySelector(".table-wrapper").innerHTML =
      `<p style="padding:24px;color:#f783ac;font-family:monospace">⚠️ ${err.message}</p>`;
    return;
  }

  // Ensure user has an ID — show prompt on first visit
  let userId = loadUserId();
  if (!userId) {
    userId = await showUserIdPrompt();
  } else {
    setTrainerDisplay(userId);
  }

  // Wire up UI components
  initSidebar();
  initLuckySearch();
  initTabs();

  // Load this user's saved collection and render the default tab
  _cookieData = loadCookie();
  POKEMON = TAB_DATA.pokemon;
  activeTab = "pokemon";
  renderTable();
}

init();
