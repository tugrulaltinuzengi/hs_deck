"""Command line interface: ``python -m hsdeck``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .builder import build_deck
from .carddb import CardDB
from .constraints import DeckRequest
from .decklist import deck_from_deckstring, parse_decklist
from .deckstring import DeckstringError
from .enums import CardClass, class_label, parse_class, parse_format
from .meta import JsonMetaProvider, MetaProvider
from .render import deck_code_block, render_markdown
from .validate import validate


def _load_db(args: argparse.Namespace) -> CardDB:
    return CardDB.load(args.card_db)


def _load_meta(args: argparse.Namespace, db: CardDB) -> MetaProvider | None:
    if getattr(args, "meta", None):
        return JsonMetaProvider.from_file(args.meta, db)
    return None


def _request_from_args(args: argparse.Namespace, db: CardDB) -> DeckRequest:
    if args.request:
        payload = json.loads(Path(args.request).read_text(encoding="utf-8"))
    else:
        payload = {}

    if args.card_class:
        payload["class"] = args.card_class
    if args.format:
        payload["format"] = args.format
    if args.size is not None:
        payload["deck_size"] = args.size
    if args.archetype:
        payload["primary_archetype"] = args.archetype
    if args.goal:
        payload["tactical_goal"] = args.goal
    if args.require:
        required = list(payload.get("required_cards", []))
        for item in args.require:
            # "Name" or "Name:2" or "tag:IMBUE:4"
            parts = item.split(":")
            if parts[0].lower() == "tag" and len(parts) >= 2:
                entry: dict = {"tag": parts[1]}
                if len(parts) > 2:
                    entry["quantity"] = int(parts[2])
                required.append(entry)
            elif len(parts) == 2 and parts[1].isdigit():
                required.append({"name": parts[0], "quantity": int(parts[1])})
            else:
                required.append(item)
        payload["required_cards"] = required
    if args.ban:
        payload["banned_cards"] = list(payload.get("banned_cards", [])) + list(args.ban)

    if "class" not in payload:
        raise SystemExit("error: a class is required (--class PRIEST or --request FILE)")
    return DeckRequest.from_dict(payload, db)


def cmd_build(args: argparse.Namespace) -> int:
    db = _load_db(args)
    request = _request_from_args(args, db)
    result = build_deck(request, db, _load_meta(args, db))
    report = validate(result.deck, db)

    if args.json:
        print(
            json.dumps(
                {
                    "name": result.deck.name,
                    "class": result.deck.card_class.name,
                    "format": result.deck.format.name,
                    "size": result.deck.size,
                    "deckstring": result.deck.deckstring(),
                    "cards": [
                        {
                            "dbf": s.card.dbf,
                            "name": s.card.name,
                            "cost": s.card.cost,
                            "count": s.count,
                            "required": s.required,
                            "reason": s.reason,
                        }
                        for s in result.deck.sorted_slots()
                    ],
                    "curve": result.deck.curve(),
                    "notes": result.notes,
                    "issues": [str(i) for i in report.issues],
                    "valid": report.ok,
                },
                indent=2,
            )
        )
    elif args.code_only:
        print(deck_code_block(result.deck))
    else:
        print(render_markdown(result, db, report))

    return 0 if report.ok or args.allow_invalid else 1


def cmd_decode(args: argparse.Namespace) -> int:
    db = _load_db(args)
    try:
        deck = deck_from_deckstring(args.deckstring, db)
    except DeckstringError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(deck_code_block(deck))
    report = validate(deck, db)
    if report.issues:
        print("\n# Validation", file=sys.stderr)
        for issue in report.issues:
            print(f"#   {issue}", file=sys.stderr)
    return 0 if report.ok else 1


def cmd_encode(args: argparse.Namespace) -> int:
    db = _load_db(args)
    text = Path(args.file).read_text(encoding="utf-8") if args.file != "-" else sys.stdin.read()
    deck = parse_decklist(text, db)
    if args.format:
        deck.format = parse_format(args.format)
    print(deck.deckstring())
    report = validate(deck, db)
    for issue in report.issues:
        print(f"# {issue}", file=sys.stderr)
    return 0 if report.ok else 1


def cmd_search(args: argparse.Namespace) -> int:
    db = _load_db(args)
    cards = db.search(
        args.text or "",
        card_class=parse_class(args.card_class) if args.card_class else None,
        format=parse_format(args.format) if args.format else None,
        tag=args.tag,
        max_cost=args.max_cost,
    )
    for card in cards[: args.limit]:
        classes = "/".join(class_label(CardClass(c)) for c in card.classes)
        flag = "S" if card.standard else "W"
        print(f"{card.dbf:>7}  [{flag}] ({card.cost}) {card.name} - {classes}")
        if args.verbose and card.plain_text:
            print(f"         {card.plain_text}")
    print(f"# {len(cards)} match(es)", file=sys.stderr)
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    db = _load_db(args)
    print(f"cards:          {len(db)}")
    print(f"game build:     {db.game_build or 'unknown'}")
    print(f"generated:      {db.generated or 'unknown'}")
    print(f"zodiac year:    {db.zodiac_year}")
    print(f"standard sets:  {', '.join(db.standard_sets)}")
    print(f"heroes:         {len(db.heroes)}")
    print("deck-size rules:")
    for dbf, size in sorted(db.deck_size_modifiers.items()):
        card = db.by_dbf(dbf)
        print(f"  {size:>2} cards - {card.name if card else dbf}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hsdeck", description="Hearthstone deck builder and deckstring codec"
    )
    parser.add_argument("--card-db", help="path to a card database (default: bundled)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("build", help="build a deck from constraints")
    p.add_argument("--request", help="JSON file holding the deck request")
    p.add_argument("--class", dest="card_class", help="e.g. Priest")
    p.add_argument("--format", help="Standard | Wild | Twist")
    p.add_argument("--size", type=int, help="deck size (default 30, or card-driven)")
    p.add_argument("--archetype", help="e.g. 'Quest / Control'")
    p.add_argument("--goal", help="tactical goal, in plain words")
    p.add_argument(
        "--require",
        action="append",
        metavar="CARD[:N] | tag:TAG[:N]",
        help="a card or mechanic the deck must include (repeatable)",
    )
    p.add_argument("--ban", action="append", metavar="CARD", help="exclude a card")
    p.add_argument("--meta", help="JSON file of winrate data (see hsdeck/meta.py)")
    p.add_argument("--json", action="store_true", help="emit JSON instead of Markdown")
    p.add_argument("--code-only", action="store_true", help="print only the deck code block")
    p.add_argument(
        "--allow-invalid",
        action="store_true",
        help="exit 0 even when the deck fails validation",
    )
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("decode", help="expand a deckstring into a decklist")
    p.add_argument("deckstring")
    p.set_defaults(func=cmd_decode)

    p = sub.add_parser("encode", help="turn a text decklist into a deckstring")
    p.add_argument("file", help="decklist file, or - for stdin")
    p.add_argument("--format", help="override the format")
    p.set_defaults(func=cmd_encode)

    p = sub.add_parser("search", help="search the card database")
    p.add_argument("text", nargs="?", default="")
    p.add_argument("--class", dest="card_class")
    p.add_argument("--format")
    p.add_argument("--tag", help="mechanic tag, e.g. IMBUE")
    p.add_argument("--max-cost", type=int)
    p.add_argument("--limit", type=int, default=40)
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("info", help="describe the bundled card database")
    p.set_defaults(func=cmd_info)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
