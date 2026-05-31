from __future__ import annotations

import os
import tempfile
from pathlib import Path

from golem.constants import default_data_dir
from golem.indexer import initialize, search_files
from golem.scanner import index_one_file
from golem.summarizer import HeuristicSummarizer
from golem.undo import undo_last


def main() -> int:
    sandbox = Path(tempfile.mkdtemp(prefix="golem-sandbox-"))
    os.environ["GOLEM_DATA_DIR"] = str(sandbox / "data")
    assert default_data_dir() == sandbox / "data"

    watched = sandbox / "watched"
    vault = sandbox / "vault"
    watched.mkdir()
    vault.mkdir()
    sample = watched / "budget.txt"
    sample.write_text("budget report for march invoice payment", encoding="utf-8")

    conn = initialize(sandbox / "data" / "golem.db")
    file_id, status = index_one_file(conn, sample, vault, HeuristicSummarizer())
    assert status == "done" and file_id == 1
    assert search_files(conn, "march budget")[0]["confidence"] >= 0.8
    undo = undo_last(conn, vault)
    assert undo["status"] == "ok"
    assert sample.exists()
    print("sandbox smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
