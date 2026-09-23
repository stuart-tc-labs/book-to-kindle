#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ "$(uname -s)" != Darwin ]]; then echo 'Setup requires macOS.' >&2; exit 1; fi
if ! /usr/bin/xcrun --find swiftc >/dev/null 2>&1 || ! /usr/bin/python3 --version >/dev/null 2>&1; then
  echo 'Install Apple Command Line Tools with: xcode-select --install' >&2
  exit 1
fi
exec /usr/bin/python3 "$ROOT/scripts/apply.py" "$@"
