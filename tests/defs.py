"""
Definitions for Tests for :mod:`unzipwalk`
==========================================

Author, Copyright, and License
------------------------------

Copyright (c) 2022-2025 Hauke Dämpfling (haukex@zero-g.net)
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
import sys
import shutil
import importlib
from copy import deepcopy
from contextlib import contextmanager
from tempfile import TemporaryDirectory
from typing import Optional, NamedTuple
from pathlib import PurePath, Path, PurePosixPath
from igbpyutils.file import Pushd
from unzipwalk import FileType, UnzipWalkResult

# spell-checker: ignore linktest nlll Pushd mkfifo

# py7zr 1.0.0 supports 3.13, but not 3.14: https://github.com/miurahr/py7zr/issues/683
# When it does, we can adjust the corresponding cover-... comments (and dev/requirements.txt)
def _try_py7zr() -> Optional[Exception]:
    """Returns an :exc:`py7zr.exceptions.ArchiveError` instance, or :obj:`None` if _:mod:`py7zr` is not installed.
    NOTE this is also used by the tests as a flag to check if :mod:`py7zr` is installed or not."""
    try:  # cover-req-lt3.14  # pylint: disable=no-else-return
        m = importlib.import_module('py7zr.exceptions')
    except (ImportError, OSError):  # cover-req-ge3.14
        return None
    else:  # cover-req-lt3.14
        ex = getattr(m, 'ArchiveError')()
        assert isinstance(ex, Exception)
        return ex
P7Z_EX = _try_py7zr()

BAD_ZIPS = Path(__file__).parent.resolve()/'bad_zips'

class ExpectedResult(NamedTuple):
    fns :tuple[PurePath, ...]
    data :Optional[bytes]
    typ :FileType

def r2e(r :UnzipWalkResult) -> ExpectedResult:
    """Helper function for tests to simplify comparisons."""
    return ExpectedResult(fns=r.names, data=None if r.hnd is None else r.hnd.read(), typ=r.typ)

EXPECT :tuple[ExpectedResult, ...] = (
    ExpectedResult( (Path("test.csv"),), b'"ID","Name","Age"\n1,"Foo",23\n2,"Bar",45\n3,"Quz",67\n', FileType.FILE ),

    ExpectedResult( (Path("WinTest.ZIP"),), None, FileType.ARCHIVE ),
    ExpectedResult( (Path("WinTest.ZIP"), PurePosixPath("Foo.txt")),
        b"Foo\r\nBar\r\n", FileType.FILE ),
    # Note the WinTest.ZIP doesn't contain an entry for the "World/" dir
    # (this zip was created with Windows Explorer, everything else on Linux)
    ExpectedResult( (Path("WinTest.ZIP"), PurePosixPath("World/Hello.txt")),
        b"Hello\r\nWorld", FileType.FILE ),

    ExpectedResult( (Path("archive.tar.gz"),), None, FileType.ARCHIVE ),
    ExpectedResult( (Path("archive.tar.gz"), PurePosixPath("archive/")), None, FileType.DIR ),
    ExpectedResult( (Path("archive.tar.gz"), PurePosixPath("archive/abc.zip")), None, FileType.ARCHIVE ),
    ExpectedResult( (Path("archive.tar.gz"), PurePosixPath("archive/abc.zip"), PurePosixPath("abc.txt")),
        b"One two three\nfour five six\nseven eight nine\n", FileType.FILE ),
    ExpectedResult( (Path("archive.tar.gz"), PurePosixPath("archive/abc.zip"), PurePosixPath("def.txt")),
        b"3.14159\n", FileType.FILE ),
    ExpectedResult( (Path("archive.tar.gz"), PurePosixPath("archive/iii.dat")),
        b"jjj\nkkk\nlll\n", FileType.FILE ),
    ExpectedResult( (Path("archive.tar.gz"), PurePosixPath("archive/world.txt.gz")), None, FileType.ARCHIVE ),
    ExpectedResult( (Path("archive.tar.gz"), PurePosixPath("archive/world.txt.gz"), PurePosixPath("archive/world.txt")),
        b"This is a file\n", FileType.FILE ),
    ExpectedResult( (Path("archive.tar.gz"), PurePosixPath("archive/xyz.txt")),
        b"XYZ!\n", FileType.FILE ),
    ExpectedResult( (Path("archive.tar.gz"), PurePosixPath("archive/fifo")), None, FileType.OTHER ),
    ExpectedResult( (Path("archive.tar.gz"), PurePosixPath("archive/test2/")), None, FileType.DIR ),
    ExpectedResult( (Path("archive.tar.gz"), PurePosixPath("archive/test2/jjj.dat")), None, FileType.SYMLINK ),

    ExpectedResult( (Path("linktest.zip"),), None, FileType.ARCHIVE ),
    ExpectedResult( (Path("linktest.zip"), PurePosixPath("linktest/") ), None, FileType.DIR ),
    ExpectedResult( (Path("linktest.zip"), PurePosixPath("linktest/hello.txt")),
        b"Hi there\n", FileType.FILE ),
    ExpectedResult( (Path("linktest.zip"), PurePosixPath("linktest/world.txt")), None, FileType.SYMLINK ),

    ExpectedResult( (Path("more.zip"),), None, FileType.ARCHIVE ),
    ExpectedResult( (Path("more.zip"), PurePosixPath("more/")), None, FileType.DIR ),
    ExpectedResult( (Path("more.zip"), PurePosixPath("more/stuff/")), None, FileType.DIR ),
    ExpectedResult( (Path("more.zip"), PurePosixPath("more/stuff/five.txt")),
        b"5\n5\n5\n5\n5\n", FileType.FILE ),
    ExpectedResult( (Path("more.zip"), PurePosixPath("more/stuff/six.txt")),
        b"6\n6\n6\n6\n6\n6\n", FileType.FILE ),
    ExpectedResult( (Path("more.zip"), PurePosixPath("more/stuff/four.txt")),
        b"4\n4\n4\n4\n", FileType.FILE ),
    ExpectedResult( (Path("more.zip"), PurePosixPath("more/stuff/texts.tgz")), None, FileType.ARCHIVE ),
    ExpectedResult( (Path("more.zip"), PurePosixPath("more/stuff/texts.tgz"), PurePosixPath("one.txt")),
        b"111\n11\n1\n", FileType.FILE ),
    ExpectedResult( (Path("more.zip"), PurePosixPath("more/stuff/texts.tgz"), PurePosixPath("two.txt")),
        b"2222\n222\n22\n2\n", FileType.FILE ),
    ExpectedResult( (Path("more.zip"), PurePosixPath("more/stuff/texts.tgz"), PurePosixPath("three.txt")),
        b"33333\n3333\n333\n33\n3\n", FileType.FILE ),
    ExpectedResult( (Path("more.zip"), PurePosixPath("more/stuff/xyz.7z")), None, FileType.ARCHIVE ),

    ExpectedResult( (Path("opt.7z"),), None, FileType.ARCHIVE ),

    ExpectedResult( (Path("subdir"),), None, FileType.DIR ),
    ExpectedResult( (Path("subdir","ooo.txt"),),
        b"oOoOoOo\n\n", FileType.FILE ),
    ExpectedResult( (Path("subdir","foo.zip"), PurePosixPath("hello.txt")),
        b"Hallo\nWelt\n", FileType.FILE ),
    ExpectedResult( (Path("subdir","foo.zip"),), None, FileType.ARCHIVE ),
    ExpectedResult( (Path("subdir","foo.zip"), PurePosixPath("foo/")), None, FileType.DIR ),
    ExpectedResult( (Path("subdir","foo.zip"), PurePosixPath("foo/bar.txt")),
        b"Blah\nblah\n", FileType.FILE ),

    ExpectedResult( (Path("subdir","formats.tar.bz2"),), None, FileType.ARCHIVE ),
    ExpectedResult( (Path("subdir","formats.tar.bz2"), PurePosixPath("formats/")), None, FileType.DIR ),
    ExpectedResult( (Path("subdir","formats.tar.bz2"), PurePosixPath("formats/lzma.txt.xz")), None, FileType.ARCHIVE ),
    ExpectedResult( (Path("subdir","formats.tar.bz2"), PurePosixPath("formats/lzma.txt.xz"), PurePosixPath("formats/lzma.txt")),
        b'Another format!\n', FileType.FILE ),
    ExpectedResult( (Path("subdir","formats.tar.bz2"), PurePosixPath("formats/bzip2.txt.bz2")), None, FileType.ARCHIVE ),
    ExpectedResult( (Path("subdir","formats.tar.bz2"), PurePosixPath("formats/bzip2.txt.bz2"), PurePosixPath("formats/bzip2.txt")),
        b'And another!\n', FileType.FILE ),
)
EXPECT_7Z :tuple[ExpectedResult, ...] = (
    ExpectedResult( (Path("more.zip"), PurePosixPath("more/stuff/xyz.7z"), PurePosixPath("even.txt")),
        b"Adding", FileType.FILE ),
    ExpectedResult( (Path("more.zip"), PurePosixPath("more/stuff/xyz.7z"), PurePosixPath("more")),
        None, FileType.DIR ),
    ExpectedResult( (Path("more.zip"), PurePosixPath("more/stuff/xyz.7z"), PurePosixPath("more/stuff.txt")),
        b"Testing\r\nTesting", FileType.FILE ),

    ExpectedResult( (Path("opt.7z"), PurePosixPath("thing")), None, FileType.DIR ),
    ExpectedResult( (Path("opt.7z"), PurePosixPath("thing/wuv.tgz")), None, FileType.ARCHIVE ),
    ExpectedResult( (Path("opt.7z"), PurePosixPath("thing/wuv.tgz"), PurePosixPath("uvw.txt")),
        b"This\nis\na\n7z\ntest\n", FileType.FILE ),
)

@contextmanager
def TestCaseContext():  # pylint: disable=invalid-name
    with TemporaryDirectory() as td:
        testdir = Path(td)/'zips'
        shutil.copytree( Path(__file__).parent.resolve()/'zips', testdir, symlinks=True )
        with Pushd(testdir):
            expect :list[ExpectedResult] = list( deepcopy( EXPECT + (EXPECT_7Z if P7Z_EX else ()) ) )
            if sys.platform.startswith('win32'):  # cover-only-win32
                print('skipping symlink and fifo tests', file=sys.stderr, end='  ')
            else:  # cover-not-win32
                (testdir/'baz.zip').symlink_to('more.zip')
                expect.append( ExpectedResult( (Path("baz.zip"),), None, FileType.SYMLINK ) )
                os.mkfifo(testdir/'xy.fifo')  # pyright: ignore [reportAttributeAccessIssue]  # pylint: disable=no-member,useless-suppression
                expect.append( ExpectedResult( (Path("xy.fifo"),), None, FileType.OTHER ) )
            expect.sort()
            yield expect
