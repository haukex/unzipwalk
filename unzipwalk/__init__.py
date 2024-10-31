# pylint: disable=too-many-lines
"""
Recursively Walk Into Directories and Archives
==============================================

This module primarily provides the function :func:`unzipwalk`, which recursively walks
into directories and compressed files and returns all files, directories, etc. found,
together with binary file handles (file objects) for reading the files.
Currently supported are ZIP, tar, tgz (.tar.gz), bz2, xz, and gz compressed files,
plus 7zip files if the Python package :mod:`py7zr` is installed.
You can install this package with ``pip install unzipwalk[7z]`` to get the latter.
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

Please note that both :func:`unzipwalk` and :func:`recursive_open` can raise a variety of errors:

- :exc:`zipfile.BadZipFile`
- :exc:`tarfile.TarError`
- ``py7zr.exceptions.ArchiveError`` and its subclasses like :exc:`py7zr.Bad7zFile`
- :exc:`gzip.BadGzipFile` - *however*, see the notes in :func:`unzipwalk` about when these are actually raised
- :exc:`zlib.error`
- :exc:`lzma.LZMAError`
- :exc:`EOFError`
- various :exc:`OSError`\\s
- other exceptions may be possible

Therefore, you may want to catch all :exc:`RuntimeError`\\s to play it safe.

.. seealso::
    - `zipfile Issues <https://github.com/orgs/python/projects/7>`_
    - `tarfile Issues <https://github.com/orgs/python/projects/11>`_
    - `Compression issues <https://github.com/orgs/python/projects/20>`_ (gzip, bzip2, lzma)
    - `py7zr Issues <https://github.com/miurahr/py7zr/issues>`_

.. note::
    The original name of a gzip-compressed file is derived from the compressed file's name
    by simply removing the ``.gz`` extension. Using the original filename from the gzip
    file's header is currently not possible due to
    `limitations in the underlying library <https://github.com/python/cpython/issues/71638>`_.

API
---

.. autofunction:: unzipwalk.unzipwalk

.. autoclass:: unzipwalk.UnzipWalkResult
    :members:

.. autoclass:: unzipwalk.FileType
    :members:

.. autofunction:: unzipwalk.recursive_open

.. autoclass:: unzipwalk.ReadOnlyBinary
    :members:
    :undoc-members:

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
import sys
import ast
import stat
import zlib
import enum
import hashlib
import argparse
from bz2 import BZ2File
from fnmatch import fnmatch
from lzma import LZMAFile, LZMAError
from tarfile import TarFile, TarError
from contextlib import contextmanager
from gzip import GzipFile, BadGzipFile
from zipfile import ZipFile, BadZipFile, LargeZipFile
from collections.abc import Generator, Sequence, Callable
from pathlib import PurePosixPath, PurePath, Path, PureWindowsPath
from typing import Optional, cast, Protocol, Literal, BinaryIO, NamedTuple, runtime_checkable, Union
from igbpyutils.file import AnyPaths, to_Paths, Filename
import igbpyutils.error
#TODO Later: Currently this whole file and its tests are excluded from py-check-script-vs-lib due to this `try`, what's a better way?
try:  # cover-req-lt3.13
    import py7zr  # pyright: ignore [reportMissingImports]
    import py7zr.exceptions  # pyright: ignore [reportMissingImports]
except (ImportError, OSError):  # cover-req-ge3.13  # cover-only-win32
    py7zr = None  # type: ignore[assignment,unused-ignore]

class FileType(enum.IntEnum):
    """Used in :class:`UnzipWalkResult` to indicate the type of the file.

    .. warning:: Don't rely on the numeric value of the enum elements, they are automatically generated and may change!
    """
    #: A regular file.
    FILE = enum.auto()
    #: An archive file, will be descended into.
    ARCHIVE = enum.auto()
    #: A directory.
    DIR = enum.auto()
    #: A symbolic link.
    SYMLINK = enum.auto()
    #: Some other file type (e.g. FIFO).
    OTHER = enum.auto()
    #: A file was skipped due to the ``matcher`` filter.
    SKIP = enum.auto()
    #: An error was encountered with this file, when the ``raise_errors`` option is off.
    ERROR = enum.auto()

@runtime_checkable
class ReadOnlyBinary(Protocol):  # pragma: no cover  (b/c Protocol class)
    """Interface for the file handle (file object) used in :class:`UnzipWalkResult`."""
    @property
    def name(self) -> str:
        """The name of the file.

        .. deprecated:: 1.7.0
            Deprecated because not all underlying classes implement this.
            Filenames are provided by :class:`UnzipWalkResult`.

        .. warning:: Will be removed in 1.8.0! (TODO)
        """
        ...  # pylint: disable=unnecessary-ellipsis
    def close(self) -> None:
        """Close the file.

        .. note::
            :func:`unzipwalk` automatically closes files.
        """
    @property
    def closed(self) -> bool: ...
    def readable(self) -> Literal[True]:
        return True
    def read(self, n: int = -1, /) -> bytes: ...
    def readline(self, limit: int = -1, /) -> bytes: ...
    def seekable(self) -> bool: ...
    def seek(self, offset: int, whence: int = io.SEEK_SET, /) -> int: ...

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
    elements :list[str] = []
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

    def checksum_line(self, hash_algo :str, *, raise_errors :bool = True) -> str:
        """Encodes this object into a line of text suitable for use as a checksum line.

        Intended mostly for internal use by the ``--checksum`` CLI option.
        See :meth:`from_checksum_line` for the inverse operation.

        .. warning:: Requires that the file handle be open (for files), and will read from it to generate the checksum!

        :param hash_algo: The hashing algorithm to use, as recognized by :func:`hashlib.new`.
        :return: The checksum line, without trailing newline.
        """
        names = tuple( str(n) for n in self.names )
        if len(names)==1 and names[0] and names[0].strip()==names[0] and not names[0].startswith('(') \
                and '\n' not in names[0] and '\r' not in names[0]:  # pylint: disable=too-many-boolean-expressions
            name = names[0]
        else:
            name = repr(names)
            assert name.startswith('('), name
        assert '\n' not in name and '\r' not in name, name
        if self.typ == FileType.FILE:
            assert self.hnd is not None, self
            h = hashlib.new(hash_algo)
            try:
                h.update(self.hnd.read())
            except (OSError, LZMAError, EOFError):  # BadGzipFile isa OSError, and bz2 throws OSErrors directly; EOFError isn't a OSError
                if raise_errors:
                    raise
                return f"# {FileType.ERROR.name} {name}"
            return f"{h.hexdigest().lower()} *{name}"
        return f"# {self.typ.name} {name}"

    @classmethod
    def from_checksum_line(cls, line :str, *, windows :bool=False) -> Optional['UnzipWalkResult']:
        """Decodes a checksum line as produced by :meth:`checksum_line`.

        Intended as a utility function for use when reading files produced by the ``--checksum`` CLI option.

        .. warning:: The ``hnd`` of the returned object will *not* be a handle to
            the data from the file, instead it will be a handle to read the checksum of the file!
            (You could use :func:`recursive_open` to open the files themselves.)

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
            bio = io.BytesIO(bytes.fromhex(m.group(1)))
            names = mk_names(m.group(2))
            bio.name = names[-1]  # give it a .name property to make it conform to ReadOnlyBinary
            assert isinstance(bio, ReadOnlyBinary)  # type: ignore[unreachable]
            return cls( names=names, typ=FileType.FILE, hnd=bio )  # type: ignore[unreachable]
        raise ValueError(f"failed to decode checksum line {line!r}")

