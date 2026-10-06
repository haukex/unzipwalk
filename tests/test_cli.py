"""
Tests for :mod:`unzipwalk.__main__`
===================================

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
import hashlib
import unittest
from pathlib import Path
from gzip import BadGzipFile
from tarfile import TarError
from unittest.mock import patch
from zipfile import BadZipFile, ZipFile
from tempfile import TemporaryDirectory
from contextlib import redirect_stdout, redirect_stderr
from igbpyutils.file import Pushd
import unzipwalk.__main__ as uut
from unzipwalk import FileType
from .defs import BAD_ZIPS, TestCaseContext, ExpectedResult

# spell-checker: ignore csha rcmd pushd

class TestUnzipWalkCli(unittest.TestCase):

    def setUp(self) -> None:
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

    def test_cli(self) -> None:
        expect :list[ExpectedResult]
        with TestCaseContext() as expect:
            # ZIP directory entries retain their trailing slashes in raw names.
            raw_names = [tuple(str(n) for n in e.fns[:-1]) + (str(e.fns[-1])
                + ('/' if e.typ==FileType.DIR and len(e.fns)>1 and e.fns[-2].suffix.lower()=='.zip' else ''),) for e in expect]
            exp_basic = sorted( f"FILE {names!r}" for e, names in zip(expect, raw_names) if e.typ==FileType.FILE )
            self.assertEqual( self._run_cli([]), exp_basic )  # basic
            with TemporaryDirectory() as td:  # --outfile
                tf = Path(td)/'foo'
                self.assertEqual( self._run_cli(['--outfile', str(tf)]), [] )
                with tf.open(encoding='UTF-8') as fh:
                    self.assertEqual( sorted(fh.read().splitlines()), exp_basic )
            self.assertEqual( self._run_cli(['--all-files']), sorted(  # basic + all-files
                f"{e.typ.name} {names!r}" for e, names in zip(expect, raw_names) ) )
            self.assertEqual( self._run_cli(['--dump']), sorted(  # dump
                f"FILE {names!r} {e.data!r}" for e, names in zip(expect, raw_names) if e.typ==FileType.FILE ) )
            self.assertEqual( self._run_cli(['-da']), sorted(  # dump + all-files
                f"FILE {names!r} {e.data!r}" if e.typ==FileType.FILE
                else f"{e.typ.name} {names!r}" for e, names in zip(expect, raw_names) ) )
            self.assertEqual( self._run_cli(['--checksum','sha256']), sorted(  # checksum
                f"{hashlib.sha256(e.data).hexdigest()} *{names[0] if len(names)==1 else repr(names)}"
                for e, names in zip(expect, raw_names) if e.data is not None ) )
            self.assertEqual( self._run_cli(['-a','-csha512']), sorted(  # checksum + all-files
                (f"# {e.typ.name} " if e.data is None else f"{hashlib.sha512(e.data).hexdigest()} *")
                + f"{names[0] if len(names)==1 else repr(names)}"
                for e, names in zip(expect, raw_names) ) )
            self.assertEqual( self._run_cli(['-e','*world.*','--exclude=*abc*']), sorted(  # exclude
                f"FILE {names!r}" for e, names in zip(expect, raw_names) if e.typ==FileType.FILE
                and not ( e.fns[-1].name.startswith('world.') or len(e.fns)>1 and e.fns[1].name=='abc.zip' ) ) )
            self.assertEqual(self._run_cli(['--exclude', 'ooo.txt']), exp_basic)
            self.assertEqual(self._run_cli(['--exclude', str(Path('subdir')/'ooo.txt')]), sorted(
                f"FILE {names!r}" for e, names in zip(expect, raw_names)
                if e.typ==FileType.FILE and e.fns[0]!=Path('subdir')/'ooo.txt'))
            self.assertEqual(self._run_cli(['--all-files', '--exclude', 'subdir']), sorted(
                [f"{e.typ.name} {names!r}" for e, names in zip(expect, raw_names)
                    if not e.fns[0].is_relative_to(Path('subdir'))] + ["SKIP ('subdir',)"]))

    def test_cli_raw_names(self) -> None:
        with TemporaryDirectory() as td, Pushd(td):
            files = (('./file.txt', b'dotted'), ('file.txt', b'first'), ('file.txt', b'second'), ('./dir//file.txt', b'nested'))
            with ZipFile('archive.zip', 'w') as zf:
                with self.assertWarnsRegex(UserWarning, 'Duplicate name'):
                    for name, data in files:
                        zf.writestr(name, data)
                zf.writestr('./dir//', b'')
                zf.writestr('./bad//invalid.zip', b'invalid')
            for options, dump, all_files in (([], False, False), (['-a'], False, True), (['-d'], True, False), (['-da'], True, True)):
                with self.subTest(options=options):
                    expected = [f"FILE {('archive.zip', name)!r}" + (f" {data!r}" if dump else '') for name, data in files]
                    expected.append("ERROR ('archive.zip', './bad//invalid.zip')")
                    if all_files:
                        expected.extend(["DIR ('archive.zip', './dir//')", "ARCHIVE ('archive.zip',)"])
                    self.assertEqual(self._run_cli([*options, 'archive.zip']), sorted(expected))
            self.assertEqual(self._run_cli(['-csha1', 'archive.zip']), sorted(
                [f"{hashlib.sha1(data).hexdigest()} *{('archive.zip', name)!r}" for name, data in files]
                + ["# ERROR ('archive.zip', './bad//invalid.zip')"]))
            for pattern, included in (('./file.txt', files[1:]), ('file.txt', (files[0], files[-1])), ('./dir//*', files[:3])):
                with self.subTest(pattern=pattern):
                    self.assertEqual(self._run_cli(['--exclude', pattern, 'archive.zip']), sorted(
                        [f"FILE {('archive.zip', name)!r}" for name, _ in included]
                        + ["ERROR ('archive.zip', './bad//invalid.zip')"]))
            self.assertEqual(self._run_cli(['-a', '--exclude', './dir//*', 'archive.zip']), sorted(
                [f"FILE {('archive.zip', name)!r}" for name, _ in files[:3]] + [
                    "ARCHIVE ('archive.zip',)", "ERROR ('archive.zip', './bad//invalid.zip')",
                    "SKIP ('archive.zip', './dir//')", "SKIP ('archive.zip', './dir//file.txt')" ]))

    def test_cli_outfile(self) -> None:
        with TemporaryDirectory() as td, Pushd(td):
            Path('input.txt').write_bytes(b'physical')
            with self.assertRaises(FileExistsError):
                self._run_cli(['--outfile', 'input.txt', 'input.txt'])
            self.assertEqual(Path('input.txt').read_bytes(), b'physical')
            with ZipFile('archive.zip', 'w') as zf:
                zf.writestr('output.txt', b'archived')
            for options, expected in (
                    (['--all-files'], [
                        "FILE ('input.txt',)",
                        "ARCHIVE ('archive.zip',)",
                        "FILE ('archive.zip', 'output.txt')",
                        "SKIP ('output.txt',)" ]),
                    (['--all-files', '--checksum', 'sha256'], [
                        f"{hashlib.sha256(b'physical').hexdigest()} *input.txt",
                        '# ARCHIVE archive.zip',
                        f"{hashlib.sha256(b'archived').hexdigest()} *('archive.zip', 'output.txt')",
                        '# SKIP output.txt' ]) ):
                with self.subTest(options=options):
                    # The output path is absolute and contains a dot component while traversal returns relative paths.
                    self.assertEqual(self._run_cli([*options, '--outfile', os.path.join(td, '.', 'output.txt'), '.']), [])
                    self.assertEqual(sorted(Path('output.txt').read_text(encoding='UTF-8').splitlines()), sorted(expected))
                    Path('output.txt').unlink()
            self.assertEqual(self._run_cli(['--outfile', '-', 'input.txt']), ["FILE ('input.txt',)"])

    def test_cli_errors(self) -> None:
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
            "ERROR ('bad.7z', 'broken.txt')",
            "FILE ('double.7z', 'bar.txt') b''",
            "FILE ('double.7z', 'bar.txt') b''",
            "ERROR ('not_a.7z',)",
        ] ) )
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
            "# ERROR not_a.7z",
            "# ERROR ('bad.7z', 'broken.txt')",
            "d41d8cd98f00b204e9800998ecf8427e *('double.7z', 'bar.txt')",
            "d41d8cd98f00b204e9800998ecf8427e *('double.7z', 'bar.txt')",
        ] ) )
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
