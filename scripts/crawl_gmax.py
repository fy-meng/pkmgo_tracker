#!/usr/bin/env python3
"""
Pokémon GO Gigantamax Crawler
==============================
Scrapes https://bulbapedia.bulbagarden.net/wiki/Gigantamax_(GO) for all
currently listed Gigantamax Pokémon, then enriches each entry with types,
gender, sprite ID, and region from PokeAPI.

Usage:
    pip install requests beautifulsoup4
    python crawl_pokemon_go_gmax.py

Output:
    data/pokemon-data-gmax.json
"""

import json
import os
import re
import sys
import time
from typing import Optional

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
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BULBAPEDIA_GMAX_URL = "https://bulbapedia.bulbagarden.net/wiki/Gigantamax_(GO)"
OUTPUT_FILE         = "data/pokemon-data-gmax.json"

# Bulbapedia links Pokémon species pages as /wiki/Venusaur_(Pokémon)
_SPECIES_URL_RE = re.compile(r"^/wiki/([^/]+)_\(Pok%C3%A9mon\)$")

# ---------------------------------------------------------------------------
# Step 1 — Scrape Bulbapedia Gigantamax page
# ---------------------------------------------------------------------------
# The page has a simple table: Image | Name | G-Max Move | Release date
# Each row's "Name" cell contains text like "Gigantamax Venusaur" and a link
# to /wiki/Venusaur_(Pokémon).  We extract the species name from the link href
# (more reliable than parsing the cell text).

def scrape_available_gmax() -> list[tuple[str, str]]:
    """
    Return [(species_name, display_name), ...] for every Gigantamax Pokémon
    listed on the Bulbapedia GO Gigantamax page.

    species_name  — raw Bulbapedia species name, e.g. "Venusaur", "Toxtricity"
    display_name  — full display name, e.g. "Gigantamax Venusaur"
    """
    print(f"🌐 Fetching Bulbapedia Gigantamax page …")
    soup = fetch_html(BULBAPEDIA_GMAX_URL)
    results: list[tuple[str, str]] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        m = _SPECIES_URL_RE.match(a["href"])
        if not m:
            continue

        # Decode %XX sequences in the captured species name
        raw = m.group(1)
        # URL-decode basic cases (e.g. apostrophes, accented chars)
        species_name = raw.replace("%27", "'").replace("%C3%A9", "é")

        if species_name in seen:
            continue
        seen.add(species_name)

        display_name = f"Gigantamax {species_name}"
        results.append((species_name, display_name))
        print(f"   + {display_name}")

    print(f"   Found {len(results)} Gigantamax entries.")
    return results


# ---------------------------------------------------------------------------
# Step 2 — Resolve species name → base dex ID via PokeAPI
# ---------------------------------------------------------------------------

def _species_slug(species_name: str) -> str:
    """Convert a species name to a PokeAPI-compatible slug."""
    return species_name.lower().replace(" ", "-").replace("'", "").replace(".", "").replace("é", "e")


def fetch_gmax_entry(species_name: str, display_name: str) -> Optional[dict]:
    """
    1. Resolve the species slug → dex ID via PokeAPI /pokemon-species/.
    2. Locate the -gmax variety in the species' varieties list.
    3. Fetch the gmax Pokémon entry for types and sprite ID.
    Returns a dict with the required output fields, or None on failure.
    """
    slug = _species_slug(species_name)

    # Fetch base species
    species = get_json(f"{POKEAPI_BASE}/pokemon-species/{slug}")
    if not species:
        print(f"\n  ⚠  Species not found for {display_name!r} (slug={slug!r}). Skipping.", file=sys.stderr)
        return None
    time.sleep(RATE_LIMIT_DELAY)

    base_dex_id = species["id"]
    gender      = get_gender(species.get("gender_rate", -1))
    region      = get_region(species)

    # Find the -gmax variety
    gmax_slug = None
    for variety in species.get("varieties", []):
        v_slug = variety["pokemon"]["name"]
        if v_slug.endswith("-gmax"):
            gmax_slug = v_slug
            break

    if not gmax_slug:
        print(
            f"\n  ⚠  No -gmax variety found for {display_name!r} "
            f"(#{base_dex_id}). Skipping.",
            file=sys.stderr,
        )
        return None

    # Fetch the gmax Pokémon entry
    poke = get_json(f"{POKEAPI_BASE}/pokemon/{gmax_slug}")
    if not poke:
        return None
    time.sleep(RATE_LIMIT_DELAY)

    return {
        "id":       base_dex_id,
        "name":     display_name,
        "types":    get_types(poke["types"]),
        "gender":   gender,
        "spriteId": poke["id"],
        "region":   region,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # Phase 1: scrape available Gigantamax Pokémon from Bulbapedia
    available = scrape_available_gmax()

    if not available:
        print("❌ No entries found — check the page structure.", file=sys.stderr)
        sys.exit(1)

    # Phase 2: enrich with PokeAPI data
    print(f"\n🔍 Fetching PokeAPI data for {len(available)} Gigantamax entries …")
    results: list[dict] = []
    errors:  list[str]  = []

    for i, (species_name, display_name) in enumerate(available, 1):
        print(f"   [{i:>3}/{len(available)}] {display_name}", end="\r")
        entry = fetch_gmax_entry(species_name, display_name)
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

    # Phase 3: sort by base dex ID and write output
    results.sort(key=lambda e: e["id"])
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Done — {len(results)} Gigantamax entries written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
