#!/usr/bin/env python3
"""
Pokémon GO Pokédex Crawler
===========================
Fetches all Pokémon available in Pokémon GO, including their types, gender,
forms, and sprite IDs, and writes the result to pokemon_go.json.

Data sources:
  - Bulbapedia  — "List of Pokémon by availability (GO)" for the live GO dex
  - PokeAPI     — canonical types, gender rates, English names
  - PokeAPI varieties + forms — dynamically discovered per species

Usage:
    pip install requests beautifulsoup4
    python crawl_pokemon_go.py

Output:
    pokemon-data.json  — array of Pokémon objects
"""

import json
import re
import sys
import time
from typing import Optional
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

POKEAPI_BASE  = "https://pokeapi.co/api/v2"
SEREBII_BASE  = "https://www.serebii.net/pokemongo"
SEREBII_INDEX = f"{SEREBII_BASE}/pokemon.shtml"
RATE_LIMIT_DELAY = 0.25   # seconds between PokeAPI requests — be polite
OUTPUT_FILE      = "data/pokemon-data.json"
MEGA_OUTPUT_FILE = "data/pokemon-data-mega.json"
GMAX_OUTPUT_FILE = "data/pokemon-data-gmax.json"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "pokemon-go-crawler/2.0 "
        "(https://github.com/example/pokemon-go-crawler)"
    )
})

# ---------------------------------------------------------------------------
# Generation → Region mapping (kept as fallback for PokeAPI-only lookups)
# ---------------------------------------------------------------------------
GENERATION_TO_REGION: dict[str, str] = {
    "generation-i":    "Kanto",
    "generation-ii":   "Johto",
    "generation-iii":  "Hoenn",
    "generation-iv":   "Sinnoh",
    "generation-v":    "Unova",
    "generation-vi":   "Kalos",
    "generation-vii":  "Alola",
    "generation-viii": "Galar",
    "generation-ix":   "Paldea",
}

# ---------------------------------------------------------------------------
# Step 1 — Scrape Serebii for available Pokémon IDs, grouped by region
# ---------------------------------------------------------------------------
# Strategy:
#   1. Fetch the index page (pokemon.shtml) to discover per-region page URLs
#      and their region names from the anchor table.
#   2. For each region page (gen1pokemon.shtml, gen2pokemon.shtml, …):
#        a. Parse every table row that has a dex-number cell (#NNNN).
#        b. Skip rows containing "Not Currently Available".
#        c. Extract the dex ID from the Pokémon detail link
#           (/pokemongo/pokemon/NNN.shtml) or from the #NNNN cell text.
#   3. Return a dict  { dex_id: region_name }  covering all available species.

# Regex: matches the per-region page slugs in any href form:
#   absolute:  /pokemongo/gen1pokemon.shtml
#   relative:  gen1pokemon.shtml
_REGION_SLUG_RE = re.compile(
    r"(?:^|/)(?P<slug>gen\d+pokemon|unknownpokemon|hisuipokemon)\.shtml$"
)
# Regex: extracts the 3-or-4-digit dex number from a Pokémon detail URL.
# Matches both absolute (/pokemongo/pokemon/001.shtml) and relative (pokemon/001.shtml).
_DETAIL_URL_RE = re.compile(r"(?:^|/)pokemon/(\d+)\.shtml")


def _fetch_html(url: str) -> BeautifulSoup:
    """Fetch a Serebii page and return a BeautifulSoup object (latin-1)."""
    resp = SESSION.get(url, timeout=20)
    resp.raise_for_status()
    # Serebii serves ISO-8859-1; decode explicitly to avoid mojibake
    return BeautifulSoup(resp.content.decode("latin-1", errors="replace"), "html.parser")


