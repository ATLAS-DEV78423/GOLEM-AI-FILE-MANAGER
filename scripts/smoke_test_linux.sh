#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

WORKDIR="$(mktemp -d)"
echo "Extracting artifact to $WORKDIR"
tar -xzf dist/GOLEM-linux.tar.gz -C "$WORKDIR"

# Find likely executable
EXE="$(find "$WORKDIR" -type f -perm /u+x,g+x,o+x -maxdepth 4 -name 'GOLEM' -print -quit || true)"
if [[ -z "$EXE" ]]; then
  EXE="$(find "$WORKDIR" -type f -perm /u+x,g+x,o+x -maxdepth 4 -print -quit)"
fi

if [[ -z "$EXE" ]]; then
  echo "No executable found in artifact" >&2
  exit 2
fi

echo "Found executable: $EXE"

# Run under X virtual framebuffer for a few seconds to ensure UI starts
if command -v xvfb-run >/dev/null 2>&1; then
  xvfb-run --auto-servernum --server-args='-screen 0 1280x720x24' bash -c "\
    timeout 15 \"$EXE\" & sleep 6; pkill -f \"$EXE\" || true\" || true
else
  # Try to run headless if xvfb not available; still perform timeout
  timeout 15 "$EXE" & sleep 6; pkill -f "$EXE" || true
fi

echo "Smoke run complete"
