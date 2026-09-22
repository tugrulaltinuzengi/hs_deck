"""Generate the compact card database shipped with hsdeck.

Source of truth is Blizzard's ``CardDefs.xml`` as redistributed by the
HearthSim ``hearthstone-data`` package.  This script is a *build-time* tool:
it needs ``hearthstone`` (and either ``hearthstone-data`` or an explicit
``--carddefs`` path).  The ``hsdeck`` package itself only reads the generated
file and has no third-party dependencies.

    python tools/build_carddb.py --out data/cards.json.gz
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hsdeck._vendor.hearthstone import cardxml  # noqa: E402
from hsdeck._vendor.hearthstone.enums import CardClass, CardType, GameTag  # noqa: E402
from hsdeck._vendor.hearthstone.utils import CARDCLASS_HERO_MAP  # noqa: E402
from hsdeck.enums import PLAYABLE_TYPES  # noqa: E402

# Tags that are pure presentation/bookkeeping noise for deck building.
TAG_BLOCKLIST = {
    "CARDNAME", "CARDTEXT", "FLAVORTEXT", "ARTISTNAME", "COLLECTIBLE",
    "CARD_SET", "CARDTYPE", "CLASS", "RARITY", "COST", "ATK", "HEALTH",
    "DURABILITY", "FACTION", "HIDE_WATERMARK", "HAS_SIGNATURE_QUALITY",
    "CARDRACE", "SPELL_SCHOOL", "MULTI_CLASS_GROUP", "HOW_TO_EARN",
    "HOW_TO_EARN_GOLDEN", "TARGETING_ARROW_TEXT", "ELITE", "DECK_SIZE",
    "STARTING_HERO_HEALTH", "TRIGGER_VISUAL", "IGNORE_HIDE_STATS_FOR_BIG_CARD",
    "InvisibleDeathrattle", "SHOWN_HERO_POWER",
}

# Cards that legally change the required deck size when included.  Keyed by
# name so every printing (original set + Core reprint) is picked up.
DECK_SIZE_MODIFIER_CARDS = {
    "Prince Renathal": 40,
    "Azalina Soulsever": 20,
}


def _tag_names(card: Any) -> list[str]:
    """Boolean/keyword tags worth keeping, as readable names."""
    names: set[str] = set()
    sources: Iterable[dict] = (card.tags, getattr(card, "referenced_tags", {}) or {})
    for source in sources:
        for key, value in source.items():
            if not value or not isinstance(value, int):
                continue
            try:
                name = GameTag(key).name
            except ValueError:
                continue  # unnamed/internal tag - skip
            if name in TAG_BLOCKLIST or name.isdigit():
                continue
            names.add(name)
    return sorted(names)


def _classes(card: Any) -> list[int]:
    """All classes that may run the card (multi-class cards list several)."""
    classes = {int(c) for c in card.classes} | {int(card.card_class)}
    return sorted(c for c in classes if c)


def _game_build(carddefs: str | None) -> str:
    """The Hearthstone build number CardDefs.xml was extracted from."""
    if carddefs is None:
        try:
            from hearthstone_data import get_carddefs_path

            carddefs = get_carddefs_path()
        except ImportError:
            return ""
    with open(carddefs, "rb") as fp:
        header = fp.read(512).decode("utf-8", "replace")
    match = re.search(r'<CardDefs\s+build="(\d+)"', header)
    return match.group(1) if match else ""


def build(carddefs: str | None, locale: str = "enUS") -> dict:
    db, _ = cardxml.load(path=carddefs, locale=locale)

    by_cardid = {card.id: card for card in db.values()}

    heroes: dict[str, int] = {}
    for card_class, hero_cardid in CARDCLASS_HERO_MAP.items():
        hero = by_cardid.get(hero_cardid)
        if hero is not None:
            heroes[CardClass(int(card_class)).name] = int(hero.dbf_id)

    deck_size_modifiers: dict[str, int] = {}
    for card in db.values():
        size = DECK_SIZE_MODIFIER_CARDS.get(card.name)
        if size and card.collectible and card.type in PLAYABLE_TYPES:
            deck_size_modifiers[str(int(card.dbf_id))] = size

    cards = []
    for card in db.values():
        if not card.collectible or card.type not in PLAYABLE_TYPES:
            continue
        record = {
            "dbf": int(card.dbf_id),
            "id": card.id,
            "name": card.name,
            "cost": int(card.cost or 0),
            "cls": _classes(card),
            "type": int(card.type),
            "rarity": int(card.rarity or 0),
            "set": int(card.card_set),
            "text": (card.description or "").strip(),
            "tags": _tag_names(card),
        }
        if int(card.type) in (int(CardType.MINION), int(CardType.WEAPON)):
            record["atk"] = int(card.atk or 0)
            record["hp"] = int(card.health or card.durability or 0)
        races = [int(r) for r in (getattr(card, "races", None) or [])]
        if races:
            record["races"] = races
        school = int(getattr(card, "spell_school", 0) or 0)
        if school:
            record["school"] = school
        cards.append(record)

    cards.sort(key=lambda c: c["dbf"])

    # Format legality is NOT baked in: CardDB derives it at runtime from the
    # vendored rotation table, so a rotation needs no database rebuild.
    return {
        "schema": 2,
        "game_build": _game_build(carddefs),
        "generated": date.today().isoformat(),
        "locale": locale,
        "heroes": heroes,
        "deck_size_modifiers": deck_size_modifiers,
        "cards": cards,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--carddefs",
        help="path to CardDefs.xml (defaults to the hearthstone-data package)",
    )
    parser.add_argument("--locale", default="enUS")
    parser.add_argument(
        "--out",
        default="hsdeck/data/cards.json.gz",
        help="output path (.json or .json.gz)",
    )
    args = parser.parse_args()

    payload = build(args.carddefs, args.locale)
    blob = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix == ".gz":
        # mtime=0 keeps the output byte-identical across rebuilds of the same data.
        with gzip.GzipFile(out, "wb", compresslevel=9, mtime=0) as fp:
            fp.write(blob)
    else:
        out.write_bytes(blob)

    print(
        f"wrote {out} - {len(payload['cards'])} cards from game build "
        f"{payload['game_build'] or '?'}, {len(payload['heroes'])} heroes, "
        f"{out.stat().st_size / 1024:.0f} KiB"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
