import pytest

from hsdeck.carddb import CardDB, normalize_name
from hsdeck.enums import CardClass, FormatType


def test_database_loads(db: CardDB):
    assert len(db) > 1000
    assert db.hero_dbf(CardClass.PRIEST) == 813
    assert db.zodiac_year


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Reach the Equilibrium", "reach equilibrium"),
        ("Sir Finley, Sea Guide", "sir finley sea guide"),
        ("Y'Shaarj's Strike", "yshaarjs strike"),
    ],
)
def test_normalize_name(raw, expected):
    assert normalize_name(raw) == expected


def test_resolves_a_name_with_a_dropped_article(db: CardDB):
    """The user's 'Reach the Equilibrium' is really called 'Reach Equilibrium'."""
    card = db.resolve("Reach the Equilibrium").card
    assert card is not None
    assert card.name == "Reach Equilibrium"
    assert card.dbf == 117544


def test_prefers_the_legal_printing(db: CardDB):
    """'Azalina' is ambiguous; in Standard Priest it must mean Soulsever."""
    resolution = db.resolve("Azalina", card_class=CardClass.PRIEST, format=FormatType.FT_STANDARD)
    assert resolution.card.name == "Azalina Soulsever"
    assert resolution.renamed
    assert any(c.name == "Azalina Soulthief" for c in resolution.candidates)

    wild = db.resolve("Azalina Soulthief", format=FormatType.FT_WILD)
    assert wild.card.name == "Azalina Soulthief"


def test_partial_name_resolves(db: CardDB):
    assert db.resolve("Karov").card.name == "Karov the Broken"


def test_unknown_name_resolves_to_nothing(db: CardDB):
    assert db.resolve("Zzzz Not A Card Qqq").card is None


def test_pool_is_class_and_format_filtered(db: CardDB):
    pool = db.pool(CardClass.PRIEST, FormatType.FT_STANDARD)
    assert pool
    for card in pool:
        assert card.standard
        assert card.playable_by(CardClass.PRIEST)
    assert not any(
        int(CardClass.MAGE) in card.classes and int(CardClass.PRIEST) not in card.classes
        for card in pool
    )


def test_copy_limits_follow_rarity(db: CardDB):
    assert db.resolve("Azalina Soulsever").card.max_copies == 1
    assert db.resolve("Specter Specialist").card.max_copies == 2


def test_tag_search(db: CardDB):
    imbue = db.search(card_class=CardClass.PRIEST, format=FormatType.FT_STANDARD, tag="IMBUE")
    names = {c.name for c in imbue}
    assert {"Lunarwing Messenger", "Kaldorei Priestess"} <= names


def test_text_markup_is_stripped(db: CardDB):
    card = db.resolve("Reach Equilibrium").card
    assert "[x]" not in card.plain_text
    assert "<b>" not in card.plain_text
    assert "Holy spells" in card.plain_text
