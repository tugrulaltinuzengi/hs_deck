"""Game enums used by the deck builder.

Values mirror Blizzard's ``TAG_CLASS`` / ``TAG_CARDTYPE`` / ``TAG_RARITY`` and
``PegasusShared.FormatType``.  Only the members hsdeck actually needs are kept.
"""

from __future__ import annotations

from enum import IntEnum


class CardClass(IntEnum):
    INVALID = 0
    DEATHKNIGHT = 1
    DRUID = 2
    HUNTER = 3
    MAGE = 4
    PALADIN = 5
    PRIEST = 6
    ROGUE = 7
    SHAMAN = 8
    WARLOCK = 9
    WARRIOR = 10
    DREAM = 11
    NEUTRAL = 12
    WHIZBANG = 13
    DEMONHUNTER = 14

    @classmethod
    def parse(cls, value: "str | int | CardClass") -> "CardClass":
        if isinstance(value, cls):
            return value
        if isinstance(value, int):
            return cls(value)
        key = str(value).strip().upper().replace(" ", "").replace("-", "").replace("_", "")
        aliases = {
            "DEMONHUNTER": cls.DEMONHUNTER,
            "DH": cls.DEMONHUNTER,
            "DEATHKNIGHT": cls.DEATHKNIGHT,
            "DK": cls.DEATHKNIGHT,
        }
        if key in aliases:
            return aliases[key]
        try:
            return cls[key]
        except KeyError as exc:
            raise ValueError(f"unknown class: {value!r}") from exc


class CardType(IntEnum):
    MINION = 4
    SPELL = 5
    WEAPON = 7
    LOCATION = 39


class Rarity(IntEnum):
    INVALID = 0
    COMMON = 1
    FREE = 2
    RARE = 3
    EPIC = 4
    LEGENDARY = 5


class FormatType(IntEnum):
    UNKNOWN = 0
    WILD = 1
    STANDARD = 2
    CLASSIC = 3
    TWIST = 4

    @classmethod
    def parse(cls, value: "str | int | FormatType") -> "FormatType":
        if isinstance(value, cls):
            return value
        if isinstance(value, int):
            return cls(value)
        key = str(value).strip().upper()
        # "Custom" is not a client format - it is encoded as Standard and the
        # deck is flagged as unimportable by the validator if it breaks a rule.
        if key == "CUSTOM":
            return cls.STANDARD
        try:
            return cls[key]
        except KeyError as exc:
            raise ValueError(f"unknown format: {value!r}") from exc


# Maximum copies of a single card allowed in a constructed deck.
MAX_COPIES_DEFAULT = 2
MAX_COPIES_LEGENDARY = 1


def max_copies(rarity: int) -> int:
    return MAX_COPIES_LEGENDARY if rarity == Rarity.LEGENDARY else MAX_COPIES_DEFAULT
