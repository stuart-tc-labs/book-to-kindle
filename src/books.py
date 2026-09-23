#!/usr/bin/env python3
"""Prepare a bounded, byte-preserving EPUB snapshot and a verified archive."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import stat
import sys
import subprocess
import tempfile
import unicodedata
import uuid
import xml.etree.ElementTree as ET
import zipfile

DC = 'http://purl.org/dc/elements/1.1/'
OPF = 'http://www.idpf.org/2007/opf'
TAG = 'com.apple.metadata:_kMDItemUserTags'
MAX_FILE_BYTES = 200 * 1024 * 1024
MAX_EXPANDED_BYTES = 512 * 1024 * 1024
MAX_ENTRIES = 10000
CHUNK = 1024 * 1024


def clean(value):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', value or '')).strip()


def person(value):
    value = clean(value)
    if value.count(',') == 1 and not re.search(r'\b(and|Jr|Sr)\b|&|;', value):
        family, given = [part.strip() for part in value.split(',')]
        if family and given:
            return given + ' ' + family
    return value


def filename(value, limit=210):
    value = clean(re.sub(r'[/\\:\x00-\x1f]', ' - ', value)).strip('. ')
    while len(value.encode('utf-8')) > limit:
        value = value[:-1]
    if not value:
        raise ValueError('The book has no usable title or author.')
    return value


def digest(path):
    hasher = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(CHUNK), b''):
            hasher.update(block)
    return hasher.hexdigest()


def identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def metadata(path):
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_ENTRIES:
            raise ValueError('EPUB has too many ZIP entries (limit 10,000).')
        if len({entry.filename for entry in entries}) != len(entries):
            raise ValueError('EPUB contains ambiguous duplicate ZIP entries.')
        if sum(entry.file_size for entry in entries) > MAX_EXPANDED_BYTES:
            raise ValueError('EPUB exceeds the 512 MiB expanded-size limit.')
        if any(entry.flag_bits & 1 for entry in entries):
            raise ValueError('Encrypted ZIP entries are not supported.')

        def xml(name, limit):
            if archive.getinfo(name).file_size > limit:
                raise ValueError('EPUB metadata exceeds its size limit.')
            raw = archive.read(name)
            if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
                raise ValueError('Unsupported EPUB XML declarations.')
            return ET.fromstring(raw)

        container = xml('META-INF/container.xml', 1024 * 1024)
        item = container.find('.//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile')
        if item is None or not item.get('full-path'):
            raise ValueError('No EPUB package was found.')
        root = xml(item.get('full-path'), 4 * 1024 * 1024)
        meta = root.find('{%s}metadata' % OPF)
        if meta is None:
            raise ValueError('No EPUB metadata was found.')
        titles = meta.findall('{%s}title' % DC)
        title = clean(''.join(titles[0].itertext())) if titles else ''
        refinements = meta.findall('{%s}meta' % OPF)
        for ref in refinements:
            if ref.get('property') == 'title-type' and clean(ref.text) == 'main':
                for node in titles:
                    if node.get('id') and '#' + node.get('id') == ref.get('refines'):
                        title = clean(''.join(node.itertext()))
        authors = []
        for creator in meta.findall('{%s}creator' % DC):
            role = creator.get('{%s}role' % OPF, '')
            for ref in refinements:
                if creator.get('id') and ref.get('refines') == '#' + creator.get('id') and ref.get('property') == 'role':
                    role = clean(ref.text)
            if role and role not in ('aut', 'author'):
                continue
            author = person(''.join(creator.itertext()))
            if author and author not in authors:
                authors.append(author)
        if not title or not authors:
            raise ValueError('This EPUB is missing its title or author. Correct its metadata first.')
        # testzip streams members and checks CRCs; expansion is capped above.
        if archive.testzip():
            raise ValueError('EPUB failed its ZIP integrity check.')
        return {'title': title, 'author': ' & '.join(authors)}


def xattr_names(path):
    return subprocess.check_output(['/usr/bin/xattr', str(path)], text=True).splitlines()


def xattr_read(path, name):
    return bytes.fromhex(subprocess.check_output(['/usr/bin/xattr', '-px', name, str(path)], text=True))


def xattr_write(path, name, value):
    subprocess.run(['/usr/bin/xattr', '-wx', name, value.hex(), str(path)], check=True, capture_output=True)


def add_yellow(path):
    if sys.platform != 'darwin':
        return
    tags = []
    if TAG in xattr_names(path):
        tags = plistlib.loads(xattr_read(path, TAG))
        if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
            raise ValueError('Malformed Finder tags; the source was not removed.')
    tags = [tag for tag in tags if tag.split('\n')[0].casefold() != 'yellow']
    tags.append('Yellow\n5')
    xattr_write(path, TAG, plistlib.dumps(tags, fmt=plistlib.FMT_BINARY))


def verify_source(source, original, expected_digest):
    """Do not remove a download that was changed or replaced during processing."""
    if identity(source.lstat()) != identity(original) or digest(source) != expected_digest:
        raise ValueError('The source changed during processing. It was not removed; the archive snapshot was retained.')
    if identity(source.lstat()) != identity(original):
        raise ValueError('The source changed during processing. It was not removed.')


def copy_attributes(source, target):
    if sys.platform == 'darwin':
        # copyfile.h: COPYFILE_METADATA copies stat, ACLs, and extended attributes,
        # without replacing snapshot bytes. Never follow either path as a symlink.
        libc = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
        copyfile = libc.copyfile
        copyfile.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_uint32]
        copyfile.restype = ctypes.c_int
        if copyfile(os.fsencode(source), os.fsencode(target), None, 7 | (1 << 18) | (1 << 19)) != 0:
            code = ctypes.get_errno()
            raise OSError(code, os.strerror(code))
    else:
        shutil.copystat(source, target, follow_symlinks=False)


def prepare(source, destination, cache):
    source = Path(source).absolute()
    destination, cache = Path(destination).expanduser().resolve(), Path(cache).expanduser().resolve()
    original = source.lstat()
    if not stat.S_ISREG(original.st_mode) or source.suffix.lower() != '.epub':
        raise ValueError('Select one regular EPUB file. Symbolic links and other formats are not supported.')
    if original.st_size > MAX_FILE_BYTES:
        raise ValueError('EPUB exceeds the 200 MiB file-size limit.')
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    folder = Path(tempfile.mkdtemp(prefix='book-', dir=str(cache)))
    snapshot = folder/'snapshot.epub'
    archived = None
    try:
        fd = os.open(str(source), os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as incoming, snapshot.open('xb') as outgoing:
            if identity(os.fstat(incoming.fileno())) != identity(original):
                raise ValueError('The source changed before copying. Nothing was moved.')
            total = 0
            for block in iter(lambda: incoming.read(CHUNK), b''):
                total += len(block)
                if total > MAX_FILE_BYTES:
                    raise ValueError('EPUB exceeds the file-size limit while copying.')
                outgoing.write(block)
            outgoing.flush(); os.fsync(outgoing.fileno())
        info = metadata(snapshot)
        checksum = digest(snapshot)
        verify_source(source, original, checksum)
        copy_attributes(source, snapshot)
        # Share copies must remain writable so they can be cleaned up afterwards.
        snapshot.chmod(0o600)
        destination.mkdir(parents=True, exist_ok=True)
        stem = filename(info['title'] + ' — ' + info['author'])
        for number in range(1, 10001):
            suffix = '' if number == 1 else ' (%d)' % number
            target = destination/(stem + suffix + '.epub')
            if target.exists() or target.is_symlink():
                if source == target and target.is_file() and not target.is_symlink():
                    archived = target
                    add_yellow(target)
                    break
                continue
            # Publish a complete file atomically; linking never replaces a collision.
            fd, temp_name = tempfile.mkstemp(prefix='.book-to-kindle-', dir=str(destination))
            temp_path = Path(temp_name)
            try:
                with os.fdopen(fd, 'wb') as out, snapshot.open('rb') as incoming:
                    shutil.copyfileobj(incoming, out, CHUNK)
                    out.flush(); os.fsync(out.fileno())
                copy_attributes(source, temp_path)
                add_yellow(temp_path)
                if digest(temp_path) != checksum:
                    raise ValueError('Archive verification failed. The source was not removed.')
                try:
                    os.link(str(temp_path), str(target))
                except FileExistsError:
                    continue
                archived = target
                break
            finally:
                temp_path.unlink(missing_ok=True)
        if archived is None:
            raise ValueError('Too many files with the same title. Nothing was removed.')
        # Tagging an already archived original changes its ctime; do not remove it.
        if source != archived:
            verify_source(source, original, checksum)
            source.unlink()
        token = uuid.uuid4().hex
        staged = folder/(filename(info['title'], 180) + ' [btk-' + token[:12] + '].epub')
        snapshot.rename(staged)
        return dict(info, id=token, archive=str(archived), send=str(staged),
                    expectedFilename=staged.name, sha256=checksum)
    except Exception:
        shutil.rmtree(folder)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(args.source, args.destination, args.cache), ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError, zipfile.BadZipFile, ET.ParseError, plistlib.InvalidFileException, subprocess.CalledProcessError) as error:
        print('Book to Kindle: ' + str(error), file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
