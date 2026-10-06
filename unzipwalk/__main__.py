#!/usr/bin/env python3
"""
Command-Line Interface for :mod:`unzipwalk`
===========================================

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
import hashlib
import argparse
from fnmatch import fnmatch
from collections.abc import Sequence
from igbpyutils.file import open_out
import igbpyutils.error
from . import unzipwalk, FileType

def _arg_parser() -> argparse.ArgumentParser:
    # exclude hash algorithms that are variable length (their .hexdigest requires a length argument that we don't provide)
    algorithms = sorted(hashlib.algorithms_available - {'shake_128', 'shake_256'})
    parser = argparse.ArgumentParser('unzipwalk', description='Recursively walk into directories and archives',
        epilog="* Note --exclude matches the full final name in the sequence, including directory components. "
        "For archive members, this is the path within the innermost archive. "
        "For more control, use the library instead of this command-line tool.\n\n"
        f"** Possible values for ALGO: {', '.join(algorithms)}")
    parser.add_argument('-a','--all-files', help="also list dirs, symlinks, etc.", action="store_true")
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-d','--dump', help="also dump file contents", action="store_true")
    group.add_argument('-c','--checksum', help="generate a checksum for each file**", choices=algorithms, metavar="ALGO")
    parser.add_argument('-e', '--exclude', help="filename globs to exclude*", action="append", default=[])
    parser.add_argument('-r', '--raise-errors', help="raise errors instead of reporting them in output", action="store_true")
    parser.add_argument('-o', '--outfile', help="output filename (must not already exist)")
    parser.add_argument('paths', metavar='PATH', help='paths to process (default is current directory)', nargs='*')
    return parser

def main(argv :Sequence[str]|None = None) -> None:
    igbpyutils.error.init_handlers()
    parser = _arg_parser()
    args = parser.parse_args(argv)
    outfile = args.outfile if args.outfile and args.outfile != '-' else None
    def matcher(names :Sequence[str]) -> bool:
        if outfile is not None and len(names)==1 and os.path.samefile(names[0], outfile):
            return False  # skip the output file if we're using one
        return not any( fnmatch(names[-1], pat) for pat in args.exclude )
    report = (FileType.FILE, FileType.ERROR)
    with open_out(args.outfile, mode='x') as fh:
        for result in unzipwalk( args.paths if args.paths else os.curdir, matcher=matcher, raise_errors=args.raise_errors ):
            if args.checksum:
                if result.typ in report or args.all_files:
                    print(result.checksum_line(args.checksum, raise_errors=args.raise_errors), file=fh)
            else:
                names = result.raw_names
                if result.typ == FileType.FILE and args.dump:
                    assert result.hnd is not None, result
                    try:
                        data = result.hnd.read()
                    except Exception:
                        if args.raise_errors:
                            raise
                        print(f"{FileType.ERROR.name} {names!r}", file=fh)
                    else:
                        print(f"{result.typ.name} {names!r} {data!r}", file=fh)
                elif result.typ in report or args.all_files:
                    print(f"{result.typ.name} {names!r}", file=fh)
    parser.exit(0)

if __name__=='__main__':  # pragma: no cover
    main()
