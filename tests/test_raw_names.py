"""
Tests for exact archive member names
====================================

Author, Copyright, and License
------------------------------

Copyright (c) 2022-2026 Hauke Dämpfling (haukex@zero-g.net)
at the Leibniz Institute of Freshwater Ecology and Inland Fisheries (IGB),
Berlin, Germany, https://www.igb-berlin.de/

This library is free software: you can redistribute it and/or modify it under
the terms of the GNU Lesser General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your option) any
later version.

This library is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public License for more
details.

You should have received a copy of the GNU Lesser General Public License
along with this program. If not, see https://www.gnu.org/licenses/
"""
import os
import io
import unittest
from contextlib import ExitStack
from tarfile import TarFile, TarInfo
from zipfile import ZipFile, ZipInfo
from tempfile import TemporaryDirectory
from bz2 import compress as bz2_compress
from gzip import compress as gzip_compress
from lzma import compress as lzma_compress
from pathlib import Path, PurePosixPath, PurePath, PureWindowsPath
from unzipwalk import FileType
import unzipwalk as uut

# spell: ignore fspath noname

class LiteralArchiveName(os.PathLike[str]):
    def __init__(self, name :str) -> None:
        self._name = name
    def __fspath__(self) -> str:
        return self._name

class TestRawNames(unittest.TestCase):

    def test_raw_member_names(self) -> None:
        with TemporaryDirectory() as td:
            for ext in ('zip', 'tar', '7z'):
                with self.subTest(ext=ext):
                    fn = Path(td)/f"archive.{ext}"
                    if ext=='zip':
                        with ZipFile(fn, 'w') as zf:
                            zf.writestr('./file.txt', b'dotted')
                            zf.writestr('file.txt', b'first')
                            with self.assertWarnsRegex(UserWarning, 'Duplicate name'):
                                zf.writestr('file.txt', b'second')
                            zf.writestr('../file.txt', b'parent')
                            zf.writestr('C:/dir/file.txt', b'drive')
                    elif ext=='tar':
                        with TarFile.open(fn, 'w') as tf:
                            for name, data in (('./file.txt', b'dotted'), ('file.txt', b'first'), ('file.txt', b'second'),
                                    ('../file.txt', b'parent'), ('C:/dir/file.txt', b'drive')):
                                ti = TarInfo(name)
                                ti.size = len(data)
                                tf.addfile(ti, io.BytesIO(data))
                    else:
                        fn.write_bytes((Path(__file__).parent/'raw_names.7z').read_bytes())
                    found :list[tuple[tuple[PurePath, ...], tuple[str, ...], bytes]] = []
                    for result in uut.unzipwalk(fn):
                        if result.typ==FileType.FILE:
                            assert result.hnd is not None
                            data = result.hnd.read()
                            found.append((result.names, result.raw_names, data))
                    self.assertCountEqual(found, [
                        ((fn, PurePosixPath('file.txt')), (str(fn), './file.txt'), b'dotted'),
                        ((fn, PurePosixPath('file.txt')), (str(fn), 'file.txt'), b'first'),
                        ((fn, PurePosixPath('file.txt')), (str(fn), 'file.txt'), b'second'),
                        ((fn, PurePosixPath('../file.txt')), (str(fn), '../file.txt'), b'parent'),
                        ((fn, PurePosixPath('C:/dir/file.txt')), (str(fn), 'C:/dir/file.txt'), b'drive') ])
                    self.assertCountEqual([(r.raw_names, r.typ, r.hnd.read() if r.hnd is not None else None)
                        for r in uut.unzipwalk(fn, matcher=lambda names: names[-1]!='./file.txt')], [
                        ((str(fn), './file.txt'), FileType.SKIP, None),
                        ((str(fn), 'file.txt'), FileType.FILE, b'first'),
                        ((str(fn), 'file.txt'), FileType.FILE, b'second'),
                        ((str(fn), '../file.txt'), FileType.FILE, b'parent'),
                        ((str(fn), 'C:/dir/file.txt'), FileType.FILE, b'drive'),
                        ((str(fn),), FileType.ARCHIVE, None) ])
                    for name, data in (('./file.txt', b'dotted'), ('../file.txt', b'parent'), ('C:/dir/file.txt', b'drive')):
                        with self.subTest(member=name):
                            with uut.recursive_open((fn, name)) as fh:
                                self.assertEqual(fh.read(), data)
                    if ext!='7z':
                        with self.assertRaises(KeyError), ExitStack() as stack:
                            stack.enter_context(uut.recursive_open((fn, 'missing.txt')))
                    for member in ('file.txt', PurePosixPath('./file.txt')):
                        if ext=='7z':
                            with self.assertRaises(FileExistsError), ExitStack() as stack:
                                stack.enter_context(uut.recursive_open((fn, member)))
                        else:
                            with uut.recursive_open((fn, member)) as fh:
                                self.assertIn(fh.read(), (b'first', b'second'))

    def test_raw_nested_names(self) -> None:
        with TemporaryDirectory() as td:
            for ext, compress in (('gz', gzip_compress), ('bz2', bz2_compress), ('xz', lzma_compress)):
                with self.subTest(ext=ext):
                    fn = Path(td)/'archive.zip'
                    with io.BytesIO() as inner:
                        with ZipFile(inner, 'w') as zf:
                            zf.writestr(f"./dir//file.txt.{ext}", compress(b'nested contents'))
                        with ZipFile(fn, 'w') as zf:
                            zf.writestr('./nested//inner.zip', inner.getvalue())
                            # ZipInfo construction normalizes backslashes on Windows; set the stored spelling explicitly.
                            zi = ZipInfo('dir/literal.txt')
                            zi.filename = 'dir\\literal.txt'
                            zi.orig_filename = zi.filename
                            zf.writestr(zi, b'literal backslash')
                    for result in uut.unzipwalk(fn):
                        self.assertEqual(len(result.raw_names), len(result.names))
                        if result.typ==FileType.FILE:
                            assert result.hnd is not None
                            data = result.hnd.read()
                            with uut.recursive_open(result.raw_names) as fh:
                                self.assertEqual(fh.read(), data)
                            if len(result.names)==4:
                                self.assertEqual(result.raw_names,
                                    (str(fn), './nested//inner.zip', f"./dir//file.txt.{ext}", './dir//file.txt'))
                                self.assertEqual(data, b'nested contents')
                    skipped = list(uut.unzipwalk(fn, matcher=lambda p: not p[-1].endswith('.zip') or len(p)==1))
                    self.assertCountEqual([(r.raw_names, r.typ) for r in skipped], [
                        ((str(fn), './nested//inner.zip'), FileType.SKIP),
                        ((str(fn), 'dir\\literal.txt'), FileType.FILE),
                        ((str(fn),), FileType.ARCHIVE) ])

    def test_raw_7z_skipped_duplicate(self) -> None:
        fn = Path(__file__).parent/'raw_names.7z'
        matches = iter((True, True, False, True, True, True))
        found :list[tuple[tuple[str, ...], FileType, bytes|None]] = []
        for result in uut.unzipwalk(fn, matcher=lambda _p: next(matches)):
            found.append((result.raw_names, result.typ, result.hnd.read() if result.hnd is not None else None))
        self.assertCountEqual(found, [
            ((str(fn), './file.txt'), FileType.FILE, b'dotted'),
            ((str(fn), 'file.txt'), FileType.SKIP, None),
            ((str(fn), 'file.txt'), FileType.FILE, b'second'),
            ((str(fn), '../file.txt'), FileType.FILE, b'parent'),
            ((str(fn), 'C:/dir/file.txt'), FileType.FILE, b'drive'),
            ((str(fn),), FileType.ARCHIVE, None) ])

    def test_tar_literal_trailing_slash(self) -> None:
        with TemporaryDirectory() as td:
            fn = Path(td)/'archive.tar'
            with TarFile.open(fn, 'w') as tf:
                for name, data in (('file.txt/', b'slashed'), ('file.txt', b'plain')):
                    ti = TarInfo(name)
                    ti.size = len(data)
                    tf.addfile(ti, io.BytesIO(data))
            for result in uut.unzipwalk(fn):
                if result.typ==FileType.FILE:
                    assert result.hnd is not None
                    data = result.hnd.read()
                    with uut.recursive_open(result.raw_names) as fh:
                        self.assertEqual(fh.read(), data)
            with uut.recursive_open((fn, 'file.txt/')) as fh:
                self.assertEqual(fh.read(), b'slashed')

    def test_raw_format_detection(self) -> None:
        with TemporaryDirectory() as td:
            fn = Path(td)/'archive.tar'
            members = tuple(f"./dir//file.{ext}{ending}"
                for ext in ('zip', 'tar', 'tgz', '7z', 'gz', 'bz2', 'xz') for ending in ('/', '/.', '//'))
            with TarFile.open(fn, 'w') as tf:
                for name in members:
                    ti = TarInfo(name)
                    ti.size = 5
                    tf.addfile(ti, io.BytesIO(b'plain'))
            self.assertCountEqual([(r.raw_names, r.typ, r.hnd.read() if r.hnd is not None else None) for r in uut.unzipwalk(fn)],
                [((str(fn), name), FileType.FILE, b'plain') for name in members] + [((str(fn),), FileType.ARCHIVE, None)])
            for name in members:
                with self.subTest(name=name):
                    with uut.recursive_open((fn, name)) as fh:
                        self.assertEqual(fh.read(), b'plain')
                    # A suffix followed by a separator or dot component does not denote a nested archive.
                    with self.assertRaises(ValueError), ExitStack() as stack:
                        stack.enter_context(uut.recursive_open((fn, name, 'child.txt')))

    def test_archive_pathlike_arguments(self) -> None:
        cases :tuple[tuple[os.PathLike[str], str], ...] = (
            (PureWindowsPath('C:/dir/file.txt'), 'C:/dir/file.txt'),
            (PureWindowsPath('//server/share/dir/file.txt'), '//server/share/dir/file.txt'),
            (PurePosixPath('dir/file.txt'), 'dir/file.txt'),
            (LiteralArchiveName('./dir//file.txt'), './dir//file.txt'),
            (LiteralArchiveName(r'dir\literal.txt'), r'dir\literal.txt') )
        with TemporaryDirectory() as td:
            fn = Path(td)/'archive.zip'
            with ZipFile(fn, 'w') as zf:
                for _, name in cases:
                    # Set the stored spelling explicitly so ZIP creation does not rewrite Windows separators.
                    zi = ZipInfo('file.txt')
                    zi.filename = name
                    zi.orig_filename = name
                    zf.writestr(zi, name.encode('UTF-8'))
            for member, name in cases:
                with self.subTest(name=name):
                    with uut.recursive_open((fn, member)) as fh:
                        self.assertEqual(fh.read(), name.encode('UTF-8'))

    def test_raw_compression_suffixes(self) -> None:
        with TemporaryDirectory() as td:
            fn = Path(td)/'archive.tar'
            for ext, compress in (('gz', gzip_compress), ('bz2', bz2_compress), ('xz', lzma_compress)):
                with self.subTest(ext=ext):
                    members = ((f"./dir//file.txt.{ext.upper()}", './dir//file.txt'),
                        (f"dir\\.{ext}", 'dir\\'), (f"..{ext}", '.'), (f".{ext}", 'noname'),
                        (f"./dir//.{ext.upper()}", './dir//noname'))
                    data = compress(b'contents')
                    with TarFile.open(fn, 'w') as tf:
                        for name, _ in members:
                            ti = TarInfo(name)
                            ti.size = len(data)
                            tf.addfile(ti, io.BytesIO(data))
                    found :list[tuple[str, ...]] = []
                    for result in uut.unzipwalk(fn):
                        if result.typ==FileType.FILE:
                            assert result.hnd is not None
                            self.assertEqual(result.hnd.read(), b'contents')
                            found.append(result.raw_names)
                            with uut.recursive_open(result.raw_names) as fh:
                                self.assertEqual(fh.read(), b'contents')
                    self.assertCountEqual(found, [(str(fn), name, derived) for name, derived in members])
                    for name, derived in members:
                        with self.subTest(name=name):
                            with uut.recursive_open((fn, name, derived)) as fh:
                                self.assertEqual(fh.read(), b'contents')

    def test_suffix_only_compression(self) -> None:
        with TemporaryDirectory() as td:
            for ext, compress in (('gz', gzip_compress), ('bz2', bz2_compress), ('xz', lzma_compress)):
                for depth in (1, 2):
                    with self.subTest(ext=ext, depth=depth):
                        fn = Path(td)/(('.'+ext)*depth)
                        data = b'contents'
                        for _ in range(depth):
                            data = compress(data)
                        fn.write_bytes(data)
                        names = (str(fn), *(os.path.join(td, ('.'+ext)*i) for i in range(depth-1, 0, -1)),
                            os.path.join(td, 'noname'))
                        results = [(r.names, r.raw_names, r.typ, r.hnd.read() if r.hnd is not None else None)
                            for r in uut.unzipwalk(fn)]
                        self.assertEqual(results, [
                            (tuple(Path(n) for n in names), names, FileType.FILE, b'contents'),
                            *((tuple(Path(n) for n in names[:i]), names[:i], FileType.ARCHIVE, None)
                                for i in range(depth, 0, -1)) ])
                        for reopen_names in (results[0][0], results[0][1]):
                            with uut.recursive_open(reopen_names) as fh:
                                self.assertEqual(fh.read(), b'contents')

    def test_physical_compression_suffixes(self) -> None:
        with TemporaryDirectory() as td:
            folder = Path(td)/'dir.with.dots'
            folder.mkdir()
            for ext, compress in (('gz', gzip_compress), ('bz2', bz2_compress), ('xz', lzma_compress)):
                with self.subTest(ext=ext):
                    fn = folder/f".hidden.txt.{ext.upper()}"
                    fn.write_bytes(compress(b'contents'))
                    results = [(r.names, r.raw_names, r.hnd.read()) for r in uut.unzipwalk(fn) if r.hnd is not None]
                    self.assertEqual(results, [((fn, folder/'.hidden.txt'), (str(fn), str(folder/'.hidden.txt')), b'contents')])
                    for names in (results[0][0], results[0][1]):
                        with uut.recursive_open(names) as fh:
                            self.assertEqual(fh.read(), b'contents')