def _normalise_serebii_url(href: str, page_base: str) -> str:
    """
    Turn any Serebii href into an absolute URL.
    Handles three forms:
      /pokemongo/gen1pokemon.shtml  → absolute path
      gen1pokemon.shtml             → relative to page_base directory
      https://www.serebii.net/...   → already absolute
    """
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return "https://www.serebii.net" + href
    # Bare relative — resolve against the directory of the current page
    base_dir = page_base.rsplit("/", 1)[0]
    return base_dir + "/" + href


def _discover_region_pages(index_soup: BeautifulSoup) -> list[tuple[str, str]]:
    """
    Return [(region_name, full_url), ...] by scanning the anchor table on the
    index page.  Links appear as both absolute and relative hrefs:
      <a href="/pokemongo/gen1pokemon.shtml">Kanto Pokémon</a>
      <a href="gen1pokemon.shtml">Kanto Pokémon</a>
    """
    pages = []
    seen  = set()
    for a in index_soup.find_all("a", href=True):
        href = a["href"]
        m = _REGION_SLUG_RE.search(href)
        if not m:
            continue
        slug     = m.group("slug")
        full_url = _normalise_serebii_url(href, SEREBII_INDEX)
        if full_url in seen:
            continue
        seen.add(full_url)

        # Extract a clean region name from the link text, e.g. "Kanto Pokémon" → "Kanto"
        raw    = a.get_text(separator=" ", strip=True)
        region = re.sub(r"\s*Pok[é\?]mon.*", "", raw, flags=re.IGNORECASE).strip()
        # Fall back to deriving it from the slug if text was garbled/empty
        if not region:
            region = slug.replace("gen", "Gen ").replace("pokemon", "").strip()
        pages.append((region, full_url))

    return pages


# Type alias for the per-species availability record returned by the scraper.
# "available_forms" is either:
#   None        — no form rows appeared on Serebii; treat all PokeAPI forms as available
#   set[str]    — the lowercased display-name suffixes of form rows that were
#                 available on Serebii, e.g. {"low key form", "noice face"}
#                 Forms not in this set should be excluded.
SpeciesInfo = dict  # {"region": str, "available_forms": set[str] | None}


def _is_unavailable(row_text: str) -> bool:
    """Return True if a Serebii table row is marked as not in GO."""
    # Serebii uses both "Not Currently Available" and (rarely) the lowercase
    # variant "Not currently available" in form rows.
    return "not currently available" in row_text.lower()


def _parse_region_page(soup: BeautifulSoup, region: str) -> dict[int, SpeciesInfo]:
    """
    Parse one Serebii gen-page and return a dict:
      { dex_id: {"region": str, "available_forms": set[str] | None} }

    The base species is included only when its first row does NOT carry the
    unavailability notice.  For form rows (rows[1:]):
      - If there are no form rows, available_forms is None (all PokeAPI forms
        should be treated as available).
      - Otherwise available_forms is the set of lowercased form-name suffixes
        whose row was available, e.g. {"low key form", "hangry mode"}.
    """
    # dex_id -> list of (form_suffix: str, is_unavailable: bool)
    # form_suffix is the parenthesised label, e.g. "Low Key Form"; "" for the base row
    rows_by_id: dict[int, list[tuple[str, bool]]] = {}

    for tr in soup.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 2:
            continue

        # Extract dex ID from Pokémon detail link, or fall back to #NNNN cell
        dex_id = None
        for a in tr.find_all("a", href=True):
            m = _DETAIL_URL_RE.search(a["href"])
            if m:
                dex_id = int(m.group(1))
                break
        if dex_id is None:
            first_cell = cells[0].get_text(strip=True)
            m = re.match(r"#(\d+)", first_cell)
            if m:
                dex_id = int(m.group(1))
        if dex_id is None:
            continue

        # Full row text for availability check and suffix extraction
        name_cell_text = ""
        for a in tr.find_all("a", href=True):
            if _DETAIL_URL_RE.search(a["href"]):
                name_cell_text = tr.get_text(separator=" ", strip=True)
                break

        # Pull out any form suffix in parentheses, e.g. "(Low Key Form)" -> "Low Key Form"
        form_suffix_match = re.search(r"\(([^)]+)\)", name_cell_text)
        form_suffix = form_suffix_match.group(1).strip() if form_suffix_match else ""

        unavailable = _is_unavailable(name_cell_text)
        rows_by_id.setdefault(dex_id, []).append((form_suffix, unavailable))

    # Convert to SpeciesInfo dicts
    result: dict[int, SpeciesInfo] = {}
    for dex_id, rows in rows_by_id.items():
        # Skip entire species if the base row is unavailable
        _, base_unavailable = rows[0]
        if base_unavailable:
            continue

        form_rows = rows[1:]
        if not form_rows:
            # No form rows on Serebii — all PokeAPI forms are available
            available_forms = None
        else:
            # Collect only the suffixes of available form rows
            available_forms = {
                suffix.lower()
                for suffix, unavail in form_rows
                if not unavail and suffix
            }

        result[dex_id] = {"region": region, "available_forms": available_forms}

    return result


