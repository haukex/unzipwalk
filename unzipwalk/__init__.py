"""
Recursively Walk Into Directories and Archives
==============================================

This module primarily provides the function :func:`unzipwalk`, which recursively walks
into directories and compressed files and returns all files, directories, etc. found,
together with binary file handles (file objects) for reading the files.
Currently supported are ZIP, tar, tgz, and gz compressed files.
File types are detected based on their extensions.

    >>> from unzipwalk import unzipwalk
    >>> results = []
    >>> for result in unzipwalk('.'):
    ...     names = tuple( name.as_posix() for name in result.names )
    ...     if result.hnd:  # result is a file opened for reading (binary)
    ...         # could use result.hnd.read() here, or for line-by-line:
    ...         for line in result.hnd:
    ...             pass  # do something interesting with the data here
    ...     results.append(names + (result.typ.name,))
    >>> print(sorted(results))# doctest: +NORMALIZE_WHITESPACE
    [('bar.zip', 'ARCHIVE'),
     ('bar.zip', 'bar.txt', 'FILE'),
     ('bar.zip', 'test.tar.gz', 'ARCHIVE'),
     ('bar.zip', 'test.tar.gz', 'hello.csv', 'FILE'),
     ('bar.zip', 'test.tar.gz', 'test', 'DIR'),
     ('bar.zip', 'test.tar.gz', 'test/cool.txt.gz', 'ARCHIVE'),
     ('bar.zip', 'test.tar.gz', 'test/cool.txt.gz', 'test/cool.txt', 'FILE'),
     ('foo.txt', 'FILE')]

**Note** that :func:`unzipwalk` automatically closes files as it goes from file to file.
This means that you must use the handles as soon as you get them from the generator -
something as seemingly simple as ``sorted(unzipwalk('.'))`` would cause the code above to fail,
because all files will have been opened and closed during the call to :func:`sorted`
and the handles to read the data would no longer be available in the body of the loop.
This is why the above example first processes all the files before sorting the results.
You can also use :func:`recursive_open` to open the files later.

The yielded file handles can be wrapped in :class:`io.TextIOWrapper` to read them as text files.
For example, to read all CSV files in the current directory and below, including within compressed files:

    >>> from unzipwalk import unzipwalk, FileType
    >>> from io import TextIOWrapper
    >>> import csv
    >>> for result in unzipwalk('.'):
    ...     if result.typ==FileType.FILE and result.names[-1].suffix.lower()=='.csv':
    ...         print([ name.as_posix() for name in result.names ])
    ...         with TextIOWrapper(result.hnd, encoding='UTF-8', newline='') as handle:
    ...             csv_rd = csv.reader(handle, strict=True)
    ...             for row in csv_rd:
    ...                 print(repr(row))
    ['bar.zip', 'test.tar.gz', 'hello.csv']
    ['Id', 'Name', 'Address']
    ['42', 'Hello', 'World']

Members
-------

.. autofunction:: unzipwalk.unzipwalk

.. autoclass:: unzipwalk.UnzipWalkResult
    :members:

.. autoclass:: unzipwalk.ReadOnlyBinary
    :members:
    :undoc-members:

.. autoclass:: unzipwalk.FileType
    :members:

.. autofunction:: unzipwalk.recursive_open

Command-Line Interface
----------------------

.. unzipwalk_clidoc::

The available checksum algorithms may vary depending on your system and Python version.
Run the command with ``--help`` to see the list of currently available algorithms.

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
import re
import io
import ast
import stat
import hashlib
import argparse
from enum import Enum
from gzip import GzipFile
from tarfile import TarFile
from zipfile import ZipFile
from itertools import chain
from fnmatch import fnmatch
from contextlib import contextmanager
from collections.abc import Generator, Sequence, Callable
from pathlib import PurePosixPath, PurePath, Path, PureWindowsPath
from typing import Optional, cast, Protocol, Literal, BinaryIO, NamedTuple, runtime_checkable, Union
from igbpyutils.file import AnyPaths, to_Paths, Filename
import igbpyutils.error

class FileType(Enum):
    """Used in :class:`UnzipWalkResult` to indicate the type of the file."""
    #: A regular file.
    FILE = 0
    #: An archive file, will be descended into.
    ARCHIVE = 1
    #: A directory.
    DIR = 2
    #: A symbolic link.
    SYMLINK = 3
    #: Some other file type (e.g. FIFO).
    OTHER = 4

@runtime_checkable
class ReadOnlyBinary(Protocol):  # pragma: no cover  (b/c Protocol class)
    """Interface for the file handle (file object) used in :class:`UnzipWalkResult`.

    The interface is the intersection of :class:`typing.BinaryIO`, :class:`gzip.GzipFile`, and :mod:`zipfile.ZipExtFile<zipfile>`.
    Because :class:`gzip.GzipFile` doesn't implement ``.tell()``, that method isn't available here.
    Whether the handle supports seeking depends on the underlying library.

    Note :func:`unzipwalk` automatically closes files."""
    @property
    def name(self) -> str: ...
    def close(self) -> None: ...
    @property
    def closed(self) -> bool: ...
    def readable(self) -> Literal[True]: ...
    def read(self, n: int = -1) -> bytes: ...
    def readline(self, limit: int = -1) -> bytes: ...
    def seekable(self) -> bool: ...
    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int: ...

def decode_tuple(code :str) -> tuple[str, ...]:
    """Helper function to parse a string as produced by :func:`repr` from a :class:`tuple` of one or more :class:`str`.

    :param code: The code to parse.
    :return: The :class:`tuple` that was parsed.
    :raises ValueError: If the code could not be parsed.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as ex:
        raise ValueError() from ex
    if not len(tree.body)==1 or not isinstance(tree.body[0], ast.Expr) or not isinstance(tree.body[0].value, ast.Tuple) \
            or not isinstance(tree.body[0].value.ctx, ast.Load) or len(tree.body[0].value.elts)<1:
        raise ValueError(f"failed to decode tuple {code!r}")
    elements = []
    for e in tree.body[0].value.elts:
        if not isinstance(e, ast.Constant) or not isinstance(e.value, str):
            raise ValueError(f"failed to decode tuple {code!r}")
        elements.append(e.value)
    return tuple(elements)

