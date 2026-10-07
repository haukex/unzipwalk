"""
Definitions for :mod:`unzipwalk`
================================

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
import io
import os
import re
import enum
import hashlib
import posixpath
from contextlib import AbstractContextManager
from pathlib import Path, PurePosixPath, PurePath, PureWindowsPath
from collections.abc import Callable, Sequence, Generator, Iterator
from typing import Optional, Protocol, NamedTuple, runtime_checkable, IO, Union, TypeVar, overload
from igbpyutils.file import Filename
from .utils import decode_tuple

# spell: ignore fspath noname

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
    """Common readable interface for the file handles used in :class:`UnzipWalkResult`.

    This protocol is used for runtime validation. Returned handles are annotated as
    :class:`typing.IO` with binary contents for compatibility with standard I/O utilities.
    The concrete stream depends on the compression format; attributes such as ``name``
    are not available on every backend. Use :attr:`UnzipWalkResult.raw_names` for filenames.
    """
    def __iter__(self) -> Iterator[bytes]: ...
    def __next__(self) -> bytes: ...
    def close(self) -> None:
        """Close the file.

        .. note::
            :func:`unzipwalk` automatically closes files.
        """
    @property
    def closed(self) -> bool: ...
    def readable(self) -> bool:
        return True
    def read(self, n: int = -1, /) -> bytes: ...
    def readline(self, limit: int = -1, /) -> bytes: ...
    def seekable(self) -> bool:
        """See :meth:`io.IOBase.seekable`.

        .. warning:: Some underlying classes may return `True` even in cases where :meth:`seek` will fail!
            (e.g. GH `python/cpython#77354 <https://github.com/python/cpython/issues/77354>`_)
        """
        ...
    def seek(self, offset: int, whence: int = io.SEEK_SET, /) -> int: ...

CHECKSUM_LINE_RE = re.compile(r'^([0-9a-f]+) \*(.+)$')
CHECKSUM_COMMENT_RE = re.compile(r'^# ([A-Z]+) (.+)$')
TARFILE_RE = re.compile(r'\.(?:tar(?:\.gz|\.bz2|\.xz)?|tgz|txz|tbz2?)\Z', re.I)

_ArchiveName = TypeVar('_ArchiveName', bound=Union[PurePath, str])
def convert_names(fns :Sequence[Filename], physical_cls :type[PurePath], archive_name :Callable[[Filename], _ArchiveName]) \
        -> tuple[Union[PurePath, _ArchiveName], ...]:
    """Convert a sequence of path names in the same way as it would be returned by :func:`unzipwalk`.

    Physical path names as well as filenames derived directly from them (gz/xz/bz2) are os-native,
    while path names inside archives are typically POSIX paths. """
    names :list[Union[PurePath, _ArchiveName]] = []
    in_archive = False
    for fn in fns:
        name = archive_name(fn) if in_archive else physical_cls(fn)
        names.append(name)
        if not in_archive:
            nl = str(name).lower()
            if TARFILE_RE.search(nl) or nl.endswith(('.zip', '.7z')):
                in_archive = True
    return tuple(names)

@overload
def compression_stem(name :str, *, physical :bool = False) -> str: ...
@overload
def compression_stem(name :PurePath, *, physical :bool = False) -> PurePath: ...
def compression_stem(name :Union[str, PurePath], *, physical :bool = False) -> Union[str, PurePath]:
    """Remove a compression suffix, using ``noname`` for an extension-only basename.

    Preserve literal strings and the flavor of normalized path objects.
    """
    path = os.path if physical or isinstance(name, Path) else posixpath
    filename = os.fspath(name)
    stem, suffix = path.splitext(filename)
    # splitext ignores all leading dots. An extension-only name needs a synthetic basename
    # so recursion advances; names such as '..gz' retain their existing suffix removal.
    if not suffix:
        basename = path.basename(filename)
        if basename.lower() in ('.gz', '.bz2', '.xz'):
            stem = filename[:-len(basename)]+'noname'
        elif basename.rfind('.') > 0:
            stem = filename[:filename.rfind('.')]
    return type(name)(stem) if isinstance(name, PurePath) else stem

class UnzipWalkResult(NamedTuple):
    """Return type for :func:`unzipwalk`."""
    #: A tuple of the filename(s) as :mod:`pathlib` objects. The first element is always the physical file in the file system.
    #: If the tuple has more than one element, then the yielded file is contained in a compressed file, possibly nested in
    #: other compressed file(s), and the last element of the tuple will contain the file's normalized name. Note that
    #: :class:`~pathlib.Path` objects normalize filenames, for example by removing ``./`` prefixes and repeated separators, and
    #: you can use :attr:`raw_names` to access the exact archive member names, for example for use in :func:`recursive_open`.
    names :tuple[PurePath, ...]
    #: The filename sequence as strings, preserving archive member names exactly as reported by the archive library (though
    #: for gzip, bzip2, and lzma files, the extension is removed and an extension-only basename becomes ``noname``).
    #: Pass this sequence to :func:`recursive_open` to avoid path normalization.
    #: This field must have the same number of elements as :attr:`names`.
    raw_names :tuple[str, ...]
    #: A :class:`FileType` value representing the type of the current file.
    typ :FileType
    #: When :attr:`typ` is :class:`FileType.FILE<FileType>`, this is a file handle (file object) for reading the file contents
    #: in binary mode, validated at runtime against :class:`ReadOnlyBinary`. Otherwise, this is :obj:`None`.
    #: If this object was produced by :meth:`from_checksum_line`, this handle will read the checksum of the data, *not the data itself!*
    hnd :Optional[IO[bytes]] = None
    #: When :attr:`typ` is :class:`FileType.FILE<FileType>` or :class:`FileType.ARCHIVE<FileType>`, this field *may* hold the size of the
    #: file, if the compression format and library support knowing the compressed file's size in advance. Otherwise, this is :obj:`None`.
    size :Optional[int] = None

    def validate(self) -> 'UnzipWalkResult':
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
        if len(self.raw_names) != len(self.names):
            raise ValueError('raw_names and names have different lengths')
        if not all( isinstance(n, str) for n in self.raw_names ):  # pyright: ignore [reportUnnecessaryIsInstance]
            raise TypeError(f"invalid raw_names {self.raw_names!r}")
        if not isinstance(self.typ, FileType):  # pyright: ignore [reportUnnecessaryIsInstance]
            raise TypeError(f"invalid type {self.typ!r}")
        if self.typ==FileType.FILE and not isinstance(self.hnd, ReadOnlyBinary):
            raise TypeError(f"invalid handle {self.hnd!r}")
        if self.typ!=FileType.FILE and self.hnd is not None:
            raise TypeError(f"invalid handle, should be None but is {self.hnd!r}")
        if self.typ not in (FileType.FILE, FileType.ARCHIVE) and self.size is not None:
            raise TypeError(f"invalid size, should be None but is {self.size!r}")
        if self.size is not None and not isinstance(self.size, int):  # pyright: ignore [reportUnnecessaryIsInstance]
            raise TypeError(f"invalid size {self.size!r}")
        return self

    def checksum_line(self, hash_algo :str, *, raise_errors :bool = True) -> str:
        """Encodes this object into a line of text suitable for use as a checksum line.

        Intended mostly for internal use by the ``--checksum`` CLI option.
        See :meth:`from_checksum_line` for the inverse operation.
        Uses :attr:`raw_names` to preserve the exact spelling of archive member names.

        .. warning:: Requires that the file handle be open (for files), and will read from it to generate the checksum!

        :param hash_algo: The hashing algorithm to use, as recognized by :func:`hashlib.new`.
        :return: The checksum line, without trailing newline.
        """
        names = self.raw_names
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
                while chunk := self.hnd.read(io.DEFAULT_BUFFER_SIZE):
                    h.update(chunk)
            except Exception:
                if raise_errors:
                    raise
                return f"# {FileType.ERROR.name} {name}"
            return f"{h.hexdigest().lower()} *{name}"
        return f"# {self.typ.name} {name}"

    @classmethod
    def from_checksum_line(cls, line :str, *, windows :bool = os.name=='nt') -> Optional['UnzipWalkResult']:
        """Decodes a checksum line as produced by :meth:`checksum_line`.

        Intended as a utility function for use when reading files produced by the ``--checksum`` CLI option.
        The filename strings are preserved in :attr:`raw_names`, alongside the normalized path objects in :attr:`names`.

        .. warning:: The ``hnd`` of the returned object will *not* be a handle to
            the data from the file, instead it will be a handle to read the checksum of the file!
            (You could use :func:`recursive_open` to open the files themselves.)

        :param line: The line to parse, optionally ending with LF or CRLF on any platform.
        :param windows: Whether the physical pathname (and gzip, bzip2, or lzma paths derived from it) are in Windows format. Defaults
            to the current platform. Archive member names always use POSIX path objects, including any files nested inside archives.
        :return: The :class:`UnzipWalkResult` object, or :obj:`None` for empty or comment lines.
        :raises ValueError: If the line could not be parsed.
        """
        # Remove only the line ending, preserving any whitespace in the filename.
        line = line[:-2] if line.endswith('\r\n') else line.removesuffix('\n')
        if not line.strip():
            return None
        def mk_result(name :str, typ :FileType, hnd :Optional[IO[bytes]] = None) -> 'UnzipWalkResult':
            raw_names = decode_tuple(name) if name.startswith('(') else (name,)
            return cls(names=convert_names(raw_names, PureWindowsPath if windows else PurePosixPath, PurePosixPath),
                raw_names=raw_names, typ=typ, hnd=hnd)
        if line.lstrip().startswith('#'):  # comment, be lenient to allow user comments
            if m := CHECKSUM_COMMENT_RE.match(line):
                if m.group(1) in FileType.__members__:
                    return mk_result(m.group(2), FileType[m.group(1)])
            return None
        if m := CHECKSUM_LINE_RE.match(line):
            return mk_result(m.group(2), FileType.FILE, io.BytesIO(bytes.fromhex(m.group(1))))
        raise ValueError(f"failed to decode checksum line {line!r}")

# internal types:

FilterType = Callable[[Sequence[str]], bool]

class ProcessCallContext(NamedTuple):
    matcher :Optional[FilterType]
    raise_errors :bool

class FileProcessorArgs(NamedTuple):
    ctx :ProcessCallContext
    fns :tuple[PurePath, ...]
    raw_names :tuple[str, ...]
    fh :IO[bytes]
    size :Optional[int]

FileProcessor = Callable[[FileProcessorArgs], Generator[UnzipWalkResult, None, None]]

class RecursiveOpenArgs(NamedTuple):
    fns :tuple[Union[PurePath, str], ...]
    fh :IO[bytes]

RecursiveOpener = Callable[[RecursiveOpenArgs], AbstractContextManager[IO[bytes]]]
