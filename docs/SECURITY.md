# Security

GOLEM is a local desktop app, so the main security boundary is the user's machine.

## What the app does to protect itself

- stores settings locally in SQLite
- encrypts supported secret settings on Windows using DPAPI
- validates installer payload manifests before copying
- validates install directories before deleting them
- escapes PowerShell shortcut creation literals
- skips user-edited notes when archiving or undoing

## What it does not promise

- It does not make local compromise impossible.
- It does not guarantee that third-party AI providers will keep your data private.
- It does not guarantee that an incorrectly configured provider or vault path cannot cause trouble.

## Best practices

- Keep backups of the watched folder and vault.
- Use dry-run before letting GOLEM reorganize a large folder.
- Use heuristic mode if you do not want any external API calls.
- Review the Terms of Service before first use.

