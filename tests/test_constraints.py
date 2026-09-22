import pytest

from hsdeck.carddb import CardDB
from hsdeck.constraints import (
    CardRequirement,
    DeckRequest,
    TagRequirement,
    infer_deck_size,
)
from hsdeck.enums import CardClass, FormatType

CASE_STUDY = {
    "class": "Priest",
    "format": "Standard",
    "deck_size": 20,
    "required_cards": [
        "Azalina",
        "Karov",
        "Reach the Equilibrium",
        {"name": "Imbue priest cards", "quantity": 4},
        {"name": "Specter Specialist", "quantity": 2},
    ],
    "primary_archetype": "Quest / Control / Survival",
    "tactical_goal": "Survive early game aggro, dominate late game",
    "target_winrate_bias": "Anti-Aggro / Value Engine",
}


def test_parses_the_specification_case_study(db: CardDB):
    request = DeckRequest.from_dict(CASE_STUDY, db)

    assert request.card_class is CardClass.PRIEST
    assert request.format is FormatType.STANDARD
    assert request.deck_size == 20

    named = {r.name: r.quantity for r in request.required if isinstance(r, CardRequirement)}
    assert named == {
        "Azalina Soulsever": 1,
        "Karov the Broken": 1,
        "Reach Equilibrium": 1,
        "Specter Specialist": 2,
    }

    tags = [r for r in request.required if isinstance(r, TagRequirement)]
    assert len(tags) == 1
    assert tags[0].tag == "IMBUE"
    assert tags[0].quantity == 4
    assert tags[0].class_only is True

    assert any("Azalina Soulsever" in note for note in request.notes)


def test_plural_mechanic_phrase_becomes_a_tag_requirement(db: CardDB):
    request = DeckRequest.from_dict(
        {"class": "Priest", "required_cards": [{"name": "2 Taunt cards", "quantity": 2}]}, db
    )
    assert isinstance(request.required[0], TagRequirement)
    assert request.required[0].tag == "TAUNT"


def test_quantity_above_the_copy_limit_is_read_as_a_group(db: CardDB):
    request = DeckRequest.from_dict(
        {"class": "Priest", "required_cards": [{"name": "Imbue", "quantity": 4}]}, db
    )
    assert isinstance(request.required[0], TagRequirement)


def test_explicit_tag_key(db: CardDB):
    request = DeckRequest.from_dict(
        {"class": "Mage", "required_cards": [{"tag": "quest", "quantity": 1}]}, db
    )
    assert request.required == [TagRequirement("QUEST", 1, False, "")]


def test_unfindable_card_is_dropped_with_a_note(db: CardDB):
    request = DeckRequest.from_dict(
        {"class": "Priest", "required_cards": ["Qqzzx Nonexistent"]}, db
    )
    assert request.required == []
    assert any("could not find" in note for note in request.notes)


def test_missing_class_is_an_error(db: CardDB):
    with pytest.raises(ValueError):
        DeckRequest.from_dict({"format": "Standard"}, db)


def test_deck_size_defaults_to_thirty(db: CardDB):
    assert infer_deck_size([], db)[0] == 30


def test_azalina_sets_the_deck_size_to_twenty(db: CardDB):
    azalina = db.resolve("Azalina Soulsever").card
    size, note = infer_deck_size([azalina], db)
    assert size == 20
    assert "Azalina Soulsever" in note


def test_renathal_sets_the_deck_size_to_forty(db: CardDB):
    renathal = db.resolve("Prince Renathal", format=FormatType.STANDARD).card
    assert infer_deck_size([renathal], db)[0] == 40


def test_conflicting_explicit_size_is_reported(db: CardDB):
    azalina = db.resolve("Azalina Soulsever").card
    size, note = infer_deck_size([azalina], db, explicit=30)
    assert size == 30
    assert "disagrees" in note
