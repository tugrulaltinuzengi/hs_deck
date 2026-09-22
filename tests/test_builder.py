import pytest

from hsdeck.builder import DeckBuilder, build_deck, choose_curve_plan, suggest_deck_name
from hsdeck.carddb import CardDB
from hsdeck.constraints import DeckRequest
from hsdeck.enums import CardClass, FormatType
from hsdeck.meta import JsonMetaProvider
from hsdeck.validate import validate

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


@pytest.fixture(scope="module")
def case_study(db: CardDB):
    return build_deck(DeckRequest.from_dict(CASE_STUDY, db), db)


def test_case_study_is_legal_and_importable(case_study, db: CardDB):
    report = validate(case_study.deck, db)
    assert report.ok, [str(i) for i in report.issues]


def test_case_study_honours_the_requested_size(case_study):
    assert case_study.deck.size == 20


def test_every_mandatory_card_is_present(case_study):
    names = {slot.card.name for slot in case_study.deck.slots}
    assert {
        "Azalina Soulsever",
        "Karov the Broken",
        "Reach Equilibrium",
        "Specter Specialist",
    } <= names

    specter = next(s for s in case_study.deck.slots if s.card.name == "Specter Specialist")
    assert specter.count == 2

    imbue = sum(s.count for s in case_study.deck.slots if s.card.has_tag("IMBUE") and s.required)
    assert imbue == 4


def test_early_game_floor_is_met(case_study):
    deck = case_study.deck
    floor = case_study.curve_plan.early_floor
    assert deck.early_game_count() / deck.size >= floor


def test_survival_goal_selects_the_control_curve(case_study):
    assert case_study.curve_plan.name == "control / survival"


def test_curve_has_no_holes(case_study):
    curve = case_study.deck.curve()
    assert all(count > 0 for count in curve.values()), curve


def test_deckstring_round_trips(case_study, db: CardDB):
    from hsdeck.decklist import deck_from_deckstring

    rebuilt = deck_from_deckstring(case_study.deck.deckstring(), db)
    assert rebuilt.entries() == case_study.deck.entries()
    assert rebuilt.card_class is CardClass.PRIEST
    assert rebuilt.format is FormatType.FT_STANDARD


def test_build_is_deterministic(db: CardDB):
    first = build_deck(DeckRequest.from_dict(CASE_STUDY, db), db)
    second = build_deck(DeckRequest.from_dict(CASE_STUDY, db), db)
    assert first.deck.deckstring() == second.deck.deckstring()


def test_default_deck_is_thirty_cards(db: CardDB):
    request = DeckRequest.from_dict({"class": "Mage", "format": "Standard"}, db)
    result = build_deck(request, db)
    assert result.deck.size == 30
    assert validate(result.deck, db).ok


@pytest.mark.parametrize(
    "card_class",
    ["Priest", "Mage", "Warrior", "Rogue", "Druid", "Paladin", "Hunter", "Shaman",
     "Warlock", "DemonHunter", "DeathKnight"],
)
def test_every_class_builds_a_legal_thirty_card_deck(db: CardDB, card_class):
    request = DeckRequest.from_dict(
        {"class": card_class, "format": "Standard", "tactical_goal": "control the board"}, db
    )
    result = build_deck(request, db)
    report = validate(result.deck, db)
    assert result.deck.size == 30
    assert report.ok, [str(i) for i in report.issues]


def test_copy_limits_are_respected(db: CardDB):
    result = build_deck(
        DeckRequest.from_dict({"class": "Warrior", "format": "Standard"}, db), db
    )
    for slot in result.deck.slots:
        assert slot.count <= slot.card.max_copies


def test_deck_size_modifiers_are_never_added_unasked(db: CardDB):
    """Renathal/Azalina silently change the legal size, so they need asking for."""
    for card_class in ("Priest", "Warlock", "Warrior"):
        result = build_deck(
            DeckRequest.from_dict({"class": card_class, "format": "Standard"}, db), db
        )
        assert not any(s.card.dbf in db.deck_size_modifiers for s in result.deck.slots)
        assert result.deck.size == 30


