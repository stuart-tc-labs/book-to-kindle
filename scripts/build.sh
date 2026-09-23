#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ "$(uname -s)" != Darwin ]]; then echo 'Build requires macOS.' >&2; exit 1; fi
if ! /usr/bin/xcrun --find swiftc >/dev/null 2>&1 || ! /usr/bin/python3 --version >/dev/null 2>&1; then
  echo 'Install Apple Command Line Tools with: xcode-select --install' >&2
  exit 1
fi
STAGE="$(mktemp -d "${TMPDIR:-/tmp}/book-to-kindle-build.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT
APP="$STAGE/Book to Kindle.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
/usr/bin/xcrun swiftc -O -target "$(uname -m)-apple-macosx13.0" \
  "$ROOT/src/SendJob.swift" "$ROOT/src/Accessibility.swift" "$ROOT/src/App.swift" \
  -o "$APP/Contents/MacOS/BookToKindle"
cp "$ROOT/src/books.py" "$APP/Contents/Resources/books.py"
/usr/bin/python3 - "$APP/Contents/Info.plist" <<'PY'
import plistlib, sys
from pathlib import Path
Path(sys.argv[1]).write_bytes(plistlib.dumps({
 'CFBundleExecutable':'BookToKindle',
 'CFBundleIdentifier':'io.github.book-to-kindle.helper',
 'CFBundleName':'Book to Kindle',
 'CFBundleDisplayName':'Book to Kindle',
 'CFBundlePackageType':'APPL',
 'CFBundleVersion':'1',
 'CFBundleShortVersionString':'0.1.0',
 'LSMinimumSystemVersion':'13.0',
 'NSPrincipalClass':'NSApplication',
 'NSHighResolutionCapable':True,
}))
PY
# Generated files in a synced folder may inherit FinderInfo, which codesign rejects.
# This only clears metadata on our generated app; it does not alter system policy.
/usr/bin/xattr -cr "$APP"
/usr/bin/codesign --force --sign - "$APP"
/usr/bin/codesign --verify --strict "$APP"
mkdir -p "$ROOT/build"
/usr/bin/ditto -c -k --norsrc --keepParent "$APP" "$ROOT/build/BookToKindle.zip"
printf 'Built %s\n' "$ROOT/build/BookToKindle.zip"
