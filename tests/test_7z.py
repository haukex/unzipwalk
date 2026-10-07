"""
Tests specific to :mod:`unzipwalk`'s 7z handling
================================================

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
from pathlib import Path
from typing import IO, Literal
from collections.abc import Generator
from unittest.mock import DEFAULT, patch
from contextlib import contextmanager, closing, ExitStack, nullcontext
from py7zr.exceptions import ArchiveError
from igbpyutils.file import Filename
import unzipwalk as uut
from unzipwalk import FileType
from .defs import BAD_ZIPS, TestCaseContext

# spell: ignore blabla

@contextmanager
def capture_7z_buffers() -> Generator[list[IO[bytes]], None, None]:
    buffers :list[IO[bytes]] = []
    def new_buffer() -> io.BytesIO:
        buffer = io.BytesIO()
        buffers.append(buffer)
        return buffer
    def open_buffer(filename :Filename, mode :Literal['rb']) -> IO[bytes]:
        # The walker takes ownership of each returned handle; the tests verify it closes them.
        buffer = open(filename, mode)  # pylint: disable=consider-using-with
        buffers.append(buffer)
        return buffer
    with (patch('unzipwalk.wrap7z.BytesIO', side_effect=new_buffer),
          patch('unzipwalk.wrap7z.open', side_effect=open_buffer, create=True)):
        yield buffers

class TestSevenZip(unittest.TestCase):

    def setUp(self) -> None:
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_7z_walk_handle_lifetime(self) -> None:
        with TestCaseContext():
            for archive in ('opt.7z', 'more.zip'):
                for mode in ('complete', 'close', 'exception'):
                    with self.subTest(archive=archive, mode=mode), capture_7z_buffers() as buffers:
                        handles :list[uut.ReadOnlyBinary] = []
                        with closing(uut.unzipwalk(archive)) as walk:
                            for result in walk:
                                self.assertTrue(all(h.closed for h in handles))
                                if result.hnd is not None:
                                    self.assertFalse(result.hnd.closed)
                                    result.hnd.read()
                                    handles.append(result.hnd)
                                    if mode!='complete' and any(n.lower().endswith('.7z') for n in result.raw_names[:-1]):
                                        if mode=='exception':
                                            with self.assertRaisesRegex(RuntimeError, 'consumer failure'):
                                                walk.throw(RuntimeError('consumer failure'))
                                        break
                        self.assertTrue(buffers)
                        self.assertTrue(handles)
                        self.assertTrue(all(h.closed for h in handles))
                        self.assertTrue(all(b.closed for b in buffers))

    def test_7z_recursive_open_handle_lifetime(self) -> None:
        with TestCaseContext():
            for names, expected in (
                    (('opt.7z', 'thing/blah.txt'), b'blabla\n'),
                    (('opt.7z', 'thing/wuv.tgz', 'uvw.txt'), b'This\nis\na\n7z\ntest\n'),
                    (('more.zip', 'more/stuff/xyz.7z', 'even.txt'), b'Adding') ):
                for fail in (False, True):
                    with self.subTest(names=names, fail=fail), capture_7z_buffers() as buffers:
                        with self.assertRaisesRegex(RuntimeError, 'consumer failure') if fail else nullcontext():
                            with uut.recursive_open(names) as fh:
                                self.assertFalse(fh.closed)
                                self.assertEqual(fh.read(), expected)
                                self.assertTrue(buffers)
                                self.assertTrue(all(not b.closed for b in buffers))
                                if fail:
                                    raise RuntimeError('consumer failure')
                        self.assertTrue(fh.closed)
                        self.assertTrue(all(b.closed for b in buffers))
            with capture_7z_buffers() as buffers, self.assertRaises(KeyError), ExitStack() as stack:
                stack.enter_context(uut.recursive_open(('opt.7z', 'thing/wuv.tgz', 'missing.txt')))
            self.assertTrue(buffers)
            self.assertTrue(all(b.closed for b in buffers))

    def test_7z_extraction_error_cleanup(self) -> None:
        for archive, member, error in (
                (BAD_ZIPS/'bad.7z', 'broken.txt', ArchiveError),
                (BAD_ZIPS/'double.7z', 'bar.txt', FileExistsError) ):
            with self.subTest(archive=archive), capture_7z_buffers() as buffers:
                with self.assertRaises(error), ExitStack() as stack:
                    stack.enter_context(uut.recursive_open((archive, member)))
                self.assertTrue(buffers)
                self.assertTrue(all(b.closed for b in buffers))

    def test_7z_error_recovery(self) -> None:
        # Each member has its own compression block; both broken.txt entries have incorrect CRCs.
        archive = Path(__file__).parent/'7z_recovery.7z'
        expected = [
            ((str(archive), 'before.txt'), FileType.FILE, b'before error\n'),
            ((str(archive), 'broken.txt'), FileType.ERROR, None),
            ((str(archive), 'after.txt'), FileType.FILE, b'after first error\n'),
            ((str(archive), 'broken.txt'), FileType.ERROR, None),
            ((str(archive), './after.txt'), FileType.FILE, b'after second error\n'),
            ((str(archive),), FileType.ARCHIVE, None) ]
        with self.assertRaises(ArchiveError):
            list(uut.unzipwalk(archive))
        with uut.recursive_open((archive, 'after.txt')) as fh:
            self.assertEqual(fh.read(), b'after first error\n')
        with capture_7z_buffers() as buffers:
            self.assertCountEqual([(r.raw_names, r.typ, r.hnd.read() if r.hnd is not None else None)
                for r in uut.unzipwalk(archive, raise_errors=False)], expected)
        self.assertTrue(buffers)
        self.assertTrue(all(b.closed for b in buffers))
        self.assertCountEqual([(r.raw_names, r.typ, r.hnd.read() if r.hnd is not None else None)
            for r in uut.unzipwalk(archive, matcher=lambda names: names[-1]!='broken.txt')],
            [(names, FileType.SKIP if typ==FileType.ERROR else typ, data) for names, typ, data in expected])

    def test_7z_member_access_error_recovery(self) -> None:
        archive = Path(__file__).parent/'zips'/'opt.7z'
        for raise_errors in (False, True):
            error = PermissionError('injected member access error')
            with self.subTest(raise_errors=raise_errors), patch('unzipwalk.wrap7z.open', create=True,
                    wraps=open, side_effect=(error, DEFAULT)) as mock_open:
                if raise_errors:
                    with self.assertRaises(PermissionError) as caught:
                        list(uut.unzipwalk(archive, raise_errors=raise_errors))
                    self.assertIs(caught.exception, error)
                else:
                    self.assertCountEqual([(r.raw_names, r.typ, r.hnd.read() if r.hnd is not None else None)
                        for r in uut.unzipwalk(archive, raise_errors=raise_errors)], [
                        ((str(archive), 'thing'), FileType.DIR, None),
                        ((str(archive), 'thing/blah.txt'), FileType.ERROR, None),
                        ((str(archive), 'thing/wuv.tgz', 'uvw.txt'), FileType.FILE, b'This\nis\na\n7z\ntest\n'),
                        ((str(archive), 'thing/wuv.tgz'), FileType.ARCHIVE, None),
                        ((str(archive),), FileType.ARCHIVE, None) ])
                self.assertEqual(mock_open.call_count, 1 if raise_errors else 2)

    def test_7z_member_types(self) -> None:
        archive = Path(__file__).parent/'member_types.7z'
        expected = [
            ('folder', FileType.DIR, None), ('target.txt', FileType.FILE, b'target contents'),
            ('fifo.gz', FileType.OTHER, None), ('socket.zip', FileType.OTHER, None),
            ('shared.txt', FileType.FILE, b'regular duplicate'), ('member_types.7z', FileType.ARCHIVE, None),
        ] + [(name, FileType.SYMLINK, None) for name in (
            'link.txt', 'link.gz', 'link.bz2', 'link.xz', 'link.zip', 'link.tar', 'link.7z', 'shared.txt', 'dir_link.zip')]
        with capture_7z_buffers() as buffers:
            self.assertCountEqual([(os.path.basename(r.raw_names[-1]), r.typ, r.hnd.read() if r.hnd is not None else None)
                for r in uut.unzipwalk(archive)], expected)
            self.assertEqual(len(buffers), 2)
            self.assertTrue(all(b.closed for b in buffers))
        with patch('py7zr.SevenZipFile.extract') as extract:
            self.assertCountEqual([(os.path.basename(r.raw_names[-1]), r.typ, r.hnd.read() if r.hnd is not None else None)
                for r in uut.unzipwalk(archive, matcher=lambda names: names[-1] not in ('target.txt', 'shared.txt', 'link.gz', 'fifo.gz'))],
                [(name, FileType.SKIP if name in ('target.txt', 'shared.txt', 'link.gz', 'fifo.gz') else typ, None)
                    for name, typ, _ in expected])
            extract.assert_not_called()

    def test_wrap7z(self) -> None:
        from unzipwalk.wrap7z import Py7zBytesIO, SingleBytesIOFactory  # pylint: disable=import-outside-toplevel
        pio = Py7zBytesIO(io.BytesIO(b'abc'))
        self.assertEqual(pio.size(), 3)
        self.assertEqual(pio.read(), b'abc')
        pio.flush()
        fact = SingleBytesIOFactory()
        with self.assertRaises(TypeError):
            fact.create(123)  # type: ignore[arg-type]
