#!/usr/bin/env python3
"""Reproducibly build and apply the complete local workflow."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
from install import install, installation_lock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', help='Archive folder; defaults to ~/Documents/Books on first install.')
    parser.add_argument('--mode', choices=['auto', 'review'], help='Defaults to auto on first install.')
    parser.add_argument('--no-open', action='store_true', help='Build and apply without opening setup windows.')
    args = parser.parse_args()
    if sys.platform != 'darwin': parser.error('macOS is required.')
    if args.destination and not os.path.expanduser(args.destination).startswith('/'):
        parser.error('Destination must be an absolute path (or ~/path).')
    root = Path(__file__).resolve().parents[1]
    support = Path.home()/'Library/Application Support/Book to Kindle Shortcut'
    shortcut = root/'dist/Book to Kindle.shortcut'
    try:
        # Covers build, signing, app replacement, and settings; the sender uses this lock too.
        with installation_lock(support):
            subprocess.run([str(root/'scripts/build.sh')], check=True)
            unsigned = root/'build/Book to Kindle.unsigned.shortcut'
            subprocess.run(['/usr/bin/python3', str(root/'scripts/generate_shortcut.py'), str(unsigned)], check=True)
            shortcut.parent.mkdir(parents=True, exist_ok=True)
            print('Signing the shortcut with Apple (requires internet)…', flush=True)
            subprocess.run(['/usr/bin/shortcuts', 'sign', '--mode', 'anyone', '--input', str(unsigned), '--output', str(shortcut)], check=True)
            app, config = install(root/'build/BookToKindle.zip', Path.home(), args.destination, args.mode, locked=True)
        print('Installed:', app)
        print('Archive folder:', config['destination'])
        print('Sending mode:', config['mode'])
        print('Generated shortcut:', shortcut)
        print('Approve Add Shortcut (or Replace) when Shortcuts opens.')
        print('Enable Shortcuts → Settings → Advanced → Allow Running Scripts.')
        print('Enable Book to Kindle in Privacy & Security → Accessibility.')
        print('Optional hotkey: Shortcut Details → Add Keyboard Shortcut (suggested Control–Option–K).')
        if not args.no_open:
            subprocess.run(['/usr/bin/open', str(shortcut)], check=True)
            subprocess.run(['/usr/bin/open', str(app)], check=True)
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print('Setup failed: ' + str(error), file=sys.stderr)
        return 1

if __name__ == '__main__': sys.exit(main())
