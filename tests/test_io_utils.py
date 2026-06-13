import json
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class IoUtilsTests(unittest.TestCase):
    def test_atomic_write_text_replaces_existing_file_and_removes_tmp(self):
        import io_utils

        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "out.txt"
            path.write_text("old", encoding="utf-8")

            io_utils.atomic_write_text(path, "new")

            self.assertEqual(path.read_text(encoding="utf-8"), "new")
            self.assertFalse(path.with_name("out.txt.tmp").exists())

    def test_atomic_write_json_uses_utf8_and_indented_json(self):
        import io_utils

        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "data.json"

            io_utils.atomic_write_json(path, {"title": "Café", "n": 2})

            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["title"], "Café")
            self.assertIn("\n  ", path.read_text(encoding="utf-8"))

    def test_atomic_write_csv_writes_header_and_rows(self):
        import io_utils

        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "rows.csv"

            io_utils.atomic_write_csv(path, [{"b": 2, "a": 1}], fieldnames=["a", "b"])

            self.assertEqual(path.read_text(encoding="utf-8").splitlines(), ["a,b", "1,2"])

    def test_atomic_copy_file_copies_via_tmp_path(self):
        import io_utils

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            src = root / "source.txt"
            dst = root / "nested" / "dest.txt"
            src.write_text("payload", encoding="utf-8")

            io_utils.atomic_copy_file(src, dst)

            self.assertEqual(dst.read_text(encoding="utf-8"), "payload")
            self.assertFalse(dst.with_name("dest.txt.tmp").exists())

    def test_atomic_copy_tree_copies_via_tmp_directory(self):
        import io_utils

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            src = root / "source.Data"
            dst = root / "target.Data"
            src.mkdir()
            (src / "sdb").mkdir()
            (src / "sdb" / "sdb.eni").write_text("sqlite-placeholder", encoding="utf-8")

            io_utils.atomic_copy_tree(src, dst)

            self.assertEqual((dst / "sdb" / "sdb.eni").read_text(encoding="utf-8"), "sqlite-placeholder")
            self.assertFalse(dst.with_name("target.Data.tmp").exists())


if __name__ == "__main__":
    unittest.main()
