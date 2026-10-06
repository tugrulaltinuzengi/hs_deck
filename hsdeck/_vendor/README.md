# Vendored dependencies

## `hearthstone/` — HearthSim `python-hearthstone`

| | |
| --- | --- |
| Upstream | https://github.com/HearthSim/python-hearthstone |
| Version | **9.21.0** (PyPI sdist `hearthstone-9.21.0.tar.gz`) |
| Vendored | 2026-09-22 |
| Licence | MIT — see [`hearthstone/LICENSE`](hearthstone/LICENSE), © Jerome Leclanche |

This is the authoritative source for Hearthstone's own data model, and hsdeck
uses it directly rather than restating it:

| File | What hsdeck uses it for |
| --- | --- |
| `enums.py` | `GameTag`, `CardClass`, `CardType`, `CardSet`, `Rarity`, `Race`, `SpellSchool`, `FormatType`, `ZodiacYear` — including `CardSet.is_standard`, which decides format legality |
| `deckstrings.py` | The reference deckstring codec. `hsdeck.deckstring` wraps it; it does not reimplement it |
| `utils/__init__.py` | `CARDCLASS_HERO_MAP` (hero portraits), `STANDARD_SETS` and `ZODIAC_ROTATION_DATES` (rotation), `CARDRACE_TAG_MAP` (tribes) |
| `cardxml.py`, `xmlutils.py` | Parsing Blizzard's `CardDefs.xml` in `tools/build_carddb.py` |

Only these five modules are vendored; `bountyxml`, `dbf`, `entities`,
`mercenaryxml`, `stringsfile` and `typedefs` cover Battlegrounds, Mercenaries
and replay parsing, which hsdeck does not do.

### Local modifications

Both are import-time mechanics, not logic. No card data, enum value, table or
encoding rule has been altered.

1. **`__init__.py`** — upstream resolves `__version__` from installed
   distribution metadata, which a vendored copy has none of. Replaced with a
   pinned literal.
2. **`xmlutils.py`** — `import requests` moved from module scope into
   `download_to_tempfile`. hsdeck always reads `CardDefs.xml` from a local
   path, so the download path is never taken, and this keeps the whole tree
   importable with no third-party packages.
3. **`cardxml.py`** — `_bootstrap_from_library` imported `hearthstone_data`
   unconditionally, so passing an explicit `path` still required the 100 MB
   data package to be installed. The import now happens only when no path is
   given.

Each modification is marked with a `LOCAL MODIFICATION` comment in place.

### Updating

```console
$ pip download hearthstone --no-deps --no-binary :all: -d /tmp/hs
$ tar xzf /tmp/hs/hearthstone-*.tar.gz -C /tmp/hs
$ cp /tmp/hs/hearthstone-*/hearthstone/{enums,deckstrings,cardxml,xmlutils}.py \
     hsdeck/_vendor/hearthstone/
$ cp /tmp/hs/hearthstone-*/hearthstone/utils/__init__.py \
     hsdeck/_vendor/hearthstone/utils/
$ cp /tmp/hs/hearthstone-*/LICENSE hsdeck/_vendor/hearthstone/
```

Then re-apply the two modifications above, bump the version in this file and in
`hsdeck/_vendor/hearthstone/__init__.py`, and run `python -m pytest`.
`tests/test_vendor.py` checks the vendored tree imports without third-party
packages and still exposes everything hsdeck depends on.

Refreshing the vendored copy is also how Standard rotation is updated —
`CardSet.is_standard` is evaluated at runtime, so a new `STANDARD_SETS` table
takes effect without regenerating the card database.
