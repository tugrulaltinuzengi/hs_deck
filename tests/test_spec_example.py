"""The worked example in AGENT.md section 6 does not survive the card database.

These tests pin each defect, so that if a future card database (a new set, a
rotation) changes one of them, the claims in README.md get re-examined rather
than silently going stale.
"""

import pytest

from hsdeck.carddb import CardDB
from hsdeck.deckstring import DeckstringError, parse_deckstring
from hsdeck.enums import CardClass, FormatType

SPEC_DECKSTRING = (
    "AAECAa0GCAmXoATSpQOitgO3swPjtAOT1APm5AOL6wMMoAegkwOXowS+nwTBnwT41AS63AT83gT24wS15AIA"
)

# The "20-card" list exactly as section 6 prints it.
SPEC_LIST = [
    (1, "Seek Guidance"),
    (2, "Holy Smite"),
    (2, "Specter Specialist"),
    (2, "Imbued Flash"),
    (2, "Imbued Shieldbearer"),
    (2, "Shadow Word: Devastate"),
    (2, "Hysteria"),
    (1, "Reach the Equilibrium"),
    (2, "Lightshower Elemental"),
    (1, "Azalina Soulthief"),
    (1, "Karov"),
    (1, "Xyrella, the Devout"),
]


def test_spec_deckstring_does_not_parse():
    with pytest.raises(DeckstringError):
        parse_deckstring(SPEC_DECKSTRING)


def test_spec_list_is_nineteen_cards_not_twenty():
    assert sum(count for count, _ in SPEC_LIST) == 19


@pytest.mark.parametrize(
    "name",
    ["Imbued Flash", "Imbued Shieldbearer", "Shadow Word: Devastate", "Xyrella, the Devout"],
)
def test_invented_card_names(db: CardDB, name):
    """No card is spelled this way; the resolver either misses or substitutes."""
    resolution = db.resolve(name, card_class=CardClass.PRIEST, format=FormatType.FT_STANDARD)
    assert resolution.card is None or resolution.renamed


def test_reach_the_equilibrium_is_misnamed(db: CardDB):
    assert db.resolve("Reach the Equilibrium").card.name == "Reach Equilibrium"


@pytest.mark.parametrize(
    "name", ["Seek Guidance", "Hysteria", "Mass Dispel", "Azalina Soulthief"]
)
def test_cards_listed_as_standard_are_wild_only(db: CardDB, name):
    card = db.resolve(name, format=FormatType.FT_WILD).card
    assert card is not None
    assert not card.standard
    assert not card.legal_in(FormatType.FT_STANDARD)


def test_only_soulsever_makes_a_twenty_card_deck(db: CardDB):
    soulsever = db.resolve("Azalina Soulsever").card
    soulthief = db.resolve("Azalina Soulthief", format=FormatType.FT_WILD).card

    assert db.deck_size_modifiers.get(soulsever.dbf) == 20
    assert soulthief.dbf not in db.deck_size_modifiers


def test_specter_specialist_costs_three(db: CardDB):
    assert db.resolve("Specter Specialist").card.cost == 3


def test_hero_dbf_ids(db: CardDB):
    """Section 4 offers "Priest Hero = 813 or 637"; 637 is Mage."""
    assert db.hero_dbf(CardClass.PRIEST) == 813
    assert db.hero_dbf(CardClass.MAGE) == 637
