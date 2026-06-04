from __future__ import annotations

import argparse
import sys

from golem.app import run

__all__ = ["main"]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="golem",
        description="GOLEM — local-first AI file manager for Obsidian.",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Override the data directory (default: %%LOCALAPPDATA%%/GOLEM on Windows, ~/.golem elsewhere).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default: INFO).",
    )
    parser.add_argument(
        "--no-tray",
        action="store_true",
        help="Do not start the system tray icon.",
    )
    parser.add_argument(
        "--no-watcher",
        action="store_true",
        help="Do not start the polling file watcher.",
    )
    parser.add_argument(
        "--no-hotkey",
        action="store_true",
        help="Do not register global hotkeys.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Process files but do not move them (overrides the saved setting).",
    )
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="Wipe the files index and trigger a full rescan on startup.",
    )
    parser.add_argument(
        "--export-db",
        default=None,
        help="Copy the database to this path and exit.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print the GOLEM version and exit.",
    )
    parser.add_argument(
        "--install-autostart",
        action="store_true",
        help="Register GOLEM to launch at system startup.",
    )
    parser.add_argument(
        "--remove-autostart",
        action="store_true",
        help="Remove the system startup registration for GOLEM.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
