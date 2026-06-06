from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import installer


class InstallerTests(unittest.TestCase):
    def _write_payload_manifest(self, payload: Path) -> None:
        files = []
        for path in sorted(payload.rglob("*")):
            if path.is_file() and path.name != "payload-manifest.json":
                files.append(
                    {
                        "path": str(path.relative_to(payload)).replace("\\", "/"),
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                )
        manifest = {
            "app_name": installer.APP_NAME,
            "version": installer.APP_VERSION,
            "files": files,
        }
        (payload / "payload-manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

    def test_install_and_uninstall_round_trip(self) -> None:
        sandbox = Path(tempfile.mkdtemp())
        payload = sandbox / "payload"
        payload.mkdir()
        (payload / "GOLEM.exe").write_text("exe", encoding="utf-8")
        internal = payload / "_internal"
        internal.mkdir()
        (internal / "data.txt").write_text("payload", encoding="utf-8")
        self._write_payload_manifest(payload)
        install_dir = sandbox / "Programs" / "GOLEM"

        def fake_shortcut(
            shortcut_path: Path, target_path: Path, workdir: Path, icon_path: Path | None = None
        ):
            shortcut_path.parent.mkdir(parents=True, exist_ok=True)
            shortcut_path.write_text(f"{target_path}\n", encoding="utf-8")
            return shortcut_path

        env_overrides = {
            "LOCALAPPDATA": str(sandbox),
            "GOLEM_PAYLOAD_BYPASS_ROOT_CHECK": "1",
        }
        with (
            patch.dict(os.environ, env_overrides),
            patch("installer.create_shortcut", side_effect=fake_shortcut),
            patch("installer.registry_write_install"),
            patch("installer.subprocess.Popen"),
        ):
            manifest = installer.install_app(
                installer.InstallOptions(install_dir=install_dir, launch_after=False),
                payload_dir=payload,
            )
            self.assertTrue((install_dir / "GOLEM.exe").exists())
            self.assertTrue((install_dir / "_internal" / "data.txt").exists())
            self.assertTrue((install_dir / "install-manifest.json").exists())
            # Resolve symlinks so the comparison works on macOS where
            # /var is a symlink to /private/var.
            self.assertEqual(Path(manifest["install_dir"]).resolve(), install_dir.resolve())

            result = installer.uninstall_app(install_dir)
            self.assertEqual(result["status"], "ok")
            self.assertFalse(install_dir.exists())

    def test_rejects_install_dir_outside_safe_root(self) -> None:
        sandbox = Path(tempfile.mkdtemp())
        payload = sandbox / "payload"
        payload.mkdir()
        (payload / "GOLEM.exe").write_text("exe", encoding="utf-8")
        (payload / "_internal").mkdir()
        self._write_payload_manifest(payload)

        unsafe_install_dir = sandbox / "outside" / "GOLEM"
        with patch.dict(os.environ, {"LOCALAPPDATA": str(sandbox)}):
            with self.assertRaises(ValueError):
                installer.install_app(
                    installer.InstallOptions(install_dir=unsafe_install_dir, launch_after=False),
                    payload_dir=payload,
                )

    def test_rejects_tampered_payload_manifest(self) -> None:
        sandbox = Path(tempfile.mkdtemp())
        payload = sandbox / "payload"
        payload.mkdir()
        (payload / "GOLEM.exe").write_text("exe", encoding="utf-8")
        internal = payload / "_internal"
        internal.mkdir()
        self._write_payload_manifest(payload)
        manifest = {
            "app_name": "GOLEM",
            "version": "0.0.0",
            "files": [{"path": "GOLEM.exe", "sha256": "not-a-real-hash"}],
        }
        (payload / "payload-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        install_dir = sandbox / "Programs" / "GOLEM"
        with patch.dict(os.environ, {"LOCALAPPDATA": str(sandbox)}):
            with self.assertRaises(ValueError):
                installer.install_app(
                    installer.InstallOptions(install_dir=install_dir, launch_after=False),
                    payload_dir=payload,
                )

    def test_uninstall_refuses_when_no_manifest(self) -> None:
        """Uninstall must refuse to delete a directory that has no install-manifest.json."""
        sandbox = Path(tempfile.mkdtemp())
        install_dir = sandbox / "Programs" / "GOLEM"
        install_dir.mkdir(parents=True)
        with patch.dict(os.environ, {"LOCALAPPDATA": str(sandbox)}):
            with self.assertRaises(FileNotFoundError):
                installer.uninstall_app(install_dir)
        self.assertTrue(install_dir.exists(), "install dir must not be deleted")

    def test_uninstall_refuses_manifest_for_wrong_app(self) -> None:
        """Uninstall must refuse if the manifest declares a different app_name."""
        sandbox = Path(tempfile.mkdtemp())
        install_dir = sandbox / "Programs" / "GOLEM"
        install_dir.mkdir(parents=True)
        (install_dir / "install-manifest.json").write_text(
            json.dumps({"app_name": "EVIL_APP", "version": "1.0", "shortcuts": []}),
            encoding="utf-8",
        )
        with patch.dict(os.environ, {"LOCALAPPDATA": str(sandbox)}):
            with self.assertRaises(ValueError):
                installer.uninstall_app(install_dir)
        self.assertTrue(install_dir.exists(), "install dir must not be deleted")

    def test_uninstall_skips_shortcuts_outside_safe_dirs(self) -> None:
        """Uninstall must not unlink paths declared in a manifest that are outside
        the Start Menu or Desktop directories."""
        sandbox = Path(tempfile.mkdtemp())
        install_dir = sandbox / "Programs" / "GOLEM"
        install_dir.mkdir(parents=True)
        innocent = sandbox / "important_file.txt"
        innocent.write_text("don't delete me", encoding="utf-8")
        (install_dir / "install-manifest.json").write_text(
            json.dumps(
                {
                    "app_name": installer.APP_NAME,
                    "version": installer.APP_VERSION,
                    "shortcuts": [str(innocent)],
                }
            ),
            encoding="utf-8",
        )
        with (
            patch.dict(os.environ, {"LOCALAPPDATA": str(sandbox)}),
            patch("installer.registry_remove_install"),
        ):
            result = installer.uninstall_app(install_dir)
            self.assertEqual(result["status"], "ok")
        self.assertFalse(install_dir.exists(), "install dir was removed")
        self.assertTrue(innocent.exists(), "innocent file outside Start Menu/Desktop must survive")


if __name__ == "__main__":
    unittest.main()
