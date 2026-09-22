"""Deck legality checks.

Two independent questions are answered:

* **legal** - would the game accept this deck in the requested format?
* **importable** - will the client accept the deckstring when it is pasted?

They differ.  A 25-card deck encodes into a perfectly well-formed deckstring,
but the client refuses to create a deck from it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .carddb import CardDB
from .deck import Deck
from .enums import CardClass, class_label, format_label

# Deck sizes the client accepts, and what unlocks each one.
STANDARD_DECK_SIZE = 30


@dataclass(frozen=True)
class Issue:
    level: str  # "error" | "warning"
    message: str

    def __str__(self) -> str:
        return f"[{self.level}] {self.message}"


@dataclass
class ValidationReport:
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, message: str) -> None:
        self.issues.append(Issue("error", message))

    def warn(self, message: str) -> None:
        self.issues.append(Issue("warning", message))

    def __bool__(self) -> bool:
        return self.ok


def expected_deck_size(deck: Deck, db: CardDB) -> tuple[int, str]:
    """The deck size the client will require, given the cards in the list."""
    for slot in deck.slots:
        size = db.deck_size_modifiers.get(slot.card.dbf)
        if size:
            return size, slot.card.name
    return STANDARD_DECK_SIZE, ""


def validate(deck: Deck, db: CardDB) -> ValidationReport:
    report = ValidationReport()

    required_size, modifier = expected_deck_size(deck, db)
    if deck.size != required_size:
        because = f" (required by {modifier})" if modifier else ""
        report.error(
            f"deck holds {deck.size} cards but must hold exactly "
            f"{required_size}{because}; the client will not import it"
        )

    for slot in deck.slots:
        card = slot.card
        limit = card.max_copies
        if slot.count > limit:
            kind = "Legendary" if card.is_legendary else "card"
            report.error(
                f"{slot.count}x {card.name}: a {kind} is limited to {limit} "
                f"{'copy' if limit == 1 else 'copies'}"
            )
        if not card.playable_by(deck.card_class):
            report.error(
                f"{card.name} cannot be played by {class_label(deck.card_class)}"
            )
        if not card.legal_in(deck.format):
            report.error(
                f"{card.name} is not legal in {format_label(deck.format)} "
                "(it has rotated to Wild)"
            )

    quests = [
        s for s in deck.slots if s.card.has_tag("QUEST") or s.card.has_tag("QUESTLINE")
    ]
    quest_total = sum(s.count for s in quests)
    if quest_total > 1:
        names = ", ".join(f"{s.count}x {s.card.name}" for s in quests)
        report.error(f"a deck may hold only one Quest, found {quest_total}: {names}")

    modifiers = [s.card.name for s in deck.slots if s.card.dbf in db.deck_size_modifiers]
    if len(modifiers) > 1:
        report.error(
            "two cards both try to set the deck size: " + ", ".join(modifiers)
        )

    if deck.card_class == CardClass.NEUTRAL:
        report.error("a deck must belong to a playable class, not Neutral")

    if deck.hero_dbf <= 0:
        report.error("missing hero portrait")

    # Advisory checks - the deck is legal, but probably not good.
    curve = deck.curve()
    if deck.size and curve["1-2 Mana"] == 0:
        report.warn("no 1-2 mana cards: the deck cannot contest the board early")
    if deck.size and curve["3-4 Mana"] == 0:
        report.warn("no 3-4 mana cards: there is a hole in the curve")
    if deck.size and deck.early_game_count() / deck.size < 0.30:
        report.warn(
            f"only {deck.early_game_count()}/{deck.size} cards cost 3 or less; "
            "aggressive decks will out-tempo this one"
        )

    return report
