"""
Tests for :mod:`unzipwalk`
==========================

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
import sys
import errno
import doctest
import unittest
from hashlib import sha1
from lzma import LZMAError
from gzip import BadGzipFile
from tarfile import TarError
from zipfile import BadZipFile
from unittest.mock import patch
from tempfile import TemporaryDirectory
from pathlib import Path, PurePosixPath, PureWindowsPath
from py7zr.exceptions import ArchiveError
import unzipwalk as uut
from unzipwalk import FileType
from .defs import EXPECT, EXPECT_7Z, BAD_ZIPS, ExpectedResult, TestCaseContext, r2e

# spell: ignore strerror

def load_tests(_loader :unittest.TestLoader, tests :unittest.TestSuite, _ignore :str|None) -> unittest.TestSuite:
    globs :dict[str, str] = {}
    def doctest_setup(_t :doctest.DocTest) -> None:
        globs['_prev_dir'] = os.getcwd()
        os.chdir( Path(__file__).parent/'doctest_wd' )
    def doctest_teardown(_t :doctest.DocTest) -> None:
        os.chdir( globs['_prev_dir'] )
        del globs['_prev_dir']
    tests.addTests(doctest.DocTestSuite(uut, setUp=doctest_setup, tearDown=doctest_teardown, globs=globs))
    return tests

class TestUnzipWalk(unittest.TestCase):

    def setUp(self) -> None:
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_unzipwalk(self) -> None:
        with TestCaseContext() as expect:
            self.assertEqual( expect, r2e(uut.unzipwalk(os.curdir)) )
            # and again, definitely without 7z
            prev = uut.W7Z
            try:  # temporarily pretend 7z is not installed
                uut.W7Z = None
                self.assertEqual( [ x for x in expect if x not in EXPECT_7Z ],
                    r2e(uut.unzipwalk(os.curdir)) )
                with self.assertRaises(ImportError):
                    with uut.recursive_open((Path("more.zip"), PurePosixPath("more/stuff/xyz.7z"), PurePosixPath("even.txt"))):
                        pass  # pragma: no cover
            finally:
                uut.W7Z = prev

    def test_unzipwalk_errs(self) -> None:
        with self.assertRaises(FileNotFoundError):
            list(uut.unzipwalk('/this_file_should_not_exist'))

    def test_unzipwalk_matcher(self) -> None:
        with TestCaseContext() as expect:
            # filter from the initial path list
            self.assertEqual( sorted(
                    [ r for r in expect if r.fns[0].name != 'more.zip' ]
                    + [ ExpectedResult( (Path("more.zip"),), None, FileType.SKIP, None ) ]
                ), r2e(uut.unzipwalk(os.curdir, matcher=lambda p: p[0].stem.lower()!='more')) )
            # filter from zip file
            self.assertEqual( sorted(
                    [ r for r in expect if r.fns[-1].name != 'six.txt' ]
                    + [ ExpectedResult( (Path("more.zip"), PurePosixPath("more/stuff/six.txt")), None, FileType.SKIP, None ) ]
                ), r2e(uut.unzipwalk(os.curdir, matcher=lambda p: p[-1].name.lower()!='six.txt')) )
            # filter a gz file
            self.assertEqual( sorted(
                    [ r for r in expect if not ( r.fns[0].name=='archive.tar.gz' and len(r.fns)>1 and r.fns[1].name == 'world.txt.gz' ) ]
                    + [ ExpectedResult( (Path("archive.tar.gz"), PurePosixPath("archive/world.txt.gz")), None, FileType.SKIP, None ) ]
                ), r2e(uut.unzipwalk(os.curdir, matcher=lambda p: len(p)<2 or p[-2].as_posix()!='archive/world.txt.gz')) )
            # filter a bz2 file
            self.assertEqual( sorted(
                    [ r for r in expect if not ( r.fns[0].name=='formats.tar.bz2' and len(r.fns)>1 and r.fns[1].name == 'bzip2.txt.bz2' ) ]
                    + [ ExpectedResult( (Path("subdir","formats.tar.bz2"), PurePosixPath("formats/bzip2.txt.bz2")), None, FileType.SKIP, None ) ]
                ), r2e(uut.unzipwalk(os.curdir, matcher=lambda p: len(p)<2 or p[-2].as_posix()!='formats/bzip2.txt.bz2')) )
            # filter an xz file
            self.assertEqual( sorted(
                    [ r for r in expect if not ( r.fns[0].name=='formats.tar.bz2' and len(r.fns)>1 and r.fns[1].name == 'lzma.txt.xz' ) ]
                    + [ ExpectedResult( (Path("subdir","formats.tar.bz2"), PurePosixPath("formats/lzma.txt.xz")), None, FileType.SKIP, None ) ]
                ), r2e(uut.unzipwalk(os.curdir, matcher=lambda p: len(p)<2 or p[-2].as_posix()!='formats/lzma.txt.xz')) )
            # filter from tar file
            self.assertEqual( sorted(
                    [ r for r in expect if not ( len(r.fns)>1 and r.fns[1].stem=='abc' ) ]
                    + [ ExpectedResult( (Path("archive.tar.gz"), PurePosixPath("archive/abc.zip")), None, FileType.SKIP, None ) ]
                ), r2e(uut.unzipwalk(os.curdir, matcher=lambda p: p[-1].name != 'abc.zip')) )
            # filter a file from 7z file
            self.assertEqual( sorted(
                    [ r for r in expect if not ( r.fns[0].name=='opt.7z' and len(r.fns)>1 and r.fns[1].name=='wuv.tgz' ) ]
                    + [ ExpectedResult( (Path("opt.7z"), PurePosixPath("thing/wuv.tgz")), None, FileType.SKIP, None ), ]
                ), r2e(uut.unzipwalk(os.curdir, matcher=lambda p: p[-1].name != 'wuv.tgz')) )
            # filter a directory from a 7z file
            self.assertEqual( sorted(
                    [ r for r in expect if not ( r.fns[0].name=='opt.7z' and len(r.fns)>1 ) ]
                    + [ ExpectedResult( (Path("opt.7z"), PurePosixPath("thing")), None, FileType.SKIP, None ),
                        ExpectedResult( (Path("opt.7z"), PurePosixPath("thing/blah.txt")), None, FileType.SKIP, None ),
                        ExpectedResult( (Path("opt.7z"), PurePosixPath("thing/wuv.tgz")), None, FileType.SKIP, None ), ]
                ), r2e(uut.unzipwalk(os.curdir, matcher=lambda p: not ( len(p)>1 and p[1].parts[0] == 'thing')) ) )

    def test_skip_dirs(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            td = Path(tmp_dir)
            for d in (td/'excl', td/'inc'/'excl'):
                d.mkdir(parents=True)
                (d/'kaboom.zip').write_bytes(b'I am not a zip file, reading me would cause an error')
            (td/'inc'/'good.txt').write_bytes(b'good')
            self.assertEqual(
                r2e(uut.unzipwalk(td, matcher=lambda p: p[-1].name != 'excl')),
                sorted([
                    ExpectedResult((td/'excl',), None, FileType.SKIP, None),
                    ExpectedResult((td/'inc',), None, FileType.DIR, None),
                    ExpectedResult((td/'inc'/'excl',), None, FileType.SKIP, None),
                    ExpectedResult((td/'inc'/'good.txt',), b'good', FileType.FILE, 4) ]) )
            self.assertEqual(
                list( uut.unzipwalk(td/'excl', matcher=lambda p: p[-1].name != 'excl') ),
                [ uut.UnzipWalkResult(names=(td/'excl',), typ=FileType.SKIP) ])

    def test_recursive_open(self) -> None:
        with TestCaseContext() as expect:
            for file in expect:
                if file.typ == FileType.FILE:
                    with uut.recursive_open(file.fns) as fh:
                        self.assertEqual( fh.read(), file.data )
            # text mode
            with uut.recursive_open(("archive.tar.gz", "archive/abc.zip", "abc.txt"), encoding='UTF-8') as fh:
                assert isinstance(fh, io.TextIOWrapper)
                self.assertEqual( fh.readlines(), ["One two three\n", "four five six\n", "seven eight nine\n"] )
            # open an archive
            with uut.recursive_open(('archive.tar.gz', 'archive/abc.zip')) as fh:
                assert isinstance(fh, uut.ReadOnlyBinary)
                self.assertEqual( sha1(fh.read()).hexdigest(), '4d6be7a2e79c3341dd5c4fe669c0ca40a8765031' )
            # basic error
            with self.assertRaises(ValueError):
                with uut.recursive_open(()):
                    pass  # pragma: no cover
            # gzip bad filename
            with self.assertRaises(FileNotFoundError):
                with uut.recursive_open(("archive.tar.gz", "archive/world.txt.gz", "archive/bang.txt")):
                    pass  # pragma: no cover
            # bz2 bad filename
            with self.assertRaises(FileNotFoundError):
                with uut.recursive_open(("subdir/formats.tar.bz2","formats/bzip2.txt.bz2","formats/kaboom.txt")):
                    pass  # pragma: no cover
            # xz bad filename
            with self.assertRaises(FileNotFoundError):
                with uut.recursive_open(("subdir/formats.tar.bz2","formats/lzma.txt.xz","formats/kaboom.txt")):
                    pass  # pragma: no cover
            # TarFile.extractfile: attempt to open a directory
            with self.assertRaises(FileNotFoundError):
                with uut.recursive_open(("archive.tar.gz", "archive/test2/")):
                    pass  # pragma: no cover
            # 7z bad filename
            with self.assertRaises(FileNotFoundError):
                with uut.recursive_open(("opt.7z", "bang")):
                    pass  # pragma: no cover
            # bad filename
            with self.assertRaises(ValueError):
                with uut.recursive_open(("test.csv", "blammo")):
                    pass  # pragma: no cover

    def test_result_validate(self) -> None:
        with self.assertRaises(ValueError):
            uut.UnzipWalkResult((), FileType.OTHER, None, None).validate()
        with self.assertRaises(TypeError):
            uut.UnzipWalkResult(('foo',), FileType.OTHER, None, None).validate()  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            uut.UnzipWalkResult((Path(),), 'foo', None, None).validate()  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            uut.UnzipWalkResult((Path(),), FileType.FILE, None, None).validate()
        with self.assertRaises(TypeError):
            uut.UnzipWalkResult((Path(),), FileType.OTHER, io.BytesIO(), None).validate()
        with self.assertRaises(TypeError):
            uut.UnzipWalkResult((Path(),), FileType.FILE, io.BytesIO(), 'x').validate()  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            uut.UnzipWalkResult((Path(),), FileType.OTHER, None, 42).validate()

    def test_checksum_lines(self) -> None:
        res = uut.UnzipWalkResult(names=(PurePosixPath('hello'),), typ=FileType.DIR)
        ln = res.checksum_line("md5")
        self.assertEqual( ln, "# DIR hello" )
        self.assertEqual( uut.UnzipWalkResult.from_checksum_line(ln), res )

        res = uut.UnzipWalkResult(names=(PurePosixPath('hello\nworld'),), typ=FileType.DIR)
        ln = res.checksum_line("md5")
        self.assertEqual( ln, "# DIR ('hello\\nworld',)" )
        self.assertEqual( uut.UnzipWalkResult.from_checksum_line(ln), res )

        res = uut.UnzipWalkResult(names=(PurePosixPath('(hello'),), typ=FileType.DIR)
        ln = res.checksum_line("md5")
        self.assertEqual( ln, "# DIR ('(hello',)" )
        self.assertEqual( uut.UnzipWalkResult.from_checksum_line(ln), res )

        res = uut.UnzipWalkResult(names=(PurePosixPath(' hello '),), typ=FileType.DIR)
        ln = res.checksum_line("md5")
        self.assertEqual( ln, "# DIR (' hello ',)" )
        self.assertEqual( uut.UnzipWalkResult.from_checksum_line(ln), res )

        res2 = uut.UnzipWalkResult.from_checksum_line("# DIR C:\\Foo\\Bar", windows=True)
        assert res2 is not None
        self.assertEqual( res2.names, (PureWindowsPath('C:\\','Foo','Bar'),) )

        res = uut.UnzipWalkResult(names=(PurePosixPath('hello'),PurePosixPath('world')),
            typ=FileType.FILE, hnd=io.BytesIO(b'abcdef'))
        ln = res.checksum_line("md5")
        self.assertEqual( ln, "e80b5017098950fc58aad83c8c14978e *('hello', 'world')" )
        res2 = uut.UnzipWalkResult.from_checksum_line(ln)
        assert res2 is not None
        self.assertEqual( res2.names, (PurePosixPath('hello'),PurePosixPath('world')) )
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

    def test_errors(self) -> None:
        with self.assertRaises(BadZipFile):
            list(uut.unzipwalk(BAD_ZIPS/'not_a.zip'))
        with self.assertRaises(TarError):
            list(uut.unzipwalk(BAD_ZIPS/'not_a.tgz'))
        with self.assertRaises(BadGzipFile):
            list(uut.unzipwalk(BAD_ZIPS/'not_a.tgz.gz'))
        # apparently, some Python versions now throw a ValueError instead
        with self.assertRaises((EOFError, ValueError)):
            list(uut.unzipwalk(BAD_ZIPS/'not_a.tgz.bz2'))
        with self.assertRaises(BadZipFile):
            list(uut.unzipwalk(BAD_ZIPS/'not_a.zip.gz'))
        with self.assertRaises(BadZipFile):
            list(uut.unzipwalk(BAD_ZIPS/'not_a.zip.bz2'))
        with self.assertRaises(LZMAError):
            list(uut.unzipwalk(BAD_ZIPS/'not_a.zip.xz'))
        with self.assertRaises(ArchiveError):
            list(uut.unzipwalk(BAD_ZIPS/'not_a.7z'))
        with self.assertRaises(ArchiveError):
            list(uut.unzipwalk(BAD_ZIPS/'bad.7z'))
        with self.assertRaises(FileExistsError):
            list(uut.unzipwalk(BAD_ZIPS/'double.7z'))
        with self.assertRaises(RuntimeError):
            list(uut.unzipwalk(BAD_ZIPS/'features.zip'))
        # the following is commented out due to https://github.com/python/cpython/issues/120740
        #with self.assertRaises(TarError):
        #    list(uut.unzipwalk(pth/'bad.tar.gz'))
        self.assertEqual( sorted(
               (r.names, None if r.hnd is None or r.names[0].name in ('not_a.gz','not_a.bz2','not_a.xz') else r.hnd.read(), r.typ)
               for r in uut.unzipwalk( (BAD_ZIPS, Path('does_not_exist')) , raise_errors=False) ),
            sorted( [
                 ( (Path("does_not_exist"),), None, FileType.ERROR ),
                 ( (BAD_ZIPS/"not_a.gz",), None, FileType.ARCHIVE ),
                 ( (BAD_ZIPS/"not_a.gz", BAD_ZIPS/"not_a"), None, FileType.FILE ),  # no error until the file is read (tested below)
                 ( (BAD_ZIPS/"not_a.bz2",), None, FileType.ARCHIVE ),
                 ( (BAD_ZIPS/"not_a.bz2", BAD_ZIPS/"not_a"), None, FileType.FILE ),  # no error until the file is read (tested below)
                 ( (BAD_ZIPS/"not_a.xz",), None, FileType.ARCHIVE ),
                 ( (BAD_ZIPS/"not_a.xz", BAD_ZIPS/"not_a"), None, FileType.FILE ),  # no error until the file is read (tested below)
                 ( (BAD_ZIPS/"not_a.tar",), None, FileType.ERROR ),
                 ( (BAD_ZIPS/"not_a.tar.gz",), None, FileType.ERROR ),
                 ( (BAD_ZIPS/"not_a.tgz",), None, FileType.ERROR ),
                 ( (BAD_ZIPS/"not_a.zip",), None, FileType.ERROR ),
                 ( (BAD_ZIPS/"not_a.tgz.gz",), None, FileType.ARCHIVE ),
                 ( (BAD_ZIPS/"not_a.tgz.gz", BAD_ZIPS/"not_a.tgz"), None, FileType.ERROR ),
                 ( (BAD_ZIPS/"not_a.tgz.bz2",), None, FileType.ARCHIVE ),
                 ( (BAD_ZIPS/"not_a.tgz.bz2", BAD_ZIPS/"not_a.tgz"), None, FileType.ERROR ),
                 ( (BAD_ZIPS/"not_a.zip.gz",), None, FileType.ARCHIVE ),
                 ( (BAD_ZIPS/"not_a.zip.gz", BAD_ZIPS/"not_a.zip"), None, FileType.ERROR ),
                 ( (BAD_ZIPS/"not_a.zip.bz2",), None, FileType.ARCHIVE ),
                 ( (BAD_ZIPS/"not_a.zip.bz2", BAD_ZIPS/"not_a.zip"), None, FileType.ERROR ),
                 ( (BAD_ZIPS/"not_a.zip.xz",), None, FileType.ARCHIVE ),
                 ( (BAD_ZIPS/"not_a.zip.xz", BAD_ZIPS/"not_a.zip"), None, FileType.ERROR ),
                 ( (BAD_ZIPS/"features.zip",), None, FileType.ARCHIVE ),
                 ( (BAD_ZIPS/"features.zip", PurePosixPath("spiral.pl")), None, FileType.ERROR ),  # unsupported compression method
                 ( (BAD_ZIPS/"features.zip", PurePosixPath("foo.txt")), b'Top Secret\n', FileType.FILE ),
                 ( (BAD_ZIPS/"features.zip", PurePosixPath("bar.txt")), None, FileType.ERROR ),  # encrypted
                 ( (BAD_ZIPS/"bad.tar.gz",), None, FileType.ARCHIVE ),
                 ( (BAD_ZIPS/"bad.tar.gz", PurePosixPath("a")), b'One\n', FileType.FILE ),
                 # the following is commented out due to https://github.com/python/cpython/issues/120740
                 #( (pth/"bad.tar.gz", PurePosixPath("b")), None, FileType.ERROR ),  # bad checksum
                 #( (pth/"bad.tar.gz", PurePosixPath("c")), b'Three\n', FileType.FILE ),
                 ( (BAD_ZIPS/"double.7z",), None, FileType.ARCHIVE ),
                 ( (BAD_ZIPS/"bad.7z",), None, FileType.ARCHIVE ),
            ] + (
                [
                 ( (BAD_ZIPS/"double.7z", PurePosixPath("bar.txt")), None, FileType.ERROR ),
                 ( (BAD_ZIPS/"double.7z", PurePosixPath("bar.txt")), None, FileType.ERROR ),
                 ( (BAD_ZIPS/"bad.7z", PurePosixPath("broken.txt")), None, FileType.ERROR ),  # bad checksum
                 ( (BAD_ZIPS/"not_a.7z",), None, FileType.ERROR ),
                ]) ) )
        with self.assertRaises(BadGzipFile):
            for r in uut.unzipwalk((BAD_ZIPS/'not_a.gz')):  # pragma: no branch
                assert r.hnd is not None
                r.hnd.read()
        with self.assertRaises(OSError):
            for r in uut.unzipwalk((BAD_ZIPS/'not_a.bz2')):  # pragma: no branch
                assert r.hnd is not None
                r.hnd.read()
        with self.assertRaises(LZMAError):
            for r in uut.unzipwalk((BAD_ZIPS/'not_a.xz')):  # pragma: no branch
                assert r.hnd is not None
                r.hnd.read()
        with self.assertRaises(FileExistsError):
            with uut.recursive_open((BAD_ZIPS/"double.7z", "bar.txt")):
                pass  # pragma: no cover

    @unittest.skipIf(condition=not sys.platform.startswith('linux'), reason='only on Linux')
    def test_errors_linux(self) -> None:  # cover-only-linux
        with TemporaryDirectory() as td:
            f = Path(td)/'foo'
            f.touch()
            f.chmod(0)
            with self.assertRaises(PermissionError):
                list(uut.unzipwalk(td))
            self.assertEqual(
                r2e(uut.unzipwalk(td, raise_errors=False)),
                sorted( [ ExpectedResult( (f,), None, FileType.ERROR, None ), ] ) )

    def test_dir_walk_errors(self) -> None:
        with TemporaryDirectory() as td:
            error = PermissionError(errno.EACCES, os.strerror(errno.EACCES), td)
            with patch('unzipwalk.os.scandir', side_effect=error):
                with self.assertRaises(PermissionError) as caught:
                    list(uut.unzipwalk(td))
                self.assertIs(caught.exception, error)
                self.assertEqual(r2e(uut.unzipwalk(td, raise_errors=False)),
                    [ExpectedResult((Path(td),), None, FileType.ERROR, None)])

    @unittest.skipIf(condition = os.name!='posix', reason='only on POSIX')
    def test_dir_perms(self) -> None:  # cover-only-posix
        with TemporaryDirectory() as temp_dir:
            td = Path(temp_dir)
            blocked = td/'blocked'
            blocked.mkdir()
            (blocked/'hidden.txt').write_bytes(b'hidden')
            (td/'readable').mkdir()
            (td/'readable'/'good.txt').write_bytes(b'good')
            blocked.chmod(0)
            try:
                for path in (td, blocked):
                    with self.subTest(path=path):
                        with self.assertRaises(PermissionError) as caught:
                            list(uut.unzipwalk(path))
                        self.assertEqual(caught.exception.filename, str(blocked))
                self.assertEqual( r2e(uut.unzipwalk(td, raise_errors=False)),
                    sorted([ExpectedResult((blocked,), None, FileType.ERROR, None),
                            ExpectedResult((td/'readable',), None, FileType.DIR, None),
                            ExpectedResult((td/'readable'/'good.txt',), b'good', FileType.FILE, 4) ]) )
                self.assertEqual( r2e(uut.unzipwalk(blocked, raise_errors=False)),
                    [ExpectedResult((blocked,), None, FileType.ERROR, None)] )
                self.assertEqual( r2e(uut.unzipwalk((blocked, td/'readable'), raise_errors=False)),
                    sorted([ExpectedResult((blocked,), None, FileType.ERROR, None),
                            ExpectedResult((td/'readable'/'good.txt',), b'good', FileType.FILE, 4) ]) )
                self.assertEqual( r2e(uut.unzipwalk(td, matcher=lambda p: p[-1].name != 'blocked')),
                    sorted([ExpectedResult((blocked,), None, FileType.SKIP, None),
                            ExpectedResult((td/'readable',), None, FileType.DIR, None),
                            ExpectedResult((td/'readable'/'good.txt',), b'good', FileType.FILE, 4) ]) )
            finally:
                blocked.chmod(0o700)

    def test_wrap7z(self) -> None:
        from unzipwalk.wrap7z import Py7zBytesIO, SingleBytesIOFactory  # pylint: disable=import-outside-toplevel
        pio = Py7zBytesIO(io.BytesIO(b'abc'))
        self.assertEqual(pio.size(), 3)
        self.assertEqual(pio.read(), b'abc')
        pio.flush()
        fact = SingleBytesIOFactory()
        with self.assertRaises(TypeError):
            fact.create(123)  # type: ignore[arg-type]

    def test_archive_re(self) -> None:
        for f in EXPECT + EXPECT_7Z:
            if f.typ == FileType.ARCHIVE:
                self.assertRegex(f.fns[-1].name, uut.ARCHIVE_RE)
            else:
                self.assertNotRegex(f.fns[-1].name, uut.ARCHIVE_RE)
