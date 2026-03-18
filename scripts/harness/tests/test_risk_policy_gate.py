import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import risk_policy_gate as gate


class RiskPolicyGateTests(unittest.TestCase):
    def _make_contract(self, **overrides):
        contract = {
            "rolloutPolicy": {
                "currentPhase": "phase-0",
                "phases": {
                    "phase-0": {
                        "enforceMergeBlock": False,
                        "enforceReviewState": False,
                        "enableRemediation": False,
                        "requireEvidence": False,
                        "enforceDocsDrift": False,
                    }
                },
            },
            "riskTierRules": {"low": ["**"]},
            "mergePolicy": {"low": {"requiredChecks": ["risk-policy-gate"]}},
            "reviewPolicy": {
                "provider": "coderabbit",
                "checkRunName": "coderabbit-review",
                "timeoutMinutes": 1,
                "weakConfidenceThreshold": 0.55,
                "actionableSummaryKeywords": [],
            },
            "reviewProviders": {
                "providers": {
                    "coderabbit": {"enforcement": "advisory"},
                }
            },
            "docsDriftRules": [],
            "evidencePolicy": {"uiImpactPaths": []},
        }
        contract.update(overrides)
        return contract

    def test_pass_in_phase_0(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            changed = tmp / "changed.txt"
            changed.write_text("docs/readme.md\n", encoding="utf-8")

            contract = self._make_contract()
            contract_path = tmp / "contract.json"
            contract_path.write_text(json.dumps(contract), encoding="utf-8")

            review_findings = tmp / "review-findings.json"
            report_out = tmp / "risk-policy-report.json"

            args = Namespace(
                pr=1,
                head_sha="abc1234",
                changed_files=str(changed),
                contract=str(contract_path),
                repo="",
                token_env="GITHUB_TOKEN",
                review_findings=str(review_findings),
                browser_evidence_manifest=str(tmp / "browser-evidence-manifest.json"),
                report_out=str(report_out),
                poll_seconds=1,
            )

            with patch.object(gate, "parse_args", return_value=args):
                exit_code = gate.main()

            self.assertEqual(exit_code, 0)
            report = json.loads(report_out.read_text(encoding="utf-8"))
            self.assertEqual(report["decision"], "pass")

    def test_high_risk_detected(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            changed = tmp / "changed.txt"
            changed.write_text("lib/fac_web/controllers/api.ex\n", encoding="utf-8")

            contract = self._make_contract(
                riskTierRules={
                    "high": ["lib/fac_web/controllers/**"],
                    "low": ["**"],
                }
            )
            contract_path = tmp / "contract.json"
            contract_path.write_text(json.dumps(contract), encoding="utf-8")

            review_findings = tmp / "review-findings.json"
            report_out = tmp / "risk-policy-report.json"

            args = Namespace(
                pr=2,
                head_sha="def5678",
                changed_files=str(changed),
                contract=str(contract_path),
                repo="",
                token_env="GITHUB_TOKEN",
                review_findings=str(review_findings),
                browser_evidence_manifest=str(tmp / "browser-evidence-manifest.json"),
                report_out=str(report_out),
                poll_seconds=1,
            )

            with patch.object(gate, "parse_args", return_value=args):
                exit_code = gate.main()

            self.assertEqual(exit_code, 0)
            report = json.loads(report_out.read_text(encoding="utf-8"))
            self.assertEqual(report["risk_tier"], "high")


class TestRerunCommentDedupe(unittest.TestCase):
    def test_module_imports(self):
        import rerun_comment_dedupe
        self.assertTrue(hasattr(rerun_comment_dedupe, "main"))


if __name__ == "__main__":
    unittest.main()
