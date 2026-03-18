import json
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checks_resolver import (
    compute_required_checks,
    compute_risk_tier,
    evaluate_docs_drift,
    load_contract,
    normalize_path,
    path_matches,
    read_changed_files,
    requires_browser_evidence,
)


class TestNormalizePath(unittest.TestCase):
    def test_strips_leading_dot_slash(self):
        self.assertEqual(normalize_path("./lib/foo.ex"), "lib/foo.ex")

    def test_strips_leading_slash(self):
        self.assertEqual(normalize_path("/lib/foo.ex"), "lib/foo.ex")

    def test_normalizes_backslashes(self):
        self.assertEqual(normalize_path("lib\\foo.ex"), "lib/foo.ex")

    def test_strips_whitespace(self):
        self.assertEqual(normalize_path("  lib/foo.ex  "), "lib/foo.ex")


class TestPathMatches(unittest.TestCase):
    def test_glob_match(self):
        self.assertTrue(path_matches("lib/fac/tools/agent.ex", "lib/fac/tools/**"))

    def test_no_match(self):
        self.assertFalse(path_matches("test/foo_test.exs", "lib/fac/tools/**"))

    def test_wildcard_all(self):
        self.assertTrue(path_matches("anything.txt", "**"))


class TestComputeRiskTier(unittest.TestCase):
    def test_high_risk_controller(self):
        rules = {
            "high": ["lib/fac_web/controllers/**"],
            "medium": ["lib/fac/**"],
            "low": ["**"],
        }
        self.assertEqual(compute_risk_tier(["lib/fac_web/controllers/page_controller.ex"], rules), "high")

    def test_medium_risk(self):
        rules = {
            "high": ["lib/fac_web/controllers/**"],
            "medium": ["lib/fac/**"],
            "low": ["**"],
        }
        self.assertEqual(compute_risk_tier(["lib/fac/repo.ex"], rules), "medium")

    def test_low_risk_default(self):
        rules = {
            "high": ["lib/fac_web/controllers/**"],
            "medium": ["lib/fac/**"],
            "low": ["**"],
        }
        self.assertEqual(compute_risk_tier(["README.md"], rules), "low")

    def test_empty_files(self):
        rules = {"high": ["lib/**"]}
        self.assertEqual(compute_risk_tier([], rules), "low")


class TestComputeRequiredChecks(unittest.TestCase):
    def test_returns_checks_for_tier(self):
        contract = {
            "mergePolicy": {
                "high": {"requiredChecks": ["risk-policy-gate", "ci-pipeline"]},
                "low": {"requiredChecks": ["risk-policy-gate"]},
            }
        }
        self.assertEqual(compute_required_checks(contract, "high"), ["risk-policy-gate", "ci-pipeline"])

    def test_fallback_empty(self):
        contract = {"mergePolicy": {}}
        self.assertEqual(compute_required_checks(contract, "high"), [])


class TestEvaluateDocsDrift(unittest.TestCase):
    def test_violation_detected(self):
        rules = [
            {
                "name": "api-docs",
                "whenTouched": ["lib/fac_web/controllers/**"],
                "requireAny": ["docs/**", "README.md"],
            }
        ]
        violations = evaluate_docs_drift(["lib/fac_web/controllers/page_controller.ex"], rules)
        self.assertEqual(len(violations), 1)
        self.assertIn("api-docs", violations[0])

    def test_no_violation_when_docs_updated(self):
        rules = [
            {
                "name": "api-docs",
                "whenTouched": ["lib/fac_web/controllers/**"],
                "requireAny": ["docs/**", "README.md"],
            }
        ]
        violations = evaluate_docs_drift(
            ["lib/fac_web/controllers/page_controller.ex", "README.md"], rules
        )
        self.assertEqual(len(violations), 0)


class TestRequiresBrowserEvidence(unittest.TestCase):
    def test_ui_path_requires_evidence(self):
        contract = {"evidencePolicy": {"uiImpactPaths": ["assets/**"]}}
        self.assertTrue(requires_browser_evidence(["assets/js/app.js"], contract))

    def test_non_ui_path(self):
        contract = {"evidencePolicy": {"uiImpactPaths": ["assets/**"]}}
        self.assertFalse(requires_browser_evidence(["lib/fac/repo.ex"], contract))


class TestReadChangedFiles(unittest.TestCase):
    def test_reads_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("lib/foo.ex\nlib/bar.ex\n")
            f.flush()
            files = read_changed_files(f.name)
        self.assertEqual(files, ["lib/foo.ex", "lib/bar.ex"])

    def test_missing_file(self):
        self.assertEqual(read_changed_files("/nonexistent/path.txt"), [])


if __name__ == "__main__":
    unittest.main()
