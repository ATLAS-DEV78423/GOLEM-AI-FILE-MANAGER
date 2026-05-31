from __future__ import annotations

import ast
import os
import tempfile
import unittest
from pathlib import Path

from golem.constants import default_data_dir


class PackagingTests(unittest.TestCase):
    def test_spec_parses(self) -> None:
        root = Path(__file__).resolve().parent.parent
        for spec_name in ("golem.spec", "golem_macos.spec", "installer.spec"):
            spec_path = root / spec_name
            ast.parse(spec_path.read_text(encoding="utf-8"))

    def test_data_dir_override(self) -> None:
        old = os.environ.get("GOLEM_DATA_DIR")
        try:
            sandbox = Path(tempfile.mkdtemp()) / "data"
            os.environ["GOLEM_DATA_DIR"] = str(sandbox)
            self.assertEqual(default_data_dir(), sandbox)
        finally:
            if old is None:
                os.environ.pop("GOLEM_DATA_DIR", None)
            else:
                os.environ["GOLEM_DATA_DIR"] = old


if __name__ == "__main__":
    unittest.main()
