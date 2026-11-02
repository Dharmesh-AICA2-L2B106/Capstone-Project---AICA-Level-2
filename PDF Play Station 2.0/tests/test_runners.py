"""The runners connect the screens to the engines: option labels, naming, batches."""

import socket

import pytest

from app import runners
from app.catalog import ALL_TOOLS
from app.jobs import run_function
from app.services.common import Cancelled, Job, UserError
from helpers import make_pdf, page_markers, rotations


def _opts(tool_id, **over):
    """Default option values exactly as the tool page would collect them."""
    _s, tool = ALL_TOOLS[tool_id]
    out = {}
    for o in tool.options:
        if o.kind == "info" or not o.label:
            continue
        if o.kind == "check":
            out[o.label] = bool(o.default)
        elif o.kind == "checks":
            out[o.label] = list(o.default or [])
        elif o.kind == "combo":
            out[o.label] = o.default if o.default in o.choices else o.choices[0]
        elif o.kind == "spin":
            out[o.label] = int(o.default or 1)
        else:
            out[o.label] = str(o.default or "")
    out.update(over)
    return out


def test_every_ready_tool_has_a_runner():
    for tool_id, (_s, tool) in ALL_TOOLS.items():
        assert tool.ready == (tool_id in runners.RUNNERS or tool_id in runners.WORKSPACE_TOOLS), tool_id


def test_batch_split_names_and_failure_isolation(tmp_path, job):
    a = make_pdf(tmp_path / "a.pdf", 4)
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-broken")
    res = runners.split(job, [str(a), str(bad)], _opts("split", **{"N (pages per file)": 2}), "", {})
    assert sorted(p.split("\\")[-1] for p in res["files"]) == ["a_p1-2.pdf", "a_p3-4.pdf"]
    assert "1 of 2" in res["message"] and any("bad.pdf" in w for w in res["warnings"])


def test_split_ranges_and_every_page(tmp_path, job):
    a = make_pdf(tmp_path / "a.pdf", 3)
    res = runners.split(job, [str(a)], _opts("split", **{"Split by": "Page ranges", "Page ranges": "3, 1-2"}),
                        "", {})
    assert [page_markers(f) for f in res["files"]] == [["MARKER-003"], ["MARKER-001", "MARKER-002"]]
    res = runners.split(job, [str(a)], _opts("split", **{"Split by": "Every page"}), str(tmp_path / "o"), {})
    assert len(res["files"]) == 3


def test_merge_needs_two_and_never_overwrites(tmp_path, job):
    a, b = make_pdf(tmp_path / "a.pdf", 1), make_pdf(tmp_path / "b.pdf", 1)
    with pytest.raises(UserError):
        runners.merge(job, [str(a)], _opts("merge"), "", {})
    r1 = runners.merge(job, [str(a), str(b)], _opts("merge"), "", {})
    r2 = runners.merge(job, [str(a), str(b)], _opts("merge"), "", {})
    assert r1["files"][0].endswith("Merged.pdf") and r2["files"][0].endswith("Merged (2).pdf")


def test_rotate_runner_modes(tmp_path, job):
    a = make_pdf(tmp_path / "a.pdf", 4)
    r = runners.rotate(job, [str(a)], _opts("rotate", **{"Rotate which pages": "Even pages only",
                                                          "Direction": "180° (upside down)"}), "", {})
    assert rotations(r["files"][0]) == [0, 180, 0, 180]
    r = runners.rotate(job, [str(a)], _opts("rotate", **{"Rotate which pages": "Selected pages",
                                                          "Page numbers": "1, 3-4"}), "", {})
    assert rotations(r["files"][0]) == [90, 0, 90, 90]
    with pytest.raises(UserError):
        runners.rotate(job, [str(a)], _opts("rotate", **{"Rotate which pages": "Selected pages"}), "", {})


