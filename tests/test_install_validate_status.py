import json
import pathlib
import shutil
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class PackageValidationTests(unittest.TestCase):
    def test_validate_current_package_reports_required_files(self):
        import validate_package

        summary = validate_package.validate_package(ROOT)

        self.assertTrue(summary["ok"])
        self.assertIn("SKILL.md", summary["required_files"])
        self.assertIn("scripts/reference_lookup.py", summary["required_files"])
        self.assertEqual(summary["errors"], [])

    def test_validate_rejects_local_absolute_paths(self):
        import validate_package

        with tempfile.TemporaryDirectory() as tmp:
            package = pathlib.Path(tmp) / "pkg"
            shutil.copytree(
                ROOT,
                package,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
            (package / "references" / "local.md").write_text(
                "bad path /Users/example/private/file.docx\n",
                encoding="utf-8",
            )

            summary = validate_package.validate_package(package)

        self.assertFalse(summary["ok"])
        self.assertTrue(
            any("local absolute path" in error for error in summary["errors"]),
            summary["errors"],
        )


class InstallerTests(unittest.TestCase):
    def test_codex_installer_copies_skill_without_tests(self):
        import install_codex_skill

        with tempfile.TemporaryDirectory() as tmp:
            target_root = pathlib.Path(tmp) / "codex" / "skills"
            destination = install_codex_skill.install(
                source=ROOT,
                target_root=target_root,
                force=False,
            )

            self.assertEqual(destination, (target_root / "autocite").resolve())
            self.assertTrue((destination / "SKILL.md").is_file())
            self.assertTrue((destination / "agents" / "openai.yaml").is_file())
            self.assertTrue((destination / "scripts" / "reference_lookup.py").is_file())
            self.assertFalse((destination / "tests").exists())

    def test_claude_installer_uses_claude_home_skills_default(self):
        import install_claude_skill

        with tempfile.TemporaryDirectory() as tmp:
            claude_home = pathlib.Path(tmp) / ".claude"
            target_root = install_claude_skill.default_target_root(claude_home=claude_home)

            self.assertEqual(target_root, claude_home / "skills")


class RunStatusTests(unittest.TestCase):
    def test_write_and_read_status(self):
        import run_status

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = pathlib.Path(tmp)
            status = run_status.write_status(
                run_dir,
                "extracting_comments",
                step="docx_comment_audit",
                details={"comments": 12},
            )
            loaded = run_status.read_status(run_dir)

        self.assertEqual(status["state"], "extracting_comments")
        self.assertEqual(loaded["step"], "docx_comment_audit")
        self.assertEqual(loaded["details"], {"comments": 12})

    def test_invalid_status_is_rejected(self):
        import run_status

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                run_status.write_status(pathlib.Path(tmp), "nearly_done")


if __name__ == "__main__":
    unittest.main()
