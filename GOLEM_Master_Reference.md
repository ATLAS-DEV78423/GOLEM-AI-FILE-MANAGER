# GOLEM — Master Reference Document

**Version:** 2.0.0
**Date:** 2026-05-31
**Status:** Ready for implementation

> This is the single source of truth for building GOLEM. It covers product vision, honest critique, risks, full technical architecture, data models, UI specs, concurrency model, API contracts, MVP checklist, demo plan, and long-term roadmap. Hand this document to any AI coding tool or developer and they have everything they need.

---

## Table of Contents

1. [Product Vision & Pitch](#1-product-vision--pitch)
2. [Target Users](#2-target-users)
3. [Honest Critique & Major Risks](#3-honest-critique--major-risks)
4. [Missing Features to Know About](#4-missing-features-to-know-about)
5. [Core Workflow — End to End](#5-core-workflow--end-to-end)
6. [Features & Prioritisation](#6-features--prioritisation)
7. [Technical Architecture](#7-technical-architecture)
8. [Data Models & API Contracts](#8-data-models--api-contracts)
9. [UI/UX Specifications](#9-uiux-specifications)
10. [Error Handling & Safety](#10-error-handling--safety)
11. [Development Roadmap](#11-development-roadmap)
12. [Complete MVP Checklist](#12-complete-mvp-checklist)
13. [Hackathon Strategy & Demo Plan](#13-hackathon-strategy--demo-plan)
14. [Long-Term Vision & Roadmap](#14-long-term-vision--roadmap)

---

## 1. Product Vision & Pitch

**GOLEM** is a local-first desktop companion for Windows that automatically transforms a messy folder into an organised, searchable knowledge base inside **Obsidian**. It acts like the mythical Copper Golem: you place it, it wakes up, and it works — organising, remembering, and retrieving your files on command.

**One-line pitch:**
*"Point GOLEM at a folder — it wakes up, organises everything, writes a living Obsidian note for each file, and lets you find anything just by describing it. No cloud. No subscription. Just a companion that remembers."*

**Why it matters:**
Messy folders, lost documents, and the frustration of knowing a file exists but not its name is something every computer user has felt. GOLEM's core promise is therefore instantly relatable. It does not just search — it organises, documents, and remembers, compounding in value the longer it runs.

**Competitive positioning:**
Microsoft Recall, Apple's on-device intelligence, and Rewind.ai are all entering the "what did I see?" space. GOLEM's sharpest defence is its **local-first, Obsidian-native, fully user-controlled** nature. Everything runs on the user's machine. Nothing is uploaded. No subscription. This must be communicated relentlessly.

---

## 2. Target Users

- **Knowledge workers, developers, and students** overwhelmed by unorganised files.
- **Obsidian users** — a passionate, high-value niche already practising personal knowledge management. They will immediately appreciate auto-generated vault notes.
- **Privacy-conscious users** who refuse to upload personal files to cloud services.
- **Pain point:** They know a file exists but cannot remember its name or location. They waste time digging. GOLEM eliminates that entirely.

---

## 3. Honest Critique & Major Risks

Read this section before building. These are the ways the project fails if not handled correctly.

### Critique

**Automated note generation is a double-edged sword.**
If generated Obsidian notes are inaccurate, incomplete, or noisy, users will see their vault polluted with low-value content. Trust is lost almost immediately and extremely difficult to restore. Notes must be high quality — or clearly marked as auto-generated and easily filterable — from day one.

**The Obsidian integration is both a strength and a dependency.**
Obsidian users are protective of their vaults. GOLEM must guarantee it never touches existing user notes. Auto-generated notes must live in a dedicated `GOLEM/` subfolder with no exceptions. The "wow" moment of the graph view is also partly dependent on Obsidian's UI, which GOLEM does not control.

**The product feels like a CLI-core with a UI shell.**
To feel like a true companion, the experience must be fluid and beautiful. A slow startup, clunky search box, or a 10-second query wait will kill the magic. The interface must match the ambition of the idea.

### Major Risks

| Risk | Consequence | Mitigation |
|---|---|---|
| Vault pollution from poor summaries | User abandons product immediately | Skip unreadable files gracefully; never write a junk note |
| Extraction quality is uneven | Scanned PDFs and images produce nothing | Be upfront; mark unsupported files clearly |
| File organisation is destructive if wrong | User loses files | Dry-run mode + undo log are non-negotiable from day one |
| Scalability at 100k+ files | Python process freezes | Incremental indexing on daemon threads from the start |
| No API key = broken product | Low adoption | Core indexing and FTS5 search must work without any LLM |
| "Spyware" perception | User never installs | Exclusion rules, pause scanning, delete index options visible |

---

## 4. Missing Features to Know About

These are not in the MVP but must be designed for from the start so they can be added without architectural rework:

- **Deduplication** — identical files (hash-based) produce one note, not many. Already handled in the schema via `content_hash`.
- **Exclusion rules** — ignore patterns, minimum file size, hidden directories. Add to `config.py` settings.
- **User-change detection** — if a user edits an auto-generated note (`user_edited: true` frontmatter), GOLEM must never overwrite it.
- **Note lifecycle** — when the original file is deleted, archive the note into an `Orphaned/` subfolder rather than deleting it.
- **Manual curation** — ability to regenerate a single note, mark a file as "ignored", or manually link concepts.
- **Multi-vault / multi-root support** — users often have more than one Obsidian vault or several independent folder sets.
- **OCR for scanned PDFs and images** — without it, a large class of documents is invisible to GOLEM.
- **Confidence scoring in search** — show how certain GOLEM is so the user can decide to trust the result.
- **Context menu integration** — "Open with GOLEM" as a Windows Explorer right-click entry.

---

## 5. Core Workflow — End to End

### First-Time Setup
1. User opens GOLEM — a clean onboarding wizard appears.
2. User selects:
   - The folder to organise (e.g. `C:\Users\You\Downloads`)
   - Their Obsidian vault folder (auto-detected if `.obsidian/` exists inside)
   - Their Groq API key (free tier, link to `console.groq.com` provided)
3. User clicks **"Awaken GOLEM"**.
4. Progress bar runs. For each file, GOLEM:
   - Extracts readable text content
   - Sends filename + snippet to Groq (Llama 3.1 8B) — one call per file, cached forever
   - Receives structured JSON: `summary`, `tags`, `category`, `clean_name`
   - Writes a `.md` note into `<vault>/GOLEM/`
   - Moves the file into `<vault>/GOLEM Files/<category>/`
   - Commits the record to SQLite
5. GOLEM minimises to the system tray silently.

### Every Day After
- GOLEM watches the folder in the background.
- Any new file dropped in → automatically indexed, note written, file sorted. Tray notification fires.
- User hits `Ctrl+Space` anywhere on the desktop → floating popup appears.
- User types a vague description → file opens.

### Search Flow (per query)
1. User types description and hits Enter.
2. GOLEM queries SQLite FTS5 — returns top 10 ranked candidates (< 200ms).
3. If top result confidence score ≥ 0.8 → open file immediately. No API call.
4. If confidence < 0.8 → send top 5 candidates + query to Groq (Llama 3.3 70B) → return best filepath.
5. If `NOT_FOUND` → show 3 most recently indexed files as fallback. Never crash.

### Data Integrity Rule
A file is moved **only after** its note is written and its DB entry is committed. The entire per-file pipeline (extract → summarise → write note → move → index) is wrapped in a single SQLite transaction. If any step fails, the transaction rolls back and the file is left untouched in its original location.

---

## 6. Features & Prioritisation

### 🟢 Must-Have (MVP — Hackathon Entry)

- Folder selection and recursive scanning with exclusion patterns
- Content extraction for `pdf`, `docx`, `xlsx`, `txt` (text-based only)
- Groq integration: Llama 3.1 8B for indexing, Llama 3.3 70B for search re-rank
- `.md` note generation in `<vault>/GOLEM/` with YAML frontmatter
- File organisation into category subfolders with clean names
- **Dry-run mode** — show planned moves, require confirmation before applying
- **Undo log** — reverse any file move action
- SQLite with FTS5 full-text search as the canonical index
- System tray icon with right-click menu and 3 icon states
- Global hotkey `Ctrl+Space` → floating search popup
- Click result to open file; right-click to reveal in File Explorer
- Progress bar during scan
- Graceful error handling: skip unreadable files, retry on rate limits, log all errors

### 🟡 Should-Have (if time allows)

- File watcher (watchdog) for automatic processing of new files
- Settings panel to change folder, vault, or API key post-setup
- Confidence score display per search result
- Re-scan button for changed files
- Multiple watched folders

### 🔴 Nice-to-Have (post-hackathon)

- Embedded vector search (`sqlite-vec` + local `all-MiniLM-L6-v2` model)
- OCR for scanned PDFs and images (Tesseract)
- Learning loop: local behavioural tracking → personalised re-ranking
- Obsidian companion plugin for deeper graph integration
- Cross-platform support (macOS, Linux)
- Local LLM backend (Ollama, llama-cpp) as an alternative to Groq

---

## 7. Technical Architecture

### 7.1 High-Level System Diagram

```
┌──────────────┐     ┌─────────────────────┐     ┌──────────────────────┐
│  File System  │────▶│   SQLite (canonical)│────▶│  Obsidian Vault      │
│  (watched)    │     │   index + FTS5      │     │  (generated notes)   │
└──────────────┘     └─────────────────────┘     └──────────────────────┘
       │                       │
       ▼                       ▼
[Scanner] ──► Extractor ──► Summarizer (Groq) ──► Vault Writer ──► Organizer
                                                         │
                                              [Search Engine]
                                         ◄── User query (Popup)
                                         ──► Groq optional re-rank
```

- **SQLite** is the single source of truth. The Obsidian vault is a derived output.
- A note can be regenerated at any time from the SQLite index.
- Files are moved into `GOLEM Files/` — a separate root — so the watched folder becomes clean.

### 7.2 Concurrency & Threading Model

This is the most critical architectural decision. Four components run concurrently and must never block each other.

| Component | Thread | Requirement |
|---|---|---|
| `pystray` tray icon | **Main thread** | pystray strictly requires the main thread |
| Scanner / indexing pipeline | `threading.Thread` (daemon) | Reports progress via `progress_queue` |
| File watcher (watchdog) | `threading.Thread` (daemon) | Fires new-file events into `command_queue` |
| Popup / search window | `threading.Thread` (daemon) | Reads results from `result_queue` |
| Orchestrator loop | `threading.Thread` (daemon) | Drains `command_queue`, dispatches actions |

**Three shared queues — all created in `main.py`:**

```python
import queue, threading

progress_queue = queue.Queue()  # scanner → UI (progress %, current filename)
command_queue  = queue.Queue()  # tray/popup/watcher → orchestrator (actions)
result_queue   = queue.Queue()  # search engine → popup (search results)
```

**Message formats:**
```python
# progress_queue messages
{"progress": 0.45, "current_file": "report.pdf"}
{"progress": 1.0, "current_file": "done"}

# command_queue messages
{"action": "rescan"}
{"action": "undo"}
{"action": "search", "query": "the budget from March"}
{"action": "new_file", "path": "C:/Downloads/contract.pdf"}

# result_queue messages
{"results": [{"filepath": "...", "clean_name": "...", "summary": "...", "category": "..."}]}
{"results": [], "message": "No matches found"}
```

**Hotkey registration — with fallback:**

```python
try:
    import keyboard
    keyboard.add_hotkey("ctrl+space", open_popup)
except Exception:
    # keyboard requires admin on some Windows environments
    from pynput import keyboard as pynput_kb
    def on_activate():
        open_popup()
    hotkey = pynput_kb.GlobalHotKeys({"<ctrl>+<space>": on_activate})
    hotkey.start()
```

### 7.3 Technology Stack

| Component | Technology | Reason |
|---|---|---|
| Core language | Python 3.11 | Best ecosystem for file system + desktop |
| File extraction | pypdf, python-docx, openpyxl | Reliable text extraction, all free |
| AI indexing | Groq API — Llama 3.1 8B | Free tier, fast, sufficient for metadata |
| AI search re-rank | Groq API — Llama 3.3 70B | Higher accuracy for fuzzy matching |
| Local database | SQLite + FTS5 | Zero-dependency, sub-200ms full-text search |
| System tray | pystray | Cross-platform tray icon |
| Global hotkey | keyboard (pynput fallback) | Global hotkey without blocking |
| UI popup | PyWebView + HTML/CSS/JS | Modern floating window, full styling control |
| File watching | watchdog | Reliable cross-platform file system events |
| Concurrency | threading + queue.Queue | Safe cross-thread communication |
| Packaging | PyInstaller | Single `.exe`, no Python install required |

**LLM backend strategy — local-first, cloud-optional:**
- Extraction and FTS5 search must work entirely offline with no API key.
- LLM features (summarisation, fuzzy search re-rank) are optional enhancements.
- Post-MVP: add a backend selector supporting Groq, OpenAI, Anthropic, and local Ollama/llama-cpp.
- This ensures GOLEM works for everyone and becomes more powerful with optional AI.

### 7.4 Project File Structure

```
GOLEM/
├── main.py                  # Entry point: init queues, start tray on main thread
├── config.py                # Load/save settings from SQLite settings table
├── orchestrator.py          # Daemon thread: drains command_queue, dispatches actions
├── scanner.py               # Recursive folder walk, skips indexed files by hash
├── extractor.py             # Text extraction per file type (pdf/docx/xlsx/txt)
├── summarizer.py            # Groq API: indexing prompt + search re-rank prompt
├── vault_writer.py          # Writes .md notes into <vault>/GOLEM/
├── organizer.py             # Moves files into GOLEM Files/<category>/, logs undo
├── indexer.py               # All SQLite CRUD + FTS5 queries + trigger setup
├── search.py                # FTS5 query → confidence check → optional Groq re-rank
├── watcher.py               # watchdog observer → fires command_queue on new files
├── tray.py                  # pystray icon, 3 states, right-click menu
├── popup.py                 # Daemon thread: hotkey → opens search window
├── onboarding.py            # First-run wizard: folder picker, vault picker, API key
├── undo.py                  # Reverses last file move using undo_log table
├── db/
│   └── golem.db             # SQLite database (auto-created on first run)
├── ui/
│   ├── popup.html           # Search popup HTML
│   ├── popup.css            # Dark theme, copper accent styling
│   ├── popup.js             # Frontend: input handling, result rendering
│   └── onboarding.html      # 3-step wizard HTML
├── assets/
│   ├── golem_awake.png      # Tray icon: idle/ready state
│   ├── golem_busy.png       # Tray icon: scanning state
│   └── golem_idle.png       # Tray icon: after scan, no watcher
├── logs/
│   ├── golem.log            # All events, errors, warnings
│   └── undo.log             # Human-readable record of file moves
└── requirements.txt         # Pinned dependency versions
```

---

## 8. Data Models & API Contracts

### 8.1 SQLite Schema

```sql
-- Core file index
CREATE TABLE files (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    original_filename   TEXT,
    clean_filename      TEXT,
    original_path       TEXT UNIQUE,
    current_path        TEXT,           -- updated after file move
    file_type           TEXT,
    size_kb             REAL,
    content_hash        TEXT,           -- SHA256 of first 1KB + file size
    extracted_text      TEXT,           -- first 500 chars of readable content
    summary             TEXT,
    tags                TEXT,           -- comma-separated
    key_contents        TEXT,
    category            TEXT,
    obsidian_note_path  TEXT,
    date_indexed        TEXT,           -- ISO 8601 timestamp
    last_modified       TEXT,
    index_status        TEXT DEFAULT 'pending'
    -- values: 'pending' | 'done' | 'skipped' | 'error' | 'missing'
);

-- FTS5 virtual table for full-text search
CREATE VIRTUAL TABLE files_fts USING fts5(
    original_filename,
    clean_filename,
    summary,
    tags,
    key_contents,
    category,
    content='files',
    content_rowid='id'
);

-- Triggers keep FTS5 automatically in sync with the files table
CREATE TRIGGER files_ai AFTER INSERT ON files BEGIN
    INSERT INTO files_fts(rowid, original_filename, clean_filename, summary, tags, key_contents, category)
    VALUES (new.id, new.original_filename, new.clean_filename, new.summary, new.tags, new.key_contents, new.category);
END;

CREATE TRIGGER files_ad AFTER DELETE ON files BEGIN
    INSERT INTO files_fts(files_fts, rowid, original_filename, clean_filename, summary, tags, key_contents, category)
    VALUES('delete', old.id, old.original_filename, old.clean_filename, old.summary, old.tags, old.key_contents, old.category);
END;

CREATE TRIGGER files_au AFTER UPDATE ON files BEGIN
    INSERT INTO files_fts(files_fts, rowid, original_filename, clean_filename, summary, tags, key_contents, category)
    VALUES('delete', old.id, old.original_filename, old.clean_filename, old.summary, old.tags, old.key_contents, old.category);
    INSERT INTO files_fts(rowid, original_filename, clean_filename, summary, tags, key_contents, category)
    VALUES (new.id, new.original_filename, new.clean_filename, new.summary, new.tags, new.key_contents, new.category);
END;

-- Undo log: every file move is recorded and reversible
CREATE TABLE undo_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    action       TEXT,       -- 'move' | 'rename'
    file_id      INTEGER,
    from_path    TEXT,
    to_path      TEXT,
    timestamp    TEXT,
    reversed     INTEGER DEFAULT 0
);

-- Settings key-value store
CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
```

### 8.2 Obsidian Note Template

```markdown
---
filename: <clean_filename>
original_name: <original_filename>
path: <current_path>
type: <file_type>
size: <size_kb>KB
date_indexed: <ISO timestamp>
tags: [<tag1>, <tag2>, <tag3>]
golem_category: <category>
user_edited: false
---

# <clean_filename without extension>

**Summary:** <Groq-generated one-sentence summary>

**Key contents:** <Groq-generated comma-separated topics>

**Moved to:** `GOLEM Files/<category>/`

[[<category>]] [[<tag1>]] [[<tag2>]]
```

> **Critical rule:** If `user_edited: true` is present in the frontmatter, GOLEM must never overwrite or regenerate this note under any circumstances.

> **Orphan rule:** If the source file is deleted, move the note to `<vault>/GOLEM/Orphaned/` rather than deleting it. Update `index_status = 'missing'` in SQLite.

### 8.3 Groq API Contracts

**Base URL:** `https://api.groq.com/openai/v1/chat/completions`
**Auth header:** `Authorization: Bearer <GROQ_API_KEY>`

**Indexing prompt** — model: `llama-3.1-8b-instant` (fast, cheap, one call per file):

```
You are GOLEM, a file indexing assistant.
Given a filename and a snippet of its content, return ONLY a valid JSON object.
No explanation, no markdown, no backticks. Pure JSON only.

Required keys:
{
  "summary": "one sentence describing what this file is",
  "tags": ["tag1", "tag2", "tag3"],
  "key_contents": "comma-separated list of main topics or items found",
  "category": "one folder name — Finance | Research | Design | Code | Media | Personal | Legal | Other",
  "clean_name": "a readable filename if the current one is messy, otherwise keep original"
}

File: {filename}
Content snippet: {first_300_chars}
```

**Search re-rank prompt** — model: `llama-3.3-70b-versatile` (smarter, used only when FTS5 confidence < 0.8):

```
You are a file finder. A user is looking for a file but does not know its exact name.
Given their description and a list of candidate files, return ONLY the filepath of the
single best matching file. If no file matches well, return exactly: NOT_FOUND
No explanation. No other text.

User description: {user_query}

Candidate files:
{json_array_of_top_5_candidates}
```

### 8.4 Groq Rate & Token Management

| Situation | API call? | Model | Approx tokens |
|---|---|---|---|
| New file, never indexed | Yes — once | Llama 3.1 8B | ~400 in, ~100 out |
| File unchanged (same `content_hash`) | No — SQLite hit | — | 0 |
| File modified (hash changed) | Yes — re-index | Llama 3.1 8B | ~400 in, ~100 out |
| Search, FTS5 confident (score ≥ 0.8) | No | — | 0 |
| Search, FTS5 uncertain (score < 0.8) | Yes | Llama 3.3 70B | ~800 in, ~50 out |
| Binary / unreadable file | No | — | 0 |

**Rate limit rules:**
- 1-second `time.sleep()` between every indexing API call.
- On HTTP 429: wait 60 seconds, retry once. If still failing: mark `index_status = 'error'`, log, continue.
- A 500-file folder ≈ 250,000 tokens on first run ≈ 10 minutes of scanning. After that, near-zero daily usage.
- JSON parse failure: retry once with stricter system prompt. If still invalid: index file using filename heuristics only, still write a note.

---

## 9. UI/UX Specifications

### 9.1 Visual Identity
- **Theme:** Dark, near-black background (`#0f0f0f`), copper accent (`#B87333`), off-white text (`#e8e8e8`).
- **Feel:** Minimal, focused, slightly mysterious — like the golem itself. No clutter.

### 9.2 Onboarding Wizard

- **Window:** 400×500px, modal, centered, dark theme, copper accent button.
- **Step 1:** "Choose the folder you want GOLEM to organise" → folder picker button.
- **Step 2:** "Where is your Obsidian vault?" → folder picker (auto-detects `.obsidian/` folder).
- **Step 3:** "Paste your free Groq API key" → masked text input + link to `console.groq.com`.
- **CTA:** "Awaken GOLEM" — full-width copper button. Transitions to progress view on click.

### 9.3 System Tray

- **Icon states:**
  - `golem_busy.png` — while scanning
  - `golem_awake.png` — idle, file watcher active
  - `golem_idle.png` — after scan, no watcher running
- **Right-click menu:**
  - 🔍 Search files `Ctrl+Space`
  - 🔄 Re-scan watched folder
  - 👁 Dry-run preview
  - ↩ Undo last organisation
  - ⚙ Settings
  - ❌ Quit

### 9.4 Search Popup

- **Trigger:** `Ctrl+Space` globally (pynput fallback if keyboard requires admin).
- **Runs on:** its own daemon thread. Communicates with search engine via `result_queue`.
- **Window:** 350×500px, rounded corners, semi-transparent dark background, centered on screen.
- **Layout:**
  - Large text input at top: placeholder "Describe what you're looking for…"
  - Scrollable results list below. Each result shows:
    - Clean filename (bold)
    - One-line summary (muted)
    - Category badge (copper pill)
    - Confidence bar (optional)
  - Single click → `os.startfile(filepath)`
  - Right-click → "Open file location" in Explorer
  - `Esc` or click-outside closes popup
- **Loading:** Spinner appears while querying. FTS5 responds in < 200ms. Groq fallback ~2s.
- **No results:** "No exact match. Here are some recent files that might help." + 3 recent files.

### 9.5 Dry-run & Undo

- **Dry-run:** Toggle from tray. When active, shows a "Before → After" list of planned file moves. User clicks "Confirm" to apply. Nothing moves until confirmed.
- **Undo:** Available from tray menu. Reverses the most recent file move. Restores file to `from_path`. Deletes Obsidian note unless `user_edited: true`. Updates SQLite.

---

## 10. Error Handling & Safety

| Scenario | Behaviour |
|---|---|
| Unreadable / binary file | Mark `index_status = 'skipped'`, log warning, continue silently |
| Groq HTTP 429 rate limit | Wait 60 seconds, retry once. If still failing: mark `error`, log, skip |
| Groq returns invalid JSON | Retry with stricter prompt. If still failing: index by filename only, still write note |
| File move name collision | Append ` (1)`, ` (2)`, etc. to filename before moving |
| File deleted externally | On re-scan: set `index_status = 'missing'`, move note to `Orphaned/` subfolder |
| Obsidian vault not found | Alert user via popup, prompt to re-select. Never write to disk without valid vault path |
| Search yields nothing | Show "No exact match" + 3 most recently indexed files. Never crash |
| Large folder (10k+ files) | Daemon thread + progress queue. UI never freezes. Show estimated time remaining |
| `keyboard` hotkey fails | Silent fallback to pynput. Log info. User never sees this |
| Pipeline transaction fails mid-file | SQLite rollback. File left untouched. Log error. Continue to next file |
| User edits a GOLEM note | `user_edited: true` in frontmatter → GOLEM skips it on all future re-scans |

---

## 11. Development Roadmap

### Phase 1 — Core Engine (Hours 0–12)

**Goal:** One file goes in, a note comes out, the file moves. End to end.

**Strict build order — do not deviate:**
1. `extractor.py` — extract text from all 4 file types
2. `summarizer.py` — call Groq, return valid dict
3. `indexer.py` — write file record to SQLite
4. `vault_writer.py` — write `.md` note to vault folder
5. `organizer.py` — move file, write to undo log
6. `scanner.py` — wire all of the above for a full folder

Test the full pipeline on 20 mixed real files before moving to Phase 2. Do not touch the UI yet.

> **Realistic warning:** `extractor.py` alone — handling PDF, docx, and xlsx edge cases — can take half a day. Budget accordingly.

### Phase 2 — Interface & Companion (Hours 12–24)

**Goal:** Give GOLEM a face.

- `orchestrator.py` — daemon thread draining `command_queue`
- `tray.py` — pystray icon, 3 states, menu wired to command_queue
- `popup.py` + `ui/popup.html` — floating search window
- `search.py` — FTS5 query + confidence check + Groq fallback
- `onboarding.py` — 3-step wizard
- `main.py` — wire everything together with the 3 queues

### Phase 3 — Polish & Demo Prep (Hours 24–48)

**Goal:** Make the demo airtight.

- Progress bar reading from `progress_queue`
- Dry-run mode with confirmation
- Undo via tray menu
- `watcher.py` — watchdog for new files (impressive live demo moment)
- Dark theme CSS finishes, copper accents
- Error dialogs and tray notifications
- PyInstaller packaging into single `.exe`
- Prepare staged demo folder (100+ messy files, pre-indexed)
- Record backup demo video

---

## 12. Complete MVP Checklist

### Setup & Config
- [ ] Git init, `requirements.txt` with pinned versions
- [ ] `config.py` reads/writes `settings` table in SQLite
- [ ] API key stored in `settings` table, not plaintext file

### Concurrency (do this before writing any UI)
- [ ] Three `queue.Queue` instances in `main.py`: `progress_queue`, `command_queue`, `result_queue`
- [ ] Scanner runs on a daemon thread, reports to `progress_queue`
- [ ] Orchestrator runs on a daemon thread, drains `command_queue`
- [ ] Popup runs on a daemon thread, reads from `result_queue`
- [ ] Tray icon runs on main thread via `pystray.Icon.run()`

### Database
- [ ] `indexer.py` creates all tables + FTS5 virtual table + 3 sync triggers on first run
- [ ] Insert with conflict resolution (by `content_hash`)
- [ ] Update `current_path` after file move
- [ ] FTS5 query returning top 10 ranked results with scores

### Extractor
- [ ] `.txt` — `open()`, read directly
- [ ] `.pdf` — pypdf `PdfReader`, extract first 500 chars
- [ ] `.docx` — python-docx `Document`, join paragraphs
- [ ] `.xlsx` — openpyxl, cell values as concatenated string
- [ ] All others — return empty string (index by filename only)

### Summarizer (Groq)
- [ ] `get_file_metadata(filename, text_snippet)` → dict with `summary, tags, key_contents, category, clean_name`
- [ ] `search_rerank(query, candidates_json)` → filepath string or `"NOT_FOUND"`
- [ ] System prompt forces pure JSON output
- [ ] Safe `try/except` JSON parsing with sensible fallback defaults
- [ ] 1-second delay between calls; 60-second wait + single retry on HTTP 429

### Vault Writer
- [ ] Creates `GOLEM/` subfolder inside vault if it doesn't exist
- [ ] Writes `.md` file with full YAML frontmatter and all body sections
- [ ] Checks `user_edited: true` before writing — skip if set
- [ ] Returns note path for storage in DB

### Organizer
- [ ] Creates `GOLEM Files/` root folder if absent
- [ ] Creates `<category>/` subfolder if needed
- [ ] Handles name collisions: appends ` (1)`, ` (2)`, etc.
- [ ] Moves file only after note is written and DB entry is committed (single transaction)
- [ ] Records action in `undo_log`

### Undo
- [ ] `undo_last()` finds most recent `reversed = 0` entry in `undo_log`
- [ ] Moves file back to `from_path`
- [ ] Deletes Obsidian note unless `user_edited: true`
- [ ] Marks log entry `reversed = 1`
- [ ] Updates `current_path` in `files` table

### Scanner
- [ ] Walks folder recursively with `os.walk()`
- [ ] Skips hidden/system folders: `$Recycle.Bin`, `.obsidian`, `System Volume Information`, etc.
- [ ] Skips files where `content_hash` matches existing DB record
- [ ] Reports `{"progress": float, "current_file": str}` to `progress_queue` per file

### UI & Tray
- [ ] `pystray` icon with 3 state images
- [ ] All tray menu items put commands into `command_queue`
- [ ] Global hotkey registered — `keyboard` first, `pynput` fallback
- [ ] Popup window: dark theme, centered, single input field
- [ ] Popup reads results from `result_queue` and renders them
- [ ] Click result → `os.startfile(filepath)`
- [ ] Right-click result → `subprocess.Popen(['explorer', '/select,', filepath])`

### Search
- [ ] FTS5 query returning top 10 ranked candidates
- [ ] Confidence threshold: score ≥ 0.8 → return immediately, no API call
- [ ] Score < 0.8 → send top 5 to Groq re-rank
- [ ] `NOT_FOUND` → return 3 most recently indexed files

### File Watcher (optional but impressive for demo)
- [ ] `watchdog` observer on watched folder
- [ ] Wait for file write to complete (poll file size until stable)
- [ ] Run full pipeline on new file
- [ ] Fire tray notification: "New note created: {clean_filename}"

### Polish
- [ ] 3-screen onboarding wizard with folder pickers and API key input
- [ ] Progress bar reads from `progress_queue` and updates live
- [ ] Dry-run: show planned moves list, require "Confirm" click
- [ ] All events and errors written to `golem.log` with timestamps

### Packaging
- [ ] `requirements.txt` with pinned versions
- [ ] PyInstaller `.spec` file, one-folder build
- [ ] `assets/`, `db/`, `ui/` folders included in bundle
- [ ] Tested successfully on a clean Windows machine with no Python installed

---

## 13. Hackathon Strategy & Demo Plan

### The Golden Rule
**Stage perfection. Don't build a production app.**
Judges see a 90-second demo, not 48 hours of code. Pre-build the index. Rehearse until it's muscle memory. One keyboard slip kills the magic.

### What to Actually Build for the Hackathon
- The full core engine (Phase 1) must work perfectly.
- A pre-built SQLite index from a curated "messy folder" of 100–200 files — eliminates scan time during the live demo.
- The search popup must be flawless. This is the money moment.
- Groq is only called live for the "new file drops in" moment and the live search query. Everything else is pre-cached. This avoids rate limits and guarantees speed.
- Have a dry-run toggle visible and demonstrate it before committing a file move.
- **Add a hardcoded "learning" preview** after the demo search: "You often open Budget.pdf after reviewing this file. Linking them…" — this shows the future vision without having to build it.

### What to Avoid
- Scanning a real large folder live
- Network errors from Groq rate limits
- Long installation steps
- Slow or ugly UI
- Explaining what it does — show it

### Live Demo Script (90 seconds)

```
0:00 – 0:10
"Your Downloads folder is a mess. Filenames like 'final_v3_REAL.pdf'.
You can't find anything unless you remember the exact name."

0:10 – 0:25
"Meet GOLEM. Point it at the folder, pick the Obsidian vault, hit Awaken."
[Click Awaken. Progress bar zips through pre-indexed files.]

0:25 – 0:40
"Every file now has a beautiful, linked note in Obsidian —
summary, tags, clean name — written automatically."
[Show 2–3 Obsidian notes. Show graph view briefly.]

0:40 – 0:55
"Watch. A new file drops in."
[Drop a PDF. Tray notification fires: "New note created."]
"Already indexed. Already filed."

0:55 – 1:15
"The real magic."
[Ctrl+Space. Type: "the spreadsheet about the marketing budget". Hit Enter.]
"Opens instantly. No filename guessing."

1:15 – 1:30
"All local. All free. No subscription.
GOLEM builds your second brain for you — automatically."
[Show Obsidian graph with interconnected notes.]
```

### Pitch Angles for Judges

- **Relatable pain:** Judges are developers. They have a messy Downloads folder. They feel this in their soul.
- **Honest AI use:** Groq free tier for exactly two tasks. Everything else is local. "Privacy-first AI."
- **Obsidian fanbase:** Saying "Obsidian" wins you instant supporters in any developer audience.
- **Copper Golem story:** "You place it, it works. It organises, it remembers, it never forgets."
- **Compounding value:** The longer it runs, the richer the vault. It compounds like a savings account.
- **Clear roadmap:** Point to semantic search, the learning loop, and the vision below. Show you're thinking beyond the hackathon.

---

## 14. Long-Term Vision & Roadmap

### Phase 4 — Smart Search & Auto-watch (2–3 months post-launch)
- `sqlite-vec` + local `all-MiniLM-L6-v2` embedding model for hybrid keyword + vector search.
- OCR via Tesseract for scanned PDFs and images.
- Fully autonomous file watcher replacing manual re-scan.
- Note lifecycle: orphaned notes move to `Orphaned/` when source file is deleted.
- Tag extraction from text without requiring an LLM call.

### Phase 5 — Intelligence & Learning (3–6 months)
- Local behavioural tracking: which files open together, which search results get clicked.
- Personalised relevance model — completely local, no cloud.
- Suggested `[[wikilinks]]` between files based on co-occurrence and vector similarity. User must accept or dismiss each one.
- "Map of Content" generation for folders or topic clusters (LLM-assisted, user-approved).
- "Resurface old files" when a related topic becomes active again (spaced repetition for documents).

### Phase 6 — Ecosystem & Polish (6–12 months)
- Abstracted LLM backend: Groq, OpenAI, Anthropic, and local Ollama/llama-cpp — user chooses.
- Obsidian companion plugin for richer integration: direct file preview from within notes, custom vault views.
- "Diff summaries" — when a file changes, generate a summary of what changed since last index.
- Support for multiple watched folders and multiple Obsidian vaults.
- Advanced exclusion rules and privacy controls (exclude by folder, file type, size).
- Cross-platform: macOS and Linux.
- Optional context menu entry: "Open with GOLEM" in Windows Explorer.

### The Category-Defining Vision

**Do not build a file search tool. Build a memory prosthesis.**

Category-defining products change user behaviour. GOLEM does that if it:

1. **Becomes an autonomous knowledge co-pilot.** It doesn't wait to be searched. It notices you're working on a topic and proactively surfaces the relevant spreadsheet, PDF, or image — acting like a silent research assistant who knows your entire digital world.

2. **Learns your mental models over time.** By observing which files you open together and which searches you click, GOLEM builds a personalised relevance model that begins to predict what you need before you ask. Completely local. Completely transparent.

3. **Respects the lifecycle of thoughts.** Notes age, evolve, and relate to each other over time. GOLEM surfaces old files when a related topic reactivates. It generates diff summaries showing how a document changed over months. It becomes a time-machine for your own past work.

4. **Creates a new interface paradigm.** The search box is just the beginning. Imagine voice queries, drag-and-drop linking of files to notes, a spatial knowledge map you navigate instead of a file tree. GOLEM abstracts the file system entirely, replacing it with a semantic space that matches how humans actually think.

If you deliver a product that feels like *a faithful companion that grows with you* — not a utility — you will have defined a new category: the **personal knowledge gardener**.

---

**End of Master Reference.**

*Any AI coding tool or developer should be able to read this single document and build GOLEM exactly as intended, from first file to shipped `.exe`.*

*Go awaken your Golem.*
