import importlib.util
import os
from pathlib import Path
import plistlib
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

class BooksTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((ROOT/'src/books.py').exists(), 'Public book processor is missing')
        import books
        self.books = books
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root/'Books'
        self.cache = self.root/'cache'

    def epub(self, name='messy.epub', title='A Book: A Story', author='Doe, Jane', body=b'original content'):
        path = self.root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr('mimetype', 'application/epub+zip', compress_type=zipfile.ZIP_STORED)
            z.writestr('META-INF/container.xml', '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="content.opf"/></rootfiles></container>')
            z.writestr('content.opf', '<package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/"><metadata><dc:title>'+title+'</dc:title><dc:creator opf:role="aut" xmlns:opf="http://www.idpf.org/2007/opf">'+author+'</dc:creator><dc:creator opf:role="trl" xmlns:opf="http://www.idpf.org/2007/opf">Other Translator</dc:creator></metadata></package>')
            z.writestr('chapter.xhtml', body)
        return path

    def prepare(self, path):
        return self.books.prepare(path, self.archive, self.cache)

    def test_preserves_bytes_and_cleans_metadata(self):
        source = self.epub(); before = source.read_bytes()
        if sys.platform == 'darwin':
            self.books.xattr_write(source, 'test.book-to-kindle', b'keep')
        result = self.prepare(source)
        self.assertFalse(source.exists())
        self.assertEqual(Path(result['archive']).name, 'A Book - A Story — Jane Doe.epub')
        self.assertEqual(Path(result['archive']).read_bytes(), before)
        self.assertEqual(Path(result['send']).read_bytes(), before)
        self.assertEqual(result['title'], 'A Book: A Story')
        self.assertEqual(result['author'], 'Jane Doe')
        self.assertIn('[btk-', result['expectedFilename'])
        if sys.platform == 'darwin':
            self.assertEqual(self.books.xattr_read(result['archive'], 'test.book-to-kindle'), b'keep')
            self.assertIn('Yellow\n5', plistlib.loads(self.books.xattr_read(result['archive'], self.books.TAG)))

    def test_replaced_source_is_never_deleted(self):
        source = self.epub(); replacement = b'new download must survive'
        real = self.books.add_yellow
        def replace_then_tag(path):
            source.unlink(); source.write_bytes(replacement); real(path)
        with patch.object(self.books, 'add_yellow', side_effect=replace_then_tag):
            with self.assertRaisesRegex(ValueError, 'changed'):
                self.prepare(source)
        self.assertEqual(source.read_bytes(), replacement)

    def test_modified_source_is_never_deleted(self):
        source = self.epub(); real = self.books.add_yellow
        def modify_then_tag(path):
            with source.open('ab') as f: f.write(b'modified')
            real(path)
        with patch.object(self.books, 'add_yellow', side_effect=modify_then_tag):
            with self.assertRaisesRegex(ValueError, 'changed'): self.prepare(source)
        self.assertTrue(source.read_bytes().endswith(b'modified'))

    def test_tag_failure_keeps_source(self):
        source = self.epub(); before = source.read_bytes()
        with patch.object(self.books, 'add_yellow', side_effect=OSError('tag failed')):
            with self.assertRaises(OSError): self.prepare(source)
        self.assertEqual(source.read_bytes(), before)

    def test_archive_file_is_also_renamed(self):
        result = self.prepare(self.epub('Books/download mess.epub'))
        self.assertEqual(Path(result['archive']).name, 'A Book - A Story — Jane Doe.epub')
        self.assertFalse((self.archive/'download mess.epub').exists())

    def test_collisions_do_not_overwrite(self):
        first = self.prepare(self.epub())
        before = Path(first['archive']).read_bytes()
        second = self.prepare(self.epub(body=b'different edition'))
        self.assertNotEqual(first['archive'], second['archive'])
        self.assertEqual(Path(first['archive']).read_bytes(), before)

    def test_selecting_clean_archived_book_does_not_duplicate_it(self):
        first = self.prepare(self.epub())
        second = self.prepare(Path(first['archive']))
        self.assertEqual(first['archive'], second['archive'])
        self.assertEqual(len(list(self.archive.glob('*.epub'))), 1)

    @unittest.skipUnless(sys.platform == 'darwin', 'Finder attributes require macOS')
    def test_same_bytes_with_different_attributes_are_not_deduplicated(self):
        source = self.epub(); before = source.read_bytes(); first = self.prepare(source)
        source.write_bytes(before)
        self.books.xattr_write(source, 'test.book-to-kindle', b'new metadata')
        second = self.prepare(source)
        self.assertNotEqual(first['archive'], second['archive'])
        self.assertEqual(self.books.xattr_read(second['archive'], 'test.book-to-kindle'), b'new metadata')

    def test_missing_metadata_leaves_source(self):
        source = self.epub(author='')
        with self.assertRaises(ValueError): self.prepare(source)
        self.assertTrue(source.exists())
        self.assertFalse(self.archive.exists())

    def test_expansion_limit_leaves_source(self):
        source = self.epub(body=b'x'*10000)
        with patch.object(self.books, 'MAX_EXPANDED_BYTES', 5000):
            with self.assertRaisesRegex(ValueError, 'expanded'): self.prepare(source)
        self.assertTrue(source.exists())

    def test_symlink_is_rejected(self):
        source = self.epub(); link = self.root/'link.epub'; link.symlink_to(source)
        with self.assertRaises(ValueError): self.prepare(link)
        self.assertTrue(source.exists()); self.assertTrue(link.is_symlink())

    def test_unicode_filename_stays_within_filesystem_limit(self):
        result = self.prepare(self.epub(title='本'*200))
        self.assertLessEqual(len(Path(result['archive']).name.encode()), 255)
        self.assertLessEqual(len(result['expectedFilename'].encode()), 255)

if __name__ == '__main__': unittest.main()