CHECKSUM_LINE_RE = re.compile(r'^([0-9a-f]+) \*(.+)$')
CHECKSUM_COMMENT_RE = re.compile(r'^# ([A-Z]+) (.+)$')

class UnzipWalkResult(NamedTuple):
    """Return type for :func:`unzipwalk`."""
    #: A tuple of the filename(s) as :mod:`pathlib` objects. The first element is always the physical file in the file system.
    #: If the tuple has more than one element, then the yielded file is contained in a compressed file, possibly nested in
    #: other compressed file(s), and the last element of the tuple will contain the file's actual name.
    names :tuple[PurePath, ...]
    #: A :class:`FileType` value representing the type of the current file.
    typ :FileType
    #: When :attr:`typ` is :class:`FileType.FILE<FileType>`, this is a :class:`ReadOnlyBinary` file handle (file object)
    #: for reading the file contents in binary mode. Otherwise, this is :obj:`None`.
    #: If this object was produced by :meth:`from_checksum_line`, this handle will read the checksum of the data, *not the data itself!*
    hnd :Optional[ReadOnlyBinary] = None

    def validate(self):
        """Validate whether the object's fields are set properly and throw errors if not.

        Intended for internal use, mainly when type checkers are not being used.
        :func:`unzipwalk` validates all the results it returns.

        :return: The object itself, for method chaining.
        :raises ValueError, TypeError: If the object is invalid.
        """
        if not self.names:
            raise ValueError('names is empty')
        if not all( isinstance(n, PurePath) for n in self.names ):  # pyright: ignore [reportUnnecessaryIsInstance]
            raise TypeError(f"invalid names {self.names!r}")
        if not isinstance(self.typ, FileType):  # pyright: ignore [reportUnnecessaryIsInstance]
            raise TypeError(f"invalid type {self.typ!r}")
        if self.typ==FileType.FILE and not isinstance(self.hnd, ReadOnlyBinary):
            raise TypeError(f"invalid handle {self.hnd!r}")
        if self.typ!=FileType.FILE and self.hnd is not None:
            raise TypeError(f"invalid handle, should be None but is {self.hnd!r}")
        return self

    def checksum_line(self, hash_algo :str) -> str:
        """Encodes this object into a line of text suitable for use as a checksum line.

        Intended mostly for internal use by the ``--checksum`` CLI option.

        **Warning:** Requires that the file handle be open (for files), and will read from it!

        See also :meth:`from_checksum_line` for the inverse operation.

        :param hash_algo: The hashing algorithm to use, as recognized by :func:`hashlib.new`.
        :return: The checksum line, without trailing newline.
        """
        names = tuple( str(n) for n in self.names )
        if len(names)==1 and names[0] and names[0].strip()==names[0] and not names[0].startswith('(') \
                and '\n' not in names[0] and '\r' not in names[0]:  # pylint: disable=too-many-boolean-expressions
            name = names[0]
        else:
            name = repr(names)
            assert name.startswith('(')
        assert '\n' not in name and '\r' not in name
        if self.typ == FileType.FILE:
            assert self.hnd is not None
            h = hashlib.new(hash_algo)
            h.update(self.hnd.read())
            return f"{h.hexdigest().lower()} *{name}"
        return f"# {self.typ.name} {name}"

    @classmethod
    def from_checksum_line(cls, line :str, *, windows :bool=False) -> Optional['UnzipWalkResult']:
        """Decodes a checksum line as produced by :meth:`checksum_line`.

        **Warning:** The ``hnd`` of the returned object will *not* be a handle to
        the data from the file, instead it will be a handle to read the checksum of the file!
        (You could use :func:`recursive_open` to open the files themselves.)

        Intended as a utility function for use when reading files produced by the ``--checksum`` CLI option.

        :param line: The line to parse.
        :param windows: Set this to :obj:`True` if the pathname in the line is in Windows format,
            otherwise it is assumed the filename is in POSIX format.
        :return: The :class:`UnzipWalkResult` object, or :obj:`None` for empty or comment lines.
        :raises ValueError: If the line could not be parsed.
        """
        if not line.strip():
            return None
        path_cls = PureWindowsPath if windows else PurePosixPath
        def mk_names(name :str)-> tuple[PurePath, ...]:
            names = decode_tuple(name) if name.startswith('(') else (name,)
            return tuple(path_cls(p) for p in names)
        if line.lstrip().startswith('#'):  # comment, be lenient to allow user comments
            if m := CHECKSUM_COMMENT_RE.match(line):
                if m.group(1) in FileType.__members__:
                    return cls( names=mk_names(m.group(2)), typ=FileType[m.group(1)] )
            return None
        if m := CHECKSUM_LINE_RE.match(line):
            return cls( names=mk_names(m.group(2)), typ=FileType.FILE, hnd=cast(ReadOnlyBinary, io.BytesIO(bytes.fromhex(m.group(1)))) )
        raise ValueError(f"failed to decode checksum line {line!r}")

