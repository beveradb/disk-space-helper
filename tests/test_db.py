from dsh_lib import db


def _entry(path, physical, category="other", kind="file"):
    return dict(path=path, kind=kind, category=category, logical=physical,
                physical=physical, mtime=1.0, atime=1.0, dataless=0)


def test_insert_and_query(tmp_path):
    conn = db.connect(tmp_path / "s.sqlite")
    db.set_meta(conn, "df_free", "123")
    assert db.get_meta(conn, "df_free") == "123"
    db.insert_entry(conn, _entry("/a", 100, "dev-cache"))
    db.insert_entry(conn, _entry("/b", 300, "media"))
    db.insert_entry(conn, _entry("/c", 50, "dev-cache"))
    conn.commit()

    top = db.top_by_physical(conn, limit=2)
    assert [r["path"] for r in top] == ["/b", "/a"]

    top_dev = db.top_by_physical(conn, category="dev-cache")
    assert [r["path"] for r in top_dev] == ["/a", "/c"]

    totals = db.totals_by_category(conn)
    assert totals["dev-cache"] == 150
    assert totals["media"] == 300
