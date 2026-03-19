"""Tests for pr_packet.py and media_manifest.py — stdlib only, no pip deps."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure harness scripts are importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestProviderOk(unittest.TestCase):
    """Test _provider_ok helper from pr_packet."""

    def setUp(self):
        from pr_packet import _provider_ok
        self._provider_ok = _provider_ok

    def test_success_no_actionable(self):
        ok, count, status = self._provider_ok({"status": "success", "findings": []})
        self.assertTrue(ok)
        self.assertEqual(count, 0)
        self.assertEqual(status, "success")

    def test_success_with_actionable(self):
        ok, count, status = self._provider_ok({
            "status": "success",
            "findings": [{"actionable": True}, {"actionable": False}],
        })
        self.assertFalse(ok)
        self.assertEqual(count, 1)

    def test_missing_status(self):
        ok, count, status = self._provider_ok({})
        self.assertFalse(ok)
        self.assertEqual(status, "missing")

    def test_failure_status(self):
        ok, count, status = self._provider_ok({"status": "failure", "findings": []})
        self.assertFalse(ok)
        self.assertEqual(status, "failure")


class TestBuildMediaSection(unittest.TestCase):
    """Test _build_media_section rendering."""

    def setUp(self):
        from pr_packet import _build_media_section
        self._build_media_section = _build_media_section

    def test_empty_manifest(self):
        lines = self._build_media_section({})
        text = "\n".join(lines)
        self.assertIn("No media attachments provided", text)

    def test_empty_items(self):
        lines = self._build_media_section({"items": []})
        text = "\n".join(lines)
        self.assertIn("No media attachments provided", text)

    def test_screenshot_embed(self):
        manifest = {
            "items": [{"type": "screenshot", "path": "artifacts/before.png", "label": "Before"}]
        }
        lines = self._build_media_section(manifest)
        text = "\n".join(lines)
        self.assertIn("![Before](artifacts/before.png)", text)
        self.assertIn("<details>", text)
        self.assertIn("</details>", text)

    def test_screenshot_with_url(self):
        manifest = {
            "items": [{"type": "screenshot", "url": "https://example.com/img.png", "label": "After"}]
        }
        lines = self._build_media_section(manifest)
        text = "\n".join(lines)
        self.assertIn("![After](https://example.com/img.png)", text)

    def test_loom_embed_with_thumbnail(self):
        manifest = {
            "items": [{
                "type": "loom",
                "url": "https://www.loom.com/share/abc123",
                "thumbnail": "https://cdn.loom.com/sessions/thumbnails/abc123.jpg",
            }]
        }
        lines = self._build_media_section(manifest)
        text = "\n".join(lines)
        self.assertIn("[![Loom recording](https://cdn.loom.com/sessions/thumbnails/abc123.jpg)]"
                       "(https://www.loom.com/share/abc123)", text)

    def test_loom_embed_no_thumbnail(self):
        manifest = {
            "items": [{"type": "loom", "url": "https://www.loom.com/share/abc123", "thumbnail": ""}]
        }
        lines = self._build_media_section(manifest)
        text = "\n".join(lines)
        self.assertIn("[Loom recording](https://www.loom.com/share/abc123)", text)

    def test_asciinema_embed(self):
        manifest = {
            "items": [{"type": "asciinema", "url": "https://asciinema.org/a/12345"}]
        }
        lines = self._build_media_section(manifest)
        text = "\n".join(lines)
        self.assertIn("[![asciicast](https://asciinema.org/a/12345.svg)]"
                       "(https://asciinema.org/a/12345)", text)

    def test_video_embed(self):
        manifest = {
            "items": [{"type": "video", "url": "https://example.com/vid.mp4", "label": "Demo"}]
        }
        lines = self._build_media_section(manifest)
        text = "\n".join(lines)
        self.assertIn("[Demo](https://example.com/vid.mp4)", text)

    def test_mixed_media(self):
        manifest = {
            "items": [
                {"type": "screenshot", "path": "a.png", "label": "A"},
                {"type": "loom", "url": "https://loom.com/share/x", "thumbnail": "https://cdn.loom.com/x.jpg"},
                {"type": "asciinema", "url": "https://asciinema.org/a/99"},
            ]
        }
        lines = self._build_media_section(manifest)
        text = "\n".join(lines)
        self.assertIn("![A](a.png)", text)
        self.assertIn("Loom recording", text)
        self.assertIn("asciicast", text)


class TestBuildMarkdown(unittest.TestCase):
    """Test full markdown assembly."""

    def setUp(self):
        from pr_packet import _build_markdown
        self._build_markdown = _build_markdown

    def test_markers_present(self):
        md = self._build_markdown(
            [{"label": "Test check", "passed": True, "details": "ok"}],
            ["", "## Validation Artifacts", "", "| a | b | c |"],
            ["", "## Execution Evidence", "", "_No media._"],
        )
        self.assertIn("<!-- pr-review-checklist:start -->", md)
        self.assertIn("<!-- pr-review-checklist:end -->", md)

    def test_checklist_items(self):
        md = self._build_markdown(
            [
                {"label": "Passed item", "passed": True, "details": "pass"},
                {"label": "Failed item", "passed": False, "details": "fail"},
            ],
            [],
            [],
        )
        self.assertIn("- [x] Passed item (pass)", md)
        self.assertIn("- [ ] Failed item (fail)", md)

    def test_all_three_sections(self):
        md = self._build_markdown(
            [{"label": "Check", "passed": True, "details": "ok"}],
            ["", "## Validation Artifacts"],
            ["", "## Execution Evidence"],
        )
        self.assertIn("## Acceptance Criteria", md)
        self.assertIn("## Validation Artifacts", md)
        self.assertIn("## Execution Evidence", md)


class TestBuildArtifactTable(unittest.TestCase):
    """Test artifact table rendering."""

    def setUp(self):
        from pr_packet import _build_artifact_table
        self._build_artifact_table = _build_artifact_table

    def test_table_structure(self):
        args = argparse.Namespace(
            risk_report="artifacts/risk-policy-report.json",
            review_findings="artifacts/review-findings.json",
            browser_evidence_manifest="artifacts/browser-evidence-manifest.json",
            out_json="artifacts/pr-review-packet.json",
        )
        lines = self._build_artifact_table(args, "pass", "success", True)
        text = "\n".join(lines)
        self.assertIn("## Validation Artifacts", text)
        self.assertIn("| Artifact | Path | Status |", text)
        self.assertIn("Risk policy report", text)
        self.assertIn("Review findings", text)
        self.assertIn("Evidence manifest", text)
        self.assertIn("PR review packet", text)

    def test_browser_not_ok(self):
        args = argparse.Namespace(
            risk_report="r.json",
            review_findings="f.json",
            browser_evidence_manifest="b.json",
            out_json="o.json",
        )
        lines = self._build_artifact_table(args, "pass", "success", False)
        text = "\n".join(lines)
        self.assertIn("missing", text)


class TestMainIntegration(unittest.TestCase):
    """Integration test: run main() with fixture files and verify outputs."""

    def _write_json(self, path: Path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def test_all_pass(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts = Path(tmpdir) / "artifacts"
            artifacts.mkdir()

            self._write_json(Path(tmpdir) / "harness" / "contract.json", {
                "evidencePolicy": {"requiredFlows": [], "requiredAssertions": []},
            })
            self._write_json(artifacts / "risk-policy-report.json", {
                "decision": "pass",
                "head_sha": "abc123",
                "pr_number": 42,
                "risk_tier": "low",
                "required_checks": [],
            })
            self._write_json(artifacts / "review-findings.json", {
                "status": "success",
                "findings": [],
            })
            self._write_json(artifacts / "sentry-logs-validation.json", {
                "status": "not-required",
                "ok": True,
            })
            self._write_json(artifacts / "media-manifest.json", {
                "items": [
                    {"type": "screenshot", "path": "artifacts/before.png", "label": "Before"},
                ],
            })

            from pr_packet import main

            old_argv = sys.argv
            try:
                sys.argv = [
                    "pr_packet.py",
                    "--contract", str(Path(tmpdir) / "harness" / "contract.json"),
                    "--risk-report", str(artifacts / "risk-policy-report.json"),
                    "--review-findings", str(artifacts / "review-findings.json"),
                    "--browser-evidence-manifest", str(artifacts / "browser-evidence-manifest.json"),
                    "--sentry-validation-report", str(artifacts / "sentry-logs-validation.json"),
                    "--media-manifest", str(artifacts / "media-manifest.json"),
                    "--out-json", str(artifacts / "pr-review-packet.json"),
                    "--out-md", str(artifacts / "pr-review-packet.md"),
                ]
                rc = main()
            finally:
                sys.argv = old_argv

            self.assertEqual(rc, 0)

            # Verify JSON output
            packet = json.loads((artifacts / "pr-review-packet.json").read_text())
            self.assertTrue(packet["all_passed"])
            self.assertEqual(packet["pr_number"], 42)
            self.assertEqual(len(packet["checklist"]), 5)

            # Verify markdown output
            md = (artifacts / "pr-review-packet.md").read_text()
            self.assertIn("## Acceptance Criteria", md)
            self.assertIn("## Validation Artifacts", md)
            self.assertIn("## Execution Evidence", md)
            self.assertIn("<!-- pr-review-checklist:start -->", md)
            self.assertIn("<!-- pr-review-checklist:end -->", md)
            self.assertIn("![Before]", md)
            # All items should be checked
            self.assertNotIn("- [ ]", md)

    def test_review_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts = Path(tmpdir) / "artifacts"
            artifacts.mkdir()

            self._write_json(Path(tmpdir) / "harness" / "contract.json", {})
            self._write_json(artifacts / "risk-policy-report.json", {
                "decision": "pass",
                "head_sha": "def456",
                "pr_number": 99,
                "risk_tier": "medium",
                "required_checks": [],
            })
            self._write_json(artifacts / "review-findings.json", {
                "status": "success",
                "findings": [{"actionable": True, "message": "bug found"}],
            })
            self._write_json(artifacts / "sentry-logs-validation.json", {
                "status": "not-required",
                "ok": True,
            })

            from pr_packet import main

            old_argv = sys.argv
            try:
                sys.argv = [
                    "pr_packet.py",
                    "--contract", str(Path(tmpdir) / "harness" / "contract.json"),
                    "--risk-report", str(artifacts / "risk-policy-report.json"),
                    "--review-findings", str(artifacts / "review-findings.json"),
                    "--browser-evidence-manifest", str(artifacts / "nonexistent.json"),
                    "--sentry-validation-report", str(artifacts / "sentry-logs-validation.json"),
                    "--media-manifest", str(artifacts / "nonexistent-media.json"),
                    "--out-json", str(artifacts / "pr-review-packet.json"),
                    "--out-md", str(artifacts / "pr-review-packet.md"),
                ]
                rc = main()
            finally:
                sys.argv = old_argv

            self.assertEqual(rc, 1)  # Not all passed

            packet = json.loads((artifacts / "pr-review-packet.json").read_text())
            self.assertFalse(packet["all_passed"])

            # CodeRabbit check should fail
            coderabbit_item = next(c for c in packet["checklist"] if c["id"] == "coderabbit_clean")
            self.assertFalse(coderabbit_item["passed"])

            md = (artifacts / "pr-review-packet.md").read_text()
            self.assertIn("- [ ] CodeRabbit review clean", md)
            self.assertIn("No media attachments provided", md)


class TestMediaManifest(unittest.TestCase):
    """Test media_manifest.py scanning and manifest building."""

    def test_scan_empty_dir(self):
        from media_manifest import scan_artifacts
        with tempfile.TemporaryDirectory() as tmpdir:
            items = scan_artifacts(tmpdir)
            self.assertEqual(items, [])

    def test_scan_nonexistent_dir(self):
        from media_manifest import scan_artifacts
        items = scan_artifacts("/nonexistent/path/that/should/not/exist")
        self.assertEqual(items, [])

    def test_scan_with_media_files(self):
        from media_manifest import scan_artifacts
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "before.png").write_bytes(b"fake png")
            (Path(tmpdir) / "after.jpg").write_bytes(b"fake jpg")
            (Path(tmpdir) / "demo.mp4").write_bytes(b"fake mp4")
            (Path(tmpdir) / "session.cast").write_bytes(b"fake cast")
            (Path(tmpdir) / "report.json").write_text("{}")  # not media

            items = scan_artifacts(tmpdir)
            types = [i["type"] for i in items]
            labels = [i["label"] for i in items]

            self.assertEqual(len(items), 4)
            self.assertIn("screenshot", types)
            self.assertIn("video", types)
            self.assertIn("asciinema", types)
            self.assertIn("after", labels)
            self.assertIn("before", labels)

    def test_build_manifest_with_loom(self):
        from media_manifest import build_manifest
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = build_manifest(
                artifacts_dir=tmpdir,
                loom_urls=["https://www.loom.com/share/abc123"],
            )
            self.assertEqual(len(manifest["items"]), 1)
            item = manifest["items"][0]
            self.assertEqual(item["type"], "loom")
            self.assertEqual(item["url"], "https://www.loom.com/share/abc123")
            self.assertIn("abc123", item["thumbnail"])

    def test_build_manifest_with_asciinema(self):
        from media_manifest import build_manifest
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = build_manifest(
                artifacts_dir=tmpdir,
                asciinema_urls=["https://asciinema.org/a/12345"],
            )
            self.assertEqual(len(manifest["items"]), 1)
            item = manifest["items"][0]
            self.assertEqual(item["type"], "asciinema")
            self.assertEqual(item["url"], "https://asciinema.org/a/12345")

    def test_build_manifest_combined(self):
        from media_manifest import build_manifest
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "shot.png").write_bytes(b"png")
            manifest = build_manifest(
                artifacts_dir=tmpdir,
                loom_urls=["https://www.loom.com/share/x"],
                asciinema_urls=["https://asciinema.org/a/1"],
            )
            self.assertEqual(len(manifest["items"]), 3)
            types = {i["type"] for i in manifest["items"]}
            self.assertEqual(types, {"screenshot", "loom", "asciinema"})

    def test_main_writes_file(self):
        from media_manifest import main as mm_main
        with tempfile.TemporaryDirectory() as tmpdir:
            outpath = str(Path(tmpdir) / "media-manifest.json")
            old_argv = sys.argv
            try:
                sys.argv = ["media_manifest.py", "--artifacts-dir", tmpdir, "--out", outpath]
                rc = mm_main()
            finally:
                sys.argv = old_argv

            self.assertEqual(rc, 0)
            data = json.loads(Path(outpath).read_text())
            self.assertIn("items", data)


if __name__ == "__main__":
    unittest.main()
