"""
Recursively Walk Into Directories and Archives
==============================================

This module primarily provides the function :func:`unzipwalk`, which recursively walks into
directories and compressed files and returns all files, directories, etc. found, together with
binary file handles (file objects) for reading the files. Currently supported are ``zip``, ``gz``,
``bz2``, ``xz``, and the various ``tar`` compressed formats ``tar.gz``/``tgz``, ``tar.xz``/``txz``,
and ``tar.bz2``/``tbz``/``tbz2``, plus ``7z`` files if the Python package :mod:`py7zr` is installed
(to get the latter, you can install this package with ``pip install unzipwalk[7z]``). File types
are detected based on the aforementioned extensions.

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
You can also use :func:`recursive_open` to open the files later, though using that function
is less efficient that :func:`unzipwalk` if you are opening multiple files inside of Zip
or tar archives.

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

.. note::
    The original names of files compressed with gzip, bzip2, and lzma are derived by
    simply removing the respective ``.gz``, ``.bz2``, or ``.xz`` extensions.

    Using the original filename from the gzip file's header is currently not possible due to
    `limitations in the underlying library <https://github.com/python/cpython/issues/71638>`_.

.. seealso::
    - `zipfile Issues <https://github.com/orgs/python/projects/7>`_
    - `tarfile Issues <https://github.com/orgs/python/projects/11>`_
    - `Compression issues <https://github.com/orgs/python/projects/20>`_ (gzip, bzip2, lzma)
    - `py7zr Issues <https://github.com/miurahr/py7zr/issues>`_

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
Run the command with ``--help`` to see the list of algorithms available on your system.

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
import io
import re
import stat
from bz2 import BZ2File
from gzip import GzipFile
from lzma import LZMAFile
from tarfile import TarFile
from zipfile import ZipFile
from contextlib import contextmanager
from pathlib import PurePosixPath, Path
from typing import Optional, cast, IO, Union
from collections.abc import Generator, Sequence
from igbpyutils.file import AnyPaths, to_Paths, Filename
from .defs import FileType, UnzipWalkResult, ReadOnlyBinary, FilterType, FileProcessorArgs, ProcessCallContext, RecursiveOpenArgs

# spell-checker: ignore autoclass autofunction clidoc seealso undoc

__all__ = ['FileType', 'UnzipWalkResult', 'ReadOnlyBinary', 'FilterType', 'recursive_open', 'unzipwalk']

try:  # cover-req-lt3.14
    from .wrap7z import Wrap7Z
    W7Z :Optional[Wrap7Z] = Wrap7Z()  # pylint: disable=invalid-name,useless-suppression
except (ImportError, OSError):  # cover-req-ge3.14
    W7Z = None  # pylint: disable=invalid-name,useless-suppression  # pyright: ignore [reportConstantRedefinition]

_TARFILE_RE = re.compile(r'\.(?:tar(?:\.gz|\.bz2|\.xz)?|tgz|txz|tbz2?)\Z', re.I)

@contextmanager
def _inner_recur_open(a: RecursiveOpenArgs) -> Generator[IO[bytes], None, None]:
    try:
        bl = a.fns[0].name.lower()
        assert a.fns, a.fns
        if len(a.fns)==1:
            yield a.fh
        # the following code is very similar to _proc_file, please see those code comments for details
        elif _TARFILE_RE.search(bl):
            with TarFile.open(fileobj=a.fh) as tf:
                ef = tf.extractfile(str(a.fns[1]))
                if not ef:  # e.g. directory
                    raise FileNotFoundError(f"not a file? {a.fns[0:2]}")  # [0]=the current file, [1]=the file we're trying to open
                #TODO Later: I'm not sure why the following two branch coverage exceptions are necessary on 3.14?
                with ef as fh2:
                    with _inner_recur_open(RecursiveOpenArgs(fns=a.fns[1:], fh=fh2)) as inner:  # pragma: no branch
                        yield inner
        elif bl.endswith('.zip'):
            with ZipFile(a.fh) as zf:
                with zf.open(str(a.fns[1])) as fh2:
                    with _inner_recur_open(RecursiveOpenArgs(fns=a.fns[1:], fh=fh2)) as inner:  # pragma: no branch
                        yield inner
        elif bl.endswith('.7z'):
            if W7Z:  # cover-req-lt3.14
                yield from W7Z.recursive_open(a, _inner_recur_open)
            else:  # cover-req-ge3.14
                raise ImportError("The py7zr package must be installed to open 7z files.")
        elif bl.endswith('.bz2'):
            if a.fns[1] != a.fns[0].with_suffix(''):
                raise FileNotFoundError(f"invalid bz2 filename {a.fns[0]} => {a.fns[1]}")
            with BZ2File(a.fh, mode='rb') as fh2:
                with _inner_recur_open(RecursiveOpenArgs(fns=a.fns[1:], fh=fh2)) as inner:
                    yield inner
        elif bl.endswith('.xz'):
            if a.fns[1] != a.fns[0].with_suffix(''):
                raise FileNotFoundError(f"invalid xz filename {a.fns[0]} => {a.fns[1]}")
            with LZMAFile(a.fh, mode='rb') as fh2:
                with _inner_recur_open(RecursiveOpenArgs(fns=a.fns[1:], fh=fh2)) as inner:
                    yield inner
        elif bl.endswith('.gz'):
            if a.fns[1] != a.fns[0].with_suffix(''):
                raise FileNotFoundError(f"invalid gzip filename {a.fns[0]} => {a.fns[1]}")
            with GzipFile(fileobj=a.fh, mode='rb') as fh2:
                with _inner_recur_open(RecursiveOpenArgs(fns=a.fns[1:], fh=cast(IO[bytes], fh2))) as inner:
                    yield inner
        else:
            assert False, 'should be unreachable: not all file types covered?'  # pragma: no cover
    except GeneratorExit:  # https://pylint.readthedocs.io/en/latest/user_guide/messages/warning/contextmanager-generator-missing-cleanup.html
        pass  # pragma: no cover

@contextmanager
def recursive_open(fns :Sequence[Filename], encoding=None, errors=None, newline=None) \
        -> Generator[Union[ReadOnlyBinary, io.TextIOWrapper], None, None]:
    # note Sphinx's "WARNING: py:class reference target not found: _io.TextIOWrapper" can be ignored
    """This context manager allows opening files nested inside archives directly.

    :func:`unzipwalk` automatically closes files as it iterates through directories and archives;
    this function exists to allow you to open the returned files after the iteration.
    However, this function will be less efficient that :func:`unzipwalk` if you're opening
    multiple files inside of Zip or tar archives.

    .. note: If *any* of ``encoding``, ``errors``, or ``newline`` is specified, the returned
        file is wrapped in :class:`io.TextIOWrapper`!

    .. note: If the last file in the list of files is an archive file, then it won't be decompressed,
        instead you'll be able to read the archive's raw compressed data from the handle.

    In this example, we open a gzip-compressed file, stored inside a tgz archive, which
    in turn is stored in a Zip file:

    >>> from unzipwalk import recursive_open
    >>> with recursive_open(('bar.zip', 'test.tar.gz', 'test/cool.txt.gz', 'test/cool.txt'), encoding='UTF-8') as fh:
    ...     print(fh.read())# doctest: +NORMALIZE_WHITESPACE
    Hi, I'm a compressed file!

    :raises ImportError: If you try to open a 7z file but :mod:`py7zr` is not installed.
    :raises Exception: See description in :func:`unzipwalk`.
    """
    if not fns:
        raise ValueError('no filenames given')
    with open(fns[0], 'rb') as fh:
        with _inner_recur_open(RecursiveOpenArgs(fns=(Path(fns[0]),) + tuple( PurePosixPath(f) for f in fns[1:] ), fh=fh)) as inner:
            assert inner.readable(), inner
            if encoding is not None or errors is not None or newline is not None:
                yield io.TextIOWrapper(inner, encoding=encoding, errors=errors, newline=newline)
            else:
                yield inner

def _proc_file(a :FileProcessorArgs) -> Generator[UnzipWalkResult, None, None]:  # pylint: disable=too-many-statements,too-many-branches
    bl = a.fns[-1].name.lower()
    if _TARFILE_RE.search(bl):
        try:
            with TarFile.open(fileobj=a.fh, errorlevel=2) as tf:
                for ti in tf.getmembers():
                    new_names = (*a.fns, PurePosixPath(ti.name))
                    if a.ctx.matcher is not None and not a.ctx.matcher(new_names):
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
                                yield from _proc_file(FileProcessorArgs(fns=new_names, fh=fh2, size=ti.size, ctx=a.ctx))
                        except Exception:  # pragma: no cover
                            # This can't be covered (yet) because I haven't yet found a way to trigger a TarError here.
                            # Also, https://github.com/python/cpython/issues/120740
                            if a.ctx.raise_errors:
                                raise
                            yield UnzipWalkResult(names=new_names, typ=FileType.ERROR)
                    else:
                        yield UnzipWalkResult(names=new_names, typ=FileType.OTHER)
        except Exception:
            if a.ctx.raise_errors:
                raise
            yield UnzipWalkResult(names=a.fns, typ=FileType.ERROR)
        else:
            yield UnzipWalkResult(names=a.fns, typ=FileType.ARCHIVE, size=a.size)
    elif bl.endswith('.zip'):
        try:
            with ZipFile(a.fh) as zf:
                for zi in zf.infolist():
                    # Note the ZIP specification requires forward slashes for path separators.
                    # https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT
                    new_names = (*a.fns, PurePosixPath(zi.filename))
                    if a.ctx.matcher is not None and not a.ctx.matcher(new_names):
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
                                yield from _proc_file(FileProcessorArgs(fns=new_names, fh=fh2, size=zi.file_size, ctx=a.ctx))
                        except Exception:
                            if a.ctx.raise_errors:
                                raise
                            yield UnzipWalkResult(names=new_names, typ=FileType.ERROR)
        except Exception:
            if a.ctx.raise_errors:
                raise
            yield UnzipWalkResult(names=a.fns, typ=FileType.ERROR)
        else:
            yield UnzipWalkResult(names=a.fns, typ=FileType.ARCHIVE, size=a.size)
    elif bl.endswith('.7z'):
        if W7Z:  # cover-req-lt3.14
            yield from W7Z.process_7z(a, _proc_file)
        else:  # cover-req-ge3.14
            yield UnzipWalkResult(names=a.fns, typ=FileType.ARCHIVE, size=a.size)
    elif bl.endswith('.bz2'):
        new_names = (*a.fns, a.fns[-1].with_suffix(''))
        if a.ctx.matcher is not None and not a.ctx.matcher(new_names):
            yield UnzipWalkResult(names=a.fns, typ=FileType.SKIP)
        else:
            with BZ2File(a.fh, mode='rb') as fh2:  # always binary, but specify explicitly for clarity
                yield from _proc_file(FileProcessorArgs(fns=new_names, fh=fh2, size=None, ctx=a.ctx))
            yield UnzipWalkResult(names=a.fns, typ=FileType.ARCHIVE, size=a.size)
    elif bl.endswith('.xz'):
        new_names = (*a.fns, a.fns[-1].with_suffix(''))
        if a.ctx.matcher is not None and not a.ctx.matcher(new_names):
            yield UnzipWalkResult(names=a.fns, typ=FileType.SKIP)
        else:
            with LZMAFile(a.fh, mode='rb') as fh2:  # always binary, but specify explicitly for clarity
                yield from _proc_file(FileProcessorArgs(fns=new_names, fh=fh2, size=None, ctx=a.ctx))
            yield UnzipWalkResult(names=a.fns, typ=FileType.ARCHIVE, size=a.size)
    elif bl.endswith('.gz'):
        new_names = (*a.fns, a.fns[-1].with_suffix(''))
        if a.ctx.matcher is not None and not a.ctx.matcher(new_names):
            yield UnzipWalkResult(names=a.fns, typ=FileType.SKIP)
        else:
            with GzipFile(fileobj=a.fh, mode='rb') as fh2:  # always binary, but specify explicitly for clarity
                # NOTE casting GzipFile to IO[bytes] isn't 100% safe because the former doesn't
                # implement the full interface, but testing seems to show it's ok...
                yield from _proc_file(FileProcessorArgs(fns=new_names, fh=cast(IO[bytes], fh2), size=None, ctx=a.ctx))
            yield UnzipWalkResult(names=a.fns, typ=FileType.ARCHIVE, size=a.size)
    else:
        assert a.fh.readable(), a.fh  # expected by ReadOnlyBinary
        yield UnzipWalkResult(names=a.fns, typ=FileType.FILE, hnd=a.fh, size=a.size)

def unzipwalk(paths :AnyPaths, *, matcher :Optional[FilterType] = None, raise_errors :bool = True) -> Generator[UnzipWalkResult, None, None]:
    """This generator recursively walks into directories and compressed files and yields named tuples of type :class:`UnzipWalkResult`.

    :param paths: A filename or iterable of filenames.

    :param matcher: When you provide this optional argument, it must be a callable that accepts a sequence of paths
        as its only argument, and returns a boolean value whether this filename should be further processed or not.
        If a file is skipped, a :class:`UnzipWalkResult` of type :class:`FileType.SKIP<FileType>` is yielded.

        *Be aware* that within Zip and tar archives, all files are basically a flat list, so if your matcher
        excludes a directory inside an archive, it must also exclude all files within that directory as well.
        This behavior is different for physical directories in the file system: if you exclude a directory there,
        it will not be descended into, so you won't have to exclude the files inside (though it's good practice
        to write your matcher to exclude them anyway - see for example :meth:`~pathlib.PurePath.is_relative_to`).

    :param raise_errors: When this is turned on (the default), any errors are raised immediately,
        aborting the iteration. If this is turned off, when decompression errors occur, a
        :class:`UnzipWalkResult` of type :class:`FileType.ERROR<FileType>` is yielded for those files instead.

    .. note:: If :mod:`py7zr` is not installed, those archives will not be descended into.

    .. note:: Do not rely on the order of results! But see also the discussion in the main documentation about why
        e.g. ``sorted(unzipwalk(...))`` automatically closes files and so may not be what you want.

    :raises Exception: Because of the various underlying libraries, both this function and :func:`recursive_open` can raise
        a variety of exceptions: :exc:`zipfile.BadZipFile`, :exc:`tarfile.TarError`, ``py7zr.exceptions.ArchiveError``
        and its subclasses like :exc:`py7zr.Bad7zFile`, :exc:`gzip.BadGzipFile`, :exc:`zlib.error`, :exc:`lzma.LZMAError`,
        :exc:`EOFError`, various :exc:`OSError`\\s, and other exceptions may be possible. Therefore, you may need to catch
        all :exc:`Exception`\\s to play it safe.

    .. important:: Errors from :mod:`gzip`, :mod:`bz2`, and :mod:`lzma` (``.gz``, ``.bz2``, and ``.xz`` files,
        respectively) may not be raised until the file is actually read, so you'll probably also want to add an
        exception handler around your ``read()`` call!
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
                    yield from ( r.validate() for r in
                        _proc_file(FileProcessorArgs(fns=(p,), fh=fh, size=p.stat().st_size,
                            ctx=ProcessCallContext(matcher=matcher, raise_errors=raise_errors))) )
            else:
                yield UnzipWalkResult(names=(p,), typ=FileType.OTHER).validate()  # cover-not-win32
        except Exception:  # cover-only-linux  # e.g. PermissionError
            if raise_errors:
                raise
            yield UnzipWalkResult(names=(p,), typ=FileType.ERROR).validate()
    for p in to_Paths(paths):
        try:
            is_dir = p.resolve(strict=True).is_dir()
        except Exception:
            if raise_errors:
                raise
            yield UnzipWalkResult(names=(p,), typ=FileType.ERROR).validate()
        else:
            if is_dir:
                for pa in p.rglob('*'):
                    yield from handle(pa)
            else:
                yield from handle(p)
