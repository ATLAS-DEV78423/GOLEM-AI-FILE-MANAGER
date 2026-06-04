from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

if sys.platform.startswith("win"):
    import winreg  # type: ignore
else:
    winreg = None  # type: ignore

from golem.constants import APP_NAME, APP_VERSION

INSTALL_MANIFEST = "install-manifest.json"
UNINSTALL_CMD_NAME = f"Uninstall {APP_NAME}.cmd"
UNINSTALL_PS1_NAME = f"Uninstall {APP_NAME}.ps1"
UNINSTALL_REG_KEY = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_NAME}"


@dataclass(slots=True)
class InstallOptions:
    install_dir: Path
    create_start_menu: bool = True
    create_desktop: bool = True
    launch_after: bool = True
    skip_registry: bool = False


def _allowed_payload_roots() -> list[Path]:
    """Directories that may legitimately contain a GOLEM payload.

    Used to constrain ``GOLEM_PAYLOAD_DIR`` so a user (or a malicious shim)
    cannot point the installer at ``C:\\Windows`` and have us recursively
    copy system files. Only build outputs are acceptable.
    """
    candidates = [
        Path.cwd() / "dist",
        Path(__file__).resolve().parent / "dist",
    ]
    seen: set[Path] = set()
    roots: list[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        roots.append(resolved)
    return roots


def source_payload_dir() -> Path:
    override = os.getenv("GOLEM_PAYLOAD_DIR")
    if override:
        candidate = Path(override).expanduser().resolve()
        if not candidate.exists():
            raise FileNotFoundError(f"GOLEM_PAYLOAD_DIR does not exist: {candidate}")
        if os.environ.get("GOLEM_PAYLOAD_BYPASS_ROOT_CHECK") != "1":
            allowed = _allowed_payload_roots()
            if not any(_is_within(candidate, root) for root in allowed):
                raise ValueError(
                    f"GOLEM_PAYLOAD_DIR must be inside a build output directory. "
                    f"Got {candidate!s}; allowed roots: {[str(r) for r in allowed]}. "
                    f"Set GOLEM_PAYLOAD_BYPASS_ROOT_CHECK=1 to override."
                )
        return candidate
    if getattr(sys, "frozen", False):
        candidate = Path(getattr(sys, "_MEIPASS", Path.cwd())) / "payload" / APP_NAME
        if candidate.exists():
            return candidate
    dist = Path(__file__).resolve().parent / "dist" / APP_NAME
    if dist.exists():
        return dist
    raise FileNotFoundError("GOLEM payload not found. Build the app bundle first.")


def default_install_dir() -> Path:
    override = os.getenv("GOLEM_INSTALL_DIR")
    if override:
        return Path(override)
    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "Programs" / APP_NAME
    return Path.home() / APP_NAME


def start_menu_dir() -> Path:
    override = os.getenv("GOLEM_START_MENU_DIR")
    if override:
        return Path(override)
    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / APP_NAME
    return Path.home() / "Start Menu" / APP_NAME


def desktop_dir() -> Path:
    override = os.getenv("GOLEM_DESKTOP_DIR")
    if override:
        return Path(override)
    userprofile = os.getenv("USERPROFILE")
    if userprofile:
        return Path(userprofile) / "Desktop"
    return Path.home() / "Desktop"


def _safe_install_root() -> Path:
    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        return (Path(local_appdata) / "Programs").resolve()
    return (Path.home() / "Programs").resolve()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def _validate_install_dir(install_dir: Path) -> Path:
    resolved = install_dir.expanduser().resolve()
    root = _safe_install_root()
    if resolved == Path(resolved.anchor):
        raise ValueError("Install directory cannot be a drive root or filesystem root.")
    if len(resolved.parts) < 3:
        raise ValueError("Install directory is too short to be safe.")
    if not _is_within(resolved, root):
        raise ValueError(f"Install directory must be inside {root}.")
    if resolved == root:
        raise ValueError("Install directory cannot be the shared programs root.")
    return resolved


def _validate_payload_dir(payload_dir: Path) -> Path:
    resolved = payload_dir.expanduser().resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise FileNotFoundError(f"Payload directory does not exist: {resolved}")

    launcher = resolved / f"{APP_NAME}.exe"
    internal = resolved / "_internal"
    manifest = resolved / "payload-manifest.json"
    if not launcher.is_file():
        raise FileNotFoundError(f"Payload is missing launcher executable: {launcher}")
    if not internal.is_dir():
        raise FileNotFoundError(f"Payload is missing internal runtime directory: {internal}")
    if not manifest.is_file():
        raise FileNotFoundError(f"Payload manifest is required but missing: {manifest}")

    expected = json.loads(manifest.read_text(encoding="utf-8"))
    if expected.get("app_name") != APP_NAME:
        raise ValueError("Payload manifest app name mismatch.")
    if expected.get("version") != APP_VERSION:
        raise ValueError("Payload manifest version mismatch.")
    files = expected.get("files", [])
    if not isinstance(files, list):
        raise ValueError("Payload manifest is malformed.")
    for entry in files:
        if not isinstance(entry, dict):
            raise ValueError("Payload manifest is malformed.")
        rel_path = entry.get("path")
        expected_hash = entry.get("sha256")
        if not isinstance(rel_path, str) or not isinstance(expected_hash, str):
            raise ValueError("Payload manifest is malformed.")
        file_path = resolved / rel_path
        if not file_path.is_file():
            raise FileNotFoundError(f"Payload file missing: {file_path}")
        actual_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
        if actual_hash.lower() != expected_hash.lower():
            raise ValueError(f"Payload hash mismatch for {rel_path}")

    return resolved


def _safe_rmtree(path: Path) -> None:
    resolved = _validate_install_dir(path)
    if resolved.exists():
        shutil.rmtree(resolved)


def _ps_single_quoted(text: str) -> str:
    return text.replace("'", "''")


def _powershell_shortcut(shortcut_path: Path, target_path: Path, workdir: Path, icon_path: Path | None = None) -> None:
    shortcut_path.parent.mkdir(parents=True, exist_ok=True)
    shortcut_literal = _ps_single_quoted(str(shortcut_path))
    target_literal = _ps_single_quoted(str(target_path))
    workdir_literal = _ps_single_quoted(str(workdir))
    icon_expr = f"$shortcut.IconLocation = '{_ps_single_quoted(str(icon_path))}'" if icon_path else ""
    script = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$shortcut = $ws.CreateShortcut('{shortcut_literal}'); "
        f"$shortcut.TargetPath = '{target_literal}'; "
        f"$shortcut.WorkingDirectory = '{workdir_literal}'; "
        f"$shortcut.Description = '{APP_NAME}'; "
        f"{icon_expr} "
        "$shortcut.Save()"
    )
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
        check=True,
        capture_output=True,
        text=True,
    )


