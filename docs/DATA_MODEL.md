# Data Model

The local SQLite database at `<data_dir>/golem.db` is the single source
of truth for the index. The Obsidian vault is a derived output; you
can delete the vault and re-derive it from the DB by re-running the
scanner.

## Tables

### `files`

One row per indexed file. Updated by `upsert_file` and the various
`mark_*` helpers.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Autoincrement |
| `original_filename` | TEXT | Filename as it was on disk at index time |
| `clean_filename` | TEXT | LLM-suggested human-readable filename |
| `original_path` | TEXT UNIQUE | Absolute path the file was first seen at |
| `current_path` | TEXT | Where the file lives after `organize_file` moved it |
| `file_type` | TEXT | Extension without the dot (`pdf`, `docx`, …) |
| `size_kb` | REAL | File size in KB at index time |
| `content_hash` | TEXT | `sha256[:size]` (or `head+tail[:size]` for large files) |
| `duplicate_of` | INTEGER | FK to `files.id` if this is a duplicate |
| `extracted_text` | TEXT | First 500 chars of readable text |
| `summary` | TEXT | LLM-generated one-sentence summary |
| `tags` | TEXT | Comma-separated tags |
| `key_contents` | TEXT | LLM-generated comma-separated topics |
| `category` | TEXT | One of the closed taxonomy in `summarizer._parse_metadata` |
| `obsidian_note_path` | TEXT | Absolute path of the generated `.md` note |
| `date_indexed` | TEXT | ISO 8601 timestamp |
| `last_modified` | TEXT | ISO 8601 timestamp |
| `index_status` | TEXT | `pending` / `done` / `skipped` / `error` / `missing` / `duplicate` |
| `user_edited` | INTEGER 0/1 | True if the user edited the Obsidian note (preserved across re-index) |

### `files_fts` (FTS5 virtual table)

Mirrors the searchable columns of `files`. The triggers
`files_ai`, `files_ad`, `files_au` keep it in sync with the parent
table; do not write to it directly.

### `undo_log`

One row per file move, marked `reversed = 0` while still undoable.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Autoincrement |
| `action` | TEXT | Always `move` for now |
| `file_id` | INTEGER | FK to `files.id` |
| `from_path` | TEXT | Where the file was |
| `to_path` | TEXT | Where the file went |
| `timestamp` | TEXT | ISO 8601 |
| `reversed` | INTEGER 0/1 | Set to 1 after undo |

Only the **most recent** `reversed = 0` row is undoable. The rest are
retained for audit but `undo_last` ignores them.

### `settings`

Key-value store for the user's configuration. Special keys:

- `llm_api_key` and `groq_api_key` are DPAPI-protected (Windows) or
  base64-wrapped (other platforms) by `_encode_setting_value` /
  `_decode_setting_value`.
- `terms_accepted` and `terms_version` track Terms of Service
  acceptance. On startup, the app checks the version; if the user
  has not accepted the current version, onboarding is shown.

## Migrations

The `initialize` function applies the schema idempotently and runs
any one-time migrations. The current migrations are:

1. `ALTER TABLE files ADD COLUMN duplicate_of INTEGER` (added in v2.0).
2. `_migrate_legacy_settings`: any plaintext `groq_api_key` row is
   promoted to `llm_api_key` and the legacy row is deleted. Runs on
   every `initialize` but is a no-op once the migration has happened.

There is no version column on the schema. Future migrations should
use the standard SQLite pattern: a `PRAGMA user_version` check that
runs `ALTER TABLE` only if the current version is below the target.

## Backups

The DB is a single file at `<data_dir>/golem.db`. The `-wal` and
`-shm` sidecar files are created by SQLite in WAL mode. To make a
consistent backup:

```python
import sqlite3
conn = sqlite3.connect("<data_dir>/golem.db")
conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
# now safe to copy golem.db
```

`main.py --export-db <path>` does this for you.

## Vault directory layout

```
<vault>/
├── GOLEM/                       # Generated notes
│   ├── *.md                     # One note per indexed file
│   └── Orphaned/                # Notes whose file went missing
└── GOLEM Files/                 # Moved source files
    ├── Finance/
    ├── Research/
    ├── Design/
    ├── Code/
    ├── Media/
    ├── Personal/
    ├── Legal/
    ├── Duplicates/              # Hash collisions
    └── Other/                   # Default fallback category
```

The user is responsible for the vault root; GOLEM only writes inside
these two subdirectories.
