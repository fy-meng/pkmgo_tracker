#!/usr/bin/env python3
"""
Pokémon GO Pokédex Crawler
===========================
Fetches all Pokémon available in Pokémon GO, including their types, gender,
forms, and sprite IDs, and writes the result to pokemon_go.json.

Data sources:
  - Serebii     — availability and form lists per region
  - PokeAPI     — canonical types, gender rates, English names

Usage:
    pip install requests beautifulsoup4
    python crawl_pokemon_go.py

Output:
    data/pokemon-data.json
"""

import json
import os
import re
import sys
import time
from typing import Optional

import unicodedata as _ud
from bs4 import BeautifulSoup

from utils import (
    POKEAPI_BASE,
    RATE_LIMIT_DELAY,
    SESSION,
    GENERATION_TO_REGION,
    fetch_html,
    get_english_name,
    get_gender,
    get_json,
    get_region,
    get_types,
    is_unavailable,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SEREBII_BASE  = "https://www.serebii.net/pokemongo"
SEREBII_INDEX = f"{SEREBII_BASE}/pokemon.shtml"
OUTPUT_FILE   = "data/pokemon-data.json"

FORM_BLACKLIST: list[str] = [
    "rock star",
    "pop star",
    "libre",
    "partner",
    "spiky-eared",
    "zen",
    "male",
    "female",
    "shield forme",
    "blade forme",
    "size",
    "active mode",
    "neutral mode",
    "own tempo",
    "full belly",
    "hangry",
]

# ---------------------------------------------------------------------------
# Step 1 — Scrape Serebii for available Pokémon IDs, grouped by region
# ---------------------------------------------------------------------------

_REGION_SLUG_RE = re.compile(
    r"(?:^|/)(?P<slug>gen\d+pokemon|unknownpokemon|hisuipokemon)\.shtml$"
)
_DETAIL_URL_RE = re.compile(r"(?:^|/)pokemon/(\d+)\.shtml")


def _normalise_serebii_url(href: str, page_base: str) -> str:
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return "https://www.serebii.net" + href
    base_dir = page_base.rsplit("/", 1)[0]
    return base_dir + "/" + href


def _discover_region_pages(index_soup: BeautifulSoup) -> list[tuple[str, str]]:
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
        raw    = a.get_text(separator=" ", strip=True)
        region = re.sub(r"\s*Pok[é\?]mon.*", "", raw, flags=re.IGNORECASE).strip()
        if not region:
            region = slug.replace("gen", "Gen ").replace("pokemon", "").strip()
        pages.append((region, full_url))
    return pages


SpeciesInfo = dict  # {"region": str, "available_forms": set[str] | None}


def _parse_region_page(soup: BeautifulSoup, region: str) -> dict[int, SpeciesInfo]:
    rows_by_id: dict[int, list[tuple[str, bool]]] = {}

    for tr in soup.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 2:
            continue

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

        name_cell_text = ""
        for a in tr.find_all("a", href=True):
            if _DETAIL_URL_RE.search(a["href"]):
                name_cell_text = tr.get_text(separator=" ", strip=True)
                break

        form_suffix_match = re.search(r"\(([^)]+)\)", name_cell_text)
        form_suffix = form_suffix_match.group(1).strip() if form_suffix_match else ""

        unavailable = is_unavailable(name_cell_text)
        rows_by_id.setdefault(dex_id, []).append((form_suffix, unavailable))

    result: dict[int, SpeciesInfo] = {}
    for dex_id, rows in rows_by_id.items():
        _, base_unavailable = rows[0]
        if base_unavailable:
            continue

        form_rows = rows[1:]
        if not form_rows:
            available_forms = None
        else:
            available_forms = {
                suffix.lower()
                for suffix, unavail in form_rows
                if not unavail and suffix
            }

        result[dex_id] = {"region": region, "available_forms": available_forms}

    return result


def crawl_serebii_go_ids() -> dict[int, SpeciesInfo]:
    print("🌐 Fetching Serebii GO index page …")
    index_soup   = fetch_html(SEREBII_INDEX)
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
            soup   = fetch_html(url)
            result = _parse_region_page(soup, region)
            print(f"{len(result)} available species found.")
            for dex_id, info in result.items():
                id_to_info.setdefault(dex_id, info)
        except Exception as exc:
            print(f"⚠  Failed: {exc}", file=sys.stderr)
        time.sleep(0.5)

    total_form_filters = sum(
        0 if v["available_forms"] is None else len(v["available_forms"])
        for v in id_to_info.values()
    )
    print(
        f"\n✅ Serebii: {len(id_to_info)} available species across all regions "
        f"({total_form_filters} species with explicit form availability).\n"
    )
    return id_to_info


# ---------------------------------------------------------------------------
# Step 2 — Dynamic form discovery via PokeAPI
# ---------------------------------------------------------------------------

def _norm_form_name(s: str) -> str:
    s = _ud.normalize("NFD", s)
    s = "".join(c for c in s if _ud.category(c) != "Mn")
    s = s.lower()
    s = re.sub(r"[()'\u2019\-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+form(?:e)?s?$", "", s).strip()
    return s


def _forms_match(pokeapi_name: str, serebii_suffix: str) -> bool:
    pokeapi_name   = _norm_form_name(pokeapi_name)
    serebii_suffix = _norm_form_name(serebii_suffix)
    return pokeapi_name == serebii_suffix or serebii_suffix in pokeapi_name


def _form_display_name(form_data: dict) -> str:
    for key in ("form_names", "names"):
        for entry in form_data.get(key, []):
            if entry.get("language", {}).get("name") == "en" and entry.get("name"):
                return entry["name"]
    return form_data.get("form_name") or form_data.get("name", "")


def _strip_form_suffix(name: str) -> str:
    return re.sub(r"\s+[Ff]orm$", "", name).strip()


def _full_form_name(form_name: str, species_name: str) -> str:
    if form_name.lower() == species_name.lower():
        return species_name
    if species_name.lower() in form_name.lower():
        return form_name
    return f"{form_name} {species_name}"


def _fetch_variety_form(slug: str, base_types: list) -> Optional[dict]:
    poke = get_json(f"{POKEAPI_BASE}/pokemon/{slug}")
    if not poke:
        return None
    time.sleep(RATE_LIMIT_DELAY)

    sprite_id = poke["id"]
    types     = get_types(poke["types"]) or base_types
    form_name = slug

    for form_ref in poke.get("forms", []):
        form_data = get_json(form_ref["url"])
        if form_data:
            time.sleep(RATE_LIMIT_DELAY)
            name = _form_display_name(form_data)
            if name:
                form_name = name
            break

    return {"formId": slug, "name": form_name, "types": types, "spriteId": sprite_id}


def _fetch_extra_forms(pokemon_data: dict, base_types: list) -> list:
    results = []
    for form_ref in pokemon_data.get("forms", [])[1:]:
        slug      = form_ref["name"]
        form_data = get_json(form_ref["url"])
        if not form_data:
            continue
        time.sleep(RATE_LIMIT_DELAY)
        name      = _form_display_name(form_data)
        sprite_id = pokemon_data["id"]
        results.append(
            {"formId": slug, "name": name or slug, "types": base_types, "spriteId": sprite_id}
        )
    return results


def _collect_all_forms(
    species_data: dict,
    base_pokemon: dict,
    base_types: list,
    available_forms: "set | None",
    dex_id: int,
    species_name: str = "",
) -> list:
    all_forms: list = []
    seen_slugs: set = set()

    for variety in species_data.get("varieties", []):
        if variety.get("is_default"):
            continue
        slug = variety["pokemon"]["name"]
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        form = _fetch_variety_form(slug, base_types)
        if form:
            all_forms.append(form)

    for form in _fetch_extra_forms(base_pokemon, base_types):
        if form["formId"] in seen_slugs:
            continue
        seen_slugs.add(form["formId"])
        all_forms.append(form)

    if not all_forms:
        return []

    if available_forms is not None:
        filtered = []
        for suffix in available_forms:
            matched = None
            for form_dict in all_forms:
                if _forms_match(form_dict["name"], suffix):
                    matched = form_dict
                    break
            if matched:
                filtered.append(matched)
            else:
                form_names    = [fd["name"] for fd in all_forms]
                normed_suffix = _norm_form_name(suffix)
                normed_forms  = [_norm_form_name(n) for n in form_names]
                print(
                    f"\n  ⚠  #{dex_id}: Serebii available-form suffix {suffix!r} "
                    f"(normalised: {normed_suffix!r}) "
                    f"did not match any PokeAPI form. "
                    f"Known form names: {form_names} "
                    f"(normalised: {normed_forms})",
                    file=sys.stderr,
                )
        all_forms = filtered

    def _finalise(fd: dict) -> dict:
        stripped = _strip_form_suffix(fd["name"])
        return {**fd, "name": _full_form_name(stripped, species_name)}

    return [_finalise(fd) for fd in all_forms]


# ---------------------------------------------------------------------------
# Step 3 — Build one Pokémon entry from PokeAPI
# ---------------------------------------------------------------------------

def fetch_pokemon(dex_id: int, available_forms: "set | None") -> Optional[dict]:
    """Return a Pokémon entry dict, or None on failure."""
    species = get_json(f"{POKEAPI_BASE}/pokemon-species/{dex_id}")
    if not species:
        return None
    pokemon = get_json(f"{POKEAPI_BASE}/pokemon/{dex_id}")
    if not pokemon:
        return None

    name   = get_english_name(species.get("names", []), species["name"].capitalize())
    types  = get_types(pokemon["types"])
    gender = get_gender(species.get("gender_rate", -1))
    region = get_region(species)

    entry: dict = {
        "id":       dex_id,
        "name":     name,
        "types":    types,
        "gender":   gender,
        "spriteId": dex_id,
        "region":   region,
    }

    forms = _collect_all_forms(species, pokemon, types, available_forms, dex_id, name)

    if forms:
        base_form_name = name
        if pokemon.get("forms"):
            base_form_data = get_json(pokemon["forms"][0]["url"])
            if base_form_data:
                time.sleep(RATE_LIMIT_DELAY)
                raw = _form_display_name(base_form_data)
                if raw:
                    base_form_name = _strip_form_suffix(raw)
        base_form = {
            "formId":   pokemon["name"],
            "name":     _full_form_name(base_form_name, name),
            "types":    types,
            "spriteId": dex_id,
        }
        forms = [base_form] + forms

    if FORM_BLACKLIST:
        forms = [
            f for f in forms
            if not any(bl.lower() in f["name"].lower() for bl in FORM_BLACKLIST)
        ]

    if len(forms) > 1:
        entry["forms"] = forms

    return entry


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    id_to_info = crawl_serebii_go_ids()
    go_ids     = sorted(id_to_info)

    print(f"🔍 Fetching data for {len(go_ids)} Pokémon from PokeAPI …")
    results: list[dict] = []
    errors:  list[int]  = []

    for i, dex_id in enumerate(go_ids, 1):
        available_forms = id_to_info[dex_id]["available_forms"]
        print(f"   [{i:>3}/{len(go_ids)}] #{dex_id:<4}", end="\r")
        entry = fetch_pokemon(dex_id, available_forms)
        if entry:
            results.append(entry)
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

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Done — {len(results)} Pokémon written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
