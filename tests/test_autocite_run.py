import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class AutociteRunTests(unittest.TestCase):
    def test_default_run_dir_uses_manuscript_dir_and_timestamp(self):
        import autocite_run

        docx = pathlib.Path("/tmp/project/manuscript.docx")

        run_dir = autocite_run.default_run_dir(docx, timestamp="20260613-145500")

        self.assertEqual(
            run_dir,
            pathlib.Path("/tmp/project/autocite-runs/manuscript.20260613-145500"),
        )

    def test_run_early_workflow_stages_commands_and_status(self):
        import autocite_run
        import run_status

        calls = []

        def fake_runner(command):
            calls.append([str(part) for part in command])
            return 0

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            docx = root / "paper.docx"
            docx.write_bytes(b"placeholder")
            papers = root / "papers"
            papers.mkdir()
            out_dir = root / "run"

            result = autocite_run.run_early_workflow(
                docx=docx,
                out_dir=out_dir,
                papers_dir=papers,
                check_dependencies=False,
                runner=fake_runner,
            )

            self.assertEqual(result["run_dir"], str(out_dir))
            self.assertEqual(result["next_step"], "prepare_endnote")
            self.assertEqual(run_status.read_status(out_dir)["state"], "awaiting_endnote")

        joined = [" ".join(call) for call in calls]
        self.assertTrue(any("docx_comment_audit.py" in call for call in joined))
        self.assertTrue(any("extract_pdf_references.py" in call for call in joined))
        self.assertTrue(any("generate_candidate_template.py" in call for call in joined))
        self.assertFalse(any("ensure_dependencies.py" in call for call in joined))

    def test_run_early_workflow_marks_failed_when_command_fails(self):
        import autocite_run
        import run_status

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            docx = root / "paper.docx"
            docx.write_bytes(b"placeholder")
            out_dir = root / "run"

            with self.assertRaises(RuntimeError):
                autocite_run.run_early_workflow(
                    docx=docx,
                    out_dir=out_dir,
                    papers_dir=None,
                    check_dependencies=False,
                    runner=lambda command: 2,
                )

            status = run_status.read_status(out_dir)

        self.assertEqual(status["state"], "failed")
        self.assertIn("command failed", status["reason"])


if __name__ == "__main__":
    unittest.main()
