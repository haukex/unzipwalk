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
from unittest.mock import patch
from typing import Optional, cast
from tempfile import TemporaryDirectory, TemporaryFile
from pathlib import PurePath, Path, PurePosixPath
from contextlib import redirect_stdout, redirect_stderr
from unzipwalk import FileType
import unzipwalk as uut

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
    ( (Path("subdir"),), None, FileType.DIR ),
    ( (Path("subdir","ooo.txt"),),
        b"oOoOoOo\n\n", FileType.FILE ),
    ( (Path("subdir","foo.zip"), PurePosixPath("hello.txt")),
        b"Hallo\nWelt\n", FileType.FILE ),
    ( (Path("subdir","foo.zip"),), None, FileType.ARCHIVE ),
    ( (Path("subdir","foo.zip"), PurePosixPath("foo/")), None, FileType.DIR ),
    ( (Path("subdir","foo.zip"), PurePosixPath("foo/bar.txt")),
        b"Blah\nblah\n", FileType.FILE ),
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
        self.maxDiff = None  # pylint: disable=invalid-name
        self.tempdir = TemporaryDirectory()  # pylint: disable=consider-using-with
        testdir = Path(self.tempdir.name)/'zips'
        shutil.copytree( Path(__file__).parent.resolve()/'zips', testdir, symlinks=True )
        self.prev_dir = os.getcwd()
        os.chdir( testdir )
        self.expect_all :list[ResultType] = list( deepcopy( EXPECT ) )
        #TODO Later: Use a coverage plugin for OS-dependent coverage pragmas
        try:
            (testdir/'baz.zip').symlink_to('more.zip')
            self.expect_all.append( ( (Path("baz.zip"),), None, FileType.SYMLINK ) )  # pragma: no cover  (doesn't run on Windows)
        except OSError as ex:  # pragma: no cover  (only runs on Windows)
            print(f"Skipping symlink test ({ex})", file=sys.stderr)
        if hasattr(os, 'mkfifo'):  # pragma: no cover  (doesn't run on Windows)
            os.mkfifo(testdir/'xy.fifo')  # pyright: ignore [reportAttributeAccessIssue]
            self.expect_all.append( ( (Path("xy.fifo"),), None, FileType.OTHER ) )
        else:  # pragma: no cover  (only runs on Windows)
            print("Skipping fifo test (no mkfifo)", file=sys.stderr)
        self.expect_all.sort()

    def tearDown(self):
        os.chdir( self.prev_dir )
        self.tempdir.cleanup()

    def test_unzipwalk(self):
        self.assertEqual( self.expect_all,
            sorted( (r.names, None if r.hnd is None else r.hnd.read(), r.typ) for r in uut.unzipwalk(os.curdir) ) )

    def test_unzipwalk_errs(self):
        with self.assertRaises(FileNotFoundError):
            list(uut.unzipwalk('/this_file_should_not_exist'))

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
            with uut.recursive_open(()): pass
        # gzip bad filename
        with self.assertRaises(FileNotFoundError):
            with uut.recursive_open(("archive.tar.gz", "archive/world.txt.gz", "archive/bang.txt")): pass
        # TarFile.extractfile: attempt to open a directory
        with self.assertRaises(FileNotFoundError):
            with uut.recursive_open(("archive.tar.gz", "archive/test2/")): pass

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
        self.assertEqual( self._run_cli([]), sorted(  # basic
            f"FILE {tuple(str(n) for n in e[0])!r}" for e in self.expect_all if e[2]==FileType.FILE ) )
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
