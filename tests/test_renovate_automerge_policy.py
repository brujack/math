"""Assert renovate.json's auto-merge policy is exhaustive over the updateType enum.

An updateType that matches no packageRule is not an error in Renovate -- rules are
additive overrides merged onto base config, and base ``automerge`` is false, so an
unmatched type is silently held. That makes "held deliberately" and "held because
nobody thought of it" the same observable in renovate.json alone. This module is
where they stop being the same: every type must be either auto-merged by a rule or
named in _DELIBERATELY_HELD with a reason.

_UPDATE_TYPES is transcribed from https://docs.renovatebot.com/renovate-schema.json,
the URL renovate.json's own $schema names. It is hand-maintained, so it cannot catch
an eleventh type added upstream -- see test_update_types_matches_documented_count for
the tripwire that at least makes the count explicit.
"""

import copy
import json
import pathlib
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
RENOVATE_JSON = REPO_ROOT / "renovate.json"

# The full updateType enum, from the schema renovate.json's $schema points at.
_UPDATE_TYPES = frozenset(
    {
        "major",
        "minor",
        "patch",
        "pin",
        "pinDigest",
        "digest",
        "lockFileMaintenance",
        "rollback",
        "bump",
        "replacement",
    }
)

# Types deliberately NOT auto-merged, each with the reason it is held.
_DELIBERATELY_HELD = {
    "major": "breaking by definition; needs a human to read the upstream changelog",
    "lockFileMaintenance": "wholesale lockfile regeneration; diff is unreviewable in bulk",
    "rollback": "reverting a dependency is a decision, never routine",
    "bump": "rewrites a manifest constraint rather than resolving within it",
    "replacement": "swaps one dependency for a DIFFERENT one; at least as consequential as a major",
}

# The label the auto-merge workflow requires before it will merge a Renovate PR.
_AUTOMERGE_LABEL = "automerge-ok"


def load_config(path=RENOVATE_JSON):
    """Return the parsed renovate.json."""
    return json.loads(path.read_text())


def automerged_types(config):
    """Return the set of updateTypes some rule auto-merges."""
    types = set()
    for rule in config.get("packageRules", []):
        if rule.get("automerge") is True:
            types.update(rule.get("matchUpdateTypes", []))
    return types


def rules_missing_label(config, label=_AUTOMERGE_LABEL):
    """Return auto-merging rules that do not add ``label``.

    The auto-merge workflow gates on an affirmative label, so an automerging rule
    without it produces a PR Renovate believes is auto-mergeable and the workflow
    holds -- a disagreement between two systems that both look correct alone.
    """
    return [
        rule
        for rule in config.get("packageRules", [])
        if rule.get("automerge") is True and label not in rule.get("addLabels", [])
    ]


_PY_DEP_NAMES = ["python", "library/python", "docker.io/library/python"]
_PY_PACKAGE_NAME = "actions/python-versions"
_NEGATED_DEP_NAMES = [f"!{name}" for name in _PY_DEP_NAMES]
_NEGATED_PACKAGE_NAMES = [f"!{_PY_PACKAGE_NAME}"]
_NEGATED_MANAGERS = ["!terraform", "!gomod"]


def python_hold_gaps(config):
    """Return one message per way the Python-interpreter hold is incomplete.

    Every rule that automerges (or adds the guard label) must exclude the Python
    interpreter by depName and packageName and exclude the terraform/gomod managers,
    and the two explicit hold rules must exist with automerge false.
    """
    gaps = []
    rules = config.get("packageRules", [])
    for index, rule in enumerate(rules):
        carries_label = _AUTOMERGE_LABEL in (
            rule.get("addLabels", []) + rule.get("labels", [])
        )
        if rule.get("automerge") is not True and not carries_label:
            continue
        for field, required in (
            ("matchDepNames", _NEGATED_DEP_NAMES),
            ("matchPackageNames", _NEGATED_PACKAGE_NAMES),
            ("matchManagers", _NEGATED_MANAGERS),
        ):
            for entry in required:
                if entry not in rule.get(field, []):
                    gaps.append(f"rule {index}: {field} lacks {entry}")
    hold_rules = (
        ("matchDepNames", _PY_DEP_NAMES),
        ("matchPackageNames", [_PY_PACKAGE_NAME]),
    )
    for field, expected in hold_rules:
        if not any(
            rule.get(field) == expected and rule.get("automerge") is False
            for rule in rules
        ):
            gaps.append(f"missing hold rule: {field} == {expected} automerge false")
    return gaps


