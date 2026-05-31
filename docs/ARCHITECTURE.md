# Architecture

## Overview

GOLEM is built around a local SQLite database that acts as the canonical index.

## Main components

- `main.py` starts the application.
- `golem/app.py` orchestrates UI, watcher, tray, search, scan, and undo.
- `golem/scanner.py` walks the watched folder and indexes files.
- `golem/extractor.py` extracts readable text from supported files.
- `golem/summarizer.py` provides heuristic and provider-backed metadata generation.
- `golem/vault_writer.py` writes Obsidian notes.
- `golem/organizer.py` moves files into category folders.
- `golem/indexer.py` manages SQLite schema, settings, and FTS search.
- `golem/search.py` runs local search and optional reranking.
- `golem/watcher.py` polls the watched folder for changes.
- `golem/ui.py` provides the Tk-based popup and onboarding flow.
- `golem/tray.py` manages the system tray icon and menu.
- `golem/undo.py` reverses the most recent move action.

## Data flow

1. The scanner extracts text from a file.
2. The summarizer generates metadata.
3. The vault writer creates the note.
4. The organizer moves the file.
5. The indexer stores the record in SQLite.
6. The search popup reads from SQLite and reranks when needed.

## Current limitations

- Watcher is polling-based, not event-driven.
- OCR is not implemented.
- Vector search is not implemented.
- Multi-vault support is limited.
- The UI is Tk-based rather than a richer web shell.

