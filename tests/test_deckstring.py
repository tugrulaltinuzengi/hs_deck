import base64

import pytest

from hsdeck.deckstring import DeckstringError, parse_deckstring, write_deckstring
from hsdeck.enums import FormatType

PRIEST_HERO = 813


def test_header_layout():
    encoded = write_deckstring([(1, 1)], [PRIEST_HERO], FormatType.FT_STANDARD)
    raw = base64.b64decode(encoded)
    # reserved 0x00, version 1, format 2 (Standard), then 1 hero
    assert raw[:4] == b"\x00\x01\x02\x01"
    assert encoded.startswith("AAECAa0G")


def test_roundtrip_preserves_counts():
    cards = [(117544, 1), (127065, 2), (126055, 1), (114080, 3)]
    encoded = write_deckstring(cards, [PRIEST_HERO], FormatType.FT_STANDARD)
    parsed = parse_deckstring(encoded)

    assert parsed.heroes == [PRIEST_HERO]
    assert parsed.format is FormatType.FT_STANDARD
    assert sorted(parsed.cards) == sorted(cards)
    assert parsed.size == 7
    assert parsed.to_deckstring() == encoded


def test_duplicate_entries_are_merged():
    encoded = write_deckstring([(500, 1), (500, 1)], [PRIEST_HERO], 2)
    assert parse_deckstring(encoded).cards == [(500, 2)]


def test_sideboard_roundtrip():
    cards = [(100, 1), (200, 2)]
    sideboard = [(301, 1, 100), (302, 2, 100), (303, 3, 200)]
    encoded = write_deckstring(cards, [PRIEST_HERO], FormatType.FT_WILD, sideboard)
    parsed = parse_deckstring(encoded)
    assert parsed.sideboards == sorted(sideboard, key=lambda e: (e[2], e[0]))


def test_no_sideboard_writes_trailing_zero():
    raw = base64.b64decode(write_deckstring([(1, 1)], [PRIEST_HERO], 2))
    assert raw[-1] == 0


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "not base64!!",
        base64.b64encode(b"\x01\x01\x02").decode(),  # wrong reserved byte
        base64.b64encode(b"\x00\x09\x02").decode(),  # unsupported version
        base64.b64encode(b"\x00\x01\x63").decode(),  # unknown format
        base64.b64encode(b"\x00\x01\x02\x01").decode(),  # truncated
    ],
)
def test_invalid_deckstrings_rejected(bad):
    with pytest.raises(DeckstringError):
        parse_deckstring(bad)


def test_hero_count_must_be_one():
    with pytest.raises(DeckstringError):
        write_deckstring([(1, 1)], [], 2)
    with pytest.raises(DeckstringError):
        write_deckstring([(1, 1)], [813, 637], 2)


def test_zero_count_rejected():
    with pytest.raises(DeckstringError):
        write_deckstring([(1, 0)], [PRIEST_HERO], 2)


def test_whitespace_is_tolerated():
    encoded = write_deckstring([(1, 1)], [PRIEST_HERO], 2)
    assert parse_deckstring(f"  {encoded[:6]}\n{encoded[6:]}  ").cards == [(1, 1)]
