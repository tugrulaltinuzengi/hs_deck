"""Hearthstone deckstring codec.

Binary layout (version 1), all integers unsigned LEB128 varints:

    0x00                      reserved byte
    varint  version           always 1
    varint  format            FormatType (1=Wild, 2=Standard, 3=Classic, 4=Twist)
    varint  hero_count        always 1
    varint* hero_dbf_ids      ascending
    varint  n1                number of distinct cards played as 1 copy
    varint* dbf_ids           ascending
    varint  n2                number of distinct cards played as 2 copies
    varint* dbf_ids           ascending
    varint  nN                number of distinct cards played as 3+ copies
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
from io import BytesIO
from typing import Iterable, Sequence

from .enums import FormatType
from .varint import read_varint, write_varint

DECKSTRING_VERSION = 1

CardCounts = Sequence[tuple[int, int]]
SideboardCounts = Sequence[tuple[int, int, int]]


class DeckstringError(ValueError):
    """Raised when a deckstring cannot be parsed or encoded."""


@dataclass
class ParsedDeck:
    """The raw contents of a deckstring - DBF ids only, no card names."""

    cards: list[tuple[int, int]] = field(default_factory=list)
    heroes: list[int] = field(default_factory=list)
    format: FormatType = FormatType.UNKNOWN
    sideboards: list[tuple[int, int, int]] = field(default_factory=list)

    @property
    def size(self) -> int:
        return sum(count for _, count in self.cards)

    def to_deckstring(self) -> str:
        return write_deckstring(self.cards, self.heroes, self.format, self.sideboards)


def _trisort(entries: Iterable[tuple]) -> tuple[list[tuple], list[tuple], list[tuple]]:
    """Split entries into the 1-copy, 2-copy and n-copy groups."""
    ones: list[tuple] = []
    twos: list[tuple] = []
    many: list[tuple] = []
    for entry in entries:
        count = entry[1]
        if count < 1:
            raise DeckstringError(f"card count must be positive, got {count}")
        bucket = ones if count == 1 else twos if count == 2 else many
        bucket.append(entry)
    return ones, twos, many


def write_deckstring(
    cards: CardCounts,
    heroes: Sequence[int],
    format: FormatType | int | str = FormatType.STANDARD,
    sideboards: SideboardCounts | None = None,
) -> str:
    """Encode (dbf_id, count) pairs into a deckstring the client can import."""
    format = FormatType.parse(format)
    sideboards = list(sideboards or [])

    if len(heroes) != 1:
        raise DeckstringError(f"expected exactly 1 hero, got {len(heroes)}")

    merged: dict[int, int] = {}
    for dbf_id, count in cards:
        merged[dbf_id] = merged.get(dbf_id, 0) + count

    data = BytesIO()
    data.write(b"\0")
    write_varint(data, DECKSTRING_VERSION)
    write_varint(data, int(format))

    write_varint(data, len(heroes))
    for hero in sorted(heroes):
        write_varint(data, hero)

    ones, twos, many = _trisort(sorted(merged.items()))
    for group in (ones, twos):
        write_varint(data, len(group))
        for dbf_id, _ in group:
            write_varint(data, dbf_id)

    write_varint(data, len(many))
    for dbf_id, count in many:
        write_varint(data, dbf_id)
        write_varint(data, count)

    if sideboards:
        data.write(b"\1")
        sb_ones, sb_twos, sb_many = _trisort(
            sorted(sideboards, key=lambda e: (e[2], e[0]))
        )
        for group in (sb_ones, sb_twos):
            write_varint(data, len(group))
            for dbf_id, _, owner in group:
                write_varint(data, dbf_id)
                write_varint(data, owner)
        write_varint(data, len(sb_many))
        for dbf_id, count, owner in sb_many:
            write_varint(data, dbf_id)
            write_varint(data, count)
            write_varint(data, owner)
    else:
        data.write(b"\0")

    return base64.b64encode(data.getvalue()).decode("ascii")


def parse_deckstring(deckstring: str) -> ParsedDeck:
    """Decode a deckstring back into DBF ids, heroes and format."""
    cleaned = "".join(deckstring.split())
    if not cleaned:
        raise DeckstringError("empty deckstring")
    try:
        decoded = base64.b64decode(cleaned, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise DeckstringError(f"not valid base64: {exc}") from exc

    data = BytesIO(decoded)
    if data.read(1) != b"\0":
        raise DeckstringError("missing reserved leading byte")

    try:
        version = read_varint(data)
        if version != DECKSTRING_VERSION:
            raise DeckstringError(f"unsupported deckstring version {version}")

        raw_format = read_varint(data)
        try:
            format = FormatType(raw_format)
        except ValueError as exc:
            raise DeckstringError(f"unsupported format {raw_format}") from exc

        heroes = [read_varint(data) for _ in range(read_varint(data))]

        cards: list[tuple[int, int]] = []
        for count in (1, 2):
            for _ in range(read_varint(data)):
                cards.append((read_varint(data), count))
        for _ in range(read_varint(data)):
            dbf_id = read_varint(data)
            cards.append((dbf_id, read_varint(data)))

        sideboards: list[tuple[int, int, int]] = []
        marker = data.read(1)
        if marker == b"\1":
            for count in (1, 2):
                for _ in range(read_varint(data)):
                    sideboards.append((read_varint(data), count, read_varint(data)))
            for _ in range(read_varint(data)):
                dbf_id = read_varint(data)
                sideboards.append((dbf_id, read_varint(data), read_varint(data)))
    except EOFError as exc:
        raise DeckstringError(f"truncated deckstring: {exc}") from exc

    heroes.sort()
    cards.sort()
    sideboards.sort(key=lambda e: (e[2], e[0]))
    return ParsedDeck(cards=cards, heroes=heroes, format=format, sideboards=sideboards)