@contextmanager
def _inner_recur_open(fh :BinaryIO, fns :tuple[PurePath, ...]) -> Generator[BinaryIO, None, None]:
    try:
        bl = fns[0].name.lower()
        assert fns
        if len(fns)==1:
            yield fh
        # the following code is very similar to _proc_file, please see those code comments for details
        elif bl.endswith('.tar.gz') or bl.endswith('.tgz') or bl.endswith('.tar'):
            with TarFile.open(fileobj=fh) as tf:
                ef = tf.extractfile(str(fns[1]))
                if not ef:  # e.g. directory
                    raise FileNotFoundError(f"not a file? {fns[0:2]}")
                with ef as fh2:
                    with _inner_recur_open(cast(BinaryIO, fh2), fns[1:]) as inner:
                        yield inner
        elif bl.endswith('.zip'):
            with ZipFile(fh) as zf:
                with zf.open(str(fns[1])) as fh2:
                    with _inner_recur_open(cast(BinaryIO, fh2), fns[1:]) as inner:
                        yield inner
        elif bl.endswith('.gz'):
            if fns[1] != fns[0].with_suffix(''):
                raise FileNotFoundError(f"invalid gzip filename {fns[0]} => {fns[1]}")
            with GzipFile(fileobj=fh, mode='rb') as fh2:
                with _inner_recur_open(cast(BinaryIO, fh2), fns[1:]) as inner:
                    yield inner
        else:
            assert False, 'should be unreachable'  # pragma: no cover
    except GeneratorExit:  # https://pylint.readthedocs.io/en/latest/user_guide/messages/warning/contextmanager-generator-missing-cleanup.html
        pass  # pragma: no cover

