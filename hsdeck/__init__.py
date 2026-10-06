"""hsdeck - constraint-driven Hearthstone deck construction and deckstrings.

    from hsdeck import CardDB, DeckRequest, build_deck, render_markdown

    db = CardDB.load()
    request = DeckRequest.from_dict({"class": "Priest", "format": "Standard"}, db)
    result = build_deck(request, db)
    print(result.deck.deckstring())
"""

from .builder import BuildResult, DeckBuilder, build_deck
from .carddb import Card, CardDB, Resolution
from .constraints import CardRequirement, DeckRequest, TagRequirement
from .deck import Deck, Slot
from .decklist import deck_from_deckstring, parse_decklist
from .deckstring import DeckstringError, ParsedDeck, parse_deckstring, write_deckstring
from .enums import CardClass, CardType, FormatType, Rarity
from .meta import JsonMetaProvider, MetaProvider, NullMetaProvider
from .render import deck_code_block, render_markdown
from .validate import ValidationReport, validate

__version__ = "0.1.0"

__all__ = [
    "BuildResult", "Card", "CardClass", "CardDB", "CardRequirement", "CardType",
    "Deck", "DeckBuilder", "DeckRequest", "DeckstringError", "FormatType",
    "JsonMetaProvider", "MetaProvider", "NullMetaProvider", "ParsedDeck",
    "Rarity", "Resolution", "Slot", "TagRequirement", "ValidationReport",
    "build_deck", "deck_code_block", "deck_from_deckstring", "parse_deckstring",
    "parse_decklist", "render_markdown", "validate", "write_deckstring",
]
