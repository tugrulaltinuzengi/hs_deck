"""The vendored HearthSim tree must stay usable and self-contained."""

import subprocess
import sys
from pathlib import Path

import pytest

from hsdeck._vendor import hearthstone
from hsdeck._vendor.hearthstone import deckstrings, enums
from hsdeck._vendor.hearthstone.utils import (
    CARDCLASS_HERO_MAP,
    CARDRACE_TAG_MAP,
    STANDARD_SETS,
    ZODIAC_ROTATION_DATES,
)

VENDOR_DIR = Path(hearthstone.__file__).parent


def test_version_is_pinned():
    assert hearthstone.__version__ == "9.21.0"


def test_licence_is_shipped():
    licence = (VENDOR_DIR / "LICENSE").read_text(encoding="utf-8")
    assert "MIT" in licence or "Permission is hereby granted" in licence


def test_provenance_is_documented():
    readme = (VENDOR_DIR.parent / "README.md").read_text(encoding="utf-8")
    assert "python-hearthstone" in readme
    assert hearthstone.__version__ in readme

    # Every local modification is marked where it was made...
    modified = {
        path.name
        for path in VENDOR_DIR.rglob("*.py")
        if "LOCAL MODIFICATION" in path.read_text(encoding="utf-8")
    }
    assert modified == {"__init__.py", "xmlutils.py", "cardxml.py"}

    # ...and each one is listed in the README's numbered list.
    for number in ("1.", "2.", "3."):
        assert f"\n{number} **" in readme


def test_imports_without_third_party_packages():
    """Nothing in the vendored tree may need a third-party import to load."""
    code = (
        "import sys;"
        "sys.modules['requests'] = None;"
        "sys.modules['lxml'] = None;"
        "from hsdeck._vendor.hearthstone import cardxml, deckstrings, enums, utils;"
        "print(enums.CardClass.PRIEST.name)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=VENDOR_DIR.parents[2],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "PRIEST" in result.stdout


@pytest.mark.parametrize(
    "name",
    ["GameTag", "CardClass", "CardType", "CardSet", "Rarity", "Race", "SpellSchool",
     "FormatType", "ZodiacYear"],
)
def test_enums_hsdeck_depends_on_are_present(name):
    assert hasattr(enums, name)


def test_tables_hsdeck_depends_on_are_populated():
    assert len(CARDCLASS_HERO_MAP) >= 11
    assert len(CARDRACE_TAG_MAP) > 20
    assert STANDARD_SETS and ZODIAC_ROTATION_DATES


def test_rotation_table_drives_standard_legality():
    from hsdeck.enums import is_standard, standard_sets

    current = set(standard_sets())
    assert current == {s.name for s in enums.ZodiacYear.SCARAB.standard_card_sets}
    assert is_standard(enums.CardSet.CORE)
    assert not is_standard(enums.CardSet.NAXX)


def test_hsdeck_delegates_encoding_to_the_reference():
    """hsdeck.deckstring must not have its own copy of the binary format."""
    from hsdeck.deckstring import write_deckstring

    cards, heroes, fmt = [(117544, 1), (127065, 2)], [813], enums.FormatType.FT_STANDARD
    assert write_deckstring(cards, heroes, fmt) == deckstrings.write_deckstring(
        cards, heroes, fmt
    )


def test_vendored_codec_has_not_drifted_from_the_release():
    """The vendored tree must still match the upstream release it claims.

    Skipped unless the real package is installed (it is in the `dev` extra).
    """
    released = pytest.importorskip("hearthstone.deckstrings")
    import random

    rng = random.Random(1234)
    for _ in range(200):
        cards = list(
            {
                rng.randint(1, 200_000): rng.choice([1, 1, 2, 2, 3, 5])
                for _ in range(rng.randint(1, 30))
            }.items()
        )
        hero = rng.choice([813, 637, 7, 274])
        fmt = rng.choice([1, 2, 4])
        sideboard = []
        if rng.random() < 0.3:
            owners = [d for d, _ in cards]
            sideboard = [
                (dbf, rng.choice([1, 2, 3]), owner)
                for dbf, owner in {
                    (rng.randint(1, 200_000), rng.choice(owners))
                    for _ in range(rng.randint(1, 4))
                }
            ]

        assert deckstrings.write_deckstring(
            cards, [hero], fmt, sideboard
        ) == released.write_deckstring(cards, [hero], fmt, sideboard)
