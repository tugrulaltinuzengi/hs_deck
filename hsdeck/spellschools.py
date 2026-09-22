"""Spell school and minion tribe names, used for synergy detection.

Values are Blizzard's ``SpellSchool`` and ``Race`` tag enums; only the ones
that actually appear on collectible cards are listed.
"""

from __future__ import annotations

SPELL_SCHOOLS = {
    1: "Arcane",
    2: "Fire",
    3: "Frost",
    4: "Nature",
    5: "Holy",
    6: "Shadow",
    7: "Fel",
}

RACES = {
    2: "Draenei",
    11: "Undead",
    14: "Murloc",
    15: "Demon",
    17: "Mech",
    18: "Elemental",
    20: "Beast",
    21: "Totem",
    23: "Pirate",
    24: "Dragon",
    26: "All",
    43: "Quilboar",
    92: "Naga",
}

# "All" is the wildcard tribe - it matches every tribal payoff, so it must not
# act as a synergy signal of its own.
WILDCARD_RACE = 26

SCHOOL_BY_NAME = {name.lower(): value for value, name in SPELL_SCHOOLS.items()}
RACE_BY_NAME = {name.lower(): value for value, name in RACES.items()}
