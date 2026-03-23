#!/usr/bin/env python3
"""
Pokémon GO Mega Evolution Crawler
===================================
Scrapes https://www.serebii.net/pokemongo/megaevolution.shtml for all
currently available Mega Evolutions and Primal Reversions, then enriches
each entry with types, gender, sprite ID, and region from PokeAPI.

Usage:
    pip install requests beautifulsoup4
    python crawl_pokemon_go_mega.py

Output:
    data/pokemon-go-mega.json
"""

import json
import os
import re
import sys
import time
from typing import Optional

from bs4 import BeautifulSoup

from utils import (
    POKEAPI_BASE,
    RATE_LIMIT_DELAY,
    SESSION,
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

SEREBII_MEGA_URL = "https://www.serebii.net/pokemongo/megaevolution.shtml"
OUTPUT_FILE      = "data/pokemon-data-mega.json"

# Regex: detail link to /pokemongo/pokemon/NNN.shtml (relative or absolute)
_DETAIL_URL_RE = re.compile(r"(?:^|/)pokemon/(\d+)\.shtml")

# ---------------------------------------------------------------------------
# Step 1 — Scrape Serebii mega page
# ---------------------------------------------------------------------------
# Each row in the table has:
#   - #NNNN  — base species dex ID
#   - Name   — e.g. "Mega Charizard X", "Primal Kyogre"
#   - Rows marked "Not currently available" are skipped
#
# We collect (base_dex_id, display_name) pairs for available megas only.

def _outermost_tr(tag) -> Optional["BeautifulSoup"]:
    """
    Walk up the DOM from `tag` and return the highest-level <tr> ancestor —
    i.e. the one that is NOT itself inside another <tr>.  This is the full
    Pokémon row on the Serebii mega page, which contains both the name cell
    (in a nested table) and the unavailability notice (in a sibling cell).
    """
    tr = tag.find_parent("tr")
    while tr is not None:
        parent_tr = tr.find_parent("tr")
        if parent_tr is None:
            return tr
        tr = parent_tr
    return None


def scrape_available_megas() -> list[tuple[int, str]]:
    """
    Return [(base_dex_id, display_name), ...] for every available Mega/Primal
    on the Serebii mega evolution page.
    """
    print(f"🌐 Fetching Serebii mega page …")
    soup = fetch_html(SEREBII_MEGA_URL)
    results: list[tuple[int, str]] = []
    seen: set[tuple[int, str]] = set()

    # The mega page uses deeply nested tables. Each Pokémon entry lives in an
    # *outer* <tr> with multiple <td> columns. The name link is inside a nested
    # table within one of those cells; the "Not currently available" notice is
    # in a *sibling* cell of that same outer <tr>.
    #
    # find_parent("tr") gives the innermost <tr> (just the name sub-cell), so
    # we walk all the way up to the outermost <tr> to get the full row text.
    for a in soup.find_all("a", href=True):
        m = _DETAIL_URL_RE.search(a["href"])
        if not m:
            continue

        display_name = a.get_text(strip=True)
        if not display_name or display_name.startswith("#"):
            continue

        dex_id   = int(m.group(1))
        outer_tr = _outermost_tr(a)
        if outer_tr is None:
            continue

        # Check the full row (all cells) for the unavailability notice
        row_text = outer_tr.get_text(separator=" ")
        if is_unavailable(row_text):
            continue

        key = (dex_id, display_name)
        if key in seen:
            continue
        seen.add(key)

        results.append((dex_id, display_name))

    print(f"   Found {len(results)} available Mega/Primal entries.")
    return results


# ---------------------------------------------------------------------------
# Step 2 — Map display name → PokeAPI slug
# ---------------------------------------------------------------------------
# Serebii names like "Mega Charizard X" → PokeAPI slug "charizard-mega-x"
# "Primal Kyogre" → "kyogre-primal"
# "Mega Venusaur" → "venusaur-mega"
#
# Strategy: fetch the base species from PokeAPI, iterate its varieties,
# and find the one whose slug contains the key tokens from the display name.

def _name_to_tokens(display_name: str) -> list[str]:
    """
    Turn "Mega Charizard X" into search tokens ["mega", "x"] (excluding
    the species name itself, which is implicit from the base dex ID).
    Also handles "Primal Kyogre" → ["primal"].
    """
    # Normalise
    s = display_name.lower().strip()
    # Remove leading "mega " or "primal "
    s = re.sub(r"^(mega|primal)\s+", "", s)
    # Remove the base species name — we'll match on variety slug instead
    # Keep any qualifier like "x", "y", "z"
    tokens = s.split()
    return tokens


def _slug_matches(slug: str, base_name: str, display_name: str) -> bool:
    """
    Check whether a variety slug matches the given display name.
    e.g. slug "charizard-mega-x", base "Charizard", display "Mega Charizard X"
    """
    slug_lower    = slug.lower()
    display_lower = display_name.lower()

    # Must be a mega or primal slug
    if "-mega" not in slug_lower and "-primal" not in slug_lower:
        return False

    # Build expected slug from display name:
    # "Mega Charizard X"  → charizard-mega-x
    # "Primal Kyogre"     → kyogre-primal
    # "Mega Venusaur"     → venusaur-mega
    base_slug = base_name.lower().replace(" ", "-").replace("'", "").replace(".", "")
    # Qualifier tokens (x, y, z, etc.) — everything after "Mega/Primal <Species>"
    remainder = re.sub(
        rf"^(mega|primal)\s+{re.escape(base_name.lower())}\s*", "",
        display_lower,
    ).strip()

    if display_lower.startswith("primal"):
        expected = f"{base_slug}-primal"
    elif remainder:
        qualifier = remainder.replace(" ", "-")
        expected  = f"{base_slug}-mega-{qualifier}"
    else:
        expected = f"{base_slug}-mega"

    return slug_lower == expected


# ---------------------------------------------------------------------------
# Step 3 — Fetch full data from PokeAPI for one mega entry
# ---------------------------------------------------------------------------

def fetch_mega_entry(
    base_dex_id: int,
    display_name: str,
) -> Optional[dict]:
    """
    Look up the mega variety slug via the base species, then fetch its
    types and sprite ID.  Returns a dict with the required fields or None.
    """
    # Fetch base species for gender, region, and variety list
    species = get_json(f"{POKEAPI_BASE}/pokemon-species/{base_dex_id}")
    if not species:
        return None
    time.sleep(RATE_LIMIT_DELAY)

    base_name = get_english_name(species.get("names", []), species["name"].capitalize())
    gender    = get_gender(species.get("gender_rate", -1))
    region    = get_region(species)

    # Find the matching variety slug
    mega_slug = None
    for variety in species.get("varieties", []):
        slug = variety["pokemon"]["name"]
        if _slug_matches(slug, base_name, display_name):
            mega_slug = slug
            break

    if not mega_slug:
        # Fallback: try constructing the slug directly
        print(
            f"\n  ⚠  Could not find variety for {display_name!r} "
            f"(#{base_dex_id}). Skipping.",
            file=sys.stderr,
        )
        return None

    # Fetch the mega pokemon entry for types and sprite ID
    poke = get_json(f"{POKEAPI_BASE}/pokemon/{mega_slug}")
    if not poke:
        return None
    time.sleep(RATE_LIMIT_DELAY)

    sprite_id = poke["id"]
    types     = get_types(poke["types"])

    return {
        "id":       base_dex_id,
        "name":     display_name,
        "types":    types,
        "gender":   gender,
        "spriteId": sprite_id,
        "region":   region,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # Phase 1: scrape available megas from Serebii
    available = scrape_available_megas()

    # Manually add Primal Kyogre and Primal Groudon — these are available in GO
    # but may not appear on the Serebii mega page.
    MANUAL_ENTRIES: list[tuple[int, str]] = [
        (382, "Primal Kyogre"),
        (383, "Primal Groudon"),
    ]
    existing_keys = {(dex_id, name) for dex_id, name in available}
    for entry in MANUAL_ENTRIES:
        if entry not in existing_keys:
            available.append(entry)
            print(f"   ➕ Manually added: {entry[1]}")

    # Phase 2: enrich with PokeAPI data
    print(f"\n🔍 Fetching PokeAPI data for {len(available)} Mega/Primal entries …")
    results: list[dict] = []
    errors:  list[str]  = []

    for i, (dex_id, display_name) in enumerate(available, 1):
        print(f"   [{i:>3}/{len(available)}] {display_name}", end="\r")
        entry = fetch_mega_entry(dex_id, display_name)
        if entry:
            results.append(entry)
        else:
            errors.append(display_name)
        time.sleep(RATE_LIMIT_DELAY)

    print()
    if errors:
        print(
            f"   ⚠  {len(errors)} failed: {errors[:10]}"
            + ("…" if len(errors) > 10 else ""),
            file=sys.stderr,
        )

    # Phase 3: write output
    results.sort(key=lambda e: e["id"])
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Done — {len(results)} Mega/Primal entries written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
