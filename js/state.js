// ── Global state ──────────────────────────────────────────────────
// POKEMON      : active tab's pokemon array
// TAB_DATA     : all loaded datasets keyed by tab id
// activeTab    : currently shown tab ('pokemon' | 'mega' | 'gmax')
// state        : keyed by pokemon id (number) or formId (string)
// _cookieData  : raw saved data for the active user, loaded once on init

let POKEMON = [];
const TAB_DATA = {}; // { pokemon: [...], mega: [...], gmax: [...] }
let activeTab = "pokemon";
const state = {};
let _cookieData = {};

// ── Active-user cookie wrappers ───────────────────────────────────
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
// Works for both standard Pokémon (keyed by numeric id) and flat
// Mega/G-Max entries (keyed by formId string).
function initState(p) {
  const key = p.formId || p.id;
  const base = _cookieData[key] || {};
  state[key] = {
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
