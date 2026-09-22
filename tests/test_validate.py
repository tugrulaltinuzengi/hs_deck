import pytest

from hsdeck.carddb import CardDB
from hsdeck.deck import Deck
from hsdeck.enums import CardClass, FormatType
from hsdeck.validate import validate


def make_deck(db: CardDB, card_class=CardClass.PRIEST, format=FormatType.FT_STANDARD) -> Deck:
    return Deck(
        card_class=card_class,
        format=format,
        hero_dbf=db.hero_dbf(card_class),
        name="Test Deck",
    )


def fill(db: CardDB, deck: Deck, target: int) -> Deck:
    """Pad the deck to a size with legal cards, two copies at a time."""
    for card in db.pool(deck.card_class, deck.format):
        if deck.size >= target:
            break
        if card.dbf in db.deck_size_modifiers or deck.count_of(card):
            continue
        deck.add(card, min(card.max_copies, target - deck.size))
    return deck


def test_a_full_legal_deck_passes(db: CardDB):
    deck = fill(db, make_deck(db), 30)
    assert validate(deck, db).ok


@pytest.mark.parametrize("size", [29, 31, 20])
def test_wrong_size_is_an_error(db: CardDB, size):
    report = validate(fill(db, make_deck(db), size), db)
    assert not report.ok
    assert any("must hold exactly 30" in str(i) for i in report.errors)


def test_azalina_makes_twenty_the_right_size(db: CardDB):
    deck = make_deck(db)
    deck.add(db.resolve("Azalina Soulsever").card, 1)
    assert validate(fill(db, deck, 20), db).ok
    assert not validate(fill(db, deck, 30), db).ok


def test_too_many_copies_is_an_error(db: CardDB):
    deck = make_deck(db)
    deck.add(db.resolve("Specter Specialist").card, 3)
    fill(db, deck, 30)
    report = validate(deck, db)
    assert any("limited to 2 copies" in str(i) for i in report.errors)


def test_two_legendary_copies_is_an_error(db: CardDB):
    deck = make_deck(db)
    deck.add(db.resolve("Karov the Broken").card, 2)
    fill(db, deck, 30)
    assert any("limited to 1 copy" in str(i) for i in validate(deck, db).errors)


def test_off_class_card_is_an_error(db: CardDB):
    deck = make_deck(db)
    deck.add(db.resolve("Fireball").card, 1)
    fill(db, deck, 30)
    assert any("cannot be played by Priest" in str(i) for i in validate(deck, db).errors)


def test_rotated_card_is_illegal_in_standard(db: CardDB):
    deck = make_deck(db)
    deck.add(db.resolve("Azalina Soulthief").card, 1)
    fill(db, deck, 30)
    report = validate(deck, db)
    assert any("not legal in Standard" in str(i) for i in report.errors)

    deck.format = FormatType.FT_WILD
    assert not any("not legal" in str(i) for i in validate(deck, db).errors)


def test_two_quests_is_an_error(db: CardDB):
    deck = make_deck(db)
    quests = [
        c
        for c in db.pool(CardClass.PRIEST, FormatType.FT_STANDARD)
        if c.has_tag("QUEST") or c.has_tag("QUESTLINE")
    ][:2]
    if len(quests) < 2:
        pytest.skip("only one Priest quest in the current Standard pool")
    for quest in quests:
        deck.add(quest, 1)
    fill(db, deck, 30)
    assert any("only one Quest" in str(i) for i in validate(deck, db).errors)


def test_two_deck_size_modifiers_is_an_error(db: CardDB):
    deck = make_deck(db)
    deck.add(db.resolve("Azalina Soulsever").card, 1)
    deck.add(db.resolve("Prince Renathal", format=FormatType.FT_STANDARD).card, 1)
    fill(db, deck, 20)
    assert any("set the deck size" in str(i) for i in validate(deck, db).errors)


def test_missing_early_game_is_a_warning_not_an_error(db: CardDB):
    deck = make_deck(db)
    expensive = [c for c in db.pool(CardClass.PRIEST, FormatType.FT_STANDARD) if c.cost >= 5]
    for card in expensive:
        if deck.size >= 30:
            break
        deck.add(card, min(card.max_copies, 30 - deck.size))
    report = validate(deck, db)
    assert report.ok  # legal, just bad
    assert any("cost 3 or less" in str(i) for i in report.warnings)
