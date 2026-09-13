"""Load and apply learned classification rules."""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path

import yaml

VALID_ACTIONS = {"keep", "auto-trash", "ask"}


def load_rules(path) -> list:
    p = Path(path)
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text()) or {}
    return list(data.get("rules", []))


def match_action(path: str, rules: list):
    for rule in rules:
        pattern = os.path.expanduser(str(rule.get("pattern", "")))
        if pattern and fnmatch.fnmatch(path, pattern):
            action = rule.get("action", "ask")
            return (action if action in VALID_ACTIONS else "ask"), rule
    return "ask", None


def bump_applied(rules: list, rule_id: str) -> None:
    for rule in rules:
        if rule.get("id") == rule_id:
            rule["times_applied"] = int(rule.get("times_applied", 0)) + 1
            return


def save_rules(path, rules: list) -> None:
    Path(path).write_text(yaml.safe_dump({"rules": rules}, sort_keys=False))