class TestUpdateTypeEnum(unittest.TestCase):
    def test_update_types_matches_documented_count(self):
        # A bare tripwire: the schema enum had 10 members when this was written.
        # If Renovate adds an eleventh, this stays green -- which is exactly why
        # the count is asserted rather than assumed.
        self.assertEqual(len(_UPDATE_TYPES), 10)

    def test_held_types_are_a_subset_of_the_enum(self):
        self.assertLessEqual(set(_DELIBERATELY_HELD), _UPDATE_TYPES)

    def test_every_held_type_carries_a_nonempty_reason(self):
        for update_type, reason in _DELIBERATELY_HELD.items():
            with self.subTest(update_type=update_type):
                self.assertTrue(reason.strip(), f"{update_type} held with no reason")


class TestRenovateConfigPolicy(unittest.TestCase):
    def setUp(self):
        self.config = load_config()

    def test_every_update_type_is_automerged_or_deliberately_held(self):
        classified = automerged_types(self.config) | set(_DELIBERATELY_HELD)
        self.assertEqual(
            _UPDATE_TYPES - classified,
            set(),
            "updateType is neither auto-merged nor named in _DELIBERATELY_HELD",
        )

    def test_no_update_type_is_both_automerged_and_held(self):
        self.assertEqual(
            automerged_types(self.config) & set(_DELIBERATELY_HELD),
            set(),
        )

    def test_every_automerging_rule_adds_the_guard_label(self):
        self.assertEqual(rules_missing_label(self.config), [])

    def test_package_rules_begin_with_the_canonical_prefix(self):
        # renovate_preset_sync.py tests prefix equality against ai-config's
        # renovate-presets/default.json. Anything inserted ahead of these two
        # reports DRIFT and exits 1.
        rules = self.config["packageRules"]
        self.assertGreaterEqual(len(rules), 2)
        self.assertEqual(rules[0].get("matchUpdateTypes"), ["minor", "patch"])
        self.assertEqual(rules[1].get("matchUpdateTypes"), ["major"])


def _automerge_ok_rule_indexes(config):
    return [
        i
        for i, rule in enumerate(config["packageRules"])
        if _AUTOMERGE_LABEL in rule.get("addLabels", [])
    ]