def test_rotate_sideways_asks_before_saving(tmp_path, job):
    from test_utilities import _sideways_doc
    src = _sideways_doc(tmp_path / "s.pdf", [(0, 0), (90, 0)])
    opts = _opts("rotate", **{"Rotate which pages": "Sideways pages (detected automatically)"})
    assert runners.is_heavy("rotate", opts)
    first = runners.rotate(job, [str(src)], opts, "", {})
    assert first["files"] == [] and first["confirm"]["plans"] == {str(src): {2: 90}}
    assert any("page 2" in line for line in first["confirm"]["lines"])
    assert not list(tmp_path.glob("*_rotated.pdf"))                 # nothing saved yet
    opts["_plan"] = first["confirm"]["plans"]
    assert not runners.is_heavy("rotate", opts)
    done = runners.rotate(job, [str(src)], opts, "", {})
    assert rotations(done["files"][0]) == [0, 90]


def test_protect_runner_checks_confirmation(tmp_path, job):
    a = make_pdf(tmp_path / "a.pdf", 1)
    with pytest.raises(UserError):
        runners.protect(job, [str(a)], _opts("protect", Password="x1", **{"Confirm password": "x2"}), "", {})
    r = runners.protect(job, [str(a)], _opts("protect", Password="x1", **{"Confirm password": "x1"}), "", {})
    out = r["files"][0]
    r2 = runners.unprotect(job, [out], _opts("unprotect"), "", {out: "x1"})
    assert r2["files"][0].endswith("_protected_unlocked.pdf")


def test_extract_and_numbering_and_images(tmp_path, job):
    a = make_pdf(tmp_path / "a.pdf", 3)
    r = runners.extract(job, [str(a)], _opts("extract", Pages="3,1"), "", {})
    assert page_markers(r["files"][0]) == ["MARKER-003", "MARKER-001"]
    r = runners.numbering(job, [str(a)], _opts("numbering"), "", {})
    assert r["files"][0].endswith("a_numbered.pdf")
    r = runners.pdf2img(job, [str(a)], _opts("pdf2img", Pages="2"), "", {})
    assert r["files"][0].endswith("a_page002.png")


def test_rearrange_runner(tmp_path, job):
    a = make_pdf(tmp_path / "a.pdf", 3)
    r = runners.rearrange(job, [str(a)], {"_order": [[3, 0], [1, 90]]}, "", {})
    assert page_markers(r["files"][0]) == ["MARKER-003", "MARKER-001"]


def test_md_and_back(tmp_path, job):
    md = tmp_path / "n.md"
    md.write_text("# Title\n\nHello world\n", encoding="utf-8")
    r = runners.md2pdf(job, [str(md)], _opts("md2pdf"), "", {})
    r2 = runners.pdf2md(job, [r["files"][0]], _opts("pdf2md", **{"OCR for scanned pages": "Off"}), "", {})
    assert "# Title" in open(r2["files"][0], encoding="utf-8").read()


def test_cancel_and_errors_through_run_function(tmp_path):
    a = make_pdf(tmp_path / "a.pdf", 3)
    status, payload = run_function(runners.split, {"files": [str(a)], "opts": _opts("split"), "out_dir": "",
                                                   "passwords": {}}, lambda *a: None, lambda: True)
    assert status == "cancelled"
    status, payload = run_function(runners.extract, {"files": [str(a)], "opts": _opts("extract", Pages="9"),
                                                     "out_dir": "", "passwords": {}}, lambda *a: None, lambda: False)
    assert status == "error" and "out of range" in payload


def test_everything_runs_offline(tmp_path, job, monkeypatch):
    """No engine may open a network connection."""
    def blocked(*a, **k):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    a = make_pdf(tmp_path / "a.pdf", 3)
    b = make_pdf(tmp_path / "b.pdf", 2)
    md = tmp_path / "n.md"
    md.write_text("# T\n\n![r](https://example.com/x.png)\n", encoding="utf-8")
    runners.merge(job, [str(a), str(b)], _opts("merge"), "", {})
    runners.rotate(job, [str(a)], _opts("rotate"), "", {})
    runners.md2pdf(job, [str(md)], _opts("md2pdf"), "", {})
    runners.pdf2md(job, [str(a)], _opts("pdf2md"), "", {})