def _cmd_shortcut(shortcut_path: Path, target_path: Path) -> None:
    shortcut_path.parent.mkdir(parents=True, exist_ok=True)
    content = f'@echo off\r\nstart "" "{target_path}"\r\n'
    shortcut_path.write_text(content, encoding="utf-8")


def create_shortcut(shortcut_path: Path, target_path: Path, workdir: Path, icon_path: Path | None = None) -> Path:
    if not target_path.exists():
        raise FileNotFoundError(f"Shortcut target does not exist: {target_path}")
    if not workdir.exists():
        raise FileNotFoundError(f"Shortcut working directory does not exist: {workdir}")
    try:
        _powershell_shortcut(shortcut_path, target_path, workdir, icon_path)
        return shortcut_path
    except Exception:
        fallback = shortcut_path.with_suffix(".cmd")
        _cmd_shortcut(fallback, target_path)
        return fallback


def create_uninstaller_script(install_dir: Path) -> Path:
    cmd_path = install_dir / UNINSTALL_CMD_NAME
    ps1_path = install_dir / UNINSTALL_PS1_NAME
    target = _ps_single_quoted(str(install_dir))
    key = _ps_single_quoted(UNINSTALL_REG_KEY)
    ps1 = "\n".join(
        [
            "$ErrorActionPreference = 'SilentlyContinue'",
            f"$target = '{target}'",
            f"$reg = 'HKCU:\\{key}'",
            "$manifest = Join-Path $target 'install-manifest.json'",
            "Start-Sleep -Seconds 2",
            "try {",
            "  if (Test-Path $manifest) {",
            "    $data = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json",
            "    foreach ($shortcut in $data.shortcuts) {",
            "      Remove-Item -LiteralPath $shortcut -Force -ErrorAction SilentlyContinue",
            "    }",
            "  }",
            "} catch {}",
            "try { Remove-Item -LiteralPath $reg -Recurse -Force -ErrorAction SilentlyContinue } catch {}",
            "try { Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue } catch {}",
        ]
    )
    cmd = "\r\n".join(
        [
            "@echo off",
            f'start "" /b powershell.exe -NoProfile -WindowStyle Hidden -File "%~dp0{UNINSTALL_PS1_NAME}"',
            "exit /b 0",
        ]
    )
    ps1_path.write_text(ps1, encoding="utf-8")
    cmd_path.write_text(cmd, encoding="utf-8")
    return cmd_path