def crawl_serebii_go_ids() -> dict[int, SpeciesInfo]:
    """
    Scrape all Serebii GO region pages and return a dict:
      { national_dex_id: {"region": str, "available_forms": set[str] | None} }
    for every species whose base form is available in GO.
    """
    print("🌐 Fetching Serebii GO index page …")
    index_soup   = _fetch_html(SEREBII_INDEX)
    region_pages = _discover_region_pages(index_soup)

    if not region_pages:
        raise RuntimeError(
            "Could not find any region page links on the Serebii index page. "
            "The page structure may have changed."
        )

    print(f"   Discovered {len(region_pages)} region page(s):")
    for region, url in region_pages:
        print(f"      {region:20s} → {url}")

    id_to_info: dict[int, SpeciesInfo] = {}

    for region, url in region_pages:
        print(f"\n🔎 Scraping {region} ({url}) …", end=" ")
        try:
            soup   = _fetch_html(url)
            result = _parse_region_page(soup, region)
            print(f"{len(result)} available species found.")
            for dex_id, info in result.items():
                id_to_info.setdefault(dex_id, info)
        except Exception as exc:
            print(f"⚠  Failed: {exc}", file=sys.stderr)
        time.sleep(0.5)

    total_form_filters = sum(0 if v["available_forms"] is None else len(v["available_forms"]) for v in id_to_info.values())
    print(
        f"\n✅ Serebii: {len(id_to_info)} available species across all regions "
        f"({total_form_filters} species with explicit form availability).\n"
    )
    return id_to_info


# ---------------------------------------------------------------------------
# Step 2 — Dynamic form discovery via PokeAPI
# ---------------------------------------------------------------------------
# Two complementary paths are used to find all non-default forms:
#
#   A) VARIETIES  – pokemon-species/{id}.varieties[]
#      Each non-default variety is a completely separate /pokemon/{slug}
#      with its own types. The display name is fetched from the first
#      pokemon-form record attached to that variety.
#      Example: Rotom -> rotom-heat, Wormadam -> wormadam-sandy
#
#   B) FORMS  – pokemon/{id}.forms[]
#      When a single pokemon entry has several form slugs, those extra forms
#      share the same types as the parent but may have a distinct display name
#      stored in the pokemon-form record.
#      Example: Unown-A...Unown-Z, Vivillon patterns, Basculin stripes
#
# Sprite IDs are taken from the /pokemon/{slug} numeric id field.
#
# Mega/Primal separation
# Mega Evolutions and Primal Reversions are identified via is_mega: true on the
# /pokemon-form record, or by the slug ending with -primal. They are collected
# separately and written to MEGA_OUTPUT_FILE instead of the main output.
#
# Serebii availability matching
# Serebii scrapes a suffix like "Low Key Form" or "Noice Face".
# PokeAPI returns names like "Low Key Forme" or "Noice Face Form".
# We normalise both sides with _norm_form_name() and check whether either
# string contains the other as a substring. When a Serebii suffix fails to
# match any PokeAPI form name, a warning is printed.

