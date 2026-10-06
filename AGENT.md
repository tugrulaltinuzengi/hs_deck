# Hearthstone Deck Architect — Operating Brief

The specification this repository implements. Sections 1–3, 5 and 7 are the
original brief; section 4 has been corrected against the real binary format
(the original omitted two required fields) and section 6 is preserved as the
input case study, with its defects catalogued in
[README.md § Where the original brief needed correcting](README.md#where-the-original-brief-needed-correcting).

---

## Role

An elite competitive Hearthstone deck-building agent, meta analyst and game
theory engine. It analyses user constraints, the card database, format legality
and card synergies to construct decks and emit an exact, copyable **Hearthstone
deck string** (`AAECA…`) that the game client detects and auto-imports from the
clipboard.

---

## 1. Core objectives

1. **Strict constraint parsing** — class, required cards, archetype, tactical
   objective (early-game survival, anti-aggro, late-game win condition) and
   non-standard deck sizes (20, 30, 40).
2. **Database and synergy analysis** — evaluate every card legal in the target
   format; weigh synergies, curve, removal density, card draw and win-condition
   reliability.
3. **Deck construction and tuning** — fill open slots with the cards that best
   serve the deck's stated objective.
4. **Deckstring generation** — encode the final list using DBF ids, format and
   hero tags, and base64, so the client parses it directly.
5. **Output delivery** — decklist, curve summary, mulligan guide, strategy
   breakdown and the deck code block.

Implemented by: `constraints.py`, `carddb.py` + `scoring.py`, `builder.py`,
`deckstring.py`, `render.py`. Blizzard's own data model — tag numbers, the
Standard rotation, hero portraits, tribes, and the deckstring codec — is
HearthSim's `python-hearthstone`, vendored under `hsdeck/_vendor` rather than
restated.

---

## 2. Input schema

```json
{
  "class": "Priest | Mage | Warrior | Rogue | Druid | Paladin | Hunter | Shaman | Warlock | DemonHunter | DeathKnight",
  "format": "Standard | Wild | Twist | Custom",
  "deck_size": 20,
  "required_cards": [
    "Azalina",
    "Karov",
    "Reach the Equilibrium",
    {"name": "Imbue priest cards", "quantity": 4},
    {"name": "Specter Specialist", "quantity": 2}
  ],
  "primary_archetype": "Quest / Control / Survival",
  "tactical_goal": "Survive early game aggro, dominate late game",
  "target_winrate_bias": "Anti-Aggro / Value Engine"
}
```

`DeckRequest.from_dict` accepts this verbatim. Two extensions: `banned_cards`,
and `{"tag": "IMBUE", "quantity": 4}` for an explicit mechanic requirement.

---

## 3. Deck building rules

### A. Curve and resource balance

* **Early-game survival threshold.** A deck aiming for late-game dominance
  needs at least **40–50%** of its cards at 1–3 mana: defensive drops, cheap
  removal, board-clear setup, early draw and discover.
* **Synergy matrix.** Every mandatory card must be supported by complementary
  triggers. Imbue or quest mechanics pull in the spell packages and generators
  that advance them.
* **Card ratios.** One copy for unique win conditions and Legendaries; two for
  engine components, core removal and survival tools.

### B. Non-standard deck sizes

A size other than 30 must be earned by a card that grants it — `Prince
Renathal` (40) or `Azalina Soulsever` (20). Class limits and copy limits still
apply, curve targets scale proportionally, and the encoded DBF array must match
the list exactly. A size that no card in the list supports is encoded anyway and
reported as unimportable.

---

## 4. Deckstring encoding (corrected)

Version 1, all integers unsigned LEB128 varints, the buffer base64'd:

| Field | Value |
| --- | --- |
| reserved | `0x00` |
| version | `1` |
| format | `1` Wild, `2` Standard, `3` Classic, `4` Twist |
| hero count | `1` |
| hero DBF id | e.g. Priest `813`, Mage `637` |
| 1-copy group | count, then DBF ids ascending |
| 2-copy group | count, then DBF ids ascending |
| n-copy group | count, then (DBF id, copies) pairs |
| sideboard marker | `0x00`, or `0x01` followed by the sideboard block |

> Two corrections to the original section 4: the **hero-count varint** precedes
> the hero id, and the **sideboard marker byte** is mandatory even when there is
> no sideboard. A string missing either is rejected by the client. The original
> also listed only three format values; Twist is `4`.
>
> Deck strings cannot be approximated or "simulated". `hsdeck` does not
> implement this layout at all — it calls HearthSim's reference codec, vendored
> under `hsdeck/_vendor`, so its output is by construction what every
> Hearthstone deck site produces.

---

## 5. Output template

Every generated deck is reported as:

* heading, class, archetype, format, deck size, primary strategy;
* mana curve and composition, with the bucket targets and the 1–3 mana share;
* the complete card list, with required cards marked and every pick justified;
* the synergy axis and the rules text of each mandatory card;
* a mulligan guide;
* validation results and build notes (including every name substitution);
* the copyable deck code block.

See `render.py` and [`examples/quest-priest-20.md`](examples/quest-priest-20.md).

---

## 6. Case study (as originally given)

> *"A priest quest deck that includes the cards below: Azalina, Karov, Reach
> the Equilibrium, 4 Imbue priest cards, 2 Specter Specialist. This deck mainly
> aims to survive from the early game decks. Late game will be its strong point.
> This is a 20 card deck because of Azalina."*

The brief's own answer to this prompt listed twelve entries totalling 19 cards,
four of which do not exist and four more of which are Wild-only, under a
deckstring that does not parse. Its defects are enumerated in the README and
pinned by `tests/test_spec_example.py`.

The request as *stated* is sound, and is the repository's worked example:
`examples/quest-priest-20.json` → `examples/quest-priest-20.md`.

---

## 7. Continuous meta adaptation

1. **Meta balance scan.** Tech choices should follow the live top-tier
   archetypes. `hsdeck` ships no winrate data and does not pretend to: supply it
   through `--meta` (see `hsdeck/meta.py`) and it steers selection; without it
   the output states that scoring is heuristic only.
2. **Curve strictness.** Never ship a deck with a hole in the curve. `validate.py`
   warns on an empty 1–2 or 3–4 bucket and on a thin early game.
3. **Validation check.** Before returning output, confirm every mandatory card
   is present and the totals add up — `validate.py` plus the build notes, which
   report anything that was dropped, substituted or could not be satisfied.
