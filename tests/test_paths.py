import importlib
import pytest


@pytest.fixture
def fresh_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("DSH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    import dsh_lib.paths as paths
    importlib.reload(paths)
    return paths


def test_data_dir_uses_env_and_is_created(fresh_paths, tmp_path):
    d = fresh_paths.data_dir()
    assert d == tmp_path / "data"
    assert d.is_dir()


def test_xdg_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("DSH_DATA_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    import dsh_lib.paths as paths
    importlib.reload(paths)
    assert paths.data_dir() == tmp_path / "xdg" / "disk-space-helper"


def test_subdirs_and_files(fresh_paths):
    assert fresh_paths.snapshots_dir().is_dir()
    assert fresh_paths.reports_dir().is_dir()
    assert fresh_paths.knowledge_dir().is_dir()
    assert fresh_paths.decisions_log().name == "decisions.jsonl"


def test_bootstrap_copies_examples(fresh_paths):
    fresh_paths.bootstrap()
    assert fresh_paths.profile_path().exists()
    assert fresh_paths.rules_path().exists()
    # Second call must not raise or overwrite.
    fresh_paths.profile_path().write_text("EDITED")
    fresh_paths.bootstrap()
    assert fresh_paths.profile_path().read_text() == "EDITED"
