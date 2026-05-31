# Usage

## Core workflow

1. Choose a folder to watch.
2. Choose an Obsidian vault.
3. Pick a provider or heuristic mode.
4. Accept the Terms of Service.
5. Let GOLEM scan the folder.
6. Use `Ctrl+Space` to search files by description.

## Search

The search popup queries the local SQLite FTS index first.

- If the result confidence is high, GOLEM returns the best match immediately.
- If confidence is low and a provider is configured, GOLEM asks the provider to rerank the top candidates.
- If no match is found, GOLEM shows recent files.

## File actions

- Double-click a result to open the file.
- Right-click a result to reveal it in the file manager.
- Use the tray menu to rescan, undo, or open settings.

## Watch mode

When watch mode is enabled, GOLEM polls the watched folder and rescans when new files appear.

## Undo

The undo action reverses the latest organization action recorded in the local database.

