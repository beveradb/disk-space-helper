import os
import json
import scan
from dsh_lib import db


def _make_tree(root):
    (root / "proj" / "node_modules" / "pkg").mkdir(parents=True)
    (root / "proj" / "node_modules" / "pkg" / "big.js").write_bytes(b"x" * (12 * 1024 * 1024))
    (root / "Downloads").mkdir()
    (root / "Downloads" / "small.txt").write_bytes(b"y" * 1024)  # below threshold
    (root / "Downloads" / "movie.mov").write_bytes(b"z" * (20 * 1024 * 1024))


def test_is_excluded():
    assert scan.is_excluded("/System/foo", scan.DEFAULT_EXCLUDES) is True
    assert scan.is_excluded("/Users/a/x", scan.DEFAULT_EXCLUDES) is False


def test_scan_records_rollups_and_large_files(tmp_path):
    _make_tree(tmp_path)
    conn = db.connect(tmp_path / "snap.sqlite")
    summary = scan.scan_tree([str(tmp_path)], conn, min_file_bytes=10 * 1024 * 1024,
                             excludes=set())
    conn.commit()

    paths = {r["path"]: r for r in conn.execute("SELECT * FROM entries").fetchall()}
    # node_modules recorded as a dir rollup, its inner big.js NOT individually listed
    nm = str(tmp_path / "proj" / "node_modules")
    assert nm in paths and paths[nm]["kind"] == "dir"
    assert str(tmp_path / "proj" / "node_modules" / "pkg" / "big.js") not in paths
    # large movie file individually recorded; small.txt not
    assert str(tmp_path / "Downloads" / "movie.mov") in paths
    assert str(tmp_path / "Downloads" / "small.txt") not in paths
    assert summary["entries"] >= 1


def test_main_writes_summary_json(tmp_path, monkeypatch, capsys):
    _make_tree(tmp_path)
    out = tmp_path / "snap.sqlite"
    monkeypatch.setattr(scan.dfree, "free_bytes", lambda *a, **k: 42)
    rc = scan.main(["--roots", str(tmp_path), "--min-mib", "10", "--out", str(out)])
    assert rc == 0
    assert out.exists()
    summ = json.loads((out.parent / "summary.json").read_text())
    assert "totals" in summ and summ["df_free"] == 42


def test_ordinary_dir_rollup_and_exact_category_totals(tmp_path, monkeypatch):
    # sizes.classify() only tags paths under the real $HOME/Downloads; point
    # $HOME at tmp_path so the synthetic tree below is classified as intended.
    monkeypatch.setenv("HOME", str(tmp_path))
    d = tmp_path / "Downloads" / "manysmall"
    d.mkdir(parents=True)
    for i in range(6):
        (d / f"f{i}.bin").write_bytes(b"x" * (2 * 1024 * 1024))  # 6x2MiB sub-threshold
    conn = db.connect(tmp_path / "s.sqlite")
    summary = scan.scan_tree([str(tmp_path)], conn,
                             min_file_bytes=10 * 1024 * 1024,  # each 2MiB file below
                             dir_min_bytes=10 * 1024 * 1024,   # 12MiB dir above
                             excludes=set())
    conn.commit()
    rows = {r["path"]: r for r in conn.execute("SELECT * FROM entries").fetchall()}
    dpath = str(d)
    assert dpath in rows and rows[dpath]["kind"] == "dir"
    assert rows[dpath]["physical"] >= 12 * 1024 * 1024
    assert str(d / "f0.bin") not in rows  # small files not individually recorded
    totals = db.totals_by_category(conn)
    assert totals.get("downloads", 0) >= 12 * 1024 * 1024  # exact, includes small files
    assert summary["total_physical"] >= 12 * 1024 * 1024
