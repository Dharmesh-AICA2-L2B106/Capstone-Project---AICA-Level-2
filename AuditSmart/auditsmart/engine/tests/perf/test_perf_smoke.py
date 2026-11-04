"""Smoke test of scripts/perf.py on a few thousand lines (the 1M run is manual)."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from app.core import config, db

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "perf.py"


def _load():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("perf_script", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_perf_pipeline_small(tmp_path: Path) -> None:
    perf = _load()
    saved = dict(os.environ)
    try:
        res = perf.run(3000, tmp_path / "w")
    finally:
        os.environ.clear()
        os.environ.update(saved)
        config.reset_settings()
        db.reset_engine()
    assert res["lines"] == 3000 and res["parsed_rows"] == 3000
    assert res["status_after_import"] in {"parsed", "validated"}
    assert res["validation"]["critical"] == 0
    assert res["je_status"] in {"current"}
    assert 0 < res["je_flagged_lines"] < 3000
    assert set(res["job_statuses"].values()) == {"succeeded"}
    doc = tmp_path / "PERF.md"
    doc.write_text("# Perf\n\n<!-- perf:begin -->\nold\n<!-- perf:end -->\n\ntail\n")
    perf.write_report(res, doc)
    text = doc.read_text()
    assert "old" not in text and "| JE tests" in text and text.endswith("tail\n")
    fresh = tmp_path / "NEW.md"
    fresh.write_text("# New\n")
    perf.write_report(res, fresh)
    assert "<!-- perf:end -->" in fresh.read_text()
