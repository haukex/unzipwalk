"""
``7z`` Support for :mod:`unzipwalk`
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
from typing import Union, Optional, cast, BinaryIO, IO
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from collections.abc import Generator
from contextlib import ExitStack
from io import BytesIO
# If py7zr isn't available, the following line will raise an exception, causing the imports following it to not be executed.
import py7zr     # pylint: disable=import-error,useless-suppression  # pyright: ignore [reportMissingImports]
import py7zr.io  # pylint: disable=import-error,useless-suppression  # pyright: ignore [reportMissingImports]
from .defs import FileType, UnzipWalkResult, FileProcessor, FileProcessorArgs, RecursiveOpener, RecursiveOpenArgs

class Py7zBytesIO(py7zr.io.Py7zIO):  # pyright: ignore [reportUntypedBaseClass]
    def __init__(self, buffer :IO[bytes]):
        self._buffer = buffer
    def write(self, s :Union[bytes, bytearray]) -> int:
        return self._buffer.write(s)
    def read(self, size :Optional[int] = None) -> bytes:
        return self._buffer.read(-1 if size is None else size)
    def seek(self, offset :int, whence :int = 0) -> int:
        return self._buffer.seek(offset, whence)
    def flush(self) -> None:
        return self._buffer.flush()
    def size(self) -> int:
        position = self._buffer.tell()
        self._buffer.seek(0, 2)
        size = self._buffer.tell()
        self._buffer.seek(position)
        return size

class SpoolWriter(Py7zBytesIO):
    def __init__(self, buffer :IO[bytes]):
        super().__init__(buffer)
        self.complete = False
    def close(self) -> None:
        # py7zr calls this only after the member's decompression and CRC check succeed.
        self._buffer.close()
        self.complete = True

class SpoolFactory(py7zr.io.WriterFactory):
    def __init__(self, directory :Path):
        self.directory = directory
        self._stack = ExitStack()
        self.writers :dict[str, SpoolWriter] = {}
    def create(self, filename :str) -> py7zr.io.Py7zIO:
        writer = SpoolWriter(self._stack.enter_context((self.directory/filename).open('w+b')))
        self.writers[filename] = writer
        return writer
    def extract(self, sz :py7zr.SevenZipFile, targets :list[str]) -> None:
        # Close partial outputs after each attempt, while retaining the completion state of every member.
        with self._stack:
            sz.extract(targets=targets, factory=self)

class SingleBytesIOFactory(py7zr.io.WriterFactory):  # pyright: ignore [reportUntypedBaseClass]
    def __init__(self) -> None:
        self._filename :Optional[str] = None
        self._buffer :Optional[BytesIO] = None
    def create(self, filename :str) -> py7zr.io.Py7zIO:
        # If there are multiple files of exactly the same name, then py7zr calls this factory method for each occurrence.
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
    def close(self) -> None:
        if self._buffer is not None:
            self._buffer.close()

class Wrap7Z:

    @staticmethod
    def _read_one(sz :py7zr.SevenZipFile, fn :str) -> BytesIO:
        """Read one file from a 7z archive as a BytesIO object."""
        with ExitStack() as stack:
            fact = SingleBytesIOFactory()
            stack.callback(fact.close)
            sz.reset()
            sz.extract(targets=[str(fn)], factory=fact)
            try:
                bio = fact.get()[1]
            except FileNotFoundError:  # the getter doesn't know the filename, so replace the exception
                raise FileNotFoundError(f"failed to extract {fn}")  # pylint: disable=raise-missing-from
            # The caller takes ownership only after extraction has succeeded.
            stack.pop_all()
            return bio

    @staticmethod
    def recursive_open(a :RecursiveOpenArgs, recurse :RecursiveOpener) -> Generator[IO[bytes], None, None]:
        with py7zr.SevenZipFile(cast(BinaryIO, a.fh)) as sz:
            with Wrap7Z._read_one(sz, str(a.fns[1])) as bio:
                # The following pragma seems to be needed on Python 3.14 - probably a bug in coverage.
                with recurse(RecursiveOpenArgs(fns=a.fns[1:], fh=bio)) as inner:  # pragma: no branch
                    yield inner

    @staticmethod
    def process_7z(a :FileProcessorArgs, recurse :FileProcessor) -> Generator[UnzipWalkResult, None, None]:
        try:
            # The cast from IO[bytes] to BinaryIO should be ok here I think:
            with py7zr.SevenZipFile(cast(BinaryIO, a.fh)) as sz, TemporaryDirectory() as tmp_dir:
                members = sz.list()
                accepted = [a.ctx.matcher is None or a.ctx.matcher((*a.raw_names, f7.filename)) for f7 in members]
                targets = [str(i) for i, f7 in enumerate(members) if accepted[i] and f7.is_file]
                # Keep member contents on disk, closing each write handle as extraction finishes.
                factory = SpoolFactory(Path(tmp_dir))
                if targets:
                    # The writer API receives sanitized names. Give this reader's metadata unique internal names so
                    # duplicate names and names like './file.txt' and 'file.txt' cannot collide during extraction.
                    # The archive itself and the original names saved in `members` are unchanged.
                    for i, member in enumerate(sz.files):
                        member.file_properties()['filename'] = str(i)
                try:
                    if targets:
                        factory.extract(sz, targets)
                except Exception:
                    if a.ctx.raise_errors:
                        raise
                    # Retry unprocessed members individually; independent compression blocks may still be readable.
                    for target in (fn for fn in targets if fn not in factory.writers):
                        try:
                            sz.reset()
                            factory.extract(sz, [target])
                        except Exception:
                            # A failed retry must not prevent attempts at later members.
                            pass
                for i, f7 in enumerate(members):
                    new_names = (*a.fns, PurePosixPath(f7.filename))
                    new_raw = (*a.raw_names, f7.filename)
                    if not accepted[i]:
                        yield UnzipWalkResult(names=new_names, raw_names=new_raw, typ=FileType.SKIP)
                    elif f7.is_symlink:
                        yield UnzipWalkResult(names=new_names, raw_names=new_raw, typ=FileType.SYMLINK)
                    elif f7.is_directory:
                        yield UnzipWalkResult(names=new_names, raw_names=new_raw, typ=FileType.DIR)
                    elif f7.is_file:
                        if str(i) not in factory.writers or not factory.writers[str(i)].complete:
                            yield UnzipWalkResult(names=new_names, raw_names=new_raw, typ=FileType.ERROR)
                        else:
                            with open(factory.directory/str(i), 'rb') as fh:
                                yield from recurse(FileProcessorArgs(
                                    fns=new_names, raw_names=new_raw, fh=fh, size=f7.uncompressed, ctx=a.ctx))
                    else:
                        yield UnzipWalkResult(names=new_names, raw_names=new_raw, typ=FileType.OTHER)
        except Exception:  # pylint: disable=[duplicate-code]
            if a.ctx.raise_errors:
                raise
            yield UnzipWalkResult(names=a.fns, raw_names=a.raw_names, typ=FileType.ERROR)
        else:  # pylint: disable=[duplicate-code]
            yield UnzipWalkResult(names=a.fns, raw_names=a.raw_names, typ=FileType.ARCHIVE, size=a.size)