if py7zr:  # cover-req-lt3.13
    def _rd1_7z(sz :py7zr.SevenZipFile, fn :str) -> io.BytesIO:  # pyright: ignore [reportInvalidTypeForm]
        """Read one file from a 7z archive as a BytesIO object."""
        d = sz.read(targets=[str(fn)])
        if not d:  # none or empty
            raise FileNotFoundError(f"failed to extract {fn}")
        bios = list(d.values())
        if len(bios)>1:
            raise FileExistsError(f"Unexpected: More than one file found for name {fn}")
        bio = bios[0]
        assert isinstance(bio, io.BytesIO)
        return bio
else:  # cover-req-ge3.13  # cover-only-win32
    pass

@contextmanager
def _inner_recur_open(fh :BinaryIO, fns :tuple[PurePath, ...]) -> Generator[BinaryIO, None, None]:
    try:
        bl = fns[0].name.lower()
        assert fns, fns
        if len(fns)==1:
            yield fh
        # the following code is very similar to _proc_file, please see those code comments for details
        elif bl.endswith('.tar.xz') or bl.endswith('.tar.bz2') or bl.endswith('.tar.gz') or bl.endswith('.tgz') or bl.endswith('.tar'):
            with TarFile.open(fileobj=fh) as tf:
                ef = tf.extractfile(str(fns[1]))
                if not ef:  # e.g. directory
                    #TODO Later: is the following fns[0:2] correct?
                    raise FileNotFoundError(f"not a file? {fns[0:2]}")
                with ef as fh2:
                    with _inner_recur_open(cast(BinaryIO, fh2), fns[1:]) as inner:
                        yield inner
        elif bl.endswith('.zip'):
            with ZipFile(fh) as zf:
                with zf.open(str(fns[1])) as fh2:
                    with _inner_recur_open(cast(BinaryIO, fh2), fns[1:]) as inner:
                        yield inner
        elif bl.endswith('.7z'):
            if not py7zr:  # cover-req-ge3.13  # cover-only-win32
                raise ImportError("The py7zr package must be installed to open 7z files.")
            with py7zr.SevenZipFile(fh) as sz:  # cover-req-lt3.13
                with _inner_recur_open(_rd1_7z(sz, str(fns[1])), fns[1:]) as inner:
                    yield inner
        elif bl.endswith('.bz2'):
            if fns[1] != fns[0].with_suffix(''):
                raise FileNotFoundError(f"invalid bz2 filename {fns[0]} => {fns[1]}")
            with BZ2File(fh, mode='rb') as fh2:
                with _inner_recur_open(cast(BinaryIO, fh2), fns[1:]) as inner:
                    yield inner
        elif bl.endswith('.xz'):
            if fns[1] != fns[0].with_suffix(''):
                raise FileNotFoundError(f"invalid xz filename {fns[0]} => {fns[1]}")
            with LZMAFile(fh, mode='rb') as fh2:
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

    :raises ImportError: If you try to open a 7z file but :mod:`py7zr` is not installed.
    """
    # note Sphinx's "WARNING: py:class reference target not found: _io.TextIOWrapper" can be ignored
    if not fns:
        raise ValueError('no filenames given')
    with open(fns[0], 'rb') as fh:
        with _inner_recur_open(fh, (Path(fns[0]),) + tuple( PurePosixPath(f) for f in fns[1:] )) as inner:
            assert inner.readable(), inner
            if encoding is not None or errors is not None or newline is not None:
                yield io.TextIOWrapper(inner, encoding=encoding, errors=errors, newline=newline)
            else:
                yield cast(ReadOnlyBinary, inner)

FilterType = Callable[[Sequence[PurePath]], bool]

def _proc_file(fns :tuple[PurePath, ...], fh :BinaryIO, *,  # pylint: disable=too-many-statements,too-many-branches
               matcher :Optional[FilterType], raise_errors :bool) -> Generator[UnzipWalkResult, None, None]:
    bl = fns[-1].name.lower()
    if bl.endswith('.tar.xz') or bl.endswith('.tar.bz2') or bl.endswith('.tar.gz') or bl.endswith('.tgz') or bl.endswith('.tar'):
        try:
            with TarFile.open(fileobj=fh, errorlevel=2) as tf:
                for ti in tf.getmembers():
                    new_names = (*fns, PurePosixPath(ti.name))
                    if matcher is not None and not matcher(new_names):
                        yield UnzipWalkResult(names=new_names, typ=FileType.SKIP)
                    # for ti.type see e.g.: https://github.com/python/cpython/blob/v3.12.3/Lib/tarfile.py#L88
                    elif ti.issym():
                        yield UnzipWalkResult(names=new_names, typ=FileType.SYMLINK)
                    elif ti.isdir():
                        yield UnzipWalkResult(names=new_names, typ=FileType.DIR)
                    elif ti.isfile():
                        try:
                            # Note apparently this can burn a lot of memory on <3.13: https://github.com/python/cpython/issues/102120
                            ef = tf.extractfile(ti)  # always binary
                            assert ef is not None, ti  # make type checker happy; we know this is true because we checked it's a file
                            with ef as fh2:
                                assert fh2.readable(), ti  # expected by ReadOnlyBinary
                                # NOTE type checker thinks fh2 is typing.IO[bytes], but it's actually a tarfile.ExFileObject,
                                # which is an io.BufferedReader subclass - which should be safe to cast to BinaryIO, I think.
                                yield from _proc_file(new_names, cast(BinaryIO, fh2), matcher=matcher, raise_errors=raise_errors)
                        except TarError:  # pragma: no cover
                            # This can't be covered (yet) because I haven't yet found a way to trigger a TarError here.
                            # Also, https://github.com/python/cpython/issues/120740
                            if raise_errors:
                                raise
                            yield UnzipWalkResult(names=new_names, typ=FileType.ERROR)
                    else:
                        yield UnzipWalkResult(names=new_names, typ=FileType.OTHER)
        except TarError:
            if raise_errors:
                raise
            yield UnzipWalkResult(names=fns, typ=FileType.ERROR)
        else:
            yield UnzipWalkResult(names=fns, typ=FileType.ARCHIVE)
    elif bl.endswith('.zip'):
        try:
            with ZipFile(fh) as zf:
                for zi in zf.infolist():
                    # Note the ZIP specification requires forward slashes for path separators.
                    # https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT
                    new_names = (*fns, PurePosixPath(zi.filename))
                    if matcher is not None and not matcher(new_names):
                        yield UnzipWalkResult(names=new_names, typ=FileType.SKIP)
                    # Manually detect symlinks in ZIP files (should be rare anyway)
                    # e.g. from zipfile.py: z_info.external_attr = (st.st_mode & 0xFFFF) << 16
                    # we're not going to worry about other special file types in ZIP files
                    elif zi.create_system==3 and stat.S_ISLNK(zi.external_attr>>16):  # 3 is UNIX
                        yield UnzipWalkResult(names=new_names, typ=FileType.SYMLINK)
                    elif zi.is_dir():
                        yield UnzipWalkResult(names=new_names, typ=FileType.DIR)
                    else:  # (note this interface doesn't have an is_file)
                        try:
                            with zf.open(zi) as fh2:  # always binary mode
                                assert fh2.readable(), zi  # expected by ReadOnlyBinary
                                # NOTE type checker thinks fh2 is typing.IO[bytes], but it's actually a zipfile.ZipExtFile,
                                # which is an io.BufferedIOBase subclass - which should be safe to cast to BinaryIO, I think.
                                yield from _proc_file(new_names, cast(BinaryIO, fh2), matcher=matcher, raise_errors=raise_errors)
                        except (RuntimeError, ValueError, BadZipFile, LargeZipFile):
                            if raise_errors:
                                raise
                            yield UnzipWalkResult(names=new_names, typ=FileType.ERROR)
        except (RuntimeError, ValueError, BadZipFile, LargeZipFile):
            if raise_errors:
                raise
            yield UnzipWalkResult(names=fns, typ=FileType.ERROR)
        else:
            yield UnzipWalkResult(names=fns, typ=FileType.ARCHIVE)
    elif bl.endswith('.7z'):
        if py7zr:  # cover-req-lt3.13
            try:
                with py7zr.SevenZipFile(fh) as sz:
                    for f7 in sz.list():
                        new_names = (*fns, PurePosixPath(f7.filename))
                        if matcher is not None and not matcher(new_names):
                            yield UnzipWalkResult(names=new_names, typ=FileType.SKIP)
                        elif f7.is_directory:
                            yield UnzipWalkResult(names=new_names, typ=FileType.DIR)
                        else:
                            try:
                                bio = _rd1_7z(sz, f7.filename)
                            except (OSError, py7zr.exceptions.ArchiveError):
                                if raise_errors:
                                    raise
                                yield UnzipWalkResult(names=new_names, typ=FileType.ERROR)
                            else:
                                bio.name = f7.filename  # give it a .name property to make it conform to ReadOnlyBinary
                                yield from _proc_file(new_names, bio, matcher=matcher, raise_errors=raise_errors)
            except py7zr.exceptions.ArchiveError:
                if raise_errors:
                    raise
                yield UnzipWalkResult(names=fns, typ=FileType.ERROR)
            else:
                yield UnzipWalkResult(names=fns, typ=FileType.ARCHIVE)
        else:  # cover-req-ge3.13  # cover-only-win32
            yield UnzipWalkResult(names=fns, typ=FileType.ARCHIVE)
    elif bl.endswith('.bz2'):
        new_names = (*fns, fns[-1].with_suffix(''))
        if matcher is not None and not matcher(new_names):
            yield UnzipWalkResult(names=fns, typ=FileType.SKIP)
            return
        try:
            with BZ2File(fh, mode='rb') as fh2:  # always binary, but specify explicitly for clarity
                assert fh2.readable(), new_names  # expected by ReadOnlyBinary
                # NOTE casting BZ2File to BinaryIO isn't 100% safe because the former doesn't implement the full interface,
                # but testing seems to show it's ok...
                #TODO Later: why do I need "no cover" in the following two instead of -ge-3.13 ?
                if not hasattr(fh2, 'name'):  # pragma: no cover
                    fh2.name = str(new_names[-1])  # type: ignore[misc]  # make object conform to ReadOnlyBinary
                yield from _proc_file(new_names, cast(BinaryIO, fh2), matcher=matcher, raise_errors=raise_errors)
        except (OSError, EOFError):
            if raise_errors:
                raise
            yield UnzipWalkResult(names=fns, typ=FileType.ERROR)
        else:
            yield UnzipWalkResult(names=fns, typ=FileType.ARCHIVE)
    elif bl.endswith('.xz'):
        new_names = (*fns, fns[-1].with_suffix(''))
        if matcher is not None and not matcher(new_names):
            yield UnzipWalkResult(names=fns, typ=FileType.SKIP)
            return
        try:
            with LZMAFile(fh, mode='rb') as fh2:  # always binary, but specify explicitly for clarity
                assert fh2.readable(), new_names  # expected by ReadOnlyBinary
                # NOTE casting LZMAFile to BinaryIO isn't 100% safe because the former doesn't implement the full interface,
                # but testing seems to show it's ok...
                if not hasattr(fh2, 'name'):  # pragma: no cover
                    fh2.name = str(new_names[-1])  # type: ignore[misc]  # make object conform to ReadOnlyBinary
                yield from _proc_file(new_names, cast(BinaryIO, fh2), matcher=matcher, raise_errors=raise_errors)
        except LZMAError:
            if raise_errors:
                raise
            yield UnzipWalkResult(names=fns, typ=FileType.ERROR)
        else:
            yield UnzipWalkResult(names=fns, typ=FileType.ARCHIVE)
    elif bl.endswith('.gz'):
        new_names = (*fns, fns[-1].with_suffix(''))
        if matcher is not None and not matcher(new_names):
            yield UnzipWalkResult(names=fns, typ=FileType.SKIP)
            return
        try:
            with GzipFile(fileobj=fh, mode='rb') as fh2:  # always binary, but specify explicitly for clarity
                assert fh2.readable(), new_names  # expected by ReadOnlyBinary
                # NOTE casting GzipFile to BinaryIO isn't 100% safe because the former doesn't implement the full interface,
                # but testing seems to show it's ok...
                yield from _proc_file(new_names, cast(BinaryIO, fh2), matcher=matcher, raise_errors=raise_errors)
        except (zlib.error, BadGzipFile, EOFError):
            if raise_errors:
                raise
            yield UnzipWalkResult(names=fns, typ=FileType.ERROR)
        else:
            yield UnzipWalkResult(names=fns, typ=FileType.ARCHIVE)
    else:
        assert fh.readable(), fh  # expected by ReadOnlyBinary
        # The following cast is safe since ReadOnlyBinary is a subset of the interfaces.
        yield UnzipWalkResult(names=fns, typ=FileType.FILE, hnd=cast(ReadOnlyBinary, fh))

def unzipwalk(paths :AnyPaths, *, matcher :Optional[FilterType] = None, raise_errors :bool = True) -> Generator[UnzipWalkResult, None, None]:
    """This generator recursively walks into directories and compressed files and yields named tuples of type :class:`UnzipWalkResult`.

    :param paths: A filename or iterable of filenames.
    :param matcher: When you provide this optional argument, it must be a callable that accepts a sequence of paths
        as its only argument, and returns a boolean value whether this filename should be further processed or not.
        If a file is skipped, a :class:`UnzipWalkResult` of type :class:`FileType.SKIP<FileType>` is yielded.
    :param raise_errors: When this is turned on (the default), any errors are raised immediately, aborting the iteration.
        If this is turned off, when decompression errors occur,
        a :class:`UnzipWalkResult` of type :class:`FileType.ERROR<FileType>` is yielded for those files instead.
        **However,** be aware that :exc:`gzip.BadGzipFile` errors are not raised until the file is actually read,
        so you'd need to add an exception handler around your `read()` call to handle such cases.

    If :mod:`py7zr` is not installed, those archives will not be descended into.

    .. note:: Do not rely on the order of results! But see also the discussion in the main documentation about why
        e.g. ``sorted(unzipwalk(...))`` automatically closes files and so may not be what you want.
    """
    def handle(p :Path):
        try:
            if matcher is not None and not matcher((p,)):
                yield UnzipWalkResult(names=(p,), typ=FileType.SKIP).validate()
            elif p.is_symlink():
                yield UnzipWalkResult(names=(p,), typ=FileType.SYMLINK).validate()  # cover-not-win32
            elif p.is_dir():
                yield UnzipWalkResult(names=(p,), typ=FileType.DIR).validate()
            elif p.is_file():
                with p.open('rb') as fh:
                    yield from ( r.validate() for r in _proc_file((p,), fh, matcher=matcher, raise_errors=raise_errors) )
            else:
                yield UnzipWalkResult(names=(p,), typ=FileType.OTHER).validate()  # cover-not-win32
        except (FileNotFoundError, PermissionError):  # cover-only-linux
            if raise_errors:
                raise
            yield UnzipWalkResult(names=(p,), typ=FileType.ERROR).validate()
    for p in to_Paths(paths):
        try:
            is_dir = p.resolve(strict=True).is_dir()
        except (FileNotFoundError, PermissionError):
            if raise_errors:
                raise
            yield UnzipWalkResult(names=(p,), typ=FileType.ERROR).validate()
        else:
            if is_dir:
                for pa in p.rglob('*'):
                    yield from handle(pa)
            else:
                yield from handle(p)

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
    parser.add_argument('-r', '--raise-errors', help="raise errors instead of reporting them in output", action="store_true")
    parser.add_argument('-o', '--outfile', help="output filename")
    parser.add_argument('paths', metavar='PATH', help='paths to process (default is current directory)', nargs='*')
    return parser

@contextmanager
def _open(filename :Optional[Filename]):
    """Apparently needs to be in its own context manager (instead of using nullcontext) so the type checkers are happy."""
    if filename and filename != '-':
        with open(filename, 'x', encoding='UTF-8') as fh:
            yield fh
    else:
        yield sys.stdout

def main(argv=None):
    igbpyutils.error.init_handlers()
    parser = _arg_parser()
    args = parser.parse_args(argv)
    def matcher(paths :Sequence[PurePath]) -> bool:
        return not any( fnmatch(paths[-1].name, pat) for pat in args.exclude )
    report = (FileType.FILE, FileType.ERROR)
    with _open(args.outfile) as fh:
        for result in unzipwalk( args.paths if args.paths else Path(), matcher=matcher, raise_errors=args.raise_errors ):
            if args.checksum:
                if result.typ in report or args.all_files:
                    print(result.checksum_line(args.checksum, raise_errors=args.raise_errors), file=fh)
            else:
                names = tuple( str(n) for n in result.names )
                if result.typ == FileType.FILE and args.dump:
                    assert result.hnd is not None, result
                    try:
                        data = result.hnd.read()
                    except (OSError, LZMAError, EOFError):  # BadGzipFile isa OSError, and bz2 throws OSErrors directly; EOFError isn't a OSError
                        if args.raise_errors:
                            raise
                        print(f"{FileType.ERROR.name} {names!r}", file=fh)
                    else:
                        print(f"{result.typ.name} {names!r} {data!r}", file=fh)
                elif result.typ in report or args.all_files:
                    print(f"{result.typ.name} {names!r}", file=fh)
    parser.exit(0)
