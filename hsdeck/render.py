"""Rendering a built deck into the specified Markdown report."""

from __future__ import annotations

from .builder import BuildResult
from .carddb import CardDB
from .deck import CURVE_BUCKETS, Deck
from .enums import CardType
from .scoring import card_roles
from .validate import ValidationReport, validate

_BUCKET_BLURBS = {
    "1-2 Mana": "Early Survival & Cycle",
    "3-4 Mana": "Synergy & Removal",
    "5-6 Mana": "Mid-Game Anchors",
    "7+ Mana": "Late-Game Finishers",
}


def deck_code_block(deck: Deck, title: str = "") -> str:
    """The comment-wrapped block the Hearthstone client reads from a clipboard."""
    lines = [
        f"### {title or deck.name}",
        f"# Class: {deck.card_class.name.title()}",
        f"# Format: {deck.format.name.title()}",
        "#",
    ]
    for slot in deck.sorted_slots():
        lines.append(f"# {slot.count}x ({slot.card.cost}) {slot.card.name}")
    lines += [
        "#",
        deck.deckstring(),
        "#",
        "# To use this deck, copy it to your clipboard and create a new deck in Hearthstone.",
    ]
    return "\n".join(lines)


def _mulligan(result: BuildResult) -> list[str]:
    """Cheap, proactive cards are the ones worth keeping in an opening hand."""
    keeps = [
        slot
        for slot in result.deck.sorted_slots()
        if slot.card.cost <= 3
        and (
            slot.card.type == int(CardType.MINION)
            or card_roles(slot.card) & {"removal", "board_clear", "taunt"}
        )
    ]
    keeps.sort(key=lambda s: (s.card.cost, -result.scores[s.card.dbf].total))
    return [f"**{s.card.name}** ({s.card.cost}) - {result.scores[s.card.dbf].reason()}" for s in keeps[:6]]


def render_markdown(result: BuildResult, db: CardDB, report: ValidationReport | None = None) -> str:
    deck = result.deck
    report = report or validate(deck, db)
    curve = deck.curve()
    targets = result.curve_plan.targets(result.deck_size)

    out: list[str] = []
    title = deck.name or f"{deck.card_class.name.title()} Deck"
    out.append(f"### {title}")
    out.append("")
    out.append(f"**Class:** {deck.card_class.name.title()}  ")
    if deck.archetype:
        out.append(f"**Archetype:** {deck.archetype}  ")
    out.append(f"**Format:** {deck.format.name.title()}  ")
    out.append(f"**Deck Size:** {deck.size} cards  ")
    out.append(f"**Primary Strategy:** {result.request.tactical_goal or deck.archetype or 'n/a'}  ")
    out.append(f"**Curve Plan:** {result.curve_plan.name}  ")
    out.append(f"**Meta data:** {result.meta_source}")
    out.append("")

    out.append("#### Mana Curve & Composition")
    for label, _, _ in CURVE_BUCKETS:
        blurb = _BUCKET_BLURBS[label]
        out.append(f"- **{label}:** {curve[label]} cards (target {targets[label]}) - {blurb}")
    early = deck.early_game_count()
    pct = (early / deck.size * 100) if deck.size else 0
    out.append(
        f"- **1-3 Mana total:** {early}/{deck.size} ({pct:.0f}%), "
        f"floor {result.curve_plan.early_floor:.0%}"
    )
    out.append(f"- **Average cost:** {deck.average_cost():.2f}")
    out.append("")

    out.append("#### Complete Card List")
    for slot in deck.sorted_slots():
        marker = " **[required]**" if slot.required else ""
        reason = f" - _{slot.reason}_" if slot.reason else ""
        out.append(f"- {slot.count}x **({slot.card.cost}) {slot.card.name}**{marker}{reason}")
    out.append("")

    out.append("#### Synergy Axis")
    out.append(f"- {result.synergy.describe()}")
    for slot in deck.sorted_slots():
        if slot.required:
            text = slot.card.plain_text or "(vanilla)"
            out.append(f"- **{slot.card.name}** ({slot.card.cost}): {text}")
    out.append("")

    mulligan = _mulligan(result)
    if mulligan:
        out.append("#### Mulligan Guide")
        out.append("Keep, in rough priority order:")
        for line in mulligan:
            out.append(f"- {line}")
        out.append("")

    out.append("#### Validation")
    if report.ok and not report.warnings:
        out.append("- Legal and importable: deck size, copy limits, class and format all check out.")
    else:
        for issue in report.issues:
            out.append(f"- {issue}")
    out.append("")

    if result.notes:
        out.append("#### Build Notes")
        for note in result.notes:
            out.append(f"- {note}")
        out.append("")

    out.append("#### Copyable Hearthstone Deck Code")
    out.append("```text")
    out.append(deck_code_block(deck, title))
    out.append("```")
    out.append("")
    return "\n".join(out)
