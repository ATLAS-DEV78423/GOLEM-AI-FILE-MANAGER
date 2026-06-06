import os
import sys
from pathlib import Path

APP_NAME = "GOLEM"
APP_VERSION = "2.1.0"
DB_FILENAME = "golem.db"
DEFAULT_CATEGORY = "Other"
SUPPORTED_EXTENSIONS = {".txt", ".pdf", ".docx", ".xlsx"}
SYSTEM_SKIP_DIRS = {
    ".obsidian",
    "System Volume Information",
    "$RECYCLE.BIN",
    "$Recycle.Bin",
    "GOLEM Files",
    "GOLEM",
}

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_UI_DIR = ROOT_DIR / "ui"
DEFAULT_ASSETS_DIR = ROOT_DIR / "assets"


def _meipass_dir() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return ROOT_DIR


def resource_path(*parts: str) -> Path:
    return _meipass_dir().joinpath(*parts)


def default_data_dir() -> Path:
    override = os.getenv("GOLEM_DATA_DIR")
    if override:
        return Path(override)
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_NAME
    return Path.home() / f".{APP_NAME.lower()}"
