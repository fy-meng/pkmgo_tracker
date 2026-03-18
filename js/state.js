// ── Global state ──────────────────────────────────────────────────
// POKEMON   : array loaded from pokemon-data.json
// state     : keyed by pokemon id (number) or formId (string)
// _cookieData: raw saved data for the active user, loaded once on init

let POKEMON = [];
const state = {};
let _cookieData = {};

// ── Active-user cookie wrappers ───────────────────────────────────
// These delegate to storage.js, passing the live state object.

function saveCookie() {
  const userId = loadUserId();
  if (userId) saveCookieForUser(userId, state);
}

function loadCookie() {
  const userId = loadUserId();
  if (!userId) return {};
  migrateLegacyCookie(userId);
  return loadCookieForUser(userId);
}

// ── Per-pokemon state initialisation ─────────────────────────────
function initState(p) {
  const base = _cookieData[p.id] || {};
  state[p.id] = {
    collected: !!base.c,
    male: !!base.m,
    female: !!base.f,
    genderless: !!base.g,
    lucky: !!base.l,
    shiny: !!base.s,
    expanded: false,
  };
  if (p.forms) {
    p.forms.forEach((f) => {
      const fb = _cookieData[f.formId] || {};
      state[f.formId] = { collected: !!fb.c };
    });
  }
}
