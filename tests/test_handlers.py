from unittest import mock
from handlers import base, homebrew, xcode, icloud, dropbox


def test_run_cmd_no_raise():
    rc, out, err = base.run_cmd(["/bin/sh", "-c", "exit 3"])
    assert rc == 3


def test_run_cmd_missing_binary_degrades():
    rc, out, err = base.run_cmd(["dsh-definitely-not-a-real-binary-xyz"])
    assert rc == 127 and out == "" and err == ""


def test_homebrew_report_parses(tmp_path):
    sample = "Would remove: /Users/a/Library/Caches/Homebrew/foo (1.2GB)\n" \
             "==> This operation would free approximately 3.5GB of disk space.\n"
    runner = mock.Mock(return_value=mock.Mock(returncode=0, stdout=sample, stderr=""))
    rep = homebrew.report(runner=runner)
    assert rep["handler"] == "homebrew"
    assert rep["reclaimable_bytes"] == int(3.5 * 1000 ** 3)


def test_xcode_report_sums(tmp_path, monkeypatch):
    dd = tmp_path / "DerivedData" / "App"
    dd.mkdir(parents=True)
    (dd / "big").write_bytes(b"x" * (5 * 1024 * 1024))
    monkeypatch.setattr(xcode, "_roots", lambda: [tmp_path / "DerivedData"])
    rep = xcode.report()
    assert rep["reclaimable_bytes"] >= 5 * 1024 * 1024


def test_icloud_evict_invokes_brctl():
    runner = mock.Mock(return_value=mock.Mock(returncode=0, stdout="", stderr=""))
    ok = icloud.evict("/Users/a/Library/Mobile Documents/x", runner=runner)
    assert ok is True
    assert runner.call_args.args[0][:2] == ["brctl", "evict"]


def test_dropbox_report_is_nondestructive(tmp_path, monkeypatch):
    d = tmp_path / "Dropbox"
    (d / "sub").mkdir(parents=True)
    (d / "sub" / "local.bin").write_bytes(b"z" * (2 * 1024 * 1024))
    monkeypatch.setattr(dropbox, "_dropbox_root", lambda: d)
    rep = dropbox.report()
    assert rep["experimental"] is True
    assert rep["reclaimable_bytes"] >= 2 * 1024 * 1024
    assert "manual" in rep["detail"].lower()


def test_icloud_available_checks_root_and_brctl(monkeypatch, tmp_path):
    root = tmp_path / "Mobile Documents"
    root.mkdir()
    monkeypatch.setattr(icloud, "_icloud_root", lambda: root)
    runner = mock.Mock(return_value=mock.Mock(returncode=0, stdout="", stderr=""))
    assert icloud.available(runner=runner) is True
    # missing root => unavailable, without calling brctl
    monkeypatch.setattr(icloud, "_icloud_root", lambda: tmp_path / "nope")
    assert icloud.available(runner=runner) is False


def test_icloud_report_sums_local(tmp_path, monkeypatch):
    root = tmp_path / "Mobile Documents"
    (root / "iCloud~app").mkdir(parents=True)
    (root / "iCloud~app" / "local.bin").write_bytes(b"z" * (3 * 1024 * 1024))
    monkeypatch.setattr(icloud, "_icloud_root", lambda: root)
    rep = icloud.report()
    assert rep["handler"] == "icloud"
    assert rep["reclaimable_bytes"] >= 3 * 1024 * 1024
    assert "brctl evict" in rep["detail"]