import unicodedata as _ud


def _norm_form_name(s: str) -> str:
    """Normalise a form display name for fuzzy matching.

    Strips trailing 'form'/'forme' so that Serebii's 'Alola Form' and
    PokeAPI's 'Alolan Form' both reduce to 'alola'/'alolan', allowing the
    substring check to match them correctly.
    """
    # Decompose accented chars then strip combining marks
    s = _ud.normalize("NFD", s)
    s = "".join(c for c in s if _ud.category(c) != "Mn")
    s = s.lower()
    # Remove parentheses and common punctuation
    s = re.sub(r"[()'\u2019\-]", " ", s)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    # Strip trailing "form"/"forme"/"forms" so regional suffixes align:
    # "Alolan Form" -> "alolan",  "alola form" -> "alola"
    s = re.sub(r"\s+form(?:e)?s?$", "", s).strip()
    return s

def _forms_match(pokeapi_name: str, serebii_suffix: str) -> bool:
    """True if the normalised names are compatible via substring containment."""
    a = _norm_form_name(pokeapi_name)
    b = _norm_form_name(serebii_suffix)
    return a == b or a in b or b in a


def _form_display_name(form_data: dict) -> str:
    """Extract the best English display name from a /pokemon-form response.

    Returns the raw name as-is; stripping of trailing " Form" is deferred to
    output time so matching against Serebii suffixes still works.
    """
    for key in ("form_names", "names"):
        for entry in form_data.get(key, []):
            if entry.get("language", {}).get("name") == "en" and entry.get("name"):
                return entry["name"]
    return form_data.get("form_name") or form_data.get("name", "")


def _strip_form_suffix(name: str) -> str:
    """Strip a trailing ' Form' word from a display name at output time.

    Examples: 'Heat Form' -> 'Heat', 'Low Key Form' -> 'Low Key'.
    'Forme', 'Mode', 'Face' etc. are intentionally left untouched.
    """
    return re.sub(r"\s+[Ff]orm$", "", name).strip()


def _is_mega_or_primal(slug: str, form_data: dict) -> bool:
    """Return True if this form is a Mega Evolution or Primal Reversion."""
    return form_data.get("is_mega", False) or slug.endswith("-primal")


def _is_gmax(slug: str) -> bool:
    """Return True if this form is a Gigantamax form."""
    return slug.endswith("-gmax")


def _fetch_variety_form(slug: str, base_types: list) -> Optional[tuple]:
    """
    Fetch a non-default variety.
    Returns (form_dict, is_mega_or_primal) or None on failure.
    """
    poke = _get(f"{POKEAPI_BASE}/pokemon/{slug}")
    if not poke:
        return None
    time.sleep(RATE_LIMIT_DELAY)

    sprite_id = poke["id"]
    types     = _types(poke["types"]) or base_types

    form_name  = slug
    is_mega    = False
    for form_ref in poke.get("forms", []):
        form_data = _get(form_ref["url"])
        if form_data:
            time.sleep(RATE_LIMIT_DELAY)
            name = _form_display_name(form_data)
            if name:
                form_name = name
            is_mega = _is_mega_or_primal(slug, form_data)
            break

    return (
        {"formId": slug, "name": form_name, "types": types, "spriteId": sprite_id},
        is_mega,
        _is_gmax(slug),
    )


def _fetch_extra_forms(pokemon_data: dict, base_types: list) -> list:
    """
    Walk forms[] on a /pokemon entry, skipping the default (index 0).
    Returns list of (form_dict, is_mega_or_primal, is_gmax) tuples.
    """
    results = []
    for form_ref in pokemon_data.get("forms", [])[1:]:
        slug      = form_ref["name"]
        form_data = _get(form_ref["url"])
        if not form_data:
            continue
        time.sleep(RATE_LIMIT_DELAY)
        name      = _form_display_name(form_data)
        sprite_id = pokemon_data["id"]
        is_mega   = _is_mega_or_primal(slug, form_data)
        results.append((
            {"formId": slug, "name": name or slug,
             "types": base_types, "spriteId": sprite_id},
            is_mega,
            _is_gmax(slug),
        ))
    return results


