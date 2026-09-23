import json
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import generate_shortcut
import install

class ShortcutTests(unittest.TestCase):
    def test_generated_launcher_is_portable_and_accepts_file_paths(self):
        flow = generate_shortcut.workflow()
        self.assertEqual(flow['WFQuickActionSurfaces'], ['Finder', 'Services'])
        self.assertEqual(flow['WFWorkflowInputContentItemClasses'], ['WFGenericFileContentItem'])
        self.assertEqual(len(flow['WFWorkflowActions']), 1)
        parameters = flow['WFWorkflowActions'][0]['WFWorkflowActionParameters']
        self.assertEqual(parameters['InputMode'], 'as arguments')
        self.assertEqual(parameters['Input']['Value']['Aggrandizements'][0]['PropertyName'], 'File Path')
        script = parameters['Script']
        self.assertIn('--file "$1"', script)
        self.assertNotIn('/Users/', script)
        self.assertNotIn('/opt/homebrew', script)
        self.assertNotIn('WFFile', flow)
        subprocess.run(['/bin/zsh', '-n'], input=script, text=True, check=True)
        self.assertEqual(plistlib.loads(plistlib.dumps(flow)), flow)

@unittest.skipUnless(sys.platform == 'darwin', 'Installer requires macOS')
class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.support = self.home/'Library/Application Support/Book to Kindle Shortcut'
        self.bundle = ROOT/'build/BookToKindle.zip'
        self.assertTrue(self.bundle.exists(), 'Run scripts/test.sh to build the test bundle first.')

    def test_install_and_reapply_preserves_configuration(self):
        app, config = install.install(self.bundle, self.home, '/tmp/Books with spaces', 'review')
        self.assertEqual(install.bundle_id(app), install.BUNDLE_ID)
        _, reapplied = install.install(self.bundle, self.home)
        self.assertEqual(config, reapplied)
        self.assertEqual(len(list((self.home/'Applications/.Book to Kindle Backups').glob('Previous-*.app'))), 1)

    def test_shared_lock_rejects_another_installer(self):
        with install.installation_lock(self.support):
            with self.assertRaisesRegex(ValueError, 'running'):
                install.install(self.bundle, self.home)
        self.assertFalse((self.home/'Applications/Book to Kindle.app').exists())

    def test_failed_publish_restores_previous_app(self):
        app, before = install.install(self.bundle, self.home)
        rename = Path.rename
        def injected(path, target):
            if path.name == 'Book to Kindle.app' and path.parent.name.startswith('.book-to-kindle-'):
                raise OSError('Injected failure before publishing replacement')
            return rename(path, target)
        with patch.object(Path, 'rename', injected):
            with self.assertRaisesRegex(OSError, 'Injected'):
                install.install(self.bundle, self.home, '/tmp/Changed')
        self.assertEqual(install.bundle_id(app), install.BUNDLE_ID)
        self.assertEqual(json.loads((self.support/'config.json').read_text()), before)

    def test_failure_moving_original_never_removes_it(self):
        app, before = install.install(self.bundle, self.home)
        original = (app/'Contents/MacOS/BookToKindle').read_bytes()
        rename = Path.rename
        def injected(path, target):
            if path == app and Path(target).name.startswith('Previous-'):
                raise OSError('Injected failure moving original')
            return rename(path, target)
        with patch.object(Path, 'rename', injected):
            with self.assertRaisesRegex(OSError, 'Injected'):
                install.install(self.bundle, self.home)
        self.assertEqual((app/'Contents/MacOS/BookToKindle').read_bytes(), original)
        self.assertEqual(json.loads((self.support/'config.json').read_text()), before)

    def test_invalid_config_cannot_replace_app(self):
        app, _ = install.install(self.bundle, self.home)
        with self.assertRaises(ValueError): install.install(self.bundle, self.home, 'relative/path')
        self.assertEqual(install.bundle_id(app), install.BUNDLE_ID)

    def test_unknown_app_is_never_replaced(self):
        app = self.home/'Applications/Book to Kindle.app'
        (app/'Contents').mkdir(parents=True)
        (app/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'unrelated.app'}))
        with self.assertRaisesRegex(ValueError, 'unrelated'): install.install(self.bundle, self.home)
        self.assertEqual(install.bundle_id(app), 'unrelated.app')
