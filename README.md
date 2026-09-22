# hsdeck — Hearthstone Deck Architect

Constraint-driven Hearthstone deck construction that emits a **real, importable
deckstring**.

A deck request goes in:

```json
{
  "class": "Priest",
  "format": "Standard",
  "deck_size": 20,
  "required_cards": [
    "Azalina", "Karov", "Reach the Equilibrium",
    {"name": "Imbue priest cards", "quantity": 4},
    {"name": "Specter Specialist", "quantity": 2}
  ],
  "primary_archetype": "Quest / Control / Survival",
  "tactical_goal": "Survive early game aggro, dominate late game"
}
```

A validated decklist, a strategy write-up and an `AAECAa0G…` code come out:

```console
$ hsdeck build --request examples/quest-priest-20.json
```

See [`examples/quest-priest-20.md`](examples/quest-priest-20.md) for the full
output, and [`AGENT.md`](AGENT.md) for the agent operating brief this
implements.

## Install

```console
$ pip install -e .          # runtime has no third-party dependencies
$ pip install -e '.[dev]'   # adds pytest and the reference-encoder cross-check
```

Python 3.10+.

## Commands

| Command | What it does |
| --- | --- |
| `hsdeck build` | Build a deck from constraints; Markdown, `--json`, or `--code-only` |
| `hsdeck encode FILE` | Turn a text decklist into a deckstring |
| `hsdeck decode STRING` | Expand a deckstring back into a named decklist |
| `hsdeck search TEXT` | Search cards by name, text, `--tag`, `--class`, `--max-cost` |
| `hsdeck info` | Card database provenance and deck-size rules |

Constraints can also be given entirely on the command line:

```console
$ hsdeck build --class Priest --format Standard --size 20 \
    --require Azalina --require Karov --require "Reach the Equilibrium" \
    --require tag:IMBUE:4 --require "Specter Specialist:2" \
    --archetype "Quest / Control / Survival" \
    --goal "Survive early game aggro, dominate late game"
```

`build` exits non-zero when the deck fails validation, so it can gate a script.

## Library

```python
from hsdeck import CardDB, DeckRequest, build_deck, render_markdown, validate

db = CardDB.load()
request = DeckRequest.from_json(open("examples/quest-priest-20.json").read(), db)
result = build_deck(request, db)

print(result.deck.deckstring())        # AAECAa0GCPTrBfKDB6iWB...
print(validate(result.deck, db).ok)    # True
print(render_markdown(result, db))
```

## How the build works

1. **Parse.** `constraints.py` turns the request into typed requirements. A
   plain name is one card; `{"name": "Imbue priest cards", "quantity": 4}` is
   read as *a group* — a quantity above the 2-copy limit, or a plural phrase
   naming a mechanic, cannot mean a single card. Names are resolved against the
   real card database, so `"Reach the Equilibrium"` finds `Reach Equilibrium`
   and `"Azalina"` in Standard Priest finds `Azalina Soulsever`, not the
   Wild-only `Azalina Soulthief`. Every substitution is reported in the output's
   build notes.
2. **Size.** 30 by default; `Prince Renathal` forces 40 and `Azalina Soulsever`
   forces 20. A conflicting explicit size is honoured *and* flagged.
3. **Score.** `scoring.py` classifies each card's roles (removal, board clear,
   heal, armor, taunt, draw, value, tempo, finisher, disruption) from its tags
   and rules text, weights them by the tactical goal, and adds a synergy score
   derived from the mandatory cards — shared mechanics, `CARES_ABOUT_*` payoffs,
   tribes, and spell schools pulled out of quest text ("Cast 4 **Holy** spells").
4. **Fill.** `builder.py` divides the curve into buckets with targets scaled to
   the deck size, enforces a floor on cards costing ≤ 3 (40% for decks whose
   goal is to reach the late game), and gives each remaining slot to the
   best-scoring legal card in whichever bucket is furthest behind.
5. **Validate & encode.** `validate.py` checks size, copy limits, class, format,
   one-quest and one-deck-size-modifier rules; `deckstring.py` encodes.

Builds are deterministic — the same request always produces the same deckstring.

### Scoring is a heuristic, not winrate data

The brief asks for "highest statistical winrate" cards. hsdeck ships **no
winrate numbers**: live statistics come from third-party services with their own
access terms, and inventing plausible-looking percentages would be worse than
having none. Card selection instead runs on the transparent heuristic above.

Real data is an injectable input. Point `--meta` at a JSON file of winrates and
it dominates the heuristic:

```json
{"baseline": 0.50, "weight": 12.0,
 "cards": {"Specter Specialist": 0.556, "117544": 0.528}}
```

See [`examples/meta-example.json`](examples/meta-example.json) and
`hsdeck/meta.py`. Without it, the output says so: *"Meta data: none (heuristic
scoring only)"*.

