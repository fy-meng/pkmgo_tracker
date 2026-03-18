// ── Entry point ───────────────────────────────────────────────────
// Load order (via index.html <script> tags):
//   storage.js → state.js → table.js → sidebar.js → lucky-search.js → main.js

async function init() {
  // Load Pokémon data
  try {
    const res = await fetch("data/pokemon-data.json");
    POKEMON = await res.json();
  } catch {
    document.querySelector(".table-wrapper").innerHTML =
      '<p style="padding:24px;color:#f783ac;font-family:monospace">⚠️ Could not load pokemon-data.json. Make sure it\'s in the same folder as index.html.</p>';
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

  // Load this user's saved collection and render the table
  _cookieData = loadCookie();
  renderTable();
}

init();
