"""Optional meta/winrate data.

hsdeck ships no winrate numbers.  Live statistics come from third-party
services (HSReplay and friends) that need network access and have their own
terms of use, so the builder treats them as an *injectable* input: supply a
JSON file and its numbers steer card selection, supply nothing and selection
falls back to the documented heuristic in :mod:`hsdeck.scoring`.

Expected file shape (keys may be DBF ids or card names)::

    {
      "weight": 12.0,
      "cards": {"127065": 0.54, "Reach Equilibrium": 0.51},
      "baseline": 0.50
    }

Each card's contribution is ``(winrate - baseline) * weight``, so a card 4
points above baseline with the default weight adds ~0.5 to its score.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from .carddb import Card, CardDB


class MetaProvider(Protocol):
    """Anything that can express an opinion about a card's meta standing."""

    def score(self, card: Card) -> float:
        ...

    @property
    def source(self) -> str:
        ...


class NullMetaProvider:
    """No meta data - every card scores 0 and the heuristic decides alone."""

    def score(self, card: Card) -> float:
        return 0.0

    @property
    def source(self) -> str:
        return "none (heuristic scoring only)"


class JsonMetaProvider:
    """Winrate data loaded from a local JSON file."""

    def __init__(self, payload: dict, db: CardDB, label: str = "json"):
        self.weight = float(payload.get("weight", 12.0))
        self.baseline = float(payload.get("baseline", 0.5))
        self._label = label
        self._by_dbf: dict[int, float] = {}

        for key, value in (payload.get("cards") or {}).items():
            dbf: int | None = None
            if isinstance(key, int) or str(key).isdigit():
                dbf = int(key)
            else:
                resolution = db.resolve(str(key))
                if resolution.card:
                    dbf = resolution.card.dbf
            if dbf is not None:
                self._by_dbf[dbf] = float(value)

    @classmethod
    def from_file(cls, path: str | Path, db: CardDB) -> "JsonMetaProvider":
        path = Path(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(payload, db, label=path.name)

    def score(self, card: Card) -> float:
        winrate = self._by_dbf.get(card.dbf)
        if winrate is None:
            return 0.0
        return (winrate - self.baseline) * self.weight

    @property
    def source(self) -> str:
        return f"{self._label} ({len(self._by_dbf)} cards, baseline {self.baseline:.0%})"
