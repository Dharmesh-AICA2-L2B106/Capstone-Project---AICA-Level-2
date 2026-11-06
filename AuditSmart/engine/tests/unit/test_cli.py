from __future__ import annotations

import json

import pytest

from app import cli
from tests.helpers import DATA


def test_cli_edge_blocks(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["validate", str(DATA / "edge_cases.csv")]) == 1
    out = capsys.readouterr().out
    assert "8 critical" in out and "Voucher EV-001 is out of balance by AED 0.05" in out


def test_cli_json_and_map(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["validate", str(DATA / "fy2021_2022.csv"), "--json",
                     "--map", "narration=narration"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["summary"]["critical"] == 0
    with pytest.raises(SystemExit):
        cli.main(["validate", str(DATA / "fy2021_2022.csv"), "--map", "bad"])
