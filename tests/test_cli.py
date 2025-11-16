"""
Tests for :mod:`unzipwalk.__main__`
===================================

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
import io
import sys
import hashlib
import unittest
from pathlib import Path
from gzip import BadGzipFile
from tarfile import TarError
from zipfile import BadZipFile
from unittest.mock import patch
from tempfile import TemporaryDirectory
from contextlib import redirect_stdout, redirect_stderr
import unzipwalk.__main__ as uut
from unzipwalk import FileType
from .defs import P7Z_EX, BAD_ZIPS, TestCaseContext, ExpectedResult

# spell-checker: ignore csha rcmd

class TestUnzipWalkCli(unittest.TestCase):

    def setUp(self):
        self.maxDiff = None  # pylint: disable=invalid-name

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
        expect :list[ExpectedResult]
        with TestCaseContext() as expect:
            exp_basic = sorted( f"FILE {tuple(str(n) for n in e.fns)!r}" for e in expect if e.typ==FileType.FILE )
            self.assertEqual( self._run_cli([]), exp_basic )  # basic
            with TemporaryDirectory() as td:  # --outfile
                tf = Path(td)/'foo'
                self.assertEqual( self._run_cli(['--outfile', str(tf)]), [] )
                with tf.open(encoding='UTF-8') as fh:
                    self.assertEqual( sorted(fh.read().splitlines()), exp_basic )
            self.assertEqual( self._run_cli(['--all-files']), sorted(  # basic + all-files
                f"{e.typ.name} {tuple(str(n) for n in e.fns)!r}" for e in expect ) )
            self.assertEqual( self._run_cli(['--dump']), sorted(  # dump
                f"FILE {tuple(str(n) for n in e.fns)!r} {e.data!r}" for e in expect if e.typ==FileType.FILE ) )
            self.assertEqual( self._run_cli(['-da']), sorted(  # dump + all-files
                f"FILE {tuple(str(n) for n in e.fns)!r} {e.data!r}" if e.typ==FileType.FILE
                else f"{e.typ.name} {tuple(str(n) for n in e.fns)!r}" for e in expect ) )
            self.assertEqual( self._run_cli(['--checksum','sha256']), sorted(  # checksum
                f"{hashlib.sha256(e.data).hexdigest()} *{str(e.fns[0]) if len(e.fns)==1 else repr(tuple(str(n) for n in e.fns))}"
                for e in expect if e.data is not None ) )
            self.assertEqual( self._run_cli(['-a','-csha512']), sorted(  # checksum + all-files
                (f"# {e.typ.name} " if e.data is None else f"{hashlib.sha512(e.data).hexdigest()} *")
                + f"{str(e.fns[0]) if len(e.fns)==1 else repr(tuple(str(n) for n in e.fns))}"
                for e in expect ) )
            self.assertEqual( self._run_cli(['-e','world.*','--exclude=*abc*']), sorted(  # exclude
                f"FILE {tuple(str(n) for n in e.fns)!r}" for e in expect if e.typ==FileType.FILE
                and not ( e.fns[-1].name.startswith('world.') or len(e.fns)>1 and e.fns[1].name=='abc.zip' ) ) )

    def test_cli_errors(self):
        os.chdir(BAD_ZIPS)
        self.assertEqual( self._run_cli(['-d','.','does_not_exist']), sorted( [
            "ERROR ('does_not_exist',)",
            "ERROR ('not_a.gz', 'not_a')",
            "ERROR ('not_a.bz2', 'not_a')",
            "ERROR ('not_a.xz', 'not_a')",
            "ERROR ('not_a.tar',)",
            "ERROR ('not_a.tar.gz',)",
            "ERROR ('not_a.tgz',)",
            "ERROR ('not_a.zip',)",
            "ERROR ('not_a.tgz.gz', 'not_a.tgz')",
            "ERROR ('not_a.tgz.bz2', 'not_a.tgz')",
            "ERROR ('not_a.zip.gz', 'not_a.zip')",
            "ERROR ('not_a.zip.bz2', 'not_a.zip')",
            "ERROR ('not_a.zip.xz', 'not_a.zip')",
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
        ] if P7Z_EX else []) ) )
        self.assertEqual( self._run_cli(['-cmd5','.','does_not_exist']), sorted( [
            "# ERROR does_not_exist",
            "# ERROR ('not_a.gz', 'not_a')",
            "# ERROR ('not_a.bz2', 'not_a')",
            "# ERROR ('not_a.xz', 'not_a')",
            "# ERROR not_a.tar",
            "# ERROR not_a.tar.gz",
            "# ERROR not_a.tgz",
            "# ERROR not_a.zip",
            "# ERROR ('not_a.tgz.gz', 'not_a.tgz')",
            "# ERROR ('not_a.tgz.bz2', 'not_a.tgz')",
            "# ERROR ('not_a.zip.gz', 'not_a.zip')",
            "# ERROR ('not_a.zip.bz2', 'not_a.zip')",
            "# ERROR ('not_a.zip.xz', 'not_a.zip')",
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
        ] if P7Z_EX else []) ) )
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