def _collect_all_forms(
    species_data: dict,
    base_pokemon: dict,
    base_types: list,
    available_forms: "set | None",
    dex_id: int,
) -> tuple:
    """
    Collect every non-default form/variety, filter by Serebii availability, and
    split into regular vs mega/primal.

    available_forms:
      None     — Serebii listed no form rows; include all PokeAPI forms.
      set[str] — lowercased suffixes of available form rows scraped from
                 Serebii; only forms matching one of these suffixes are kept.
                 Warn to stderr for any suffix that matches no PokeAPI form.

    Returns (regular_forms, mega_forms, gmax_forms) using schema {formId, name, types, spriteId}.
    """
    all_forms: list  = []   # list of (form_dict, is_mega, is_gmax)
    seen_slugs: set  = set()

    # Path A: varieties
    for variety in species_data.get("varieties", []):
        if variety.get("is_default"):
            continue
        slug = variety["pokemon"]["name"]
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        result = _fetch_variety_form(slug, base_types)
        if result:
            all_forms.append(result)

    # Path B: extra forms on the base pokemon entry
    for result in _fetch_extra_forms(base_pokemon, base_types):
        if result[0]["formId"] in seen_slugs:
            continue
        seen_slugs.add(result[0]["formId"])
        all_forms.append(result)

    if not all_forms:
        return [], [], []

    # Filter by Serebii available_forms (skip when None — all forms included)
    if available_forms is not None:
        unmatched_serebii = set(available_forms)
        filtered = []
        for form_dict, is_mega, is_gmax in all_forms:
            matched_suffix = None
            for suffix in available_forms:
                if _forms_match(form_dict["name"], suffix):
                    matched_suffix = suffix
                    break
            if matched_suffix:
                unmatched_serebii.discard(matched_suffix)
                filtered.append((form_dict, is_mega, is_gmax))
            # else: not in available_forms — exclude this form

        for suffix in unmatched_serebii:
            form_names = [fd["name"] for fd, _, __ in all_forms]
            normed_suffix = _norm_form_name(suffix)
            normed_forms  = [_norm_form_name(n) for n in form_names]
            print(
                f"\n  \u26a0  #{dex_id}: Serebii available-form suffix {suffix!r} "
                f"(normalised: {normed_suffix!r}) "
                f"did not match any PokeAPI form. "
                f"Known form names: {form_names} "
                f"(normalised: {normed_forms})",
                file=sys.stderr,
            )
        all_forms = filtered

    # Split into regular, mega/primal, and gigantamax.
    # Strip trailing " Form" from display names at output time.
    def _finalise(fd: dict) -> dict:
        return {**fd, "name": _strip_form_suffix(fd["name"])}

    regular_forms = [_finalise(fd) for fd, is_mega, is_gmax in all_forms if not is_mega and not is_gmax]
    mega_forms    = [_finalise(fd) for fd, is_mega, is_gmax in all_forms if is_mega]
    gmax_forms    = [_finalise(fd) for fd, is_mega, is_gmax in all_forms if is_gmax]
    return regular_forms, mega_forms, gmax_forms

# ---------------------------------------------------------------------------
# Shared HTTP helper
# ---------------------------------------------------------------------------

def _get(url: str) -> Optional[dict]:
    """GET with 3 retries; returns None on 404 or persistent failure."""
    for attempt in range(3):
        try:
            r = SESSION.get(url, timeout=15)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            if attempt == 2:
                print(f"\n  ⚠  Failed {url}: {e}", file=sys.stderr)
                return None
            time.sleep(1 + attempt)
    return None

# ---------------------------------------------------------------------------
# Step 3 — Build one Pokémon entry from PokeAPI
# ---------------------------------------------------------------------------

