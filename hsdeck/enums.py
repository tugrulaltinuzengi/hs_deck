"""Game enums and vocabulary.

Every value here comes from HearthSim's ``python-hearthstone``, vendored under
``hsdeck/_vendor``.  Blizzard's tag numbers, the Standard rotation, the hero
portraits and the tribe list are upstream's to maintain; this module only adds
the parsing and display helpers hsdeck needs on top.
"""

from __future__ import annotations

from ._vendor.hearthstone.enums import (
    CardClass,
    CardSet,
    CardType,
    FormatType,
    GameTag,
    Race,
    Rarity,
    SpellSchool,
    ZodiacYear,
)
from ._vendor.hearthstone.utils import CARDRACE_TAG_MAP

# Upstream enums are re-exported so callers import them from one place, and
# hsdeck's own helpers sit alongside them.  Declared explicitly rather than
# suppressed per-line: `# noqa` is a flake8 feature, while `__all__` is what
# pyflakes itself honours.
__all__ = [
    # re-exported from the vendored HearthSim tree
    "CardClass", "CardSet", "CardType", "FormatType", "GameTag", "Race",
    "Rarity", "SpellSchool", "ZodiacYear",
    # hsdeck's own
    "MAX_COPIES_DEFAULT", "MAX_COPIES_LEGENDARY", "PLAYABLE_RACES",
    "PLAYABLE_SPELL_SCHOOLS", "PLAYABLE_TYPES", "RACE_BY_NAME",
    "SCHOOL_BY_NAME", "WILDCARD_RACE", "class_label", "format_label",
    "is_standard", "max_copies", "parse_class", "parse_format", "race_label",
    "school_label", "standard_sets",
]

# Card types that can sit in a constructed decklist.
PLAYABLE_TYPES = frozenset(
    {CardType.MINION, CardType.SPELL, CardType.WEAPON, CardType.LOCATION}
)

# Maximum copies of a single card allowed in a constructed deck.
MAX_COPIES_DEFAULT = 2
MAX_COPIES_LEGENDARY = 1

_CLASS_ALIASES = {
    "DH": CardClass.DEMONHUNTER,
    "DK": CardClass.DEATHKNIGHT,
}

_FORMAT_ALIASES = {
    "WILD": FormatType.FT_WILD,
    "STANDARD": FormatType.FT_STANDARD,
    "CLASSIC": FormatType.FT_CLASSIC,
    "TWIST": FormatType.FT_TWIST,
    # "Custom" is not a client format.  It encodes as Standard; if the deck
    # then breaks a rule, the validator is what says so.
    "CUSTOM": FormatType.FT_STANDARD,
}

# Tribes whose in-game name differs from the upstream enum name.
_RACE_LABELS = {Race.MECHANICAL: "Mech"}


def parse_class(value: str | int | CardClass) -> CardClass:
    if isinstance(value, CardClass):
        return value
    if isinstance(value, int):
        return CardClass(value)
    key = "".join(ch for ch in str(value).upper() if ch.isalnum())
    if key in _CLASS_ALIASES:
        return _CLASS_ALIASES[key]
    try:
        return CardClass[key]
    except KeyError as exc:
        raise ValueError(f"unknown class: {value!r}") from exc


def parse_format(value: str | int | FormatType) -> FormatType:
    if isinstance(value, FormatType):
        return value
    if isinstance(value, int):
        return FormatType(value)
    key = str(value).strip().upper()
    if key in _FORMAT_ALIASES:
        return _FORMAT_ALIASES[key]
    try:
        return FormatType[key]  # accepts the upstream "FT_STANDARD" spelling
    except KeyError as exc:
        raise ValueError(f"unknown format: {value!r}") from exc


def class_label(card_class: CardClass) -> str:
    """'Demon Hunter', not 'DEMONHUNTER'."""
    return {
        CardClass.DEMONHUNTER: "Demon Hunter",
        CardClass.DEATHKNIGHT: "Death Knight",
    }.get(card_class, card_class.name.title())


def format_label(format: FormatType) -> str:
    """'Standard', not 'FT_STANDARD'."""
    return format.name.removeprefix("FT_").title()


def race_label(race: int) -> str:
    try:
        race = Race(race)
    except ValueError:
        return str(race)
    return _RACE_LABELS.get(race, race.name.title())


def school_label(school: int) -> str:
    try:
        return SpellSchool(school).name.title()
    except ValueError:
        return str(school)


def max_copies(rarity: int) -> int:
    return MAX_COPIES_LEGENDARY if rarity == Rarity.LEGENDARY else MAX_COPIES_DEFAULT


def is_standard(card_set: int) -> bool:
    """Whether a set is in the current Standard rotation.

    Evaluated at runtime from the vendored ``STANDARD_SETS`` table, so a
    rotation is picked up by refreshing ``hsdeck/_vendor`` - the generated card
    database does not have to be rebuilt.
    """
    try:
        return CardSet(card_set).is_standard
    except ValueError:
        return False


def standard_sets() -> list[str]:
    return sorted(s.name for s in ZodiacYear.SCARAB.standard_card_sets)


# The tribes that actually exist as a minion type, per upstream's tag map.
PLAYABLE_RACES = tuple(
    race for race, tag in CARDRACE_TAG_MAP.items() if tag is not None
)

# Spell schools a card can actually carry (the rest are Battlegrounds/other).
PLAYABLE_SPELL_SCHOOLS = (
    SpellSchool.ARCANE,
    SpellSchool.FIRE,
    SpellSchool.FROST,
    SpellSchool.NATURE,
    SpellSchool.HOLY,
    SpellSchool.SHADOW,
    SpellSchool.FEL,
)

SCHOOL_BY_NAME = {school_label(s).lower(): int(s) for s in PLAYABLE_SPELL_SCHOOLS}
RACE_BY_NAME = {race_label(r).lower(): int(r) for r in PLAYABLE_RACES}

# Race.ALL matches every tribal payoff, so it is not a synergy signal of its own.
WILDCARD_RACE = int(Race.ALL)