## The deckstring format

Version 1, all integers unsigned LEB128 varints, the whole buffer base64'd:

```
0x00                     reserved
varint  version          always 1
varint  format           1=Wild 2=Standard 3=Classic 4=Twist
varint  hero_count       always 1
varint* hero_dbf_ids     ascending
varint  n1               cards played as exactly 1 copy
varint* dbf_ids          ascending
varint  n2               cards played as exactly 2 copies
varint* dbf_ids          ascending
varint  nN               cards played as 3+ copies
(varint dbf_id, varint count)*
0x00 | 0x01              sideboard marker
<sideboard block>        only when the marker is 0x01
```

Sideboards (E.T.C., Band Manager and friends) are supported on both the encoding
and decoding side.

The encoder is verified **byte-for-byte against HearthSim's reference
implementation** over 200 randomised decks including sideboards
(`tests/test_deckstring.py::test_matches_reference_encoder`), so a code that
comes out of hsdeck is the same code hearthstone deck sites produce.

## Card data

`hsdeck/data/cards.json.gz` (≈330 KiB, 7360 collectible cards) is generated from
Blizzard's `CardDefs.xml` as redistributed by HearthSim's `hearthstone-data`
package. It holds DBF ids, costs, classes, rarities, sets, rules text, mechanic
tags, tribes and spell schools, plus the hero portraits and the Standard set
list for the current rotation.

Check what is bundled, and regenerate when a set releases or Standard rotates:

```console
$ hsdeck info
$ pip install -e '.[carddb]'
$ python tools/build_carddb.py
```

The checked-in file was built from game build **251952** (Year of the Scarab).
`hsdeck info` prints the build number and generation date of whatever is
installed; a deckstring referencing a card newer than the bundled data decodes
with a clear error rather than a wrong name.

## Where the original brief needed correcting

The worked example in the brief (reproduced in [`AGENT.md`](AGENT.md) §6) does
not survive contact with the real card database. Each of these is checked by a
test:

* **Its deckstring is malformed.** `AAECAa0GCAmXoATSpQ…` fails to parse — the
  varint stream is truncated. A deckstring cannot be written by hand or
  "simulated"; it is a binary encoding of DBF ids, which is why the encoder here
  is cross-checked against a reference implementation.
* **The list is 19 cards, not 20.** The counts in §6 sum to 19.
* **Four cards do not exist:** *Imbued Flash*, *Imbued Shieldbearer*, *Shadow
  Word: Devastate*, *Xyrella, the Devout*.
* **One is misnamed:** *Reach the Equilibrium* is `Reach Equilibrium`.
* **Four are Wild-only** in a deck labelled Standard: *Seek Guidance*,
  *Hysteria*, *Mass Dispel*, *Azalina Soulthief*.
* **The wrong Azalina.** Only `Azalina Soulsever` — "Your deck is 20 cards, plus
  20 copied from your enemy" — makes a 20-card deck legal. `Azalina Soulthief`
  is an unrelated Wild card and does not change deck size.
* **Specter Specialist costs 3**, not 2.
* **Hero DBF ids.** §4 offers "Priest Hero = 813 or 637". Priest is 813; 637 is
  Mage. `CardDB.hero_dbf()` looks them up rather than guessing.
* **The binary layout in §4 is incomplete** — it omits the hero-count varint
  before the hero id and the trailing sideboard marker byte. Both are required;
  the client rejects a string without them.

## Tests

```console
$ python -m pytest
136 passed
```

Coverage includes varint edge cases, deckstring round-trips and rejection of
malformed input, the reference-encoder cross-check, name resolution, constraint
parsing of the brief's own case study, legal 30-card builds for all eleven
classes, curve floors, copy limits, deck-size modifiers, highlander mode, meta
injection, and every CLI subcommand.

## Layout

```
hsdeck/
  varint.py       LEB128 codec
  deckstring.py   deckstring encode/decode, sideboards
  enums.py        CardClass, CardType, Rarity, FormatType, copy limits
  carddb.py       card records, pools, fuzzy name resolution, search
  constraints.py  request parsing, requirement types, deck-size inference
  scoring.py      role detection, goal profiles, synergy profiles
  builder.py      curve plans and the greedy quota filler
  deck.py         deck model, curve, export
  decklist.py     text decklist <-> Deck <-> deckstring
  validate.py     legality and importability checks
  render.py       the Markdown report and the clipboard block
  cli.py          command line interface
  data/           generated card database
tools/            card database generator
examples/         a worked request, its output, a meta-data sample
tests/            136 tests
```

## Licence

MIT. Hearthstone card data is © Blizzard Entertainment; this project is
unaffiliated with Blizzard.
