#!/usr/bin/env python3
"""Apply an already-built bundle under the same lock used by the sender."""
import argparse
from contextlib import contextmanager, nullcontext
import fcntl
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile
import uuid

BUNDLE_ID = 'io.github.book-to-kindle.helper'


def bundle_id(path):
    with (path/'Contents/Info.plist').open('rb') as stream:
        return plistlib.load(stream).get('CFBundleIdentifier')


@contextmanager
def installation_lock(support):
    support.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (support/'send.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Book to Kindle is running or another installer is applying. Close it and try again.')
        yield


def install(bundle_zip, home, destination=None, mode=None, locked=False):
    support = home/'Library/Application Support/Book to Kindle Shortcut'
    applications = home/'Applications'
    support.mkdir(parents=True, exist_ok=True, mode=0o700)
    applications.mkdir(parents=True, exist_ok=True)
    app = applications/'Book to Kindle.app'
    config_path = support/'config.json'
    with (nullcontext() if locked else installation_lock(support)):
        config = {'destination': '~/Documents/Books', 'mode': 'auto'}
        if config_path.exists():
            config.update(json.loads(config_path.read_text()))
        if destination:
            config['destination'] = os.path.expanduser(destination)
        if mode:
            config['mode'] = mode
        if config.get('mode') not in ('auto', 'review') or not os.path.expanduser(config.get('destination', '')).startswith('/'):
            raise ValueError('Invalid settings. Use an absolute destination and auto or review mode.')
        if app.exists() and bundle_id(app) != BUNDLE_ID:
            raise ValueError('Refusing to replace an unrelated Book to Kindle.app.')
        # Stage on the same filesystem as the final app; rename publishes a complete bundle.
        stage = Path(tempfile.mkdtemp(prefix='.book-to-kindle-', dir=str(applications)))
        backup = support/('Previous-' + uuid.uuid4().hex + '.app')
        try:
            subprocess.run(['/usr/bin/ditto', '-x', '-k', str(bundle_zip), str(stage)], check=True)
            replacement = stage/'Book to Kindle.app'
            if bundle_id(replacement) != BUNDLE_ID:
                raise ValueError('Unexpected bundle identifier in the build artifact.')
            subprocess.run(['/usr/bin/codesign', '--verify', '--strict', str(replacement)], check=True)
            config_temp = stage/'config.json'
            config_temp.write_text(json.dumps(config, indent=2) + '\n')
            old_config = config_path.read_bytes() if config_path.exists() else None
            moved_old = False
            try:
                if app.exists():
                    app.rename(backup); moved_old = True
                replacement.rename(app)
                config_temp.replace(config_path)
            except BaseException:
                if app.exists():
                    app.rename(stage/'failed.app')
                if moved_old:
                    backup.rename(app)
                if old_config is None:
                    config_path.unlink(missing_ok=True)
                else:
                    config_path.write_bytes(old_config)
                raise
        finally:
            shutil.rmtree(stage)
        return app, config


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--destination')
    parser.add_argument('--mode', choices=['auto', 'review'])
    args = parser.parse_args()
    try:
        app, config = install(args.bundle, Path.home(), args.destination, args.mode)
        print('Installed:', app)
        print('Archive folder:', config['destination'])
        print('Sending mode:', config['mode'])
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + '\n')