def test_only_one_quest_is_included(db: CardDB):
    result = build_deck(
        DeckRequest.from_dict(
            {"class": "Priest", "format": "Standard", "primary_archetype": "Quest",
             "required_cards": ["Reach Equilibrium"]},
            db,
        ),
        db,
    )
    quests = sum(
        s.count for s in result.deck.slots if s.card.has_tag("QUEST") or s.card.has_tag("QUESTLINE")
    )
    assert quests == 1


def test_banned_cards_are_excluded(db: CardDB):
    plain = build_deck(DeckRequest.from_dict({"class": "Priest", "format": "Standard"}, db), db)
    victim = plain.deck.sorted_slots()[0].card.name

    banned = build_deck(
        DeckRequest.from_dict(
            {"class": "Priest", "format": "Standard", "banned_cards": [victim]}, db
        ),
        db,
    )
    assert victim not in {s.card.name for s in banned.deck.slots}


def test_highlander_archetype_forbids_duplicates(db: CardDB):
    result = build_deck(
        DeckRequest.from_dict(
            {"class": "Rogue", "format": "Standard", "primary_archetype": "Highlander"}, db
        ),
        db,
    )
    assert all(slot.count == 1 for slot in result.deck.slots)
    assert result.deck.size == 30


def test_aggro_goal_produces_a_cheaper_deck_than_control(db: CardDB):
    aggro = build_deck(
        DeckRequest.from_dict(
            {"class": "Hunter", "format": "Standard", "tactical_goal": "aggressive face damage"},
            db,
        ),
        db,
    )
    control = build_deck(
        DeckRequest.from_dict(
            {"class": "Hunter", "format": "Standard",
             "tactical_goal": "control the late game, survive early aggro"},
            db,
        ),
        db,
    )
    assert aggro.deck.average_cost() < control.deck.average_cost()


def test_unsatisfiable_tag_requirement_is_reported(db: CardDB):
    result = build_deck(
        DeckRequest.from_dict(
            {"class": "Priest", "format": "Standard",
             "required_cards": [{"tag": "IMBUE", "quantity": 40}]},
            db,
        ),
        db,
    )
    assert any("tagged IMBUE" in note for note in result.notes)


def test_meta_data_changes_the_picks(db: CardDB):
    baseline = build_deck(DeckRequest.from_dict({"class": "Shaman", "format": "Standard"}, db), db)
    outsider = next(
        card
        for card in db.pool(CardClass.SHAMAN, FormatType.FT_STANDARD)
        if card.dbf not in {s.card.dbf for s in baseline.deck.slots}
    )

    meta = JsonMetaProvider({"weight": 500.0, "cards": {str(outsider.dbf): 0.95}}, db)
    boosted = DeckBuilder(db, meta).build(
        DeckRequest.from_dict({"class": "Shaman", "format": "Standard"}, db)
    )
    assert outsider.dbf in {s.card.dbf for s in boosted.deck.slots}
    assert "cards" in boosted.meta_source


def test_wild_format_can_use_rotated_cards(db: CardDB):
    result = build_deck(
        DeckRequest.from_dict(
            {"class": "Priest", "format": "Wild", "required_cards": ["Azalina Soulthief"]}, db
        ),
        db,
    )
    assert "Azalina Soulthief" in {s.card.name for s in result.deck.slots}
    assert validate(result.deck, db).ok


def test_off_class_required_card_is_refused(db: CardDB):
    result = build_deck(
        DeckRequest.from_dict(
            {"class": "Priest", "format": "Standard", "required_cards": ["Fireball"]}, db
        ),
        db,
    )
    assert "Fireball" not in {s.card.name for s in result.deck.slots}
    assert any("not playable by Priest" in note for note in result.notes)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Survive early game aggro, dominate late game", "control / survival"),
        ("fast aggressive face deck", "aggro"),
        ("anti-aggro control", "control / survival"),
        ("", "midrange"),
    ],
)
def test_curve_plan_selection(text, expected):
    assert choose_curve_plan(text).name == expected


def test_deck_name_mentions_odd_sizes(db: CardDB):
    request = DeckRequest.from_dict(
        {"class": "Priest", "primary_archetype": "Quest / Control"}, db
    )
    assert suggest_deck_name(request, 20) == "Quest Priest (20-Card)"
    assert suggest_deck_name(request, 30) == "Quest Priest"
