import diff
from dsh_lib import db


def _seed(path, rows):
    conn = db.connect(path)
    for p, phys in rows:
        db.insert_entry(conn, dict(path=p, kind="file", category="other",
                                   logical=phys, physical=phys, mtime=1.0,
                                   atime=1.0, dataless=0))
    conn.commit()
    return conn


def test_diff(tmp_path):
    old = _seed(tmp_path / "o.sqlite", [("/a", 100), ("/b", 500), ("/gone", 300)])
    new = _seed(tmp_path / "n.sqlite", [("/a", 400), ("/b", 200), ("/new", 250)])
    d = diff.diff_snapshots(old, new)
    assert {"path": "/a", "old": 100, "new": 400, "delta": 300} in d["grew"]
    assert {"path": "/b", "old": 500, "new": 200, "delta": -300} in d["shrank"]
    assert {"path": "/new", "old": 0, "new": 250, "delta": 250} in d["appeared"]
    assert {"path": "/gone", "old": 300, "new": 0, "delta": -300} in d["disappeared"]
