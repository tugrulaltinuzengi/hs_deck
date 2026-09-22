"""Parsing user deck requests into a structured, machine-checkable request.

The input schema is the one from the agent specification::

    {
      "class": "Priest",
      "format": "Standard",
      "deck_size": 20,
      "required_cards": [
        "Azalina",
        {"name": "Imbue priest cards", "quantity": 4},
        {"tag": "QUEST", "quantity": 1}
      ],
      "primary_archetype": "Quest / Control",
      "tactical_goal": "Survive early aggro, win late",
      "target_winrate_bias": "Anti-Aggro"
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from .carddb import CardDB, normalize_name
from .enums import CardClass, FormatType

# Words that mark a requirement as "a group of cards", not one specific card.
_GROUP_MARKERS = {"cards", "card", "package", "pkg", "suite", "tools", "spells", "minions"}


@dataclass(frozen=True)
class CardRequirement:
    """A specific card that must appear, at a specific count."""

    name: str
    quantity: int = 1

    def describe(self) -> str:
        return f"{self.quantity}x {self.name}"


@dataclass(frozen=True)
class TagRequirement:
    """N cards sharing a mechanic, e.g. "4 Imbue priest cards"."""

    tag: str
    quantity: int
    class_only: bool = False
    source: str = ""

    def describe(self) -> str:
        scope = "class" if self.class_only else "any"
        return f"{self.quantity}x [{self.tag} / {scope}]" + (
            f" (from {self.source!r})" if self.source else ""
        )


Requirement = CardRequirement | TagRequirement


@dataclass
class DeckRequest:
    """A fully parsed deck-building request."""

    card_class: CardClass
    format: FormatType = FormatType.STANDARD
    deck_size: int | None = None  # None -> inferred from required cards
    required: list[Requirement] = field(default_factory=list)
    banned: list[str] = field(default_factory=list)
    archetype: str = ""
    tactical_goal: str = ""
    winrate_bias: str = ""
    notes: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any], db: CardDB) -> "DeckRequest":
        if "class" not in payload:
            raise ValueError("deck request must specify a 'class'")
        card_class = CardClass.parse(payload["class"])
        format = FormatType.parse(payload.get("format", "Standard"))

        notes: list[str] = []
        required: list[Requirement] = []
        for entry in payload.get("required_cards", ()):
            requirement, note = _parse_requirement(entry, db, card_class, format)
            if requirement is not None:
                required.append(requirement)
            if note:
                notes.append(note)

        deck_size = payload.get("deck_size")
        if deck_size is not None:
            deck_size = int(deck_size)

        return cls(
            card_class=card_class,
            format=format,
            deck_size=deck_size,
            required=required,
            banned=[str(b) for b in payload.get("banned_cards", ())],
            archetype=str(payload.get("primary_archetype", "")),
            tactical_goal=str(payload.get("tactical_goal", "")),
            winrate_bias=str(payload.get("target_winrate_bias", "")),
            notes=notes,
        )

    @classmethod
    def from_json(cls, text: str | Path, db: CardDB) -> "DeckRequest":
        if isinstance(text, Path):
            text = text.read_text(encoding="utf-8")
        return cls.from_dict(json.loads(text), db)

    def describe(self) -> str:
        parts = [f"{self.card_class.name.title()} / {self.format.name.title()}"]
        if self.deck_size:
            parts.append(f"{self.deck_size} cards")
        if self.archetype:
            parts.append(self.archetype)
        return " - ".join(parts)


def _parse_requirement(
    entry: Any,
    db: CardDB,
    card_class: CardClass,
    format: FormatType,
) -> tuple[Requirement | None, str]:
    """Turn one ``required_cards`` entry into a requirement.

    A plain string, or a dict with ``name``, normally means one specific card.
    It is read as a *group* requirement instead when it cannot mean a single
    card: an explicit ``tag`` key, a quantity above the 2-copy limit, or a
    plural phrase naming a mechanic ("4 Imbue priest cards").
    """
    if isinstance(entry, str):
        name, quantity, tag, class_only = entry, 1, None, False
    elif isinstance(entry, dict):
        name = str(entry.get("name", "")).strip()
        quantity = int(entry.get("quantity", 1))
        tag = entry.get("tag")
        class_only = bool(entry.get("class_only", False))
    else:
        return None, f"ignored unrecognised required_cards entry: {entry!r}"

    if quantity < 1:
        return None, f"ignored requirement with non-positive quantity: {entry!r}"

    if tag:
        return TagRequirement(str(tag).upper(), quantity, class_only, name), ""

    if not name:
        return None, f"ignored requirement without a name: {entry!r}"

    words = set(normalize_name(name).split())
    looks_like_group = bool(words & _GROUP_MARKERS) or quantity > 2
    if looks_like_group:
        requirement, note = _as_tag_requirement(name, quantity, db, card_class)
        if requirement is not None:
            return requirement, note

    resolution = db.resolve(name, card_class=card_class, format=format)
    if resolution.card is None:
        return None, f"could not find any card matching {name!r} - requirement dropped"

    note = ""
    if resolution.renamed:
        note = f"{name!r} resolved to {resolution.card.name!r}"
        if resolution.ambiguous:
            others = ", ".join(c.name for c in resolution.candidates[1:4])
            note += f" (other matches: {others})"
    return CardRequirement(resolution.card.name, quantity), note


def _as_tag_requirement(
    name: str,
    quantity: int,
    db: CardDB,
    card_class: CardClass,
) -> tuple[TagRequirement | None, str]:
    """Match a phrase like "4 Imbue priest cards" against the tag vocabulary."""
    words = normalize_name(name).split()
    class_only = card_class.name.lower() in words

    for word in words:
        candidate = word.upper()
        if candidate in db.tag_vocabulary:
            return (
                TagRequirement(candidate, quantity, class_only, name),
                f"{name!r} read as {quantity} cards tagged {candidate}"
                + (f" ({card_class.name.title()} only)" if class_only else ""),
            )
    return None, ""


def infer_deck_size(
    required_cards: Sequence,
    db: CardDB,
    explicit: int | None = None,
) -> tuple[int, str]:
    """Work out how many cards the deck must hold.

    Cards like Prince Renathal (40) and Azalina Soulsever (20) override the
    normal 30.  An explicit request wins, but a mismatch is reported.
    """
    modifier_size = None
    modifier_card = None
    for card in required_cards:
        size = db.deck_size_modifiers.get(getattr(card, "dbf", None))
        if size:
            modifier_size, modifier_card = size, card
            break

    if explicit is None:
        if modifier_size:
            return modifier_size, f"deck size set to {modifier_size} by {modifier_card.name}"
        return 30, "deck size defaulted to 30"

    if modifier_size and explicit != modifier_size:
        return (
            explicit,
            f"requested size {explicit} disagrees with {modifier_card.name}, "
            f"which requires exactly {modifier_size} cards",
        )
    if not modifier_size and explicit != 30:
        return (
            explicit,
            f"requested size {explicit} is non-standard; no deck-size-modifying "
            "card (Prince Renathal / Azalina Soulsever) is in the list",
        )
    return explicit, ""