@contextmanager
def recursive_open(fns :Sequence[Filename], encoding=None, errors=None, newline=None) \
        -> Generator[Union[ReadOnlyBinary, io.TextIOWrapper], None, None]:
    """This context manager allows opening files nested inside archives directly.

    :func:`unzipwalk` automatically closes files as it iterates through directories and archives;
    this function exists to allow you to open the returned files after the iteration.

    If *any* of ``encoding``, ``errors``, or ``newline`` is specified, the returned
    file is wrapped in :class:`io.TextIOWrapper`!

    If the last file in the list of files is an archive file, then it won't be decompressed,
    instead you'll be able to read the archive's raw compressed data from the handle.

    In this example, we open a gzip-compressed file, stored inside a tgz archive, which
    in turn is stored in a Zip file:

    >>> from unzipwalk import recursive_open
    >>> with recursive_open(('bar.zip', 'test.tar.gz', 'test/cool.txt.gz', 'test/cool.txt'), encoding='UTF-8') as fh:
    ...     print(fh.read())# doctest: +NORMALIZE_WHITESPACE
    Hi, I'm a compressed file!
    """
    # note Sphinx's "WARNING: py:class reference target not found: _io.TextIOWrapper" can be ignored
    if not fns:
        raise ValueError('no filenames given')
    with open(fns[0], 'rb') as fh:
        with _inner_recur_open(fh, (Path(fns[0]),) + tuple( PurePosixPath(f) for f in fns[1:] )) as inner:
            assert inner.readable()
            if encoding is not None or errors is not None or newline is not None:
                yield io.TextIOWrapper(inner, encoding=encoding, errors=errors, newline=newline)
            else:
                yield cast(ReadOnlyBinary, inner)

FilterType = Callable[[Sequence[PurePath]], bool]

def _proc_file(fns :tuple[PurePath, ...], fh :BinaryIO, *, matcher :Optional[FilterType]) -> Generator[UnzipWalkResult, None, None]:
    bl = fns[-1].name.lower()
    if bl.endswith('.tar.gz') or bl.endswith('.tgz') or bl.endswith('.tar'):
        yield UnzipWalkResult(names=fns, typ=FileType.ARCHIVE)
        with TarFile.open(fileobj=fh) as tf:
            for ti in tf.getmembers():
                new_names = (*fns, PurePosixPath(ti.name))
                if matcher is not None and not matcher(new_names): continue
                # for ti.type see e.g.: https://github.com/python/cpython/blob/v3.12.3/Lib/tarfile.py#L88
                if ti.issym():
                    yield UnzipWalkResult(names=new_names, typ=FileType.SYMLINK)
                elif ti.isdir():
                    yield UnzipWalkResult(names=new_names, typ=FileType.DIR)
                elif ti.isfile():
                    # Note apparently this can burn a lot of memory on <3.13: https://github.com/python/cpython/issues/102120
                    ef = tf.extractfile(ti)  # always binary
                    assert ef is not None  # make type checker happy; we know this is true because we checked it's a file
                    with ef as fh2:
                        assert fh2.readable()  # expected by ReadOnlyBinary
                        # NOTE type checker thinks fh2 is typing.IO[bytes], but it's actually a tarfile.ExFileObject,
                        # which is an io.BufferedReader subclass - which should be safe to cast to BinaryIO, I think.
                        yield from _proc_file(new_names, cast(BinaryIO, fh2), matcher=matcher)
                else: yield UnzipWalkResult(names=new_names, typ=FileType.OTHER)
    elif bl.endswith('.zip'):
        yield UnzipWalkResult(names=fns, typ=FileType.ARCHIVE)
        with ZipFile(fh) as zf:
            for zi in zf.infolist():
                # Note the ZIP specification requires forward slashes for path separators.
                # https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT
                new_names = (*fns, PurePosixPath(zi.filename))
                if matcher is not None and not matcher(new_names): continue
                # Manually detect symlinks in ZIP files (should be rare anyway)
                # e.g. from zipfile.py: z_info.external_attr = (st.st_mode & 0xFFFF) << 16
                # we're not going to worry about other special file types in ZIP files
                if zi.create_system==3 and stat.S_ISLNK(zi.external_attr>>16):  # 3 is UNIX
                    yield UnzipWalkResult(names=new_names, typ=FileType.SYMLINK)
                elif zi.is_dir():
                    yield UnzipWalkResult(names=new_names, typ=FileType.DIR)
                else:  # (note this interface doesn't have an is_file)
                    with zf.open(zi) as fh2:  # always binary mode
                        assert fh2.readable()  # expected by ReadOnlyBinary
                        # NOTE type checker thinks fh2 is typing.IO[bytes], but it's actually a zipfile.ZipExtFile,
                        # which is an io.BufferedIOBase subclass - which should be safe to cast to BinaryIO, I think.
                        yield from _proc_file(new_names, cast(BinaryIO, fh2), matcher=matcher)
    elif bl.endswith('.gz'):
        yield UnzipWalkResult(names=fns, typ=FileType.ARCHIVE)
        new_names = (*fns, fns[-1].with_suffix(''))
        if matcher is not None and not matcher(new_names): return
        with GzipFile(fileobj=fh, mode='rb') as fh2:  # always binary, but specify explicitly for clarity
            assert fh2.readable()  # expected by ReadOnlyBinary
            # NOTE casting GzipFile to BinaryIO isn't 100% safe because the former doesn't implement the full interface,
            # but testing seems to show it's ok...
            yield from _proc_file(new_names, cast(BinaryIO, fh2), matcher=matcher)
    else:
        assert fh.readable()  # expected by ReadOnlyBinary
        # The following cast is safe since ReadOnlyBinary is a subset of the interfaces.
        yield UnzipWalkResult(names=fns, typ=FileType.FILE, hnd=cast(ReadOnlyBinary, fh))

