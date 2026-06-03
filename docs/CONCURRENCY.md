# Concurrency Model

GOLEM runs several threads concurrently and uses SQLite in WAL mode to
coordinate their writes. This document explains how the pieces fit
together and what invariants the code maintains.

## Threads

| Thread | Purpose | Created by | Lifetime |
|---|---|---|---|
| Tk main | Tk event loop, command pump, error pump, progress pump, on-screen UI | `DesktopApp.root.mainloop()` | App lifetime |
| Tray | pystray icon and menu callbacks | `TrayController.start()` | App lifetime (daemon) |
| Watcher poll | Periodically scans the watched folder | `PollingWatcher._run_poll` | Watcher lifetime (daemon) |
| Watcher worker | Drains watcher's bounded queue, invokes `on_new_file` callback | `PollingWatcher._run_worker` | Watcher lifetime (daemon) |
| Index worker | Drains app's `index_queue`, calls `index_one_file` per path | `GolemApplication._index_worker_loop` | App lifetime (daemon) |
| Scan | Runs `scan_folder` over the entire watched folder | `_pump_commands` (when action is `scan`) | One-shot (daemon) |
| Undo | Runs `undo_last` | `_pump_commands` (when action is `undo`) | One-shot (daemon) |
| Search | Handles a single popup search request | `DesktopApp._handle_search` | One-shot (daemon) |
| Hotkey | `keyboard` or `pynput` listener | `_start_hotkeys` | App lifetime (daemon) |

A "one-shot" thread runs to completion and is then garbage-collected.
The pumps and long-lived workers are daemons so they do not block
process exit.

## Queues

Three queues sit between threads:

| Queue | Producer | Consumer | Purpose |
|---|---|---|---|
| `command_queue` | Tray, search popup, watcher, hotkey | `_pump_commands` (UI thread) | Tray-to-UI actions |
| `progress_queue` | Scan thread | `_pump_progress` (UI thread) | "scanning X of Y" status |
| `index_queue` | Watcher → `_handle_watcher_event` → `enqueue_index` | `_index_worker_loop` | One-at-a-time file indexing |
| `error_queue` | Any background thread | `_pump_errors` (UI thread) | User-facing error messages |
| `result_queue` (defined but unused) | — | — | Reserved for future search engine result delivery |

All queues are unbounded except `PollingWatcher._queue`, which is
capped at 1024 to bound memory if the consumer falls behind.

## Database access

Every thread that touches SQLite opens its own connection. Connections
are short-lived and wrapped in `closing(connect(...))`. The DB is in
WAL mode with a 30-second busy timeout, so concurrent readers do not
block each other and a writer waits up to 30 seconds for an exclusive
lock before failing.

The index worker is the **only** thread that writes from a watcher
event. This bounds writer contention to a single connection. The
scan and undo threads each open their own connection; they are mutually
exclusive via `_scan_lock` and `_undo_lock`.

## Invariants

- Tk widgets are touched **only** on the Tk main thread. The pumps
  exist to enforce this; producer threads put state on a queue and the
  pump updates the UI.
- File moves happen on the index worker (single-writer) or scan thread
  (single-writer per scan). Two writers can never be inside
  `safe_move` for the same source.
- `_scan_lock` and `_undo_lock` are non-re-entrant. The pump checks
  `acquire(blocking=False)` and skips a duplicate request rather than
  blocking.
- The watcher debounces per-file: the same path is not enqueued twice
  within `debounce_seconds` (default 2s). This is enforced by
  `_last_dispatched` in the watcher, not in the index worker.
- The watcher's worker thread processes events serially. A burst of
  watch events produces a backlog in `index_queue`, not parallel index
  operations.

## Failure modes

- **Index worker crashes**: the thread terminates. The pump does not
  notice. The next time the watcher fires an event, the `enqueue`
  call will succeed but nothing will pull from the queue. A
  defensive guard in `_index_worker_loop` catches any exception from
  `_index_single` and logs it, so the worker keeps running.
- **UI pump blocked**: the `root.after(100, ...)` callback chain is
  re-scheduled *after* the work completes, so a slow pump does not
  double-fire; it just delays subsequent pumps.
- **Database locked**: SQLite raises `OperationalError` after 30s.
  Callers catch this in `search_files` (returns empty list) and in
  the index worker (logs and continues). A user-visible error is
  posted to `error_queue` so the status bar reflects the problem.

## Shutdown

`GolemApplication.shutdown()` is called from the UI thread on quit and
on any unhandled exception. It:

1. Sets `_index_stop` so the worker exits its loop.
2. Sends a `None` sentinel on `index_queue` to unblock the worker
   immediately.
3. Stops the watcher (which joins both of its threads).
4. Stops the tray (which is a daemon thread; the OS reaps it).

The Tk main loop exits via `root.quit()` once the quit action is
dispatched.
