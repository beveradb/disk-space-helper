import json
from unittest import mock
import reclaim


def test_is_safe():
    assert reclaim.is_safe("/System/x") is False
    assert reclaim.is_safe("/Library/x") is False
    assert reclaim.is_safe("relative/x") is False
    import os
    assert reclaim.is_safe(os.path.expanduser("~/Downloads/x")) is True


def test_is_safe_rejects_path_traversal_into_never_touch():
    # Absolute path that textually starts under a safe dir but normalizes
    # (via ".." components) into a NEVER_TOUCH prefix must be refused.
    sneaky = "/Users/whoever/Downloads/../../../System/CoreServices"
    assert reclaim.is_safe(sneaky) is False


def test_dry_run_does_not_trash(tmp_path):
    import os
    # Use a path under $HOME (not tmp_path): on macOS, pytest's tmp_path
    # resolves under /private/var, which NEVER_TOUCH correctly refuses.
    # Dry-run performs no filesystem I/O, so no real path needs to exist.
    plan = [{"path": os.path.expanduser("~/dsh-test-dry-run-item"), "reason": "test"}]
    fn = mock.Mock()
    res = reclaim.run_plan(plan, apply=False, trash_fn=fn)
    fn.assert_not_called()
    assert res["planned"] and not res["trashed"]


def test_apply_trashes_and_logs(tmp_path):
    import os
    target = os.path.expanduser("~/dsh-test-junk")  # safe (under home)
    log = tmp_path / "decisions.jsonl"
    plan = [{"path": target, "reason": "test", "rule_id": "r1"},
            {"path": "/System/nope", "reason": "bad"}]
    fn = mock.Mock(return_value=mock.Mock(ok=True, method="finder", error=None))
    res = reclaim.run_plan(plan, apply=True, trash_fn=fn, log_path=log, run_id="R1")
    assert res["trashed"] == [target]
    assert res["refused"] == ["/System/nope"]
    fn.assert_called_once_with(target)
    lines = [json.loads(l) for l in log.read_text().splitlines()]
    assert lines[0]["path"] == target and lines[0]["run_id"] == "R1"
    assert lines[1]["path"] == "/System/nope" and lines[1]["action"] == "refused"


def test_is_safe_case_insensitive_never_touch():
    assert reclaim.is_safe("/library/Caches/x") is False
    assert reclaim.is_safe("/SYSTEM/CoreServices") is False
    assert reclaim.is_safe("/System/x") is False


def test_dry_run_writes_no_log(tmp_path):
    import os
    from unittest import mock
    log = tmp_path / "decisions.jsonl"
    plan = [{"path": os.path.expanduser("~/dsh-x"), "reason": "t"},
            {"path": "/System/nope", "reason": "bad"}]
    fn = mock.Mock()
    reclaim.run_plan(plan, apply=False, trash_fn=fn, log_path=log)
    assert not log.exists()  # dry-run must be side-effect-free
