"""
Tests for :mod:`unzipwalk.defs`
================================

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
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from igbpyutils.file import Filename
import unzipwalk.defs as uut
from unzipwalk.defs import FileType
from .defs import EXPECT, EXPECT_7Z

# spell: ignore fspath

class TestDefs(unittest.TestCase):

    def test_convert_names(self) -> None:
        fns :tuple[Filename, ...]
        expected :tuple[PurePath|str, ...]
        archive_inputs :list[Filename] = []
        def archive_name(fn :Filename) -> str:
            archive_inputs.append(fn)
            return os.fspath(fn)
        for physical_cls in (Path, PurePosixPath):
            for fns, expected in (
                    ((), ()),
                    (('./physical//file.txt',), (physical_cls('physical/file.txt'),)),
                    (('physical/file.txt.gz', 'physical/file.txt'),
                        (physical_cls('physical/file.txt.gz'), physical_cls('physical/file.txt'))),
                    (('physical/file.unknown', 'physical/file'),
                        (physical_cls('physical/file.unknown'), physical_cls('physical/file'))),
                    (('physical/dir.zip/file.gz', 'physical/dir.zip/file'),
                        (physical_cls('physical/dir.zip/file.gz'), physical_cls('physical/dir.zip/file'))),
                    (('physical/archive.zip.gz.bz2.xz', 'physical/archive.zip.gz.bz2',
                      'physical/archive.zip.gz', 'physical/archive.zip', './dir//file.txt'),
                        (physical_cls('physical/archive.zip.gz.bz2.xz'), physical_cls('physical/archive.zip.gz.bz2'),
                            physical_cls('physical/archive.zip.gz'), physical_cls('physical/archive.zip'), './dir//file.txt')),
                    (('physical/archive.tar.gz.xz', 'physical/archive.tar.gz', './dir//file.txt'),
                        (physical_cls('physical/archive.tar.gz.xz'), physical_cls('physical/archive.tar.gz'), './dir//file.txt')),
                    (('physical/archive.zip', './inner//archive.tar', './dir//file.gz', './dir//file'),
                        (physical_cls('physical/archive.zip'), './inner//archive.tar', './dir//file.gz', './dir//file')),
                    ((physical_cls('physical/archive.zip'), PurePosixPath('dir/file.txt')),
                        (physical_cls('physical/archive.zip'), 'dir/file.txt')),
                    (('physical/archive.zip', r'./dir//literal\file.txt'),
                        (physical_cls('physical/archive.zip'), r'./dir//literal\file.txt')) ):
                with self.subTest(physical_cls=physical_cls.__name__, fns=fns):
                    archive_inputs.clear()
                    result = uut.convert_names(fns, physical_cls, archive_name)
                    self.assertEqual(result, expected)
                    self.assertEqual(tuple(type(n) for n in result), tuple(type(n) for n in expected))
                    self.assertEqual(archive_inputs, [fn for fn, n in zip(fns, expected) if isinstance(n, str)])
                    normalized_expected = tuple(PurePosixPath(n) if isinstance(n, str) else n for n in expected)
                    normalized = uut.convert_names(fns, physical_cls, PurePosixPath)
                    self.assertEqual(normalized, normalized_expected)
                    self.assertEqual(tuple(type(n) for n in normalized), tuple(type(n) for n in normalized_expected))
            for ext in ('zip', '7z', 'tar', 'tar.gz', 'tar.bz2', 'tar.xz', 'tgz', 'txz', 'tbz', 'tbz2'):
                with self.subTest(physical_cls=physical_cls.__name__, ext=ext):
                    archive_inputs.clear()
                    self.assertEqual(uut.convert_names((f"physical/archive.{ext.upper()}", './dir//file.txt'), physical_cls,
                        archive_name),
                        (physical_cls(f"physical/archive.{ext.upper()}"), './dir//file.txt'))
                    self.assertEqual(archive_inputs, ['./dir//file.txt'])

    def test_compression_stem(self) -> None:
        for name, expected in (
                ('', ''), ('file', 'file'), ('file.txt.gz', 'file.txt'), ('file.txt.BZ2', 'file.txt'), ('file.txt.xz', 'file.txt'),
                ('archive.tar.gz', 'archive.tar'), ('archive.zip.gz.bz2.xz', 'archive.zip.gz.bz2'),
                ('./dir//file.txt.GZ', './dir//file.txt'), (r'dir\.gz', 'dir\\'), ('.hidden.gz', '.hidden'),
                ('..gz', '.'), ('...bz2', '..'), ('.gz', '.gz'), ('.bz2', '.bz2'), ('.xz', '.xz'),
                ('dir/file.gz/', 'dir/file.gz/'), ('dir/file.gz/.', 'dir/file.gz/.') ):
            with self.subTest(name=name):
                result = uut.compression_stem(name)
                self.assertEqual(result, expected)
                self.assertIs(type(result), str)
        for name, expected in (
                ('./dir//file.txt.GZ', 'dir/file.txt'), (r'dir\.gz', 'dir\\'), ('dir/file.gz/', 'dir/file'),
                ('..gz', '.'), ('.gz', '.gz'), ('.bz2', '.bz2'), ('.xz', '.xz') ):
            with self.subTest(posix_path=name):
                result_path = uut.compression_stem(PurePosixPath(name))
                self.assertEqual(result_path, PurePosixPath(expected))
                self.assertIs(type(result_path), PurePosixPath)
        for name, expected in (
                ('file', 'file'), ('file.txt.GZ', 'file.txt'), ('file.txt.bz2', 'file.txt'), ('file.txt.XZ', 'file.txt'),
                (os.path.join('dir.with.dots', '.hidden.GZ'), os.path.join('dir.with.dots', '.hidden')),
                (os.path.join('dir', '..gz'), os.path.join('dir', '.')),
                (os.path.join('dir', '.gz'), os.path.join('dir', '.gz')),
                (os.path.join('dir', '.bz2'), os.path.join('dir', '.bz2')),
                (os.path.join('dir', '.xz'), os.path.join('dir', '.xz')) ):
            with self.subTest(physical_name=name):
                result = uut.compression_stem(name, physical=True)
                self.assertEqual(result, expected)
                self.assertIs(type(result), str)
                result_path = uut.compression_stem(Path(name))
                self.assertEqual(result_path, Path(expected))
                self.assertIs(type(result_path), type(Path(expected)))

    def test_result_validate(self) -> None:
        with self.assertRaisesRegex(TypeError, 'raw_names'):
            # Deliberately omit the required field to verify runtime constructor validation.
            uut.UnzipWalkResult(names=(Path(),), typ=FileType.OTHER)  # type: ignore[call-arg]
        with self.assertRaises(ValueError):
            uut.UnzipWalkResult(names=(Path(),), typ=FileType.OTHER, raw_names=()).validate()
        with self.assertRaises(ValueError):
            uut.UnzipWalkResult((), (), FileType.OTHER, None, None).validate()
        with self.assertRaises(TypeError):
            # Deliberately pass a string instead of a path to verify runtime validation.
            uut.UnzipWalkResult(('foo',), ('foo',), FileType.OTHER, None, None).validate()  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            # Deliberately pass an invalid file type to verify runtime validation.
            uut.UnzipWalkResult((Path(),), ('.',), 'foo', None, None).validate()  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            uut.UnzipWalkResult((Path(),), ('.',), FileType.FILE, None, None).validate()
        with self.assertRaises(TypeError):
            uut.UnzipWalkResult((Path(),), ('.',), FileType.OTHER, io.BytesIO(), None).validate()
        with self.assertRaises(TypeError):
            # Deliberately pass a string instead of an integer size to verify runtime validation.
            uut.UnzipWalkResult((Path(),), ('.',), FileType.FILE, io.BytesIO(), 'x').validate()  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            uut.UnzipWalkResult((Path(),), ('.',), FileType.OTHER, None, 42).validate()
        with self.assertRaises(ValueError):
            uut.UnzipWalkResult((Path(),), ('one', 'two'), FileType.OTHER).validate()
        with self.assertRaises(TypeError):
            # Deliberately violate the annotation to verify runtime validation of dynamically constructed results.
            uut.UnzipWalkResult((Path(),), (Path(),), FileType.OTHER).validate()  # type: ignore[arg-type]

    def test_checksum_lines(self) -> None:
        res = uut.UnzipWalkResult(names=(PurePosixPath('hello'),), typ=FileType.DIR, raw_names=('hello',))
        ln = res.checksum_line("md5")
        self.assertEqual( ln, "# DIR hello" )
        self.assertEqual( uut.UnzipWalkResult.from_checksum_line(ln, windows=False), res )

        res = uut.UnzipWalkResult(names=(PurePosixPath('hello\nworld'),), typ=FileType.DIR, raw_names=('hello\nworld',))
        ln = res.checksum_line("md5")
        self.assertEqual( ln, "# DIR ('hello\\nworld',)" )
        self.assertEqual( uut.UnzipWalkResult.from_checksum_line(ln, windows=False), res )

        res = uut.UnzipWalkResult(names=(PurePosixPath('(hello'),), typ=FileType.DIR, raw_names=('(hello',))
        ln = res.checksum_line("md5")
        self.assertEqual( ln, "# DIR ('(hello',)" )
        self.assertEqual( uut.UnzipWalkResult.from_checksum_line(ln, windows=False), res )

        res = uut.UnzipWalkResult(names=(PurePosixPath(' hello '),), typ=FileType.DIR, raw_names=(' hello ',))
        ln = res.checksum_line("md5")
        self.assertEqual( ln, "# DIR (' hello ',)" )
        self.assertEqual( uut.UnzipWalkResult.from_checksum_line(ln, windows=False), res )

        res2 = uut.UnzipWalkResult.from_checksum_line("# DIR C:\\Foo\\Bar", windows=True)
        assert res2 is not None
        self.assertEqual( res2.names, (PureWindowsPath('C:\\','Foo','Bar'),) )
        self.assertEqual( res2.raw_names, ('C:\\Foo\\Bar',) )

        res = uut.UnzipWalkResult(names=(PurePosixPath('hello'),PurePosixPath('world')),
            typ=FileType.FILE, raw_names=('hello', 'world'), hnd=io.BytesIO(b'abcdef'))
        ln = res.checksum_line("md5")
        self.assertEqual( ln, "e80b5017098950fc58aad83c8c14978e *('hello', 'world')" )
        res2 = uut.UnzipWalkResult.from_checksum_line(ln, windows=False)
        assert res2 is not None
        self.assertEqual( res2.names, (PurePosixPath('hello'),PurePosixPath('world')) )
        self.assertEqual( res2.raw_names, ('hello', 'world') )
        self.assertEqual( res2.typ, FileType.FILE )
        assert res2.hnd is not None
        self.assertEqual( res2.hnd.read(), bytes.fromhex('e80b5017098950fc58aad83c8c14978e') )

        self.assertIsNone( uut.UnzipWalkResult.from_checksum_line("# I'm just some comment") )
        self.assertIsNone( uut.UnzipWalkResult.from_checksum_line("# FOO bar") )
        self.assertIsNone( uut.UnzipWalkResult.from_checksum_line("  # and some other comment") )
        self.assertIsNone( uut.UnzipWalkResult.from_checksum_line("  ") )

        with self.assertRaises(ValueError):
            uut.UnzipWalkResult.from_checksum_line("e80b5017098950fc58aad83c8c14978g *kaboom")
        with self.assertRaises(ValueError):
            uut.UnzipWalkResult.from_checksum_line("e80b5017098950fc58aad83c8c14978e *(kaboom")

    def test_checksum_roundtrip(self) -> None:
        for file in EXPECT + EXPECT_7Z:
            with self.subTest(names=file.fns):
                result = uut.UnzipWalkResult(names=file.fns, raw_names=tuple(str(n) for n in file.fns), typ=file.typ,
                    hnd=io.BytesIO(file.data) if file.data is not None else None, size=file.size)
                decoded = uut.UnzipWalkResult.from_checksum_line(result.checksum_line('sha1'))
                assert decoded is not None
                self.assertEqual(decoded.names, file.fns)
                self.assertEqual(decoded.raw_names, result.raw_names)
                self.assertEqual(decoded.typ, result.typ)

    def test_checksum_path_types(self) -> None:
        cases = [
            ((f"file.txt.{ext}", 'file.txt'), 2) for ext in ('gz', 'bz2', 'xz')
        ] + [
            ((f"archive.{ext}", r'./dir//literal\file.txt.gz', r'./dir//literal\file.txt'), 1)
            for ext in ('zip', '7z', 'tar', 'tar.gz', 'tar.bz2', 'tar.xz', 'tgz', 'txz', 'tbz', 'tbz2')
        ] + [
            (('archive.zip.gz.bz2.xz', 'archive.zip.gz.bz2', 'archive.zip.gz', 'archive.zip',
                r'./dir//literal\file.txt.gz', r'./dir//literal\file.txt'), 4) ]
        for parts, physical_count in cases:
            with self.subTest(parts=parts):
                raw_names = tuple(str(Path('data')/p) if i<physical_count else p for i, p in enumerate(parts))
                names = tuple(Path(p) if i<physical_count else PurePosixPath(p) for i, p in enumerate(raw_names))
                result = uut.UnzipWalkResult(names=names, raw_names=raw_names, typ=FileType.DIR)
                decoded = uut.UnzipWalkResult.from_checksum_line(result.checksum_line('sha1'))
                assert decoded is not None
                self.assertEqual(decoded.names, names)
                self.assertEqual(decoded.raw_names, raw_names)

    def test_raw_checksum_comments(self) -> None:
        result = uut.UnzipWalkResult(names=(Path('archive.zip'), PurePosixPath('./dir//')),
            raw_names=('archive.zip', './dir//'), typ=FileType.DIR)
        line = result.checksum_line('sha1')
        self.assertEqual(line, "# DIR ('archive.zip', './dir//')")
        decoded = uut.UnzipWalkResult.from_checksum_line(line)
        assert decoded is not None
        self.assertEqual(decoded.raw_names, result.raw_names)
        self.assertEqual(decoded.names, result.names)

    def test_raw_checksum_names(self) -> None:
        for ext in ('zip', 'tar', '7z'):
            for name, data in (('./file.txt', b'dotted'), ('file.txt', b'first'), ('file.txt', b'second')):
                with self.subTest(ext=ext, name=name, data=data):
                    result = uut.UnzipWalkResult(names=(Path(f"archive.{ext}"), PurePosixPath('file.txt')),
                        raw_names=(f"archive.{ext}", name), typ=FileType.FILE, hnd=io.BytesIO(data))
                    decoded = uut.UnzipWalkResult.from_checksum_line(result.checksum_line('sha1'))
                    assert decoded is not None
                    self.assertEqual(decoded.raw_names, result.raw_names)
                    self.assertEqual(decoded.names, result.names)
