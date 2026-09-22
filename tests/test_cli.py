import json

import pytest

from hsdeck.cli import main
from hsdeck.deckstring import parse_deckstring

CASE_STUDY_ARGS = [
    "build", "--class", "Priest", "--format", "Standard", "--size", "20",
    "--require", "Azalina", "--require", "Karov",
    "--require", "Reach the Equilibrium", "--require", "tag:IMBUE:4",
    "--require", "Specter Specialist:2",
    "--archetype", "Quest / Control / Survival",
    "--goal", "Survive early game aggro, dominate late game",
]


def test_info(capsys):
    assert main(["info"]) == 0
    out = capsys.readouterr().out
    assert "cards:" in out
    assert "Azalina Soulsever" in out


def test_search(capsys):
    assert main(["search", "--tag", "IMBUE", "--class", "priest", "--format", "standard"]) == 0
    assert "Lunarwing Messenger" in capsys.readouterr().out


def test_build_markdown(capsys):
    assert main(CASE_STUDY_ARGS) == 0
    out = capsys.readouterr().out
    assert "Azalina Soulsever" in out
    assert "Copyable Hearthstone Deck Code" in out
    assert "AAECAa0G" in out


def test_build_json(capsys):
    assert main([*CASE_STUDY_ARGS, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["valid"] is True
    assert payload["size"] == 20
    assert sum(c["count"] for c in payload["cards"]) == 20
    parsed = parse_deckstring(payload["deckstring"])
    assert parsed.size == 20
    assert parsed.heroes == [813]


def test_build_code_only_round_trips(capsys, tmp_path):
    assert main([*CASE_STUDY_ARGS, "--code-only"]) == 0
    block = capsys.readouterr().out
    assert block.startswith("### ")

    path = tmp_path / "deck.txt"
    path.write_text(block, encoding="utf-8")
    assert main(["encode", str(path)]) == 0

    encoded = capsys.readouterr().out.strip()
    assert encoded in block


def test_decode(capsys):
    main([*CASE_STUDY_ARGS, "--code-only"])
    deckstring = next(
        line for line in capsys.readouterr().out.splitlines() if line.startswith("AAE")
    )

    assert main(["decode", deckstring]) == 0
    out = capsys.readouterr().out
    assert "# Class: Priest" in out
    assert "Azalina Soulsever" in out


def test_decode_rejects_rubbish(capsys):
    assert main(["decode", "totally-not-a-deckstring"]) == 2
    assert "error:" in capsys.readouterr().err


def test_build_without_a_class_exits(capsys):
    with pytest.raises(SystemExit):
        main(["build", "--format", "Standard"])


def test_build_from_a_request_file(tmp_path, capsys):
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "class": "Priest",
                "format": "Standard",
                "deck_size": 20,
                "required_cards": [
                    "Azalina",
                    {"name": "Imbue priest cards", "quantity": 4},
                ],
                "primary_archetype": "Quest / Control / Survival",
                "tactical_goal": "Survive early game aggro, dominate late game",
            }
        ),
        encoding="utf-8",
    )
    assert main(["build", "--request", str(request), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["size"] == 20
    assert payload["valid"] is True


def test_meta_file_is_reported(tmp_path, capsys):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"cards": {"Specter Specialist": 0.58}}), encoding="utf-8")
    assert main(["build", "--class", "Priest", "--format", "Standard", "--meta", str(meta)]) == 0
    assert "meta.json" in capsys.readouterr().out
