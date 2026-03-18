// ── Cookie primitives ─────────────────────────────────────────────
function setCookie(name, value, days = 365) {
  const exp = new Date(Date.now() + days * 864e5).toUTCString();
  document.cookie = `${name}=${encodeURIComponent(value)}; expires=${exp}; path=/; SameSite=Lax`;
}

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
    return JSON.parse(getCookie("pokedex_users") || "[]");
  } catch {
    return [];
  }
}

function saveAllUsers(users) {
  setCookie("pokedex_users", JSON.stringify([...new Set(users)]));
}

function saveUserId(id) {
  setCookie("pokedex_user", id);
  const users = loadAllUsers();
  if (!users.includes(id)) {
    users.push(id);
    saveAllUsers(users);
  }
}

function loadUserId() {
  return getCookie("pokedex_user") || null;
}

// ── Per-user collection data ──────────────────────────────────────
function saveCookieForUser(userId, state) {
  const slim = {};
  Object.entries(state).forEach(([key, s]) => {
    const entry = {};
    if (s.collected) entry.c = 1;
    if (s.male) entry.m = 1;
    if (s.female) entry.f = 1;
    if (s.genderless) entry.g = 1;
    if (s.lucky) entry.l = 1;
    if (s.shiny) entry.s = 1;
    if (Object.keys(entry).length) slim[key] = entry;
  });
  setCookie(`pokedex_data_${userId}`, JSON.stringify(slim));
}

function loadCookieForUser(userId) {
  try {
    return JSON.parse(getCookie(`pokedex_data_${userId}`) || "{}");
  } catch {
    return {};
  }
}

function deleteUser(userId) {
  deleteCookie(`pokedex_data_${userId}`);
  const users = loadAllUsers().filter((u) => u !== userId);
  saveAllUsers(users);
  if (loadUserId() === userId) deleteCookie("pokedex_user");
}

function renameUser(oldId, newId) {
  if (oldId === newId) return;
  const data = getCookie(`pokedex_data_${oldId}`);
  if (data) setCookie(`pokedex_data_${newId}`, data);
  deleteCookie(`pokedex_data_${oldId}`);
  const users = loadAllUsers().map((u) => (u === oldId ? newId : u));
  saveAllUsers(users);
  if (loadUserId() === oldId) setCookie("pokedex_user", newId);
}

// ── Legacy migration ──────────────────────────────────────────────
function migrateLegacyCookie(userId) {
  const legacy = getCookie("pokedex");
  if (legacy) {
    setCookie(`pokedex_data_${userId}`, legacy);
    deleteCookie("pokedex");
  }
}

// ── Export / Import ───────────────────────────────────────────────
function exportUserData(uid) {
  const raw = getCookie(`pokedex_data_${uid}`);
  const payload = {
    version: 1,
    user: uid,
    data: raw ? JSON.parse(raw) : {},
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
  setCookie(`pokedex_data_${uid}`, JSON.stringify(data));
}
