"""
Tests for physical file metadata access errors
==============================================

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
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import unzipwalk as uut
from unzipwalk import FileType
from .defs import ExpectedResult, r2e

@unittest.skipIf(condition = os.name!='posix', reason='only on POSIX')
class TestPermissions(unittest.TestCase):  # cover-only-posix

    def test_dir_perms(self) -> None:
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
                self.assertEqual( r2e(uut.unzipwalk(td, matcher=lambda p: os.path.basename(p[-1]) != 'blocked')),
                    sorted([ExpectedResult((blocked,), None, FileType.SKIP, None),
                            ExpectedResult((td/'readable',), None, FileType.DIR, None),
                            ExpectedResult((td/'readable'/'good.txt',), b'good', FileType.FILE, 4) ]) )
            finally:
                blocked.chmod(0o700)

    def test_excluded_inaccessible_input_paths(self) -> None:
        with TemporaryDirectory() as td:
            blocked = Path(td)/'blocked'
            blocked.mkdir()
            file = blocked/'file.txt'
            file.write_bytes(b'hidden')
            directory = blocked/'directory'
            directory.mkdir()
            blocked.chmod(0)
            try:
                for raise_errors in (False, True):
                    with self.subTest(raise_errors=raise_errors):
                        self.assertEqual(
                            r2e(uut.unzipwalk((file, directory), matcher=lambda _names: False, raise_errors=raise_errors)),
                            sorted([ExpectedResult((file,), None, FileType.SKIP, None),
                                    ExpectedResult((directory,), None, FileType.SKIP, None) ]))
            finally:
                blocked.chmod(0o700)

    def test_unreadable_file(self) -> None:
        with TemporaryDirectory() as td:
            f = Path(td)/'foo'
            f.touch()
            f.chmod(0)
            with self.assertRaises(PermissionError):
                list(uut.unzipwalk(td))
            self.assertEqual(
                r2e(uut.unzipwalk(td, raise_errors=False)),
                sorted( [ ExpectedResult( (f,), None, FileType.ERROR, None ), ] ) )

    def test_dir_search_permission(self) -> None:
        with TemporaryDirectory() as temp_dir:
            td = Path(temp_dir)
            blocked = td/'blocked'
            blocked.mkdir()
            hidden = blocked/'hidden.txt'
            hidden.write_bytes(b'hidden')
            good = td/'good.txt'
            good.write_bytes(b'good')
            blocked.chmod(0o400)
            try:
                for path, expected in (
                        (td, [ExpectedResult((blocked,), None, FileType.DIR, None),
                              ExpectedResult((hidden,), None, FileType.ERROR, None),
                              ExpectedResult((good,), b'good', FileType.FILE, 4)]),
                        (blocked, [ExpectedResult((hidden,), None, FileType.ERROR, None)])):
                    with self.subTest(path=path, raise_errors=False):
                        self.assertEqual(r2e(uut.unzipwalk(path, raise_errors=False)), sorted(expected))
                    with self.subTest(path=path, raise_errors=True):
                        with self.assertRaises(PermissionError) as caught:
                            list(uut.unzipwalk(path))
                        self.assertEqual(caught.exception.filename, str(hidden))
                self.assertEqual(r2e(uut.unzipwalk((blocked, good), raise_errors=False)), sorted([
                    ExpectedResult((hidden,), None, FileType.ERROR, None),
                    ExpectedResult((good,), b'good', FileType.FILE, 4)]))
            finally:
                blocked.chmod(0o700)
