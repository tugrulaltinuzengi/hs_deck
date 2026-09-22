"""Deck construction.

The builder is a greedy, quota-driven filler:

1. mandatory cards are placed first and never displaced;
2. the mana curve is divided into buckets with target counts scaled to the
   deck size, plus a hard floor on cheap cards for decks whose stated goal is
   to survive the early game;
3. every remaining slot goes to the highest-scoring legal candidate in
   whichever bucket is furthest below its target.

Scores come from :mod:`hsdeck.scoring` (role fit, synergy with the mandatory
package, card-quality prior) plus an optional meta provider.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .carddb import Card, CardDB
from .constraints import CardRequirement, DeckRequest, TagRequirement, infer_deck_size
from .deck import CURVE_BUCKETS, Deck
from .meta import MetaProvider, NullMetaProvider
from .scoring import (
    ScoredCard,
    SynergyProfile,
    count_keywords,
    goal_profile,
    score_card,
)


@dataclass(frozen=True)
class CurvePlan:
    """Target shape of the mana curve, as fractions of the deck."""

    name: str
    fractions: tuple[float, float, float, float]
    early_floor: float  # minimum fraction of cards costing <= 3

    def targets(self, deck_size: int) -> dict[str, int]:
        return {
            label: round(fraction * deck_size)
            for (label, _, _), fraction in zip(CURVE_BUCKETS, self.fractions)
        }


CURVE_PLANS: tuple[tuple[tuple[str, ...], CurvePlan], ...] = (
    (
        ("aggro", "aggressive", "face", "burn"),
        CurvePlan("aggro", (0.50, 0.35, 0.12, 0.03), 0.60),
    ),
    (
        ("anti-aggro", "survive", "survival", "control", "late game", "late-game",
         "stabilize", "stabilise", "attrition", "fatigue", "value engine"),
        # The spec's rule: a deck that wants to reach the late game needs
        # 40-50% of its cards at 1-3 mana to survive getting there.
        CurvePlan("control / survival", (0.32, 0.30, 0.21, 0.17), 0.40),
    ),
    (
        ("combo", "otk", "quest", "questline"),
        CurvePlan("combo / quest", (0.38, 0.32, 0.18, 0.12), 0.45),
    ),
)

DEFAULT_CURVE_PLAN = CurvePlan("midrange", (0.35, 0.33, 0.20, 0.12), 0.40)

# Words in an archetype that mean "no duplicates at all".
_SINGLETON_MARKERS = ("highlander", "singleton", "reno", "no duplicates")


def choose_curve_plan(*descriptions: str) -> CurvePlan:
    """Pick the curve whose keywords the request matches most strongly."""
    haystack = " ".join(d.lower() for d in descriptions if d)
    best, best_hits = DEFAULT_CURVE_PLAN, 0
    for keys, plan in CURVE_PLANS:
        hits = count_keywords(haystack, keys)
        if hits > best_hits:
            best, best_hits = plan, hits
    return best


def suggest_deck_name(request: DeckRequest, deck_size: int) -> str:
    """A short deck name: leading archetype word, class, and odd deck sizes."""
    archetype = request.archetype.split("/")[0].strip()
    name = f"{archetype} {request.card_class.name.title()}".strip()
    if not archetype:
        name = f"Custom {request.card_class.name.title()}"
    if deck_size != 30:
        name += f" ({deck_size}-Card)"
    return name


@dataclass
class BuildResult:
    deck: Deck
    request: DeckRequest
    curve_plan: CurvePlan
    synergy: SynergyProfile
    deck_size: int
    meta_source: str
    scores: dict[int, ScoredCard] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


class DeckBuilder:
    def __init__(
        self,
        db: CardDB,
        meta: MetaProvider | None = None,
    ):
        self.db = db
        self.meta = meta or NullMetaProvider()

    # -- public API --------------------------------------------------------

    def build(self, request: DeckRequest) -> BuildResult:
        notes = list(request.notes)
        card_class = request.card_class
        format = request.format

        required_slots, req_notes = self._resolve_requirements(request)
        notes.extend(req_notes)

        required_cards = [card for card, _, _ in required_slots]
        deck_size, size_note = infer_deck_size(required_cards, self.db, request.deck_size)
        if size_note:
            notes.append(size_note)

        synergy = SynergyProfile.from_cards(required_cards)
        profile = goal_profile(request.tactical_goal, request.archetype, request.winrate_bias)
        curve_plan = choose_curve_plan(
            request.tactical_goal, request.archetype, request.winrate_bias
        )

        deck = Deck(
            card_class=card_class,
            format=format,
            hero_dbf=self.db.hero_dbf(card_class),
            name=suggest_deck_name(request, deck_size),
            archetype=request.archetype,
        )

        singleton = any(
            marker in f"{request.archetype} {request.tactical_goal}".lower()
            for marker in _SINGLETON_MARKERS
        )

        placed = 0
        for card, count, reason in required_slots:
            allowed = 1 if singleton else card.max_copies
            count = min(count, allowed)
            if placed + count > deck_size:
                count = deck_size - placed
            if count <= 0:
                notes.append(f"no room left for required card {card.name}")
                continue
            deck.add(card, count, required=True, reason=reason)
            placed += count

        scores = self._score_pool(request, profile, synergy, deck)
        self._fill(deck, deck_size, curve_plan, scores, singleton=singleton)

        if deck.size != deck_size:
            notes.append(
                f"could only assemble {deck.size} of {deck_size} cards from the "
                f"legal {card_class.name.title()} pool in {format.name.title()}"
            )

        deck.notes = notes
        return BuildResult(
            deck=deck,
            request=request,
            curve_plan=curve_plan,
            synergy=synergy,
            deck_size=deck_size,
            meta_source=self.meta.source,
            scores=scores,
            notes=notes,
        )

    # -- internals ---------------------------------------------------------

    def _resolve_requirements(
        self, request: DeckRequest
    ) -> tuple[list[tuple[Card, int, str]], list[str]]:
        """Turn requirements into concrete (card, count, reason) triples."""
        notes: list[str] = []
        out: list[tuple[Card, int, str]] = []
        seen: set[int] = set()

        # Named cards first: they define the synergy axis the tag requirements
        # are then scored against.
        for requirement in request.required:
            if not isinstance(requirement, CardRequirement):
                continue
            resolution = self.db.resolve(
                requirement.name, card_class=request.card_class, format=request.format
            )
            card = resolution.card
            if card is None:
                notes.append(f"required card {requirement.name!r} not found - skipped")
                continue
            if not card.playable_by(request.card_class):
                notes.append(
                    f"{card.name} is not playable by {request.card_class.name.title()} "
                    "- skipped"
                )
                continue
            if not card.legal_in(request.format):
                notes.append(
                    f"{card.name} is not legal in {request.format.name.title()} "
                    "but was explicitly required - kept, deck will not be tournament legal"
                )
            if card.dbf in seen:
                continue
            seen.add(card.dbf)
            out.append((card, requirement.quantity, "explicitly requested"))

        named = [card for card, _, _ in out]
        synergy = SynergyProfile.from_cards(named)
        profile = goal_profile(request.tactical_goal, request.archetype, request.winrate_bias)

        for requirement in request.required:
            if not isinstance(requirement, TagRequirement):
                continue
            picks, note = self._pick_for_tag(requirement, request, profile, synergy, seen)
            out.extend(picks)
            if note:
                notes.append(note)

        return out, notes

    def _pick_for_tag(
        self,
        requirement: TagRequirement,
        request: DeckRequest,
        profile: dict[str, float],
        synergy: SynergyProfile,
        seen: set[int],
    ) -> tuple[list[tuple[Card, int, str]], str]:
        """Choose the best N cards carrying a required mechanic."""
        candidates = [
            card
            for card in self.db.pool(request.card_class, request.format)
            if card.has_tag(requirement.tag)
            and card.dbf not in seen
            and self._is_selectable(card, request)
            and (
                not requirement.class_only
                or int(request.card_class) in card.classes
            )
        ]
        scored = sorted(
            (
                score_card(
                    card,
                    card_class=request.card_class,
                    profile=profile,
                    synergy=synergy,
                    meta_score=self.meta.score(card),
                )
                for card in candidates
            ),
            key=lambda s: (-s.total, s.card.dbf),
        )

        picks: list[tuple[Card, int, str]] = []
        remaining = requirement.quantity
        label = requirement.source or f"{requirement.tag} package"
        for entry in scored:
            if remaining <= 0:
                break
            count = min(entry.card.max_copies, remaining)
            why = entry.reason()
            picks.append((entry.card, count, f"{label} ({why})" if why else label))
            seen.add(entry.card.dbf)
            remaining -= count

        if remaining > 0:
            scope = f"{request.card_class.name.title()} " if requirement.class_only else ""
            return picks, (
                f"only {requirement.quantity - remaining} of {requirement.quantity} "
                f"{scope}cards tagged {requirement.tag} exist in "
                f"{request.format.name.title()} - filled what was available"
            )
        return picks, ""

    def _is_selectable(self, card: Card, request: DeckRequest) -> bool:
        """Cards the builder may add on its own initiative."""
        if card.dbf in self.db.deck_size_modifiers:
            # Renathal/Azalina silently change the legal deck size; only add
            # them when the user asked for them.
            return False
        banned = {name.casefold() for name in request.banned}
        return card.name.casefold() not in banned

    def _score_pool(
        self,
        request: DeckRequest,
        profile: dict[str, float],
        synergy: SynergyProfile,
        deck: Deck,
    ) -> dict[int, ScoredCard]:
        scores: dict[int, ScoredCard] = {}
        for card in self.db.pool(request.card_class, request.format):
            if not self._is_selectable(card, request):
                continue
            scores[card.dbf] = score_card(
                card,
                card_class=request.card_class,
                profile=profile,
                synergy=synergy,
                meta_score=self.meta.score(card),
            )
        # Keep required cards scoreable too, for the explanations in the output.
        for slot in deck.slots:
            scores.setdefault(
                slot.card.dbf,
                score_card(
                    slot.card,
                    card_class=request.card_class,
                    profile=profile,
                    synergy=synergy,
                    meta_score=self.meta.score(slot.card),
                ),
            )
        return scores

    def _fill(
        self,
        deck: Deck,
        deck_size: int,
        plan: CurvePlan,
        scores: dict[int, ScoredCard],
        *,
        singleton: bool,
    ) -> None:
        targets = plan.targets(deck_size)
        early_target = math.ceil(plan.early_floor * deck_size)

        # One quest per deck is the game's rule; a second one is dead weight.
        quests_placed = sum(
            1 for s in deck.slots if s.card.has_tag("QUEST") or s.card.has_tag("QUESTLINE")
        )

        ranked = sorted(scores.values(), key=lambda s: (-s.total, s.card.dbf))

        guard = 0
        while deck.size < deck_size and guard < deck_size * 50:
            guard += 1
            remaining = deck_size - deck.size
            early_deficit = early_target - deck.early_game_count()

            if early_deficit > 0:
                bucket_range: tuple[int, int] | None = (0, 3)
                budget = min(remaining, early_deficit)
            else:
                bucket = self._neediest_bucket(deck, targets)
                if bucket is None:
                    bucket_range, budget = None, remaining
                else:
                    label, low, high = bucket
                    bucket_range = (low, high)
                    budget = min(remaining, max(1, targets[label] - deck.curve()[label]))

            pick = self._best_candidate(
                deck, ranked, bucket_range, singleton=singleton, quests_placed=quests_placed
            )
            if pick is None and bucket_range is not None:
                # Nothing left in the preferred bucket - open it up.
                pick = self._best_candidate(
                    deck, ranked, None, singleton=singleton, quests_placed=quests_placed
                )
                budget = remaining
            if pick is None:
                return  # pool exhausted

            allowed = 1 if singleton else pick.card.max_copies
            count = min(allowed - deck.count_of(pick.card), budget, remaining)
            if count <= 0:
                count = 1
            deck.add(pick.card, count, reason=pick.reason() or "curve filler")
            if pick.card.has_tag("QUEST") or pick.card.has_tag("QUESTLINE"):
                quests_placed += 1

    @staticmethod
    def _neediest_bucket(deck: Deck, targets: dict[str, int]) -> tuple[str, int, int] | None:
        curve = deck.curve()
        best = None
        best_deficit = 0
        for label, low, high in CURVE_BUCKETS:
            deficit = targets[label] - curve[label]
            if deficit > best_deficit:
                best, best_deficit = (label, low, high), deficit
        return best

    def _best_candidate(
        self,
        deck: Deck,
        ranked: list[ScoredCard],
        bucket_range: tuple[int, int] | None,
        *,
        singleton: bool,
        quests_placed: int,
    ) -> ScoredCard | None:
        for entry in ranked:
            card = entry.card
            allowed = 1 if singleton else card.max_copies
            if deck.count_of(card) >= allowed:
                continue
            if bucket_range and not (bucket_range[0] <= card.cost <= bucket_range[1]):
                continue
            if quests_placed and (card.has_tag("QUEST") or card.has_tag("QUESTLINE")):
                continue
            return entry
        return None


def build_deck(
    request: DeckRequest,
    db: CardDB,
    meta: MetaProvider | None = None,
) -> BuildResult:
    return DeckBuilder(db, meta).build(request)
