<a id="module-unzipwalk"></a>

# Recursively Walk Into Directories and Archives

This module primarily provides the function [`unzipwalk()`](#function-unzipwalk), which recursively walks
into directories and compressed files and returns all files, directories, etc. found,
together with binary file handles (file objects) for reading the files.
Currently supported are ZIP, tar, tgz (.tar.gz), bz2, xz, and gz compressed files,
plus 7zip files if the Python package [`py7zr`](https://py7zr.readthedocs.io/en/stable/api.html#module-py7zr) is installed.
You can install this package with `pip install unzipwalk[7z]` to get the latter.
File types are detected based on their extensions.

```pycon
>>> from unzipwalk import unzipwalk
>>> results = []
>>> for result in unzipwalk('.'):
...     names = tuple( name.as_posix() for name in result.names )
...     if result.hnd:  # result is a file opened for reading (binary)
...         # could use result.hnd.read() here, or for line-by-line:
...         for line in result.hnd:
...             pass  # do something interesting with the data here
...     results.append(names + (result.typ.name,))
>>> print(sorted(results))
[('bar.zip', 'ARCHIVE'),
 ('bar.zip', 'bar.txt', 'FILE'),
 ('bar.zip', 'test.tar.gz', 'ARCHIVE'),
 ('bar.zip', 'test.tar.gz', 'hello.csv', 'FILE'),
 ('bar.zip', 'test.tar.gz', 'test', 'DIR'),
 ('bar.zip', 'test.tar.gz', 'test/cool.txt.gz', 'ARCHIVE'),
 ('bar.zip', 'test.tar.gz', 'test/cool.txt.gz', 'test/cool.txt', 'FILE'),
 ('foo.txt', 'FILE')]
```

**Note** that [`unzipwalk()`](#function-unzipwalk) automatically closes files as it goes from file to file.
This means that you must use the handles as soon as you get them from the generator -
something as seemingly simple as `sorted(unzipwalk('.'))` would cause the code above to fail,
because all files will have been opened and closed during the call to [`sorted()`](https://docs.python.org/3/library/functions.html#sorted)
and the handles to read the data would no longer be available in the body of the loop.
This is why the above example first processes all the files before sorting the results.
You can also use [`recursive_open()`](#unzipwalk.recursive_open) to open the files later.

The yielded file handles can be wrapped in [`io.TextIOWrapper`](https://docs.python.org/3/library/io.html#io.TextIOWrapper) to read them as text files.
For example, to read all CSV files in the current directory and below, including within compressed files:

```pycon
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
```

Please note that both [`unzipwalk()`](#function-unzipwalk) and [`recursive_open()`](#unzipwalk.recursive_open) can raise a variety of errors:

- [`zipfile.BadZipFile`](https://docs.python.org/3/library/zipfile.html#zipfile.BadZipFile)
- [`tarfile.TarError`](https://docs.python.org/3/library/tarfile.html#tarfile.TarError)
- `py7zr.exceptions.ArchiveError` and its subclasses like [`py7zr.Bad7zFile`](https://py7zr.readthedocs.io/en/stable/api.html#py7zr.Bad7zFile)
- [`gzip.BadGzipFile`](https://docs.python.org/3/library/gzip.html#gzip.BadGzipFile) - *however*, see the notes in [`unzipwalk()`](#function-unzipwalk) about when these are actually raised
- [`zlib.error`](https://docs.python.org/3/library/zlib.html#zlib.error)
- [`lzma.LZMAError`](https://docs.python.org/3/library/lzma.html#lzma.LZMAError)
- [`EOFError`](https://docs.python.org/3/library/exceptions.html#EOFError)
- various [`OSError`](https://docs.python.org/3/library/exceptions.html#OSError)s
- other exceptions may be possible

Therefore, you may want to catch all [`RuntimeError`](https://docs.python.org/3/library/exceptions.html#RuntimeError)s to play it safe.

#### SEE ALSO
- [zipfile Issues](https://github.com/orgs/python/projects/7)
- [tarfile Issues](https://github.com/orgs/python/projects/11)
- [Compression issues](https://github.com/orgs/python/projects/20) (gzip, bzip2, lzma)
- [py7zr Issues](https://github.com/miurahr/py7zr/issues)

#### NOTE
The original name of a gzip-compressed file is derived from the compressed file’s name
by simply removing the `.gz` extension. Using the original filename from the gzip
file’s header is currently not possible due to
[limitations in the underlying library](https://github.com/python/cpython/issues/71638).

## API

<a id="function-unzipwalk"></a>

### unzipwalk.unzipwalk(paths: [str](https://docs.python.org/3/library/stdtypes.html#str) | [PathLike](https://docs.python.org/3/library/os.html#os.PathLike) | [bytes](https://docs.python.org/3/library/stdtypes.html#bytes) | [Iterable](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterable)[[str](https://docs.python.org/3/library/stdtypes.html#str) | [PathLike](https://docs.python.org/3/library/os.html#os.PathLike) | [bytes](https://docs.python.org/3/library/stdtypes.html#bytes)], \*, matcher: [Callable](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[Sequence](https://docs.python.org/3/library/collections.abc.html#collections.abc.Sequence)[[PurePath](https://docs.python.org/3/library/pathlib.html#pathlib.PurePath)]], [bool](https://docs.python.org/3/library/functions.html#bool)] | [None](https://docs.python.org/3/library/constants.html#None) = None, raise_errors: [bool](https://docs.python.org/3/library/functions.html#bool) = True) → [Generator](https://docs.python.org/3/library/collections.abc.html#collections.abc.Generator)[[UnzipWalkResult](#unzipwalk.UnzipWalkResult), [None](https://docs.python.org/3/library/constants.html#None), [None](https://docs.python.org/3/library/constants.html#None)]

This generator recursively walks into directories and compressed files and yields named tuples of type [`UnzipWalkResult`](#unzipwalk.UnzipWalkResult).

* **Parameters:**
  * **paths** – A filename or iterable of filenames.
  * **matcher** – When you provide this optional argument, it must be a callable that accepts a sequence of paths
    as its only argument, and returns a boolean value whether this filename should be further processed or not.
    If a file is skipped, a [`UnzipWalkResult`](#unzipwalk.UnzipWalkResult) of type [`FileType.SKIP`](#unzipwalk.FileType) is yielded.
  * **raise_errors** – When this is turned on (the default), any errors are raised immediately, aborting the iteration.
    If this is turned off, when decompression errors occur,
    a [`UnzipWalkResult`](#unzipwalk.UnzipWalkResult) of type [`FileType.ERROR`](#unzipwalk.FileType) is yielded for those files instead.
    **However,** be aware that [`gzip.BadGzipFile`](https://docs.python.org/3/library/gzip.html#gzip.BadGzipFile) errors are not raised until the file is actually read,
    so you’d need to add an exception handler around your read() call to handle such cases.

If [`py7zr`](https://py7zr.readthedocs.io/en/stable/api.html#module-py7zr) is not installed, those archives will not be descended into.

#### NOTE
Do not rely on the order of results! But see also the discussion in the main documentation about why
e.g. `sorted(unzipwalk(...))` automatically closes files and so may not be what you want.

<a id="unzipwalk.UnzipWalkResult"></a>

### *class* unzipwalk.UnzipWalkResult(names: [tuple](https://docs.python.org/3/library/stdtypes.html#tuple)[[PurePath](https://docs.python.org/3/library/pathlib.html#pathlib.PurePath), ...], typ: [FileType](#unzipwalk.FileType), hnd: [ReadOnlyBinary](#unzipwalk.ReadOnlyBinary) | [None](https://docs.python.org/3/library/constants.html#None) = None)

Return type for [`unzipwalk()`](#function-unzipwalk).

#### names *: [tuple](https://docs.python.org/3/library/stdtypes.html#tuple)[[PurePath](https://docs.python.org/3/library/pathlib.html#pathlib.PurePath), ...]*

A tuple of the filename(s) as [`pathlib`](https://docs.python.org/3/library/pathlib.html#module-pathlib) objects. The first element is always the physical file in the file system.
If the tuple has more than one element, then the yielded file is contained in a compressed file, possibly nested in
other compressed file(s), and the last element of the tuple will contain the file’s actual name.

#### typ *: [FileType](#unzipwalk.FileType)*

A [`FileType`](#unzipwalk.FileType) value representing the type of the current file.

#### hnd *: [ReadOnlyBinary](#unzipwalk.ReadOnlyBinary) | [None](https://docs.python.org/3/library/constants.html#None)*

When [`typ`](#unzipwalk.UnzipWalkResult.typ) is [`FileType.FILE`](#unzipwalk.FileType), this is a [`ReadOnlyBinary`](#unzipwalk.ReadOnlyBinary) file handle (file object)
for reading the file contents in binary mode. Otherwise, this is [`None`](https://docs.python.org/3/library/constants.html#None).
If this object was produced by [`from_checksum_line()`](#unzipwalk.UnzipWalkResult.from_checksum_line), this handle will read the checksum of the data, *not the data itself!*

#### validate()

Validate whether the object’s fields are set properly and throw errors if not.

Intended for internal use, mainly when type checkers are not being used.
[`unzipwalk()`](#function-unzipwalk) validates all the results it returns.

* **Returns:**
  The object itself, for method chaining.
* **Raises:**
  [**ValueError**](https://docs.python.org/3/library/exceptions.html#ValueError)**,** [**TypeError**](https://docs.python.org/3/library/exceptions.html#TypeError) – If the object is invalid.

<a id="unzipwalk.UnzipWalkResult.checksum_line"></a>

#### checksum_line(hash_algo: [str](https://docs.python.org/3/library/stdtypes.html#str), \*, raise_errors: [bool](https://docs.python.org/3/library/functions.html#bool) = True) → [str](https://docs.python.org/3/library/stdtypes.html#str)

Encodes this object into a line of text suitable for use as a checksum line.

Intended mostly for internal use by the `--checksum` CLI option.
See [`from_checksum_line()`](#unzipwalk.UnzipWalkResult.from_checksum_line) for the inverse operation.

#### WARNING
Requires that the file handle be open (for files), and will read from it to generate the checksum!

* **Parameters:**
  **hash_algo** – The hashing algorithm to use, as recognized by [`hashlib.new()`](https://docs.python.org/3/library/hashlib.html#hashlib.new).
* **Returns:**
  The checksum line, without trailing newline.

<a id="unzipwalk.UnzipWalkResult.from_checksum_line"></a>

#### *classmethod* from_checksum_line(line: [str](https://docs.python.org/3/library/stdtypes.html#str), \*, windows: [bool](https://docs.python.org/3/library/functions.html#bool) = False) → [UnzipWalkResult](#unzipwalk.UnzipWalkResult) | [None](https://docs.python.org/3/library/constants.html#None)

Decodes a checksum line as produced by [`checksum_line()`](#unzipwalk.UnzipWalkResult.checksum_line).

Intended as a utility function for use when reading files produced by the `--checksum` CLI option.

#### WARNING
The `hnd` of the returned object will *not* be a handle to
the data from the file, instead it will be a handle to read the checksum of the file!
(You could use [`recursive_open()`](#unzipwalk.recursive_open) to open the files themselves.)

* **Parameters:**
  * **line** – The line to parse.
  * **windows** – Set this to [`True`](https://docs.python.org/3/library/constants.html#True) if the pathname in the line is in Windows format,
    otherwise it is assumed the filename is in POSIX format.
* **Returns:**
  The [`UnzipWalkResult`](#unzipwalk.UnzipWalkResult) object, or [`None`](https://docs.python.org/3/library/constants.html#None) for empty or comment lines.
* **Raises:**
  [**ValueError**](https://docs.python.org/3/library/exceptions.html#ValueError) – If the line could not be parsed.

<a id="unzipwalk.FileType"></a>

### *class* unzipwalk.FileType(value)

Used in [`UnzipWalkResult`](#unzipwalk.UnzipWalkResult) to indicate the type of the file.

#### WARNING
Don’t rely on the numeric value of the enum elements, they are automatically generated and may change!

#### FILE *= 1*

A regular file.

#### ARCHIVE *= 2*

An archive file, will be descended into.

#### DIR *= 3*

A directory.

#### SYMLINK *= 4*

A symbolic link.

#### OTHER *= 5*

Some other file type (e.g. FIFO).

#### SKIP *= 6*

A file was skipped due to the `matcher` filter.

#### ERROR *= 7*

An error was encountered with this file, when the `raise_errors` option is off.

<a id="unzipwalk.recursive_open"></a>

### unzipwalk.recursive_open(fns: [Sequence](https://docs.python.org/3/library/collections.abc.html#collections.abc.Sequence)[[str](https://docs.python.org/3/library/stdtypes.html#str) | [PathLike](https://docs.python.org/3/library/os.html#os.PathLike)], encoding=None, errors=None, newline=None) → [Generator](https://docs.python.org/3/library/collections.abc.html#collections.abc.Generator)[[ReadOnlyBinary](#unzipwalk.ReadOnlyBinary) | TextIOWrapper, [None](https://docs.python.org/3/library/constants.html#None), [None](https://docs.python.org/3/library/constants.html#None)]

This context manager allows opening files nested inside archives directly.

[`unzipwalk()`](#function-unzipwalk) automatically closes files as it iterates through directories and archives;
this function exists to allow you to open the returned files after the iteration.

If *any* of `encoding`, `errors`, or `newline` is specified, the returned
file is wrapped in [`io.TextIOWrapper`](https://docs.python.org/3/library/io.html#io.TextIOWrapper)!

If the last file in the list of files is an archive file, then it won’t be decompressed,
instead you’ll be able to read the archive’s raw compressed data from the handle.

In this example, we open a gzip-compressed file, stored inside a tgz archive, which
in turn is stored in a Zip file:

```pycon
>>> from unzipwalk import recursive_open
>>> with recursive_open(('bar.zip', 'test.tar.gz', 'test/cool.txt.gz', 'test/cool.txt'), encoding='UTF-8') as fh:
...     print(fh.read())
Hi, I'm a compressed file!
```

* **Raises:**
  [**ImportError**](https://docs.python.org/3/library/exceptions.html#ImportError) – If you try to open a 7z file but [`py7zr`](https://py7zr.readthedocs.io/en/stable/api.html#module-py7zr) is not installed.

<a id="unzipwalk.ReadOnlyBinary"></a>

### *class* unzipwalk.ReadOnlyBinary(\*args, \*\*kwargs)

Interface for the file handle (file object) used in [`UnzipWalkResult`](#unzipwalk.UnzipWalkResult).

#### *property* name *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

The name of the file.

#### Deprecated
Deprecated since version 1.7.0: Deprecated because not all underlying classes implement this.
Filenames are provided by [`UnzipWalkResult`](#unzipwalk.UnzipWalkResult).

#### WARNING
Will be removed in 1.8.0! (TODO)

#### close() → [None](https://docs.python.org/3/library/constants.html#None)

Close the file.

#### NOTE
[`unzipwalk()`](#function-unzipwalk) automatically closes files.

#### *property* closed *: [bool](https://docs.python.org/3/library/functions.html#bool)*

#### readable() → [Literal](https://docs.python.org/3/library/typing.html#typing.Literal)[True]

#### read(n: [int](https://docs.python.org/3/library/functions.html#int) = -1, /) → [bytes](https://docs.python.org/3/library/stdtypes.html#bytes)

#### readline(limit: [int](https://docs.python.org/3/library/functions.html#int) = -1, /) → [bytes](https://docs.python.org/3/library/stdtypes.html#bytes)

#### seekable() → [bool](https://docs.python.org/3/library/functions.html#bool)

#### seek(offset: [int](https://docs.python.org/3/library/functions.html#int), whence: [int](https://docs.python.org/3/library/functions.html#int) = 0, /) → [int](https://docs.python.org/3/library/functions.html#int)

## Command-Line Interface

```default
usage: unzipwalk [-h] [-a] [-d | -c ALGO] [-e EXCLUDE] [-r] [-o OUTFILE]
                 [PATH ...]

Recursively walk into directories and archives

positional arguments:
  PATH                  paths to process (default is current directory)

optional arguments:
  -h, --help            show this help message and exit
  -a, --all-files       also list dirs, symlinks, etc.
  -d, --dump            also dump file contents
  -c ALGO, --checksum ALGO
                        generate a checksum for each file**
  -e EXCLUDE, --exclude EXCLUDE
                        filename globs to exclude*
  -r, --raise-errors    raise errors instead of reporting them in output
  -o OUTFILE, --outfile OUTFILE
                        output filename

* Note --exclude currently only matches against the final name in the
sequence, excluding path names, but this interface may change in future
versions. For more control, use the library instead of this command-line tool.
** Possible values for ALGO: blake2b, blake2s, md5, md5-sha1, ripemd160, sha1,
sha224, sha256, sha384, sha3_224, sha3_256, sha3_384, sha3_512, sha512,
sha512_224, sha512_256, shake_128, shake_256, sm3
```

The available checksum algorithms may vary depending on your system and Python version.
Run the command with `--help` to see the list of currently available algorithms.

## Author, Copyright, and License

Copyright (c) 2022-2024 Hauke Dämpfling ([haukex@zero-g.net](mailto:haukex@zero-g.net))
at the Leibniz Institute of Freshwater Ecology and Inland Fisheries (IGB),
Berlin, Germany, [https://www.igb-berlin.de/](https://www.igb-berlin.de/)

This library is free software: you can redistribute it and/or modify it under
the terms of the GNU Lesser General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your option) any
later version.

This library is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public License for more
details.

You should have received a copy of the GNU Lesser General Public License
along with this program. If not, see [https://www.gnu.org/licenses/](https://www.gnu.org/licenses/)
