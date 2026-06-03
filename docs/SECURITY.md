# Security

GOLEM is a local desktop app. The main security boundary is the
user's machine. This document describes what GOLEM does to protect
the user, what it does not promise, and how to report a vulnerability.

## Threat model

- The user is trusted. The threat is *accidental* data loss or
  exposure, not a malicious local user.
- The watched folder and the Obsidian vault are user-controlled. We
  must not damage their contents.
- API keys are sensitive. They must not be stored in plaintext, logged,
  or sent anywhere except the configured provider.
- The installer is downloaded from a trusted channel (GitHub
  Releases). A tampered installer is a real risk; we mitigate with
  manifest integrity checks.

## What GOLEM does

- **API key protection.** `llm_api_key` and the legacy `groq_api_key`
  are DPAPI-encrypted on Windows (`CryptProtectData`) and base64-wrapped
  on other platforms. The encryption key is the user's Windows login,
  so another user on the same machine cannot decrypt.
- **Secret migration.** On first run after upgrade, plaintext legacy
  rows are promoted to the new key name and re-encrypted on the next
  save.
- **Manifest integrity.** The installer's payload is hashed at build
  time (`scripts/write_payload_manifest.py`); the manifest is checked
  at install time. A tampered or corrupted bundle is rejected.
- **Install path safety.** The installer refuses to delete any
  directory that does not have a valid `install-manifest.json` with
  the correct `app_name`. Shortcut paths declared in the manifest are
  validated against the Start Menu and Desktop roots before unlinking.
- **Path-traversal defense.** The SQLite identifier validator
  (`_validate_identifier`) rejects table/column names that are not
  `[A-Za-z_][A-Za-z0-9_]*`. The FTS query sanitizer
  (`_sanitize_query`) strips everything that is not `[A-Za-z0-9]`.
- **No telemetry.** GOLEM does not phone home. Logs stay in
  `<data_dir>/golem.log`. The only network calls are to the
  configured LLM provider.
- **Subprocess args.** All `subprocess` calls use argv form (never
  `shell=True`). PowerShell shortcut creation escapes single quotes
  and uses `-NoProfile` to avoid loading attacker-controlled
  profiles.

## What GOLEM does not promise

- A local malware or another user with the same login can read
  unencrypted data and call the LLM provider with the user's key.
  We do not have a defense against a malicious local user.
- Provider availability, accuracy, and privacy are the provider's
  responsibility, not ours. Review the provider's terms before
  entering a key.
- An incorrectly configured vault or watched folder can cause data
  to be moved to the wrong place. Always back up before using GOLEM
  on important data, and use dry-run for the first scan.

## Best practices

- Back up the watched folder and the vault before first use.
- Use dry-run before letting GOLEM reorganize a large folder.
- Use heuristic mode if you do not want any external API calls.
- Review the [Terms of Service](../assets/legal/terms_of_service.md)
  before first use.
- Keep GOLEM up to date. Subscribe to GitHub releases for security
  notifications.

## Vulnerability disclosure

Please **do not** open a public GitHub issue for suspected security
vulnerabilities. Email security concerns to the maintainer (see
[SECURITY.md](../SECURITY.md) at the repo root) and include:

- A description of the vulnerability
- Steps to reproduce
- The version of GOLEM affected
- The platform (Windows / macOS / Linux)

We aim to acknowledge new reports within 5 business days and to
publish a fix within 30 days for high-severity issues.