def _assert_payload_within_allowed_roots(payload: Path) -> None:
    """Refuse to copy from a payload that lives outside the build output tree.

    ``_validate_payload_dir`` checks that the payload looks like a valid
    GOLEM bundle (it has the right manifest, files, and hashes). It does
    NOT check *where* the payload came from. We add that check here so a
    crafted caller cannot pass ``C:\\Windows\\System32`` as a payload and
    have us recursively copy it.

    The check is bypassed when the installer itself is a frozen PyInstaller
    binary (the payload then lives next to the installer in a trusted
    location) and when the caller passes ``payload_dir`` explicitly via the
    Python API (the caller is responsible for that path's safety; this
    function is meant to defend against the env-var override path only).
    """
    if getattr(sys, "frozen", False):
        return
    if os.environ.get("GOLEM_PAYLOAD_BYPASS_ROOT_CHECK") == "1":
        return
    allowed = _allowed_payload_roots()
    if not any(_is_within(payload, root) for root in allowed):
        raise ValueError(
            f"Payload must be inside a build output directory. "
            f"Got {payload!s}; allowed roots: {[str(r) for r in allowed]}. "
            f"Set GOLEM_PAYLOAD_BYPASS_ROOT_CHECK=1 to override (only for trusted callers)."
        )


def copy_payload(payload_dir: Path, install_dir: Path) -> None:
    payload = _validate_payload_dir(payload_dir)
    _assert_payload_within_allowed_roots(payload)
    target = _validate_install_dir(install_dir)
    if target.exists():
        _safe_rmtree(target)
    shutil.copytree(payload, target)


def registry_write_install(install_dir: Path, launcher_path: Path, uninstaller_path: Path) -> None:
    if winreg is None or os.getenv("GOLEM_SKIP_REGISTRY") == "1":
        return
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_REG_KEY)
    try:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, str(install_dir))
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, str(launcher_path))
        winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, f'"{uninstaller_path}" --uninstall --silent')
        winreg.SetValueEx(key, "QuietUninstallString", 0, winreg.REG_SZ, f'"{uninstaller_path}" --uninstall --silent')
    finally:
        winreg.CloseKey(key)


def registry_remove_install() -> None:
    if winreg is None or os.getenv("GOLEM_SKIP_REGISTRY") == "1":
        return
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_REG_KEY)
    except FileNotFoundError:
        pass