def unzipwalk(paths :AnyPaths, *, matcher :Optional[FilterType] = None) -> Generator[UnzipWalkResult, None, None]:
    """This generator recursively walks into directories and compressed files and yields named tuples of type :class:`UnzipWalkResult`.

    :param paths: A filename or iterable of filenames.
    :param matcher: When you provide this optional argument, it must be a callable that accepts a sequence of paths
        as its only argument, and returns a boolean value whether this filename should be further processed or not."""
    p_paths = tuple(to_Paths(paths))
    for p in p_paths: p.resolve(strict=True)  # force FileNotFound errors early
    for p in chain.from_iterable( pa.rglob('*') if pa.is_dir() else (pa,) for pa in p_paths ):
        if matcher is not None and not matcher((p,)): continue
        if p.is_symlink():
            yield UnzipWalkResult(names=(p,), typ=FileType.SYMLINK).validate()  # pragma: no cover  (doesn't run on Windows)
        elif p.is_dir():
            yield UnzipWalkResult(names=(p,), typ=FileType.DIR).validate()
        elif p.is_file():
            with p.open('rb') as fh:
                yield from ( r.validate() for r in _proc_file((p,), fh, matcher=matcher) )
        else:
            yield UnzipWalkResult(names=(p,), typ=FileType.OTHER).validate()  # pragma: no cover  (doesn't run on Windows)

def _arg_parser():
    parser = argparse.ArgumentParser('unzipwalk', description='Recursively walk into directories and archives',
        epilog="* Note --exclude currently only matches against the final name in the sequence, excluding path names, "
        "but this interface may change in future versions. For more control, use the library instead of this command-line tool.\n\n"
        f"** Possible values for ALGO: {', '.join(sorted(hashlib.algorithms_available))}")
    parser.add_argument('-a','--all-files', help="also list dirs, symlinks, etc.", action="store_true")
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-d','--dump', help="also dump file contents", action="store_true")
    group.add_argument('-c','--checksum', help="generate a checksum for each file**", choices=hashlib.algorithms_available, metavar="ALGO")
    parser.add_argument('-e', '--exclude', help="filename globs to exclude*", action="append", default=[])
    parser.add_argument('paths', metavar='PATH', help='paths to process (default is current directory)', nargs='*')
    return parser

def main(argv=None):
    igbpyutils.error.init_handlers()
    parser = _arg_parser()
    args = parser.parse_args(argv)
    def matcher(paths :Sequence[PurePath]) -> bool:
        return not any( fnmatch(paths[-1].name, pat) for pat in args.exclude )
    for result in unzipwalk( args.paths if args.paths else Path(), matcher=matcher ):
        if args.checksum:
            if result.typ == FileType.FILE or args.all_files:
                print(result.checksum_line(args.checksum))
        else:
            names = tuple( str(n) for n in result.names )
            if result.typ==FileType.FILE and args.dump:
                assert result.hnd is not None
                print(f"{result.typ.name} {names!r} {result.hnd.read()!r}")
            elif result.typ==FileType.FILE or args.all_files:
                print(f"{result.typ.name} {names!r}")
    parser.exit(0)