def _gender(gender_rate: int) -> str:
    if gender_rate == -1: return "none"
    if gender_rate == 0:  return "male"
    if gender_rate == 8:  return "female"
    return "male-female"


def _types(type_slots: list) -> list[str]:
    return [s["type"]["name"] for s in type_slots]


def fetch_pokemon(dex_id: int, available_forms: "set | None") -> Optional[tuple]:
    """
    Return (entry, mega_forms, gmax_forms) for one Pokémon, or None on failure.

    entry      — the main Pokémon dict (regular forms only, no megas/gmax)
    mega_forms — list of Mega/Primal form dicts; each carries a "baseId" field
    gmax_forms — list of Gigantamax form dicts; each carries a "baseId" field

    available_forms is either None (all forms available) or a set of lowercased
    form-name suffixes scraped from Serebii that are confirmed available.
    Forms and varieties are discovered dynamically from PokeAPI.
    """
    species = _get(f"{POKEAPI_BASE}/pokemon-species/{dex_id}")
    if not species:
        return None
    pokemon = _get(f"{POKEAPI_BASE}/pokemon/{dex_id}")
    if not pokemon:
        return None

    name = next(
        (n["name"] for n in species["names"] if n["language"]["name"] == "en"),
        species["name"].capitalize(),
    )
    types      = _types(pokemon["types"])
    gender     = _gender(species["gender_rate"])
    generation = species.get("generation", {}).get("name", "")
    region     = GENERATION_TO_REGION.get(generation, "Unknown")

    entry: dict = {
        "id":       dex_id,
        "name":     name,
        "types":    types,
        "gender":   gender,
        "spriteId": dex_id,
        "region":   region,
    }

    regular_forms, mega_forms, gmax_forms = _collect_all_forms(
        species, pokemon, types, available_forms, dex_id
    )
    if regular_forms:
        entry["forms"] = regular_forms

    # Tag each mega/primal and gmax with the base species id for cross-referencing
    for mf in mega_forms:
        mf["baseId"] = dex_id
    for gf in gmax_forms:
        gf["baseId"] = dex_id

    return entry, mega_forms, gmax_forms

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # --- Phase 1: discover available species + form availability from Serebii ---
    id_to_info = crawl_serebii_go_ids()
    go_ids     = sorted(id_to_info)

    # --- Phase 2: fetch full data from PokeAPI (region derived from generation) ---
    print(f"🔍 Fetching data for {len(go_ids)} Pokémon from PokeAPI …")
    results:      list[dict] = []
    mega_results: list[dict] = []
    gmax_results: list[dict] = []
    errors:       list[int]  = []

    for i, dex_id in enumerate(go_ids, 1):
        available_forms = id_to_info[dex_id]["available_forms"]
        print(f"   [{i:>3}/{len(go_ids)}] #{dex_id:<4}", end="\r")
        fetched = fetch_pokemon(dex_id, available_forms)
        if fetched:
            entry, mega_forms, gmax_forms = fetched
            results.append(entry)
            mega_results.extend(mega_forms)
            gmax_results.extend(gmax_forms)
        else:
            errors.append(dex_id)
        time.sleep(RATE_LIMIT_DELAY)

    print()
    if errors:
        print(
            f"   ⚠  {len(errors)} failed IDs: "
            + str(errors[:15])
            + ("…" if len(errors) > 15 else ""),
            file=sys.stderr,
        )

    # --- Phase 3: write output ---
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Done — {len(results)} Pokémon written to {OUTPUT_FILE}")

    with open(MEGA_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(mega_results, f, indent=2, ensure_ascii=False)
    print(f"✅ Done — {len(mega_results)} Mega/Primal forms written to {MEGA_OUTPUT_FILE}")

    with open(GMAX_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(gmax_results, f, indent=2, ensure_ascii=False)
    print(f"✅ Done — {len(gmax_results)} Gigantamax forms written to {GMAX_OUTPUT_FILE}")


if __name__ == "__main__":
    main()