def install_app(options: InstallOptions, payload_dir: Path | None = None) -> dict[str, str]:
    payload = _validate_payload_dir(payload_dir or source_payload_dir())
    install_dir = _validate_install_dir(options.install_dir)
    install_dir.parent.mkdir(parents=True, exist_ok=True)
    copy_payload(payload, install_dir)

    launcher = install_dir / f"{APP_NAME}.exe"
    uninstaller = create_uninstaller_script(install_dir)

    shortcuts: list[str] = []
    if options.create_start_menu:
        start_dir = start_menu_dir()
        shortcuts.append(str(create_shortcut(start_dir / f"{APP_NAME}.lnk", launcher, install_dir, launcher)))
        shortcuts.append(str(create_shortcut(start_dir / f"Uninstall {APP_NAME}.lnk", uninstaller, install_dir, uninstaller)))
    if options.create_desktop:
        desktop = desktop_dir()
        shortcuts.append(str(create_shortcut(desktop / f"{APP_NAME}.lnk", launcher, install_dir, launcher)))

    manifest = {
        "app_name": APP_NAME,
        "version": APP_VERSION,
        "install_dir": str(install_dir),
        "launcher": str(launcher),
        "uninstaller": str(uninstaller),
        "shortcuts": shortcuts,
        "installed_at": datetime.now(UTC).isoformat(),
    }
    (install_dir / INSTALL_MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    registry_write_install(install_dir, launcher, uninstaller)
    if options.launch_after:
        try:
            subprocess.Popen([str(launcher)])
        except Exception:
            pass
    return manifest


def _is_shortcut_safe(shortcut: Path) -> bool:
    """A shortcut is only safe to unlink if it lives in the Start Menu or Desktop.

    The install manifest is written by us, but a corrupted or tampered
    manifest could contain arbitrary paths. We refuse to unlink anything
    outside the expected shortcut directories.
    """
    try:
        resolved = shortcut.expanduser().resolve()
    except OSError:
        return False
    sm = start_menu_dir()
    dt = desktop_dir()
    try:
        sm_resolved = sm.resolve()
    except OSError:
        sm_resolved = sm
    try:
        dt_resolved = dt.resolve()
    except OSError:
        dt_resolved = dt
    return _is_within(resolved, sm_resolved) or _is_within(resolved, dt_resolved)


def uninstall_app(install_dir: Path) -> dict[str, str]:
    install_dir = _validate_install_dir(install_dir)
    manifest_path = install_dir / INSTALL_MANIFEST
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"No install manifest at {manifest_path}; refusing to uninstall. "
            f"Pass the correct install directory or remove it manually."
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("app_name") != APP_NAME:
        raise ValueError(
            f"Install manifest at {manifest_path} does not belong to {APP_NAME}; "
            f"refusing to uninstall."
        )
    for shortcut in manifest.get("shortcuts", []):
        shortcut_path = Path(shortcut)
        if not _is_shortcut_safe(shortcut_path):
            logging.warning("Skipping shortcut outside Start Menu/Desktop: %s", shortcut_path)
            continue
        try:
            shortcut_path.unlink(missing_ok=True)
        except Exception as exc:
            logging.warning("Failed to remove shortcut %s: %s", shortcut_path, exc)
    registry_remove_install()
    _safe_rmtree(install_dir)
    return {"status": "ok", "message": f"{APP_NAME} removed."}


class InstallerUI:
    def __init__(self):
        import tkinter as _tk
        from tkinter import filedialog as _fd
        from tkinter import messagebox as _mb
        from tkinter import ttk as _tt

        self._tk = _tk
        self._filedialog = _fd
        self._messagebox = _mb
        self._ttk = _tt

        self.root = _tk.Tk()
        self.root.title(f"{APP_NAME} Setup")
        self.root.geometry("560x360")
        self.root.minsize(560, 360)
        self.install_dir_var = _tk.StringVar(value=str(default_install_dir()))
        self.start_menu_var = _tk.BooleanVar(value=True)
        self.desktop_var = _tk.BooleanVar(value=True)
        self.launch_var = _tk.BooleanVar(value=True)
        self.status_var = _tk.StringVar(value="Ready to install.")
        self.progress = _tt.Progressbar(self.root, mode="indeterminate")
        self._build()

    def _build(self) -> None:
        _tt = self._ttk
        frame = _tt.Frame(self.root, padding=18)
        frame.pack(fill="both", expand=True)
        _tt.Label(frame, text=f"{APP_NAME} Installer", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        _tt.Label(frame, text=f"Version {APP_VERSION}").pack(anchor="w", pady=(2, 10))
        _tt.Label(frame, text="Install location").pack(anchor="w")
        row = _tt.Frame(frame)
        row.pack(fill="x", pady=(4, 10))
        _tt.Entry(row, textvariable=self.install_dir_var).pack(side="left", fill="x", expand=True)
        _tt.Button(row, text="Browse", command=self._browse).pack(side="left", padx=(8, 0))
        _tt.Checkbutton(frame, text="Create Start Menu shortcuts", variable=self.start_menu_var).pack(anchor="w")
        _tt.Checkbutton(frame, text="Create Desktop shortcut", variable=self.desktop_var).pack(anchor="w")
        _tt.Checkbutton(frame, text="Launch GOLEM after install", variable=self.launch_var).pack(anchor="w")
        _tt.Label(frame, textvariable=self.status_var).pack(anchor="w", pady=(12, 4))
        self.progress.pack(fill="x", pady=(0, 10))
        buttons = _tt.Frame(frame)
        buttons.pack(fill="x", pady=(10, 0))
        _tt.Button(buttons, text="Install", command=self._install).pack(side="right")
        _tt.Button(buttons, text="Uninstall", command=self._uninstall).pack(side="right", padx=(0, 8))

    def _browse(self) -> None:
        selected = self._filedialog.askdirectory(initialdir=self.install_dir_var.get())
        if selected:
            self.install_dir_var.set(selected)

    def _install(self) -> None:
        try:
            self.status_var.set("Installing...")
            self.progress.start(12)
            self.root.update_idletasks()
            manifest = install_app(
                InstallOptions(
                    install_dir=Path(self.install_dir_var.get()),
                    create_start_menu=self.start_menu_var.get(),
                    create_desktop=self.desktop_var.get(),
                    launch_after=self.launch_var.get(),
                )
            )
            self.status_var.set(f"Installed to {manifest['install_dir']}")
            self._messagebox.showinfo(APP_NAME, "Installation completed.")
        except Exception as exc:
            self._messagebox.showerror(APP_NAME, str(exc))
            self.status_var.set("Install failed.")
        finally:
            self.progress.stop()

    def _uninstall(self) -> None:
        try:
            result = uninstall_app(Path(self.install_dir_var.get()))
            self.status_var.set(result["message"])
            self._messagebox.showinfo(APP_NAME, result["message"])
        except Exception as exc:
            self._messagebox.showerror(APP_NAME, str(exc))

    def run(self) -> None:
        self.root.mainloop()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GOLEM installer")
    parser.add_argument("--install-dir", default=None)
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--silent", action="store_true")
    parser.add_argument("--no-start-menu", action="store_true")
    parser.add_argument("--no-desktop", action="store_true")
    parser.add_argument("--no-launch", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.uninstall:
        target = Path(args.install_dir or os.getenv("GOLEM_INSTALL_DIR") or default_install_dir())
        uninstall_app(target)
        return 0

    if args.silent:
        install_app(
            InstallOptions(
                install_dir=Path(args.install_dir or default_install_dir()),
                create_start_menu=not args.no_start_menu,
                create_desktop=not args.no_desktop,
                launch_after=not args.no_launch,
            )
        )
        return 0

    ui = InstallerUI()
    if args.install_dir:
        ui.install_dir_var.set(args.install_dir)
    if args.no_start_menu:
        ui.start_menu_var.set(False)
    if args.no_desktop:
        ui.desktop_var.set(False)
    if args.no_launch:
        ui.launch_var.set(False)
    ui.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
