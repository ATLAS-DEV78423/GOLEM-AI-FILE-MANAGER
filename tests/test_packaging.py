from __future__ import annotations

import ast
import importlib
import os
import tempfile
import tomllib
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

    def test_pyproject_is_parseable(self) -> None:
        """pyproject.toml must be valid TOML with required sections."""
        root = Path(__file__).resolve().parent.parent
        data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(data["project"]["name"], "golem")
        self.assertIn("scripts", data["project"])
        scripts = data["project"]["scripts"]
        self.assertIn("golem", scripts)
        self.assertIn("golem-setup", scripts)

    def test_entry_points_resolve_to_callables(self) -> None:
        """The two console_scripts entries in pyproject.toml must point
        at callable functions so ``pip install`` produces working shims.
        """
        root = Path(__file__).resolve().parent.parent
        data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        scripts = data["project"]["scripts"]
        for entry_point, target in scripts.items():
            module_name, attr = target.split(":")
            # Add the project root so root-level modules (installer.py, main.py)
            # are importable in a dev install.
            project_root = str(root)
            added = False
            if project_root not in __import__("sys").path:
                __import__("sys").path.insert(0, project_root)
                added = True
            try:
                module = importlib.import_module(module_name)
            finally:
                if added:
                    __import__("sys").path.remove(project_root)
            self.assertTrue(
                hasattr(module, attr),
                f"Entry point {entry_point!r} -> {target!r}: {module_name}.{attr} not found",
            )
            self.assertTrue(
                callable(getattr(module, attr)),
                f"Entry point {entry_point!r} -> {target!r}: not callable",
            )

    def test_pyproject_declares_required_runtime_dependencies(self) -> None:
        """All third-party imports in the golem package must be declared."""
        import re

        root = Path(__file__).resolve().parent.parent
        golem_dir = root / "golem"
        declared: set[str] = set()
        data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        for dep in data["project"]["dependencies"]:
            # "pystray>=0.19.5" -> "pystray"
            declared.add(re.split(r"[<>=!~]", dep, maxsplit=1)[0].strip().lower())
        for opt_name, opt_deps in data["project"].get("optional-dependencies", {}).items():
            for dep in opt_deps:
                declared.add(re.split(r"[<>=!~]", dep, maxsplit=1)[0].strip().lower())
        # Modules the codebase actually imports.
        needed = {
            "openpyxl",
            "pypdf",
            "docx",  # python-docx provides the `docx` module
            "pystray",
            "pillow",
            "tkinter",  # stdlib; just verify it isn't declared
        }
        for module in needed:
            if module == "tkinter":
                self.assertNotIn("tkinter", declared)
            else:
                # Some packages are imported under a different name; map them.
                aliases = {"docx": "python-docx", "pillow": "pillow"}
                expected_dep = aliases.get(module, module)
                self.assertIn(
                    expected_dep,
                    declared,
                    f"pyproject.toml is missing dependency for {module!r}",
                )

    def test_golem_spec_declares_required_hidden_imports(self) -> None:
        """PyInstaller spec must list every import the runtime touches
        via lazy import (the static analyzer does not see them).

        The hiddenimports list is the only line of defense against
        "ModuleNotFoundError" on first launch. A real PyInstaller build
        runs on the user's VM, but we can assert here that the SPEC
        FILE has the entries — that is what gets shipped to the VM.
        """
        import re

        root = Path(__file__).resolve().parent.parent
        spec = (root / "golem.spec").read_text(encoding="utf-8")
        # Extract the hiddenimports list literal. Naive but adequate
        # for our spec format (single list, line-by-line strings).
        match = re.search(r"hiddenimports=\[([^\]]*)\]", spec, re.DOTALL)
        self.assertIsNotNone(match, "golem.spec has no hiddenimports list")
        listed = set()
        for raw in re.findall(r'["\']([^"\']+)["\']', match.group(1)):
            listed.add(raw.split(".")[0])
        # Also pick up bare tokens (no quotes) just in case.
        for token in re.findall(r"\b([A-Za-z_][A-Za-z0-9_.]*)\b", match.group(1)):
            listed.add(token.split(".")[0])
        # The full names we expect to see (so we don't lose sub-imports).
        for needed in [
            "keyboard",
            "pynput",
            "pystray",
            "PIL",
            "openpyxl",
            "pypdf",
            "docx",
        ]:
            self.assertIn(
                needed,
                listed,
                f"golem.spec hiddenimports missing {needed!r} — runtime will ModuleNotFoundError",
            )

    def test_installer_spec_declares_tkinter(self) -> None:
        """The installer binary uses tkinter for its GUI prompts."""
        root = Path(__file__).resolve().parent.parent
        spec = (root / "installer.spec").read_text(encoding="utf-8")
        self.assertIn("tkinter", spec, "installer.spec must declare tkinter")


if __name__ == "__main__":
    unittest.main()
