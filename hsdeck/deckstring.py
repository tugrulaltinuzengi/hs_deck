"""Hearthstone deckstring codec.

The binary work is HearthSim's reference implementation, vendored at
``hsdeck/_vendor/hearthstone/deckstrings.py``.  hsdeck deliberately does not
reimplement it: a deckstring is only useful if the game client accepts it, and
the reference encoder is what every Hearthstone deck site already agrees with.

This module adds the things a caller needs around it — input validation before
encoding, a single :class:`DeckstringError` instead of four unrelated exception
types, and a :class:`ParsedDeck` result object.

Binary layout (version 1), all integers unsigned LEB128 varints:

    0x00                      reserved byte
    varint  version           always 1
    varint  format            FormatType (1=Wild, 2=Standard, 3=Classic, 4=Twist)
    varint  hero_count        always 1
    varint* hero_dbf_ids      ascending
    varint  n1                cards played as exactly 1 copy
    varint* dbf_ids           ascending
    varint  n2                cards played as exactly 2 copies
    varint* dbf_ids           ascending
    varint  nN                cards played as 3+ copies
    (varint dbf_id, varint count)*
    0x00 | 0x01               sideboard marker
    <sideboard block>         present only when the marker is 0x01

The whole buffer is then standard base64.  Sideboard entries are triples of
(card dbf id, count, owner dbf id) grouped by count the same way, sorted by
(owner, card).
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
from typing import Sequence

from ._vendor.hearthstone import deckstrings as _reference
from .enums import FormatType, parse_format

DECKSTRING_VERSION = _reference.DECKSTRING_VERSION

CardCounts = Sequence[tuple[int, int]]
SideboardCounts = Sequence[tuple[int, int, int]]


class DeckstringError(ValueError):
    """Raised when a deckstring cannot be parsed or encoded."""


@dataclass
class ParsedDeck:
    """The raw contents of a deckstring - DBF ids only, no card names."""

    cards: list[tuple[int, int]] = field(default_factory=list)
    heroes: list[int] = field(default_factory=list)
    format: FormatType = FormatType.FT_UNKNOWN
    sideboards: list[tuple[int, int, int]] = field(default_factory=list)

    @property
    def size(self) -> int:
        return sum(count for _, count in self.cards)

    def to_deckstring(self) -> str:
        return write_deckstring(self.cards, self.heroes, self.format, self.sideboards)


def _check_dbf(value: int, what: str) -> int:
    # The reference encoder writes unsigned varints and would loop forever on a
    # negative, so bad input is rejected here rather than passed through.
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise DeckstringError(f"{what} must be a non-negative integer, got {value!r}")
    return value


def _check_count(value: int, dbf_id: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise DeckstringError(
            f"card count for DBF id {dbf_id} must be positive, got {value!r}"
        )
    return value


def write_deckstring(
    cards: CardCounts,
    heroes: Sequence[int],
    format: FormatType | int | str = FormatType.FT_STANDARD,
    sideboards: SideboardCounts | None = None,
) -> str:
    """Encode (dbf_id, count) pairs into a deckstring the client can import."""
    format = parse_format(format)

    if len(heroes) != 1:
        raise DeckstringError(f"expected exactly 1 hero, got {len(heroes)}")
    heroes = [_check_dbf(hero, "hero DBF id") for hero in heroes]

    merged: dict[int, int] = {}
    for dbf_id, count in cards:
        _check_dbf(dbf_id, "card DBF id")
        merged[dbf_id] = merged.get(dbf_id, 0) + _check_count(count, dbf_id)

    checked_sideboards = []
    for dbf_id, count, owner in sideboards or ():
        _check_dbf(dbf_id, "sideboard card DBF id")
        _check_dbf(owner, "sideboard owner DBF id")
        checked_sideboards.append((dbf_id, _check_count(count, dbf_id), owner))

    try:
        return _reference.write_deckstring(
            sorted(merged.items()), heroes, format, checked_sideboards
        )
    except ValueError as exc:
        raise DeckstringError(str(exc)) from exc


def parse_deckstring(deckstring: str) -> ParsedDeck:
    """Decode a deckstring back into DBF ids, heroes and format."""
    cleaned = "".join(str(deckstring).split())
    if not cleaned:
        raise DeckstringError("empty deckstring")
    try:
        base64.b64decode(cleaned, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise DeckstringError(f"not valid base64: {exc}") from exc

    try:
        cards, heroes, format, sideboards = _reference.parse_deckstring(cleaned)
    except ValueError as exc:
        raise DeckstringError(str(exc)) from exc
    except (EOFError, TypeError, IndexError) as exc:
        # The reference reader signals a short buffer by failing to read a
        # varint; the exact exception type is an implementation detail.
        raise DeckstringError(f"truncated deckstring: {exc}") from exc

    return ParsedDeck(
        cards=sorted(cards),
        heroes=sorted(heroes),
        format=format,
        sideboards=sorted(sideboards, key=lambda e: (e[2], e[0])),
    )