class TestPythonHold(unittest.TestCase):
    def setUp(self):
        self.config = load_config()

    def test_real_config_has_no_gaps(self):
        self.assertEqual(python_hold_gaps(self.config), [])

    def test_there_are_two_automerge_ok_rules(self):
        self.assertEqual(len(_automerge_ok_rule_indexes(self.config)), 2)

    def test_removing_any_required_entry_is_detected(self):
        required = (
            [("matchDepNames", e) for e in _NEGATED_DEP_NAMES]
            + [("matchPackageNames", e) for e in _NEGATED_PACKAGE_NAMES]
            + [("matchManagers", e) for e in _NEGATED_MANAGERS]
        )
        for index in _automerge_ok_rule_indexes(self.config):
            for field, entry in required:
                with self.subTest(rule=index, field=field, entry=entry):
                    mutated = copy.deepcopy(self.config)
                    mutated["packageRules"][index][field].remove(entry)
                    self.assertNotEqual(python_hold_gaps(mutated), [])

    def test_removing_either_hold_rule_is_detected(self):
        for field in ("matchDepNames", "matchPackageNames"):
            with self.subTest(field=field):
                mutated = copy.deepcopy(self.config)
                mutated["packageRules"] = [
                    r
                    for r in mutated["packageRules"]
                    if not (field in r and r.get("automerge") is False)
                ]
                self.assertNotEqual(python_hold_gaps(mutated), [])

    def _rule_gaps(self, config):
        # Gaps about a packageRule's own negations, as opposed to missing hold rules.
        return [g for g in python_hold_gaps(config) if g.startswith("rule ")]

    def test_label_only_rule_is_checked(self):
        config = {"packageRules": [{"addLabels": [_AUTOMERGE_LABEL]}]}
        self.assertNotEqual(self._rule_gaps(config), [])

    def test_labels_only_rule_is_checked(self):
        config = {"packageRules": [{"labels": [_AUTOMERGE_LABEL]}]}
        self.assertNotEqual(self._rule_gaps(config), [])

    def test_automerge_only_rule_is_checked(self):
        config = {"packageRules": [{"automerge": True}]}
        self.assertNotEqual(self._rule_gaps(config), [])

    def test_non_automerging_unlabelled_rule_is_not_checked(self):
        config = {"packageRules": [{"matchUpdateTypes": ["major"], "automerge": False}]}
        self.assertEqual(self._rule_gaps(config), [])

    def test_hold_rule_without_automerge_false_is_detected(self):
        for field in ("matchDepNames", "matchPackageNames"):
            with self.subTest(field=field):
                mutated = copy.deepcopy(self.config)
                for rule in mutated["packageRules"]:
                    if field in rule and rule.get("automerge") is False:
                        del rule["automerge"]
                gaps = python_hold_gaps(mutated)
                self.assertTrue(
                    any(g.startswith(f"missing hold rule: {field}") for g in gaps),
                    gaps,
                )

    def test_hold_rule_with_partial_dep_names_is_detected(self):
        for name in _PY_DEP_NAMES:
            with self.subTest(removed=name):
                mutated = copy.deepcopy(self.config)
                for rule in mutated["packageRules"]:
                    if rule.get("automerge") is False and "matchDepNames" in rule:
                        rule["matchDepNames"].remove(name)
                gaps = python_hold_gaps(mutated)
                self.assertTrue(
                    any(g.startswith("missing hold rule: matchDepNames") for g in gaps),
                    gaps,
                )

    def test_empty_config_reports_both_missing_hold_rules(self):
        self.assertEqual(len(python_hold_gaps({})), 2)


class TestHelperBoundaries(unittest.TestCase):
    """Boundary and error paths for the helpers, exercised on synthetic configs."""

    def test_automerged_types_on_empty_config(self):
        self.assertEqual(automerged_types({}), set())

    def test_automerged_types_on_empty_rule_list(self):
        self.assertEqual(automerged_types({"packageRules": []}), set())

    def test_automerge_false_is_not_counted(self):
        config = {"packageRules": [{"matchUpdateTypes": ["major"], "automerge": False}]}
        self.assertEqual(automerged_types(config), set())

    def test_absent_automerge_key_is_not_counted(self):
        config = {"packageRules": [{"matchUpdateTypes": ["major"]}]}
        self.assertEqual(automerged_types(config), set())

    def test_truthy_non_true_automerge_is_not_counted(self):
        # Renovate's automerge is a boolean; a string "true" is a config error,
        # not an instruction, and must not be read as one.
        config = {
            "packageRules": [{"matchUpdateTypes": ["major"], "automerge": "true"}]
        }
        self.assertEqual(automerged_types(config), set())

    def test_rules_missing_label_flags_an_unlabelled_automerging_rule(self):
        config = {"packageRules": [{"matchUpdateTypes": ["patch"], "automerge": True}]}
        self.assertEqual(len(rules_missing_label(config)), 1)

    def test_rules_missing_label_ignores_non_automerging_rules(self):
        config = {"packageRules": [{"matchUpdateTypes": ["major"], "automerge": False}]}
        self.assertEqual(rules_missing_label(config), [])

    def test_rules_missing_label_accepts_a_labelled_rule(self):
        config = {
            "packageRules": [
                {
                    "matchUpdateTypes": ["patch"],
                    "automerge": True,
                    "addLabels": [_AUTOMERGE_LABEL],
                }
            ]
        }
        self.assertEqual(rules_missing_label(config), [])

    def test_load_config_raises_on_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            load_config(REPO_ROOT / "does-not-exist.json")

    def test_load_config_raises_on_malformed_json(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            bad = pathlib.Path(tmp) / "bad.json"
            bad.write_text("{not json")
            with self.assertRaises(json.JSONDecodeError):
                load_config(bad)


if __name__ == "__main__":
    unittest.main()
