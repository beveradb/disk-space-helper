import os
from dsh_lib import rules


RULESET = [
    {"id": "dd", "pattern": "~/Library/Developer/Xcode/DerivedData/*",
     "action": "auto-trash", "times_applied": 0},
    {"id": "keepphotos", "pattern": "~/Dropbox/Photos/*", "action": "keep"},
]


def test_match_action(monkeypatch):
    home = os.path.expanduser("~")
    a, rule = rules.match_action(f"{home}/Library/Developer/Xcode/DerivedData/App", RULESET)
    assert a == "auto-trash" and rule["id"] == "dd"
    a, rule = rules.match_action(f"{home}/Dropbox/Photos/2020", RULESET)
    assert a == "keep"
    a, rule = rules.match_action(f"{home}/random", RULESET)
    assert a == "ask" and rule is None


def test_bump_and_roundtrip(tmp_path):
    import copy
    rs = copy.deepcopy(RULESET)
    rules.bump_applied(rs, "dd")
    assert rs[0]["times_applied"] == 1
    p = tmp_path / "rules.yaml"
    rules.save_rules(p, rs)
    loaded = rules.load_rules(p)
    assert loaded[0]["id"] == "dd" and loaded[0]["times_applied"] == 1


def test_load_missing_returns_empty(tmp_path):
    assert rules.load_rules(tmp_path / "nope.yaml") == []
