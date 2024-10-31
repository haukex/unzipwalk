# pylint: disable=too-many-lines
"""
Tests for :mod:`unzipwalk`
==========================

Author, Copyright, and License
------------------------------

Copyright (c) 2022-2024 Hauke Dämpfling (haukex@zero-g.net)
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
import shutil
import hashlib
import doctest
import unittest
from hashlib import sha1
from copy import deepcopy
from lzma import LZMAError
from gzip import BadGzipFile
from tarfile import TarError
from zipfile import BadZipFile
from unittest.mock import patch
from typing import Optional, cast
from tempfile import TemporaryDirectory, TemporaryFile
from contextlib import redirect_stdout, redirect_stderr
from pathlib import PurePath, Path, PurePosixPath, PureWindowsPath
from unzipwalk import FileType
import unzipwalk as uut
#TODO: py7zr 1.0.0 should add support for 3.13: https://github.com/miurahr/py7zr/issues/602
# When that happens, we can adjust the corresponding cover-... comments such as the following.
# (Also adjust dev/requirements.txt)
try:  # cover-req-lt3.13
    import py7zr  # pyright: ignore [reportMissingImports]
    import py7zr.exceptions  # pyright: ignore [reportMissingImports]
except (ImportError, OSError):  # cover-req-ge3.13  # cover-only-win32
    py7zr = None  # type: ignore[assignment,unused-ignore]

ResultType = tuple[ tuple[PurePath, ...], Optional[bytes], FileType ]

EXPECT :tuple[ResultType, ...] = (
    ( (Path("test.csv"),), b'"ID","Name","Age"\n1,"Foo",23\n2,"Bar",45\n3,"Quz",67\n', FileType.FILE ),

    ( (Path("WinTest.ZIP"),), None, FileType.ARCHIVE ),
    ( (Path("WinTest.ZIP"), PurePosixPath("Foo.txt")),
        b"Foo\r\nBar\r\n", FileType.FILE ),
    # Note the WinTest.ZIP doesn't contain an entry for the "World/" dir
    # (this zip was created with Windows Explorer, everything else on Linux)
    ( (Path("WinTest.ZIP"), PurePosixPath("World/Hello.txt")),
        b"Hello\r\nWorld", FileType.FILE ),

    ( (Path("archive.tar.gz"),), None, FileType.ARCHIVE ),
    ( (Path("archive.tar.gz"), PurePosixPath("archive/")), None, FileType.DIR ),
    ( (Path("archive.tar.gz"), PurePosixPath("archive/abc.zip")), None, FileType.ARCHIVE ),
    ( (Path("archive.tar.gz"), PurePosixPath("archive/abc.zip"), PurePosixPath("abc.txt")),
        b"One two three\nfour five six\nseven eight nine\n", FileType.FILE ),
    ( (Path("archive.tar.gz"), PurePosixPath("archive/abc.zip"), PurePosixPath("def.txt")),
        b"3.14159\n", FileType.FILE ),
    ( (Path("archive.tar.gz"), PurePosixPath("archive/iii.dat")),
        b"jjj\nkkk\nlll\n", FileType.FILE ),
    ( (Path("archive.tar.gz"), PurePosixPath("archive/world.txt.gz")), None, FileType.ARCHIVE ),
    ( (Path("archive.tar.gz"), PurePosixPath("archive/world.txt.gz"), PurePosixPath("archive/world.txt")),
        b"This is a file\n", FileType.FILE ),
    ( (Path("archive.tar.gz"), PurePosixPath("archive/xyz.txt")),
        b"XYZ!\n", FileType.FILE ),
    ( (Path("archive.tar.gz"), PurePosixPath("archive/fifo")), None, FileType.OTHER ),
    ( (Path("archive.tar.gz"), PurePosixPath("archive/test2/")), None, FileType.DIR ),
    ( (Path("archive.tar.gz"), PurePosixPath("archive/test2/jjj.dat")), None, FileType.SYMLINK ),

    ( (Path("linktest.zip"),), None, FileType.ARCHIVE ),
    ( (Path("linktest.zip"), PurePosixPath("linktest/") ), None, FileType.DIR ),
    ( (Path("linktest.zip"), PurePosixPath("linktest/hello.txt")),
        b"Hi there\n", FileType.FILE ),
    ( (Path("linktest.zip"), PurePosixPath("linktest/world.txt")), None, FileType.SYMLINK ),

    ( (Path("more.zip"),), None, FileType.ARCHIVE ),
    ( (Path("more.zip"), PurePosixPath("more/")), None, FileType.DIR ),
    ( (Path("more.zip"), PurePosixPath("more/stuff/")), None, FileType.DIR ),
    ( (Path("more.zip"), PurePosixPath("more/stuff/five.txt")),
        b"5\n5\n5\n5\n5\n", FileType.FILE ),
    ( (Path("more.zip"), PurePosixPath("more/stuff/six.txt")),
        b"6\n6\n6\n6\n6\n6\n", FileType.FILE ),
    ( (Path("more.zip"), PurePosixPath("more/stuff/four.txt")),
        b"4\n4\n4\n4\n", FileType.FILE ),
    ( (Path("more.zip"), PurePosixPath("more/stuff/texts.tgz")), None, FileType.ARCHIVE ),
    ( (Path("more.zip"), PurePosixPath("more/stuff/texts.tgz"), PurePosixPath("one.txt")),
        b"111\n11\n1\n", FileType.FILE ),
    ( (Path("more.zip"), PurePosixPath("more/stuff/texts.tgz"), PurePosixPath("two.txt")),
        b"2222\n222\n22\n2\n", FileType.FILE ),
    ( (Path("more.zip"), PurePosixPath("more/stuff/texts.tgz"), PurePosixPath("three.txt")),
        b"33333\n3333\n333\n33\n3\n", FileType.FILE ),
    ( (Path("more.zip"), PurePosixPath("more/stuff/xyz.7z")), None, FileType.ARCHIVE ),

    ( (Path("opt.7z"),), None, FileType.ARCHIVE ),

    ( (Path("subdir"),), None, FileType.DIR ),
    ( (Path("subdir","ooo.txt"),),
        b"oOoOoOo\n\n", FileType.FILE ),
    ( (Path("subdir","foo.zip"), PurePosixPath("hello.txt")),
        b"Hallo\nWelt\n", FileType.FILE ),
    ( (Path("subdir","foo.zip"),), None, FileType.ARCHIVE ),
    ( (Path("subdir","foo.zip"), PurePosixPath("foo/")), None, FileType.DIR ),
    ( (Path("subdir","foo.zip"), PurePosixPath("foo/bar.txt")),
        b"Blah\nblah\n", FileType.FILE ),

    ( (Path("subdir","formats.tar.bz2"),), None, FileType.ARCHIVE ),
    ( (Path("subdir","formats.tar.bz2"), PurePosixPath("formats/")), None, FileType.DIR ),
    ( (Path("subdir","formats.tar.bz2"), PurePosixPath("formats/lzma.txt.xz")), None, FileType.ARCHIVE ),
    ( (Path("subdir","formats.tar.bz2"), PurePosixPath("formats/lzma.txt.xz"), PurePosixPath("formats/lzma.txt")),
        b'Another format!\n', FileType.FILE ),
    ( (Path("subdir","formats.tar.bz2"), PurePosixPath("formats/bzip2.txt.bz2")), None, FileType.ARCHIVE ),
    ( (Path("subdir","formats.tar.bz2"), PurePosixPath("formats/bzip2.txt.bz2"), PurePosixPath("formats/bzip2.txt")),
        b'And another!\n', FileType.FILE ),
)
EXPECT_7Z :tuple[ResultType, ...] = (
    ( (Path("more.zip"), PurePosixPath("more/stuff/xyz.7z"), PurePosixPath("even.txt")),
        b"Adding", FileType.FILE ),
    ( (Path("more.zip"), PurePosixPath("more/stuff/xyz.7z"), PurePosixPath("more")),
        None, FileType.DIR ),
    ( (Path("more.zip"), PurePosixPath("more/stuff/xyz.7z"), PurePosixPath("more/stuff.txt")),
        b"Testing\r\nTesting", FileType.FILE ),

    ( (Path("opt.7z"), PurePosixPath("thing")), None, FileType.DIR ),
    ( (Path("opt.7z"), PurePosixPath("thing/wuv.tgz")), None, FileType.ARCHIVE ),
    ( (Path("opt.7z"), PurePosixPath("thing/wuv.tgz"), PurePosixPath("uvw.txt")),
        b"This\nis\na\n7z\ntest\n", FileType.FILE ),
)

def load_tests(_loader, tests, _ignore):
    globs :dict = {}
    def doctest_setup(_t :doctest.DocTest):
        globs['_prev_dir'] = os.getcwd()
        os.chdir( Path(__file__).parent/'doctest_wd' )
    def doctest_teardown(_t :doctest.DocTest):
        os.chdir( globs['_prev_dir'] )
        del globs['_prev_dir']
    tests.addTests(doctest.DocTestSuite(uut, setUp=doctest_setup, tearDown=doctest_teardown, globs=globs))
    return tests

class UnzipWalkTestCase(unittest.TestCase):

    def setUp(self):
        self.bad_zips = Path(__file__).parent.resolve()/'bad_zips'
        self.maxDiff = None  # pylint: disable=invalid-name
        self.tempdir = TemporaryDirectory()  # pylint: disable=consider-using-with
        testdir = Path(self.tempdir.name)/'zips'
        shutil.copytree( Path(__file__).parent.resolve()/'zips', testdir, symlinks=True )
        self.prev_dir = os.getcwd()
        os.chdir( testdir )
        self.expect_all :list[ResultType] = list( deepcopy( EXPECT + (EXPECT_7Z if py7zr else ()) ) )
        if not sys.platform.startswith('win32'):  # cover-not-win32
            (testdir/'baz.zip').symlink_to('more.zip')
            self.expect_all.append( ( (Path("baz.zip"),), None, FileType.SYMLINK ) )
            os.mkfifo(testdir/'xy.fifo')  # pyright: ignore [reportAttributeAccessIssue]  # pylint: disable=no-member,useless-suppression
            self.expect_all.append( ( (Path("xy.fifo"),), None, FileType.OTHER ) )
        else:  # cover-only-win32
            print("Skipping symlink and fifo tests", file=sys.stderr)
        self.expect_all.sort()

    def tearDown(self):
        os.chdir( self.prev_dir )
        self.tempdir.cleanup()

    def test_unzipwalk(self):
        self.assertEqual( self.expect_all,
            sorted( (r.names, None if r.hnd is None else r.hnd.read(), r.typ) for r in uut.unzipwalk(os.curdir) ) )

    def test_unzipwalk_no7z(self):
        try:  # temporarily clobber the import
            uut.py7zr = None  # type: ignore[attr-defined,assignment,unused-ignore]

            self.assertEqual( [ x for x in self.expect_all if x not in EXPECT_7Z ],
                sorted( (r.names, None if r.hnd is None else r.hnd.read(), r.typ) for r in uut.unzipwalk(os.curdir) ) )

            with self.assertRaises(ImportError):
                with uut.recursive_open((Path("more.zip"), PurePosixPath("more/stuff/xyz.7z"), PurePosixPath("even.txt"))):
                    pass  # pragma: no cover

        finally:
            uut.py7zr = py7zr  # type: ignore[attr-defined]

    def test_unzipwalk_errs(self):
        with self.assertRaises(FileNotFoundError):
            list(uut.unzipwalk('/this_file_should_not_exist'))

    def test_unzipwalk_matcher(self):
        # filter from the initial path list
        self.assertEqual( sorted(
                [ r for r in self.expect_all if r[0][0].name != 'more.zip' ] + [ ( (Path("more.zip"),), None, FileType.SKIP ) ]
            ), sorted( (r.names, None if r.hnd is None else r.hnd.read(), r.typ) for r
                in uut.unzipwalk(os.curdir, matcher=lambda p: p[0].stem.lower()!='more' ) ) )
        # filter from zip file
        self.assertEqual( sorted(
                [ r for r in self.expect_all if r[0][-1].name != 'six.txt' ]
                + [ ( (Path("more.zip"), PurePosixPath("more/stuff/six.txt")), None, FileType.SKIP ) ]
            ), sorted( (r.names, None if r.hnd is None else r.hnd.read(), r.typ) for r
                in uut.unzipwalk(os.curdir, matcher=lambda p: p[-1].name.lower()!='six.txt' ) ) )
        # filter a gz file
        self.assertEqual( sorted(
                [ r for r in self.expect_all if not ( r[0][0].name=='archive.tar.gz' and len(r[0])>1 and r[0][1].name == 'world.txt.gz' ) ]
                + [ ( (Path("archive.tar.gz"), PurePosixPath("archive/world.txt.gz")), None, FileType.SKIP ) ]
            ), sorted( (r.names, None if r.hnd is None else r.hnd.read(), r.typ) for r
                in uut.unzipwalk(os.curdir, matcher=lambda p: len(p)<2 or p[-2].as_posix()!='archive/world.txt.gz' ) ) )
        # filter a bz2 file
        self.assertEqual( sorted(
                [ r for r in self.expect_all if not ( r[0][0].name=='formats.tar.bz2' and len(r[0])>1 and r[0][1].name == 'bzip2.txt.bz2' ) ]
                + [ ( (Path("subdir","formats.tar.bz2"), PurePosixPath("formats/bzip2.txt.bz2")), None, FileType.SKIP ) ]
            ), sorted( (r.names, None if r.hnd is None else r.hnd.read(), r.typ) for r
                in uut.unzipwalk(os.curdir, matcher=lambda p: len(p)<2 or p[-2].as_posix()!='formats/bzip2.txt.bz2' ) ) )
        # filter a xz file
        self.assertEqual( sorted(
                [ r for r in self.expect_all if not ( r[0][0].name=='formats.tar.bz2' and len(r[0])>1 and r[0][1].name == 'lzma.txt.xz' ) ]
                + [ ( (Path("subdir","formats.tar.bz2"), PurePosixPath("formats/lzma.txt.xz")), None, FileType.SKIP ) ]
            ), sorted( (r.names, None if r.hnd is None else r.hnd.read(), r.typ) for r
                in uut.unzipwalk(os.curdir, matcher=lambda p: len(p)<2 or p[-2].as_posix()!='formats/lzma.txt.xz' ) ) )
        # filter from tar file
        self.assertEqual( sorted(
                [ r for r in self.expect_all if not ( len(r[0])>1 and r[0][1].stem=='abc' ) ]
                + [ ( (Path("archive.tar.gz"), PurePosixPath("archive/abc.zip")), None, FileType.SKIP ) ]
            ), sorted( (r.names, None if r.hnd is None else r.hnd.read(), r.typ) for r
                in uut.unzipwalk(os.curdir, matcher=lambda p: p[-1].name != 'abc.zip' ) ) )
        if py7zr:  # cover-req-lt3.13
            # filter a file from 7z file
            self.assertEqual( sorted(
                    [ r for r in self.expect_all if not ( r[0][0].name=='opt.7z' and len(r[0])>1 and r[0][1].name=='wuv.tgz' ) ]
                    + [ ( (Path("opt.7z"), PurePosixPath("thing/wuv.tgz")), None, FileType.SKIP ), ]
                ), sorted( (r.names, None if r.hnd is None else r.hnd.read(), r.typ) for r
                    in uut.unzipwalk(os.curdir, matcher=lambda p: p[-1].name != 'wuv.tgz' ) ) )
            # filter a directory from a 7z file
            self.assertEqual( sorted(
                    [ r for r in self.expect_all if not ( r[0][0].name=='opt.7z' and len(r[0])>1 ) ]
                    + [ ( (Path("opt.7z"), PurePosixPath("thing")), None, FileType.SKIP ),
                        ( (Path("opt.7z"), PurePosixPath("thing/wuv.tgz")), None, FileType.SKIP ), ]
                ), sorted( (r.names, None if r.hnd is None else r.hnd.read(), r.typ) for r
                    in uut.unzipwalk(os.curdir, matcher=lambda p: not ( len(p)>1 and p[1].parts[0] == 'thing' ) ) ) )

    def test_recursive_open(self):
        for file in self.expect_all:
            if file[2] == FileType.FILE:
                with uut.recursive_open(file[0]) as fh:
                    self.assertEqual( fh.read(), file[1] )
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
            with uut.recursive_open(("subdir/formats.tar.bz2","formats/bzip2.txt.bz2","formats/blam.txt")):
                pass  # pragma: no cover
        # xz bad filename
        with self.assertRaises(FileNotFoundError):
            with uut.recursive_open(("subdir/formats.tar.bz2","formats/lzma.txt.xz","formats/blam.txt")):
                pass  # pragma: no cover
        # TarFile.extractfile: attempt to open a directory
        with self.assertRaises(FileNotFoundError):
            with uut.recursive_open(("archive.tar.gz", "archive/test2/")):
                pass  # pragma: no cover
        if py7zr:  # cover-req-lt3.13
            # 7z bad filename
            with self.assertRaises(FileNotFoundError):
                with uut.recursive_open(("opt.7z", "bang")):
                    pass  # pragma: no cover

    def test_result_validate(self):
        with self.assertRaises(ValueError):
            uut.UnzipWalkResult((), FileType.OTHER, None).validate()
        with self.assertRaises(TypeError):
            uut.UnzipWalkResult(('foo',), FileType.OTHER, None).validate()  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            uut.UnzipWalkResult((Path(),), 'foo', None).validate()  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            uut.UnzipWalkResult((Path(),), FileType.FILE, None).validate()
        with self.assertRaises(TypeError):
            with TemporaryFile() as tf:
                uut.UnzipWalkResult((Path(),), FileType.OTHER, cast(uut.ReadOnlyBinary, tf)).validate()

    def test_checksum_lines(self):
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
            typ=FileType.FILE, hnd=cast(uut.ReadOnlyBinary, io.BytesIO(b'abcdef')))
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
            uut.UnzipWalkResult.from_checksum_line("e80b5017098950fc58aad83c8c14978g *blam")
        with self.assertRaises(ValueError):
            uut.UnzipWalkResult.from_checksum_line("e80b5017098950fc58aad83c8c14978e *(blam")

    def test_decode_tuple(self):
        self.assertEqual( uut.decode_tuple(repr(('hi',))), ('hi',) )
        self.assertEqual( uut.decode_tuple(repr(('hi','there'))), ('hi','there') )
        self.assertEqual( uut.decode_tuple('( "foo" , \'bar\' ) '), ('foo','bar') )
        self.assertEqual( uut.decode_tuple("('hello',)"), ('hello',) )
        self.assertEqual( uut.decode_tuple('"foo","bar"'), ('foo','bar') )
        with self.assertRaises(ValueError):
            uut.decode_tuple('')
        with self.assertRaises(ValueError):
            uut.decode_tuple('X=("foo",)')
        with self.assertRaises(ValueError):
            uut.decode_tuple('(')
        with self.assertRaises(ValueError):
            uut.decode_tuple('()')
        with self.assertRaises(ValueError):
            uut.decode_tuple('("foo")')
        with self.assertRaises(ValueError):
            uut.decode_tuple('("foo","bar",3)')
        with self.assertRaises(ValueError):
            uut.decode_tuple('("foo","bar",str)')
        with self.assertRaises(ValueError):
            uut.decode_tuple('("foo","bar","x"+"y")')
        with self.assertRaises(ValueError):
            uut.decode_tuple('["foo","bar"]')

    def test_errors(self):
        with self.assertRaises(BadZipFile):
            list(uut.unzipwalk(self.bad_zips/'not_a.zip'))
        with self.assertRaises(TarError):
            list(uut.unzipwalk(self.bad_zips/'not_a.tgz'))
        with self.assertRaises(BadGzipFile):
            list(uut.unzipwalk(self.bad_zips/'not_a.tgz.gz'))
        with self.assertRaises(EOFError):
            list(uut.unzipwalk(self.bad_zips/'not_a.tgz.bz2'))
        with self.assertRaises(BadZipFile):
            list(uut.unzipwalk(self.bad_zips/'not_a.zip.gz'))
        with self.assertRaises(BadZipFile):
            list(uut.unzipwalk(self.bad_zips/'not_a.zip.bz2'))
        with self.assertRaises(LZMAError):
            list(uut.unzipwalk(self.bad_zips/'not_a.zip.xz'))
        if py7zr:  # cover-req-lt3.13
            with self.assertRaises(py7zr.exceptions.ArchiveError):
                list(uut.unzipwalk(self.bad_zips/'not_a.7z'))
            with self.assertRaises(py7zr.exceptions.ArchiveError):
                list(uut.unzipwalk(self.bad_zips/'bad.7z'))
            with self.assertRaises(FileExistsError):
                list(uut.unzipwalk(self.bad_zips/'double.7z'))
        with self.assertRaises(RuntimeError):
            list(uut.unzipwalk(self.bad_zips/'features.zip'))
        # the following is commented out due to https://github.com/python/cpython/issues/120740
        #with self.assertRaises(TarError):
        #    list(uut.unzipwalk(pth/'bad.tar.gz'))
        self.assertEqual( sorted(
               (r.names, None if r.hnd is None or r.names[0].name in ('not_a.gz','not_a.bz2','not_a.xz') else r.hnd.read(), r.typ)
               for r in uut.unzipwalk( (self.bad_zips, Path('does_not_exist')) , raise_errors=False) ),
            sorted( [
                 ( (Path("does_not_exist"),), None, FileType.ERROR ),
                 ( (self.bad_zips/"not_a.gz",), None, FileType.ARCHIVE ),
                 ( (self.bad_zips/"not_a.gz", self.bad_zips/"not_a"), None, FileType.FILE ),  # no error until the file is read (tested below)
                 ( (self.bad_zips/"not_a.bz2",), None, FileType.ARCHIVE ),
                 ( (self.bad_zips/"not_a.bz2", self.bad_zips/"not_a"), None, FileType.FILE ),  # no error until the file is read (tested below)
                 ( (self.bad_zips/"not_a.xz",), None, FileType.ARCHIVE ),
                 ( (self.bad_zips/"not_a.xz", self.bad_zips/"not_a"), None, FileType.FILE ),  # no error until the file is read (tested below)
                 ( (self.bad_zips/"not_a.tar",), None, FileType.ERROR ),
                 ( (self.bad_zips/"not_a.tar.gz",), None, FileType.ERROR ),
                 ( (self.bad_zips/"not_a.tgz",), None, FileType.ERROR ),
                 ( (self.bad_zips/"not_a.zip",), None, FileType.ERROR ),
                 ( (self.bad_zips/"not_a.tgz.gz",), None, FileType.ERROR ),
                 ( (self.bad_zips/"not_a.tgz.bz2",), None, FileType.ERROR ),
                 ( (self.bad_zips/"not_a.zip.gz",), None, FileType.ARCHIVE ),
                 ( (self.bad_zips/"not_a.zip.gz", self.bad_zips/"not_a.zip"), None, FileType.ERROR ),
                 ( (self.bad_zips/"not_a.zip.bz2",), None, FileType.ARCHIVE ),
                 ( (self.bad_zips/"not_a.zip.bz2", self.bad_zips/"not_a.zip"), None, FileType.ERROR ),
                 ( (self.bad_zips/"not_a.zip.xz",), None, FileType.ERROR ),
                 ( (self.bad_zips/"features.zip",), None, FileType.ARCHIVE ),
                 ( (self.bad_zips/"features.zip", PurePosixPath("spiral.pl")), None, FileType.ERROR ),  # unsupported compression method
                 ( (self.bad_zips/"features.zip", PurePosixPath("foo.txt")), b'Top Secret\n', FileType.FILE ),
                 ( (self.bad_zips/"features.zip", PurePosixPath("bar.txt")), None, FileType.ERROR ),  # encrypted
                 ( (self.bad_zips/"bad.tar.gz",), None, FileType.ARCHIVE ),
                 ( (self.bad_zips/"bad.tar.gz", PurePosixPath("a")), b'One\n', FileType.FILE ),
                 # the following is commented out due to https://github.com/python/cpython/issues/120740
                 #( (pth/"bad.tar.gz", PurePosixPath("b")), None, FileType.ERROR ),  # bad checksum
                 #( (pth/"bad.tar.gz", PurePosixPath("c")), b'Three\n', FileType.FILE ),
                 ( (self.bad_zips/"double.7z",), None, FileType.ARCHIVE ),
                 ( (self.bad_zips/"bad.7z",), None, FileType.ARCHIVE ),
            ] + (
                [
                 ( (self.bad_zips/"double.7z", PurePosixPath("bar.txt")), None, FileType.ERROR ),
                 ( (self.bad_zips/"double.7z", PurePosixPath("bar.txt")), None, FileType.ERROR ),
                 ( (self.bad_zips/"bad.7z", PurePosixPath("broken.txt")), None, FileType.ERROR ),  # bad checksum
                 ( (self.bad_zips/"not_a.7z",), None, FileType.ERROR ),
                ] if py7zr else [
                 ( (self.bad_zips/"not_a.7z",), None, FileType.ARCHIVE ),
                ]) ) )
        with self.assertRaises(BadGzipFile):
            for r in uut.unzipwalk((self.bad_zips/'not_a.gz'), raise_errors=False):  # pragma: no branch
                if r.hnd is not None:  # pragma: no branch
                    r.hnd.read()
        with self.assertRaises(OSError):
            for r in uut.unzipwalk((self.bad_zips/'not_a.bz2'), raise_errors=False):  # pragma: no branch
                if r.hnd is not None:  # pragma: no branch
                    r.hnd.read()
        with self.assertRaises(LZMAError):
            for r in uut.unzipwalk((self.bad_zips/'not_a.xz'), raise_errors=False):  # pragma: no branch
                if r.hnd is not None:  # pragma: no branch
                    r.hnd.read()
        if py7zr:  # cover-req-lt3.13
            with self.assertRaises(FileExistsError):
                with uut.recursive_open((self.bad_zips/"double.7z", "bar.txt")):
                    pass  # pragma: no cover

    @unittest.skipIf(condition=not sys.platform.startswith('linux'), reason='only on Linux')
    def test_errors_linux(self):  # cover-only-linux
        with TemporaryDirectory() as td:
            f = Path(td)/'foo'
            f.touch()
            f.chmod(0)
            with self.assertRaises(PermissionError):
                list(uut.unzipwalk(td))
            self.assertEqual(
                sorted( (r.names, None if r.hnd is None else r.hnd.read(), r.typ) for r in uut.unzipwalk(td, raise_errors=False) ),
                sorted( [ ( (f,), None, FileType.ERROR ), ] ) )

    def _run_cli(self, argv :list[str]) -> list[str]:
        sys.argv = [os.path.basename(uut.__file__)] + argv
        with (redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err,
              patch('argparse.ArgumentParser.exit', side_effect=SystemExit) as mock_exit):
            try:
                uut.main()
            except SystemExit:
                pass
        mock_exit.assert_called_once_with(0)
        self.assertEqual(err.getvalue(), '')
        lines = out.getvalue().splitlines()
        lines.sort()
        return lines

    def test_cli(self):
        exp_basic = sorted( f"FILE {tuple(str(n) for n in e[0])!r}" for e in self.expect_all if e[2]==FileType.FILE )
        self.assertEqual( self._run_cli([]), exp_basic )  # basic
        with TemporaryDirectory() as td:  # --outfile
            tf = Path(td)/'foo'
            self.assertEqual( self._run_cli(['--outfile', str(tf)]), [] )
            with tf.open(encoding='UTF-8') as fh:
                self.assertEqual( sorted(fh.read().splitlines()), exp_basic )
        self.assertEqual( self._run_cli(['--all-files']), sorted(  # basic + all-files
            f"{e[2].name} {tuple(str(n) for n in e[0])!r}" for e in self.expect_all ) )
        self.assertEqual( self._run_cli(['--dump']), sorted(  # dump
            f"FILE {tuple(str(n) for n in e[0])!r} {e[1]!r}" for e in self.expect_all if e[2]==FileType.FILE ) )
        self.assertEqual( self._run_cli(['-da']), sorted(  # dump + all-files
            f"FILE {tuple(str(n) for n in e[0])!r} {e[1]!r}" if e[2]==FileType.FILE
            else f"{e[2].name} {tuple(str(n) for n in e[0])!r}" for e in self.expect_all ) )
        self.assertEqual( self._run_cli(['--checksum','sha256']), sorted(  # checksum
            f"{hashlib.sha256(e[1]).hexdigest()} *{str(e[0][0]) if len(e[0])==1 else repr(tuple(str(n) for n in e[0]))}"
            for e in self.expect_all if e[1] is not None ) )
        self.assertEqual( self._run_cli(['-a','-csha512']), sorted(  # checksum + all-files
            (f"# {e[2].name} " if e[1] is None else f"{hashlib.sha512(e[1]).hexdigest()} *")
            + f"{str(e[0][0]) if len(e[0])==1 else repr(tuple(str(n) for n in e[0]))}"
            for e in self.expect_all ) )
        self.assertEqual( self._run_cli(['-e','world.*','--exclude=*abc*']), sorted(  # exclude
            f"FILE {tuple(str(n) for n in e[0])!r}" for e in self.expect_all if e[2]==FileType.FILE
            and not ( e[0][-1].name.startswith('world.') or len(e[0])>1 and e[0][1].name=='abc.zip' ) ) )

    def test_cli_errors(self):
        os.chdir(self.bad_zips)
        self.assertEqual( self._run_cli(['-d','.','does_not_exist']), sorted( [
            "ERROR ('does_not_exist',)",
            "ERROR ('not_a.gz', 'not_a')",
            "ERROR ('not_a.bz2', 'not_a')",
            "ERROR ('not_a.xz', 'not_a')",
            "ERROR ('not_a.tar',)",
            "ERROR ('not_a.tar.gz',)",
            "ERROR ('not_a.tgz',)",
            "ERROR ('not_a.zip',)",
            "ERROR ('not_a.tgz.gz',)",
            "ERROR ('not_a.tgz.bz2',)",
            "ERROR ('not_a.zip.gz', 'not_a.zip')",
            "ERROR ('not_a.zip.bz2', 'not_a.zip')",
            "ERROR ('not_a.zip.xz',)",
            "ERROR ('features.zip', 'spiral.pl')",
            "ERROR ('features.zip', 'bar.txt')",
            "FILE ('features.zip', 'foo.txt') b'Top Secret\\n'",
            "FILE ('bad.tar.gz', 'a') b'One\\n'",
            # the following is commented out due to https://github.com/python/cpython/issues/120740
            #"ERROR ('bad.tar.gz', 'b')",
            #"FILE ('bad.tar.gz', 'c') b'Three\\n'",
        ] + ([
            "ERROR ('bad.7z', 'broken.txt')",
            "ERROR ('double.7z', 'bar.txt')",
            "ERROR ('double.7z', 'bar.txt')",
            "ERROR ('not_a.7z',)",
        ] if py7zr else []) ) )
        self.assertEqual( self._run_cli(['-cmd5','.','does_not_exist']), sorted( [
            "# ERROR does_not_exist",
            "# ERROR ('not_a.gz', 'not_a')",
            "# ERROR ('not_a.bz2', 'not_a')",
            "# ERROR ('not_a.xz', 'not_a')",
            "# ERROR not_a.tar",
            "# ERROR not_a.tar.gz",
            "# ERROR not_a.tgz",
            "# ERROR not_a.zip",
            "# ERROR not_a.tgz.gz",
            "# ERROR not_a.tgz.bz2",
            "# ERROR ('not_a.zip.gz', 'not_a.zip')",
            "# ERROR ('not_a.zip.bz2', 'not_a.zip')",
            "# ERROR not_a.zip.xz",
            "# ERROR ('features.zip', 'spiral.pl')",
            "# ERROR ('features.zip', 'bar.txt')",
            "f0294cd41b8a0a0c403911bb212d9edf *('features.zip', 'foo.txt')",
            "b602183573352abf933bc7ca85fd0629 *('bad.tar.gz', 'a')",
            # the following is commented out due to https://github.com/python/cpython/issues/120740
            #"# ERROR ('bad.tar.gz', 'b')",
            #"38a460ffb4cfb15460b4b679ce534181 *('bad.tar.gz', 'c')",
        ] + ([
            "# ERROR not_a.7z",
            "# ERROR ('bad.7z', 'broken.txt')",
            "# ERROR ('double.7z', 'bar.txt')",
            "# ERROR ('double.7z', 'bar.txt')",
        ] if py7zr else []) ) )
        with self.assertRaises(BadGzipFile):
            self._run_cli(['-rd','not_a.gz'])
        with self.assertRaises(BadGzipFile):
            self._run_cli(['-rcmd5','not_a.gz'])
        with self.assertRaises(BadZipFile):
            self._run_cli(['-r','not_a.zip'])
        with self.assertRaises(TarError):
            self._run_cli(['-r','not_a.tgz'])
        with self.assertRaises(RuntimeError):
            self._run_cli(['-r','features.zip'])
