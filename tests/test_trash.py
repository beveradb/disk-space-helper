from unittest import mock
from dsh_lib import trash


def test_to_trash_uses_finder_first(tmp_path):
    f = tmp_path / "junk.bin"
    f.write_text("x")
    runner = mock.Mock(return_value=mock.Mock(returncode=0, stderr=""))
    res = trash.to_trash(str(f), runner=runner)
    assert res.ok and res.method == "finder"
    runner.assert_called_once()
    assert runner.call_args.args[0][0] == "osascript"


def test_to_trash_falls_back_to_move(tmp_path, monkeypatch):
    f = tmp_path / "junk.bin"
    f.write_text("x")
    fake_trash = tmp_path / "Trash"
    fake_trash.mkdir()
    monkeypatch.setattr(trash, "_home_trash", lambda: fake_trash)

    def boom(*a, **k):
        raise RuntimeError("no finder")
    res = trash.to_trash(str(f), runner=boom)
    assert res.ok and res.method == "move"
    assert (fake_trash / "junk.bin").exists()
    assert not f.exists()


def test_finder_script_escapes_quotes_and_backslashes():
    captured = {}

    def runner(cmd, capture_output=False, text=False):
        captured["cmd"] = cmd
        return mock.Mock(returncode=0, stderr="")

    weird = '/tmp/O\'Brien\'s "weird"\\backup.zip'
    res = trash.to_trash(weird, runner=runner)
    assert res.ok and res.method == "finder"
    script = captured["cmd"][2]  # ["osascript", "-e", <script>]
    # backslash escaped to \\ and double-quote escaped to \" inside the literal
    assert '\\\\backup.zip' in script
    assert '\\"weird\\"' in script
