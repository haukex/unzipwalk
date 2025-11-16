"""
Definitions for :mod:`unzipwalk`
================================

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
import enum
import hashlib
from contextlib import AbstractContextManager
from collections.abc import Callable, Sequence, Generator
from pathlib import PurePosixPath, PurePath, PureWindowsPath
from typing import Optional, Protocol, NamedTuple, runtime_checkable, IO
from .utils import decode_tuple

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
    """Interface for the file handle (file object) used in :class:`UnzipWalkResult`.

    This is essentially the intersection of what the underlying objects support."""
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
    def seekable(self) -> bool: ...
    def seek(self, offset: int, whence: int = io.SEEK_SET, /) -> int: ...

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
    #: When :attr:`typ` is :class:`FileType.FILE<FileType>` or :class:`FileType.ARCHIVE<FileType>`, this field *may* hold the size of the
    #: file, if the compression format and library support knowing the compressed file's size in advance. Otherwise, this is :obj:`None`.
    size :Optional[int] = None

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
        if self.typ not in (FileType.FILE, FileType.ARCHIVE) and self.size is not None:
            raise TypeError(f"invalid size, should be None but is {self.size!r}")
        if self.size is not None and not isinstance(self.size, int):  # pyright: ignore [reportUnnecessaryIsInstance]
            raise TypeError(f"invalid size {self.size!r}")
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
            except Exception:
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
            return cls( names=mk_names(m.group(2)), typ=FileType.FILE, hnd=io.BytesIO(bytes.fromhex(m.group(1))) )
        raise ValueError(f"failed to decode checksum line {line!r}")

# internal types:

FilterType = Callable[[Sequence[PurePath]], bool]

class ProcessCallContext(NamedTuple):
    matcher :Optional[FilterType]
    raise_errors :bool

class FileProcessorArgs(NamedTuple):
    ctx :ProcessCallContext
    fns :tuple[PurePath, ...]
    fh :IO[bytes]
    size :Optional[int]

FileProcessor = Callable[[FileProcessorArgs], Generator[UnzipWalkResult, None, None]]

class RecursiveOpenArgs(NamedTuple):
    fns :tuple[PurePath, ...]
    fh :IO[bytes]

RecursiveOpener = Callable[[RecursiveOpenArgs], AbstractContextManager[IO[bytes]]]
