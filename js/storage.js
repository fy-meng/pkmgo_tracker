// ── Storage primitives ────────────────────────────────────────────
// Data lives in localStorage. Cookies capped a full collection at ~44
// Pokémon: the 4KB-per-cookie limit, hit early because encodeURIComponent
// inflates every {, } and " to three bytes. Over the cap the browser
// silently drops the write, so progress just stopped saving.

function readStore(name) {
  try {
    return localStorage.getItem(name);
  } catch {
    return null;
  }
}

function writeStore(name, value) {
  try {
    localStorage.setItem(name, value);
    return true;
  } catch {
    return false;
  }
}

function removeStore(name) {
  try {
    localStorage.removeItem(name);
  } catch {
    /* storage unavailable */
  }
}

// ── Cookie primitives (legacy reads + migration only) ─────────────
function getCookie(name) {
  const match = document.cookie
    .split("; ")
    .find((r) => r.startsWith(name + "="));
  if (!match) return null;
  try {
    return decodeURIComponent(match.split("=").slice(1).join("="));
  } catch {
    return null;
  }
}

function deleteCookie(name) {
  document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/; SameSite=Lax`;
}

// ── User registry ─────────────────────────────────────────────────
// pokedex_user        active user ID
// pokedex_users       JSON array of all known user IDs
// pokedex_data_<id>   per-user collection data

function loadAllUsers() {
  try {
    return JSON.parse(readStore("pokedex_users") || "[]");
  } catch {
    return [];
  }
}

function saveAllUsers(users) {
  writeStore("pokedex_users", JSON.stringify([...new Set(users)]));
}

function saveUserId(id) {
  writeStore("pokedex_user", id);
  const users = loadAllUsers();
  if (!users.includes(id)) {
    users.push(id);
    saveAllUsers(users);
  }
}

function loadUserId() {
  return readStore("pokedex_user") || null;
}

// ── Per-user collection data ──────────────────────────────────────
// `state` only holds the tab that is currently rendered, so a save merges
// onto what is already stored instead of replacing it — otherwise saving
// from the Pokémon tab would wipe Mega/G-Max progress. Keys that are live
// in `state` but now hold nothing are dropped, so unchecking still sticks.
function saveDataForUser(userId, state) {
  const stored = loadDataForUser(userId);
  Object.entries(state).forEach(([key, s]) => {
    const entry = {};
    if (s.collected) entry.c = 1;
    if (s.male) entry.m = 1;
    if (s.female) entry.f = 1;
    if (s.genderless) entry.g = 1;
    if (s.lucky) entry.l = 1;
    if (s.shiny) entry.s = 1;
    if (Object.keys(entry).length) stored[key] = entry;
    else delete stored[key];
  });
  writeStore(`pokedex_data_${userId}`, JSON.stringify(stored));
}

function loadDataForUser(userId) {
  try {
    return JSON.parse(readStore(`pokedex_data_${userId}`) || "{}");
  } catch {
    return {};
  }
}

function deleteUser(userId) {
  removeStore(`pokedex_data_${userId}`);
  const users = loadAllUsers().filter((u) => u !== userId);
  saveAllUsers(users);
  if (loadUserId() === userId) removeStore("pokedex_user");
}

function renameUser(oldId, newId) {
  if (oldId === newId) return;
  const data = readStore(`pokedex_data_${oldId}`);
  if (data) writeStore(`pokedex_data_${newId}`, data);
  removeStore(`pokedex_data_${oldId}`);
  const users = loadAllUsers().map((u) => (u === oldId ? newId : u));
  saveAllUsers(users);
  if (loadUserId() === oldId) writeStore("pokedex_user", newId);
}

// ── Migration ─────────────────────────────────────────────────────
// Pulls anything left in cookies by an older build into localStorage.
// Cookies are only cleared once their contents are safely stored.
function migrateCookieStorage() {
  ["pokedex_user", "pokedex_users"].forEach((name) => {
    const legacy = getCookie(name);
    if (legacy && !readStore(name) && writeStore(name, legacy)) {
      deleteCookie(name);
    }
  });

  loadAllUsers().forEach((uid) => {
    const key = `pokedex_data_${uid}`;
    const legacy = getCookie(key);
    if (legacy && !readStore(key) && writeStore(key, legacy)) {
      deleteCookie(key);
    }
  });
}

function migrateLegacyCookie(userId) {
  const legacy = getCookie("pokedex");
  if (legacy) {
    const key = `pokedex_data_${userId}`;
    if (!readStore(key) && writeStore(key, legacy)) deleteCookie("pokedex");
  }
}

migrateCookieStorage();

// ── Export / Import ───────────────────────────────────────────────
function exportUserData(uid) {
  const payload = {
    version: 1,
    user: uid,
    data: loadDataForUser(uid),
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `pokedex-${uid}-${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function parseImportFile(file, onParsed) {
  const reader = new FileReader();
  reader.onload = (e) => {
    try {
      const payload = JSON.parse(e.target.result);
      if (!payload.user || !payload.data)
        throw new Error("Invalid file format — missing user or data fields.");
      const exists = loadAllUsers().includes(payload.user);
      onParsed(null, { uid: payload.user, data: payload.data, exists });
    } catch (err) {
      onParsed(err.message || "Failed to parse file.");
    }
  };
  reader.readAsText(file);
}

function applyImport(uid, data) {
  const users = loadAllUsers();
  if (!users.includes(uid)) {
    users.push(uid);
    saveAllUsers(users);
  }
  writeStore(`pokedex_data_${uid}`, JSON.stringify(data));
}
