"""Card database access and name resolution."""

from __future__ import annotations

import difflib
import gzip
import json
import re
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Iterator, Sequence

from .enums import CardClass, CardType, FormatType, Rarity, max_copies

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "cards.json.gz"

# Dropped when normalising a name for fuzzy matching, so that a request for
# "Reach the Equilibrium" still finds the card actually called
# "Reach Equilibrium".
_NOISE_WORDS = {"the", "a", "an", "of", "and"}
_PUNCT = re.compile(r"[^a-z0-9 ]+")
_MARKUP = re.compile(r"\[x\]|<[^>]+>|\$|@|_")


def normalize_name(name: str) -> str:
    text = _PUNCT.sub(" ", name.lower().replace("'", "").replace("’", ""))
    words = [w for w in text.split() if w and w not in _NOISE_WORDS]
    return " ".join(words)


def clean_text(text: str) -> str:
    """Strip Hearthstone's inline markup from card text."""
    return re.sub(r"\s+", " ", _MARKUP.sub(" ", text or "")).strip()


@dataclass(frozen=True)
class Card:
    dbf: int
    id: str
    name: str
    cost: int
    classes: tuple[int, ...]
    type: int
    rarity: int
    card_set: int
    standard: bool
    text: str
    tags: frozenset[str]
    attack: int = 0
    health: int = 0
    races: tuple[int, ...] = ()
    spell_school: int = 0

    @classmethod
    def from_record(cls, record: dict) -> "Card":
        return cls(
            dbf=record["dbf"],
            id=record["id"],
            name=record["name"],
            cost=record["cost"],
            classes=tuple(record["cls"]) or (int(CardClass.NEUTRAL),),
            type=record["type"],
            rarity=record["rarity"],
            card_set=record["set"],
            standard=record["std"],
            text=record.get("text", ""),
            tags=frozenset(record.get("tags", ())),
            attack=record.get("atk", 0),
            health=record.get("hp", 0),
            races=tuple(record.get("races", ())),
            spell_school=record.get("school", 0),
        )

    @cached_property
    def plain_text(self) -> str:
        return clean_text(self.text)

    @property
    def is_neutral(self) -> bool:
        return self.classes == (int(CardClass.NEUTRAL),)

    @property
    def is_legendary(self) -> bool:
        return self.rarity == Rarity.LEGENDARY

    @property
    def max_copies(self) -> int:
        return max_copies(self.rarity)

    def playable_by(self, card_class: CardClass) -> bool:
        return int(card_class) in self.classes or int(CardClass.NEUTRAL) in self.classes

    def legal_in(self, format: FormatType) -> bool:
        # Wild is the superset of everything collectible; Standard is the
        # rotating subset.  Classic/Twist run their own curated pools which
        # CardDefs.xml does not describe, so they are treated as Wild here.
        if format == FormatType.STANDARD:
            return self.standard
        return True

    def has_tag(self, tag: str) -> bool:
        return tag.upper() in self.tags

    def __str__(self) -> str:
        return f"{self.name} ({self.cost})"


@dataclass
class Resolution:
    """Outcome of resolving a user-supplied card name."""

    query: str
    card: Card | None
    candidates: list[Card] = field(default_factory=list)
    exact: bool = False

    @property
    def ambiguous(self) -> bool:
        return not self.exact and len(self.candidates) > 1

    @property
    def renamed(self) -> bool:
        """True when the card found is not spelled the way it was asked for."""
        if self.card is None:
            return False
        return self.query.strip().casefold() != self.card.name.casefold()


