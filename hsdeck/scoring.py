"""Heuristic card evaluation.

Nothing here is live meta data - the numbers are a transparent, auditable
heuristic over card text, mechanics and stats.  Real winrate data can be
layered on top through :mod:`hsdeck.meta`; where it is supplied it dominates
the heuristic, and where it is not the heuristic stands alone.  See
``README.md`` for why the built-in scores are not called "winrates".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from .carddb import Card
from .enums import (
    RACE_BY_NAME,
    SCHOOL_BY_NAME,
    WILDCARD_RACE,
    CardClass,
    CardType,
    Rarity,
    race_label,
    school_label,
)

# --- role detection -------------------------------------------------------

ROLES = (
    "removal",
    "board_clear",
    "heal",
    "armor",
    "taunt",
    "draw",
    "value",
    "tempo",
    "finisher",
    "disruption",
)

_PATTERNS: dict[str, tuple[re.Pattern, ...]] = {
    "removal": (
        re.compile(r"destroy (a|an|target|the highest)", re.I),
        re.compile(r"deal \d+ damage to a(n enemy)? minion", re.I),
        re.compile(r"\btransform (a|an) minion", re.I),
        re.compile(r"return (a|an|target) minion", re.I),
    ),
    "board_clear": (
        re.compile(r"(damage|destroy) .{0,24}\ball (enemy )?minions", re.I),
        re.compile(r"\bto all (enemy )?minions", re.I),
        re.compile(r"destroy all minions", re.I),
    ),
    "heal": (
        re.compile(r"\brestore\b", re.I),
        re.compile(r"\bheal(s|ing)?\b", re.I),
    ),
    "armor": (re.compile(r"\barmor\b", re.I),),
    "draw": (
        re.compile(r"\bdraw (a|\d+|your|cards?)", re.I),
        re.compile(r"add (a|\d+|two|three) .{0,40}to your hand", re.I),
    ),
    "value": (
        re.compile(r"\bcopy\b", re.I),
        re.compile(r"\bsummon .{0,30}copy", re.I),
        re.compile(r"\bdiscover\b", re.I),
        re.compile(r"at the end of your turn", re.I),
    ),
    "disruption": (
        re.compile(r"\bsilence\b", re.I),
        re.compile(r"opponent'?s? (hand|deck)", re.I),
        re.compile(r"destroy .{0,20}weapon", re.I),
        re.compile(r"\bcounter\b", re.I),
    ),
}

_ROLE_TAGS: dict[str, tuple[str, ...]] = {
    "taunt": ("TAUNT",),
    "heal": ("LIFESTEAL", "RESTORE_HEALTH"),
    "draw": ("DISCOVER", "DREDGE"),
    "value": ("DISCOVER", "DEATHRATTLE", "REBORN", "INFUSE", "TITAN"),
    "tempo": ("RUSH", "CHARGE", "DIVINE_SHIELD", "WINDFURY"),
    "disruption": ("SILENCE", "COUNTER"),
    "removal": ("POISONOUS",),
}


def card_roles(card: Card) -> set[str]:
    """Which jobs a card can do in a deck."""
    text = card.plain_text
    roles = {role for role, patterns in _PATTERNS.items() if any(p.search(text) for p in patterns)}
    for role, tags in _ROLE_TAGS.items():
        if any(card.has_tag(tag) for tag in tags):
            roles.add(role)

    if card.cost >= 7 and (card.is_legendary or card.attack + card.health >= 12):
        roles.add("finisher")
    if card.type == int(CardType.MINION) and card.cost <= 4:
        total = card.attack + card.health
        if total >= card.cost * 2 + 2:
            roles.add("tempo")
    return roles


# --- tactical goal profiles ----------------------------------------------

_DEFAULT_PROFILE = {
    "removal": 2.0, "board_clear": 2.0, "heal": 1.0, "armor": 0.5, "taunt": 1.0,
    "draw": 1.5, "value": 1.5, "tempo": 1.5, "finisher": 1.5, "disruption": 0.5,
}

_GOAL_PROFILES: tuple[tuple[tuple[str, ...], dict[str, float]], ...] = (
    (
        ("anti-aggro", "survive", "survival", "stabilize", "stabilise", "defensive"),
        {"removal": 3.5, "board_clear": 4.0, "heal": 3.0, "armor": 2.5, "taunt": 3.0,
         "draw": 2.0, "value": 1.5, "tempo": 0.5, "finisher": 1.0, "disruption": 0.5},
    ),
    (
        ("control", "late game", "late-game", "value engine", "attrition", "fatigue"),
        {"removal": 3.0, "board_clear": 3.0, "heal": 2.0, "armor": 1.5, "taunt": 1.5,
         "draw": 3.0, "value": 3.5, "tempo": 0.5, "finisher": 3.0, "disruption": 1.5},
    ),
    (
        ("aggro", "aggressive", "face", "rush", "tempo", "burn"),
        {"removal": 1.0, "board_clear": 0.0, "heal": 0.5, "armor": 0.0, "taunt": 0.5,
         "draw": 1.5, "value": 0.5, "tempo": 4.0, "finisher": 0.5, "disruption": 1.0},
    ),
    (
        ("combo", "otk", "quest", "questline"),
        {"removal": 2.0, "board_clear": 2.0, "heal": 1.5, "armor": 1.0, "taunt": 1.5,
         "draw": 3.5, "value": 2.5, "tempo": 0.5, "finisher": 2.0, "disruption": 1.0},
    ),
)


def count_keywords(haystack: str, keywords: Iterable[str]) -> int:
    """How many of the keywords occur as whole words/phrases in the text.

    Whole-word matching matters: "survive early game aggro" describes an
    anti-aggro deck, and a naive substring test would read it as an aggro one.
    """
    return sum(
        1 for key in keywords if re.search(rf"(?<!-)\b{re.escape(key)}\b", haystack)
    )


def goal_profile(*descriptions: str) -> dict[str, float]:
    """Blend role weights from the goal keywords found in the request.

    Each matching profile is weighted by how many of its keywords appear, so a
    goal like "survive early aggro, dominate late game" leans control rather
    than being pulled halfway to aggro by the word "aggro".
    """
    haystack = " ".join(d.lower() for d in descriptions if d)
    matched = [
        (count_keywords(haystack, keys), profile)
        for keys, profile in _GOAL_PROFILES
        if count_keywords(haystack, keys)
    ]
    if not matched:
        return dict(_DEFAULT_PROFILE)
    total = sum(weight for weight, _ in matched)
    return {
        role: sum(weight * p.get(role, 0.0) for weight, p in matched) / total
        for role in ROLES
    }


# --- synergy --------------------------------------------------------------

_GENERIC_TAGS = frozenset({
    # Too common to say anything about a deck's identity...
    "BATTLECRY", "DEATHRATTLE", "TAUNT", "RARITY", "ELITE",
    "AFFECTED_BY_SPELL_POWER",
    # ...and pure bookkeeping that is not a mechanic at all.
    "DONT_PICK_FROM_SUBSETS", "QUEST_REWARD_DATABASE_ID", "TRIGGER_VISUAL",
    "IGNORE_HIDE_STATS_FOR_BIG_CARD", "TOPDECK_VISUAL", "MINI_SET",
    "START_OF_GAME_KEYWORD", "DECK_RULE_MOD_DECK_SIZE",
    "DECK_RULE_MOD_STARTING_HERO_HEALTH", "HIDE_STATS", "PREMIUM_SPELL",
})


@dataclass
class SynergyProfile:
    """What the mandatory cards care about, and therefore what to build around."""

    tags: set[str] = field(default_factory=set)
    races: set[int] = field(default_factory=set)
    schools: set[int] = field(default_factory=set)
    wants_spells: bool = False
    keywords: set[str] = field(default_factory=set)

    @classmethod
    def from_cards(cls, cards: Iterable[Card]) -> "SynergyProfile":
        profile = cls()
        for card in cards:
            profile.tags |= {t for t in card.tags if t not in _GENERIC_TAGS}
            profile.races |= {r for r in card.races if r != WILDCARD_RACE}
            if card.spell_school:
                profile.schools.add(card.spell_school)

            text = card.plain_text.lower()
            # "CARES_ABOUT_IMBUE_CARDS" -> build around IMBUE.
            for tag in card.tags:
                if tag.startswith("CARES_ABOUT_"):
                    profile.tags.add(tag.removeprefix("CARES_ABOUT_").removesuffix("_CARDS"))
            # A quest that says "Cast 4 Holy spells" wants Holy spells.
            for school_name, school_id in SCHOOL_BY_NAME.items():
                if re.search(rf"\b{school_name}\b", text):
                    profile.schools.add(school_id)
            for race_name, race_id in RACE_BY_NAME.items():
                if re.search(rf"\b{race_name}s?\b", text):
                    profile.races.add(race_id)
            if re.search(r"\b(cast|spells?)\b", text):
                profile.wants_spells = True
            if card.has_tag("QUEST") or card.has_tag("QUESTLINE"):
                profile.keywords.add("quest")
        profile.races.discard(WILDCARD_RACE)
        return profile

    def score(self, card: Card) -> float:
        """How strongly a candidate supports the mandatory package."""
        score = 0.0
        shared_tags = (card.tags - _GENERIC_TAGS) & self.tags
        score += 2.5 * len(shared_tags)

        for tag in card.tags:
            if tag.startswith("CARES_ABOUT_"):
                subject = tag.removeprefix("CARES_ABOUT_").removesuffix("_CARDS")
                if subject in self.tags:
                    score += 2.0

        if card.races and self.races and set(card.races) & self.races:
            score += 2.0
        if card.spell_school and card.spell_school in self.schools:
            score += 2.5
        if self.wants_spells and card.type == int(CardType.SPELL):
            score += 1.0
        return score

    def describe(self) -> str:
        bits = []
        if self.tags:
            bits.append("tags: " + ", ".join(sorted(self.tags)[:8]))
        if self.schools:
            bits.append("schools: " + ", ".join(school_label(s) for s in sorted(self.schools)))
        if self.races:
            bits.append("tribes: " + ", ".join(race_label(r) for r in sorted(self.races)))
        return "; ".join(bits) or "no specific synergy axis"


# --- overall card score ---------------------------------------------------

@dataclass
class ScoredCard:
    card: Card
    total: float
    role_score: float
    synergy_score: float
    quality_score: float
    meta_score: float
    roles: set[str]

    def reason(self) -> str:
        """Short human explanation of why this card scored where it did."""
        parts = []
        if self.roles:
            parts.append("/".join(sorted(self.roles)))
        if self.synergy_score > 0:
            parts.append(f"synergy {self.synergy_score:.1f}")
        if self.meta_score:
            parts.append(f"meta {self.meta_score:+.1f}")
        return ", ".join(parts)


def _quality(card: Card, card_class: CardClass) -> float:
    """Generic card-quality prior: class cards, rarity and stat efficiency."""
    score = 0.0
    if int(card_class) in card.classes:
        score += 1.5  # class cards are tuned to be stronger than neutrals
    score += {Rarity.COMMON: 0.0, Rarity.FREE: 0.0, Rarity.RARE: 0.4,
              Rarity.EPIC: 0.7, Rarity.LEGENDARY: 1.0}.get(Rarity(card.rarity), 0.0)
    if card.type == int(CardType.MINION):
        expected = card.cost * 2 + 1
        score += max(-1.0, min(1.5, (card.attack + card.health - expected) * 0.35))
    if len(card.plain_text) > 40:
        score += 0.5  # text is (roughly) effect density
    return score


def score_card(
    card: Card,
    *,
    card_class: CardClass,
    profile: dict[str, float],
    synergy: SynergyProfile,
    meta_score: float = 0.0,
) -> ScoredCard:
    roles = card_roles(card)
    role_score = sum(profile.get(role, 0.0) for role in roles)
    synergy_score = synergy.score(card)
    quality_score = _quality(card, card_class)
    total = role_score + synergy_score + quality_score + meta_score
    return ScoredCard(
        card=card,
        total=total,
        role_score=role_score,
        synergy_score=synergy_score,
        quality_score=quality_score,
        meta_score=meta_score,
        roles=roles,
    )
