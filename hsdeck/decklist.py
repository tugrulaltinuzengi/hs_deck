"""Reading and writing the plain-text decklist format.

This is the block Hearthstone puts on the clipboard, e.g.::

    ### My Deck
    # Class: Priest
    # Format: Standard
    #
    # 2x (3) Specter Specialist
    #
    AAECAa0G...

Lines may be given with or without the leading ``#``, and the ``(cost)`` part
is optional, so hand-typed lists parse too.
"""

from __future__ import annotations

import re

from .carddb import CardDB
from .deck import Deck
from .deckstring import ParsedDeck, parse_deckstring
from .enums import CardClass, FormatType

_LINE = re.compile(
    r"^\s*#?\s*(?P<count>\d+)\s*[x*]?\s*(?:\((?P<cost>\d+)\)\s*)?(?P<name>.+?)\s*$"
)
_CLASS = re.compile(r"^\s*#\s*class\s*:\s*(?P<value>.+?)\s*$", re.I)
_FORMAT = re.compile(r"^\s*#\s*format\s*:\s*(?P<value>.+?)\s*$", re.I)
_TITLE = re.compile(r"^\s*###\s*(?P<value>.+?)\s*$")


class DecklistError(ValueError):
    pass


def parse_decklist(text: str, db: CardDB) -> Deck:
    """Build a Deck from a text decklist, inferring the class if not stated."""
    card_class: CardClass | None = None
    format = FormatType.STANDARD
    title = ""
    entries: list[tuple[int, str]] = []

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.strip() in {"#", "```", "```text"}:
            continue

        if match := _TITLE.match(line):
            title = match.group("value")
            continue
        if match := _CLASS.match(line):
            card_class = CardClass.parse(match.group("value"))
            continue
        if match := _FORMAT.match(line):
            format = FormatType.parse(match.group("value"))
            continue
        if line.lstrip().startswith("#") and ":" in line and not _LINE.match(line):
            continue  # some other comment header
        if match := _LINE.match(line):
            entries.append((int(match.group("count")), match.group("name")))

    if not entries:
        raise DecklistError("no card lines found in the decklist")

    resolved = []
    for count, name in entries:
        resolution = db.resolve(name, card_class=card_class, format=format)
        if resolution.card is None:
            raise DecklistError(f"unknown card: {name!r}")
        resolved.append((count, resolution.card))

    if card_class is None:
        classes = {
            cls
            for _, card in resolved
            for cls in card.classes
            if cls != int(CardClass.NEUTRAL)
        }
        if len(classes) != 1:
            raise DecklistError(
                "could not infer the deck's class; add a '# Class: <name>' line"
            )
        card_class = CardClass(classes.pop())

    deck = Deck(
        card_class=card_class,
        format=format,
        hero_dbf=db.hero_dbf(card_class),
        name=title or f"{card_class.name.title()} Deck",
    )
    for count, card in resolved:
        deck.add(card, count)
    return deck


def deck_from_deckstring(deckstring: str, db: CardDB, name: str = "") -> Deck:
    """Rebuild a named Deck from a deckstring, looking every DBF id up."""
    parsed: ParsedDeck = parse_deckstring(deckstring)
    if not parsed.heroes:
        raise DecklistError("deckstring contains no hero")

    hero_dbf = parsed.heroes[0]
    card_class = CardClass.INVALID
    for name_, dbf in db.heroes.items():
        if dbf == hero_dbf:
            card_class = CardClass[name_]
            break

    if card_class == CardClass.INVALID:
        # An alternate hero skin: fall back to whatever the cards agree on.
        classes = {
            cls
            for dbf, _ in parsed.cards
            if (card := db.by_dbf(dbf))
            for cls in card.classes
            if cls != int(CardClass.NEUTRAL)
        }
        if len(classes) == 1:
            card_class = CardClass(classes.pop())

    deck = Deck(
        card_class=card_class,
        format=parsed.format,
        hero_dbf=hero_dbf,
        name=name or f"{card_class.name.title()} Deck",
    )
    for dbf, count in parsed.cards:
        card = db.by_dbf(dbf)
        if card is None:
            raise DecklistError(
                f"deckstring references unknown card {dbf}; the bundled card "
                "database may be older than the deck"
            )
        deck.add(card, count)
    return deck
