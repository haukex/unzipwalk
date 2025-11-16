"""
``7z`` Support for :mod:`unzipwalk`
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
from typing import Union, Optional, cast, BinaryIO, IO
from collections.abc import Generator
from pathlib import PurePosixPath
from io import BytesIO
# If py7zr isn't available, the following line will raise an exception, causing the imports following it to not be executed.
import py7zr     # pylint: disable=import-error,useless-suppression  # pyright: ignore [reportMissingImports]
import py7zr.io  # pylint: disable=import-error,useless-suppression  # pyright: ignore [reportMissingImports]      # cover-req-lt3.14
from .defs import FileType, UnzipWalkResult, FileProcessor, FileProcessorArgs, RecursiveOpener, RecursiveOpenArgs  # cover-req-lt3.14

# spell-checker: ignore getbuffer nbytes

class Py7zBytesIO(py7zr.io.Py7zIO):  # pyright: ignore [reportUntypedBaseClass]  # cover-req-lt3.14
    def __init__(self, buffer :BytesIO):
        self._buffer = buffer
    def write(self, s :Union[bytes, bytearray]) -> int:
        return self._buffer.write(s)
    def read(self, size :Optional[int] = None) -> bytes:
        return self._buffer.read(size)
    def seek(self, offset :int, whence :int = 0) -> int:
        return self._buffer.seek(offset, whence)
    def flush(self) -> None:
        return self._buffer.flush()
    def size(self) -> int:
        return self._buffer.getbuffer().nbytes

class SingleBytesIOFactory(py7zr.io.WriterFactory):  # pyright: ignore [reportUntypedBaseClass]  # cover-req-lt3.14
    def __init__(self):
        self._filename :Optional[str] = None
        self._buffer :Optional[BytesIO] = None
    def create(self, filename :str) -> py7zr.io.Py7zIO:
        if not isinstance(filename, str):  # pyright: ignore [reportUnnecessaryIsInstance]
            raise TypeError()
        if self._filename is not None or self._buffer is not None:
            raise FileExistsError(f"Attempt to create second file on this factory: {filename!r}")
        self._filename = filename
        self._buffer = BytesIO()
        return Py7zBytesIO(self._buffer)
    def get(self) -> tuple[str, BytesIO]:
        if self._filename is None or self._buffer is None:
            raise FileNotFoundError
        return self._filename, self._buffer

class Wrap7Z:  # cover-req-lt3.14

    @staticmethod
    def _read_one(sz :py7zr.SevenZipFile, fn :str) -> BytesIO:
        """Read one file from a 7z archive as a BytesIO object."""
        fact = SingleBytesIOFactory()
        sz.extract(targets=[str(fn)], factory=fact)
        try:
            return fact.get()[1]
        except FileNotFoundError:  # the getter doesn't know the filename, so replace the exception
            raise FileNotFoundError(f"failed to extract {fn}")  # pylint: disable=raise-missing-from

    @staticmethod
    def recursive_open(a :RecursiveOpenArgs, recurse :RecursiveOpener) -> Generator[IO[bytes], None, None]:
        with py7zr.SevenZipFile(cast(BinaryIO, a.fh)) as sz:
            with recurse(RecursiveOpenArgs(fns=a.fns[1:], fh=Wrap7Z._read_one(sz, str(a.fns[1])))) as inner:
                yield inner

    @staticmethod
    def process_7z(a :FileProcessorArgs, recurse :FileProcessor) -> Generator[UnzipWalkResult, None, None]:
        try:
            # The cast from IO[bytes] to BinaryIO should be ok here I think:
            with py7zr.SevenZipFile(cast(BinaryIO, a.fh)) as sz:
                for f7 in sz.list():
                    new_names = (*a.fns, PurePosixPath(f7.filename))
                    if a.ctx.matcher is not None and not a.ctx.matcher(new_names):
                        yield UnzipWalkResult(names=new_names, typ=FileType.SKIP)
                    elif f7.is_directory:
                        yield UnzipWalkResult(names=new_names, typ=FileType.DIR)
                    else:
                        try:
                            bio = Wrap7Z._read_one(sz, f7.filename)
                        except Exception:  # pylint: disable=[duplicate-code]
                            if a.ctx.raise_errors:
                                raise
                            yield UnzipWalkResult(names=new_names, typ=FileType.ERROR)
                        else:
                            yield from recurse(FileProcessorArgs(fns=new_names, fh=bio, size=f7.uncompressed, ctx=a.ctx))
        except Exception:  # pylint: disable=[duplicate-code]
            if a.ctx.raise_errors:
                raise
            yield UnzipWalkResult(names=a.fns, typ=FileType.ERROR)
        else:  # pylint: disable=[duplicate-code]
            yield UnzipWalkResult(names=a.fns, typ=FileType.ARCHIVE, size=a.size)
