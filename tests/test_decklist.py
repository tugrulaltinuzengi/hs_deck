import pytest

from hsdeck.carddb import CardDB
from hsdeck.decklist import DecklistError, deck_from_deckstring, parse_decklist
from hsdeck.enums import CardClass, FormatType
from hsdeck.render import deck_code_block

CLIPBOARD = """\
### Quest Priest (20-Card)
# Class: Priest
# Format: Standard
#
# 1x (1) Reach Equilibrium
# 2x (3) Specter Specialist
# 1x (6) Karov the Broken
# 1x (7) Azalina Soulsever
#
AAECAa0G
#
# To use this deck, copy it to your clipboard and create a new deck in Hearthstone.
"""


def test_parses_a_clipboard_block(db: CardDB):
    deck = parse_decklist(CLIPBOARD, db)
    assert deck.name == "Quest Priest (20-Card)"
    assert deck.card_class is CardClass.PRIEST
    assert deck.format is FormatType.FT_STANDARD
    assert deck.size == 5
    assert deck.count_of(db.resolve("Specter Specialist").card) == 2


def test_parses_a_bare_list_and_infers_the_class(db: CardDB):
    deck = parse_decklist("2 Specter Specialist\n1 Karov the Broken\n", db)
    assert deck.card_class is CardClass.PRIEST
    assert deck.size == 3


def test_neutral_only_list_cannot_infer_a_class(db: CardDB):
    with pytest.raises(DecklistError, match="class"):
        parse_decklist("2 Flutterwing Guardian\n", db)


def test_unknown_card_raises(db: CardDB):
    with pytest.raises(DecklistError, match="unknown card"):
        parse_decklist("# Class: Priest\n2x Zzzqq Not A Card\n", db)


def test_empty_list_raises(db: CardDB):
    with pytest.raises(DecklistError):
        parse_decklist("# Class: Priest\n", db)


def test_text_block_survives_a_full_round_trip(db: CardDB):
    original = parse_decklist(CLIPBOARD, db)
    rebuilt = parse_decklist(deck_code_block(original), db)
    assert rebuilt.entries() == original.entries()
    assert rebuilt.deckstring() == original.deckstring()


def test_deckstring_round_trip_recovers_names_and_format(db: CardDB):
    original = parse_decklist(CLIPBOARD, db)
    rebuilt = deck_from_deckstring(original.deckstring(), db)
    assert rebuilt.entries() == original.entries()
    assert rebuilt.card_class is CardClass.PRIEST
    assert rebuilt.format is FormatType.FT_STANDARD
