import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class EnsureDependenciesTests(unittest.TestCase):
    def test_read_requirements_ignores_blank_lines_and_comments(self):
        import ensure_dependencies

        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "requirements.txt"
            path.write_text("\n# comment\nlxml\nopenpyxl>=3\n", encoding="utf-8")

            self.assertEqual(
                ensure_dependencies.read_requirements(path),
                ["lxml", "openpyxl>=3"],
            )

    def test_package_import_name_strips_version_specifier(self):
        import ensure_dependencies

        self.assertEqual(ensure_dependencies.import_name("openpyxl>=3"), "openpyxl")
        self.assertEqual(ensure_dependencies.import_name("lxml"), "lxml")

    def test_supported_pdftotext_install_command_for_macos_homebrew(self):
        import ensure_dependencies

        command = ensure_dependencies.pdftotext_install_command(
            system="Darwin",
            command_exists=lambda name: name == "brew",
            is_root=False,
        )

        self.assertEqual(command, ["brew", "install", "poppler"])


if __name__ == "__main__":
    unittest.main()