class CardDB:
    """Read-only view over the generated card database."""

    def __init__(self, payload: dict):
        self.schema = payload.get("schema", 1)
        self.game_build = str(payload.get("game_build", ""))
        self.generated = payload.get("generated", "")
        self.zodiac_year = payload.get("zodiac_year", "")
        self.standard_sets = tuple(payload.get("standard_sets", ()))
        self.heroes = {k: int(v) for k, v in payload.get("heroes", {}).items()}
        self.deck_size_modifiers = {
            int(k): int(v) for k, v in payload.get("deck_size_modifiers", {}).items()
        }

        self._cards: list[Card] = [Card.from_record(r) for r in payload["cards"]]
        self._by_dbf = {c.dbf: c for c in self._cards}
        self._by_id = {c.id: c for c in self._cards}
        self._by_name: dict[str, list[Card]] = {}
        for card in self._cards:
            self._by_name.setdefault(normalize_name(card.name), []).append(card)

    # -- loading -----------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path | None = None) -> "CardDB":
        path = Path(path) if path else DEFAULT_DB_PATH
        if not path.exists():
            raise FileNotFoundError(
                f"card database not found at {path}. "
                "Regenerate it with: python tools/build_carddb.py"
            )
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rb") as fp:
            return cls(json.load(fp))

    # -- access ------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._cards)

    def __iter__(self) -> Iterator[Card]:
        return iter(self._cards)

    @cached_property
    def tag_vocabulary(self) -> frozenset[str]:
        """Every mechanic tag name that appears on a collectible card."""
        return frozenset(tag for card in self._cards for tag in card.tags)

    def by_dbf(self, dbf_id: int) -> Card | None:
        return self._by_dbf.get(dbf_id)

    def by_id(self, card_id: str) -> Card | None:
        return self._by_id.get(card_id)

    def hero_dbf(self, card_class: CardClass) -> int:
        try:
            return self.heroes[CardClass(card_class).name]
        except KeyError as exc:
            raise ValueError(f"no hero portrait known for {card_class.name}") from exc

    def pool(
        self,
        card_class: CardClass,
        format: FormatType = FormatType.STANDARD,
        *,
        include_neutral: bool = True,
    ) -> list[Card]:
        """Every card the given class may legally run in the given format."""
        out = []
        for card in self._cards:
            if not card.legal_in(format):
                continue
            if int(card_class) in card.classes:
                out.append(card)
            elif include_neutral and int(CardClass.NEUTRAL) in card.classes:
                out.append(card)
        return out

    # -- name resolution ---------------------------------------------------

    def resolve(
        self,
        query: str,
        *,
        card_class: CardClass | None = None,
        format: FormatType | None = None,
    ) -> Resolution:
        """Find the card a user meant.

        Tries, in order: exact (normalised) name, name-token containment, then
        difflib similarity.  Candidates legal for the requested class/format are
        always preferred over ones that are not, which is what picks
        "Azalina Soulsever" (Standard Priest) over "Azalina Soulthief" (Wild).
        """
        needle = normalize_name(query)
        if not needle:
            return Resolution(query=query, card=None)

        def rank(cards: Sequence[Card]) -> list[Card]:
            def key(card: Card) -> tuple:
                class_ok = card_class is None or card.playable_by(card_class)
                class_own = card_class is not None and int(card_class) in card.classes
                format_ok = format is None or card.legal_in(format)
                return (
                    not format_ok,
                    not class_ok,
                    not class_own,
                    len(normalize_name(card.name)),
                    card.name,
                )

            return sorted(cards, key=key)

        exact = self._by_name.get(needle)
        if exact:
            ranked = rank(exact)
            return Resolution(query, ranked[0], ranked, exact=True)

        needle_words = set(needle.split())
        partial = [
            card
            for name, cards in self._by_name.items()
            if needle_words <= set(name.split()) or needle in name
            for card in cards
        ]
        if partial:
            ranked = rank(partial)
            return Resolution(query, ranked[0], ranked)

        close = difflib.get_close_matches(needle, self._by_name.keys(), n=5, cutoff=0.72)
        fuzzy = [card for name in close for card in self._by_name[name]]
        if fuzzy:
            ranked = rank(fuzzy)
            return Resolution(query, ranked[0], ranked)

        return Resolution(query, None)

    def search(
        self,
        text: str = "",
        *,
        card_class: CardClass | None = None,
        format: FormatType | None = None,
        tag: str | None = None,
        max_cost: int | None = None,
        card_type: CardType | None = None,
    ) -> list[Card]:
        """Free-text / tag search over names and rules text."""
        needle = text.lower().strip()
        out = []
        for card in self._cards:
            if format is not None and not card.legal_in(format):
                continue
            if card_class is not None and not card.playable_by(card_class):
                continue
            if tag is not None and not card.has_tag(tag):
                continue
            if max_cost is not None and card.cost > max_cost:
                continue
            if card_type is not None and card.type != int(card_type):
                continue
            if needle and needle not in card.name.lower() and needle not in card.plain_text.lower():
                continue
            out.append(card)
        out.sort(key=lambda c: (c.cost, c.name))
        return out
