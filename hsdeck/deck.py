"""The deck model."""

from __future__ import annotations

from dataclasses import dataclass, field

from .carddb import Card
from .deckstring import write_deckstring
from .enums import CardClass, FormatType

CURVE_BUCKETS: tuple[tuple[str, int, int], ...] = (
    ("1-2 Mana", 0, 2),
    ("3-4 Mana", 3, 4),
    ("5-6 Mana", 5, 6),
    ("7+ Mana", 7, 99),
)


@dataclass
class Slot:
    """One card entry in a decklist."""

    card: Card
    count: int
    required: bool = False
    reason: str = ""

    def __str__(self) -> str:
        return f"{self.count}x ({self.card.cost}) {self.card.name}"


@dataclass
class Deck:
    card_class: CardClass
    format: FormatType
    hero_dbf: int
    slots: list[Slot] = field(default_factory=list)
    name: str = "Untitled Deck"
    archetype: str = ""
    notes: list[str] = field(default_factory=list)

    # -- composition -------------------------------------------------------

    @property
    def size(self) -> int:
        return sum(slot.count for slot in self.slots)

    @property
    def cards(self) -> list[Card]:
        return [slot.card for slot in self.slots for _ in range(slot.count)]

    def count_of(self, card: Card) -> int:
        for slot in self.slots:
            if slot.card.dbf == card.dbf:
                return slot.count
        return 0

    def add(self, card: Card, count: int = 1, *, required: bool = False, reason: str = "") -> None:
        for slot in self.slots:
            if slot.card.dbf == card.dbf:
                slot.count += count
                slot.required = slot.required or required
                if reason and not slot.reason:
                    slot.reason = reason
                return
        self.slots.append(Slot(card, count, required=required, reason=reason))

    def sorted_slots(self) -> list[Slot]:
        return sorted(self.slots, key=lambda s: (s.card.cost, s.card.name))

    def curve(self) -> dict[str, int]:
        buckets = {label: 0 for label, _, _ in CURVE_BUCKETS}
        for slot in self.slots:
            for label, low, high in CURVE_BUCKETS:
                if low <= slot.card.cost <= high:
                    buckets[label] += slot.count
                    break
        return buckets

    def early_game_count(self, max_cost: int = 3) -> int:
        return sum(s.count for s in self.slots if s.card.cost <= max_cost)

    def average_cost(self) -> float:
        if not self.size:
            return 0.0
        return sum(s.card.cost * s.count for s in self.slots) / self.size

    # -- export ------------------------------------------------------------

    def entries(self) -> list[tuple[int, int]]:
        return sorted((slot.card.dbf, slot.count) for slot in self.slots)

    def deckstring(self) -> str:
        return write_deckstring(self.entries(), [self.hero_dbf], self.format)
