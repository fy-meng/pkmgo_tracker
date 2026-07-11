// ── Global state ──────────────────────────────────────────────────
// POKEMON      : active tab's pokemon array
// TAB_DATA     : all loaded datasets keyed by tab id
// activeTab    : currently shown tab ('pokemon' | 'mega' | 'gmax')
// state        : keyed by pokemon id (number) or formId (string)
// _savedData   : raw saved data for the active user, loaded once on init

let POKEMON = [];
const TAB_DATA = {}; // { pokemon: [...], mega: [...], gmax: [...] }
let activeTab = "pokemon";
const state = {};
let _savedData = {};

// ── Active-user storage wrappers ──────────────────────────────────
function saveData() {
  const userId = loadUserId();
  if (userId) saveDataForUser(userId, state);
}

function loadData() {
  const userId = loadUserId();
  if (!userId) return {};
  migrateLegacyCookie(userId);
  return loadDataForUser(userId);
}

// ── Storage key for a top-level entry ─────────────────────────────
// Mega/G-Max entries carry no formId and reuse the base Pokémon's dex number,
// so the raw id collides three ways: across tabs (Venusaur / Mega Venusaur /
// Gigantamax Venusaur all → 3) and within the mega tab itself (Charizard X and
// Y are both → 6). Names are unique per tab, so those tabs key off tab + name.
// The pokemon tab keeps the bare id, which is what existing saves already use.
function stateKey(p) {
  if (p.formId) return p.formId;
  if (activeTab === "pokemon") return String(p.id);
  return `${activeTab}:${p.name.toLowerCase().replace(/\s+/g, "-")}`;
}

// `state` carries keys for every tab rendered so far, and saveData() merges
// all of them into storage. Switching trainers must drop them, or the previous
// trainer's un-rendered tabs get written into the new trainer's collection.
function resetState() {
  Object.keys(state).forEach((k) => delete state[k]);
}

// ── Per-pokemon state initialisation ─────────────────────────────
// Works for both standard Pokémon (keyed by numeric id) and flat
// Mega/G-Max entries (keyed by formId string).
function initState(p) {
  const key = stateKey(p);
  const base = _savedData[key] || {};
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
      const fb = _savedData[f.formId] || {};
      state[f.formId] = { collected: !!fb.c };
    });
  }
}
