"""
Shared utilities for Pokémon GO crawlers.
"""

import re
import sys
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

POKEAPI_BASE     = "https://pokeapi.co/api/v2"
RATE_LIMIT_DELAY = 0.25  # seconds between PokeAPI requests

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "pokemon-go-crawler/2.0 "
        "(https://github.com/example/pokemon-go-crawler)"
    )
})

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
# HTTP helpers
# ---------------------------------------------------------------------------

def get_json(url: str) -> Optional[dict]:
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


def fetch_html(url: str) -> BeautifulSoup:
    """Fetch a Serebii page and return a BeautifulSoup object (latin-1)."""
    resp = SESSION.get(url, timeout=20)
    resp.raise_for_status()
    return BeautifulSoup(
        resp.content.decode("latin-1", errors="replace"), "html.parser"
    )


# ---------------------------------------------------------------------------
# Serebii helpers
# ---------------------------------------------------------------------------

def is_unavailable(row_text: str) -> bool:
    """Return True if a Serebii table row is marked as not in GO."""
    return "not currently available" in row_text.lower()


# ---------------------------------------------------------------------------
# PokeAPI helpers
# ---------------------------------------------------------------------------

def get_types(type_slots: list) -> list[str]:
    return [s["type"]["name"] for s in type_slots]


def get_gender(gender_rate: int) -> str:
    if gender_rate == -1: return "none"
    if gender_rate == 0:  return "male"
    if gender_rate == 8:  return "female"
    return "male-female"


def get_english_name(names: list, fallback: str = "") -> str:
    return next(
        (n["name"] for n in names if n["language"]["name"] == "en"),
        fallback,
    )


def get_region(species_data: dict) -> str:
    generation = species_data.get("generation", {}).get("name", "")
    return GENERATION_TO_REGION.get(generation, "Unknown")
