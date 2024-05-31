<a id="module-unzipwalk"></a>

# Recursively Walk Into Directories and Archives

This module primarily provides the function [`unzipwalk()`](#function-unzipwalk), which recursively walks
into directories and compressed files and returns all files, directories, etc. found,
together with binary file handles (file objects) for reading the files.
Currently supported are ZIP, tar, tgz, and gz compressed files.
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

## Members

<a id="function-unzipwalk"></a>

### unzipwalk.unzipwalk(paths: [str](https://docs.python.org/3/library/stdtypes.html#str) | [PathLike](https://docs.python.org/3/library/os.html#os.PathLike) | [bytes](https://docs.python.org/3/library/stdtypes.html#bytes) | [Iterable](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterable)[[str](https://docs.python.org/3/library/stdtypes.html#str) | [PathLike](https://docs.python.org/3/library/os.html#os.PathLike) | [bytes](https://docs.python.org/3/library/stdtypes.html#bytes)])

This generator recursively walks into directories and compressed files and yields named tuples of type [`UnzipWalkResult`](#unzipwalk.UnzipWalkResult).

* **Parameters:**
  **paths** – A filename or iterable of filenames.

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

#### validate()

Validate whether the object’s fields are set properly and throw errors if not.

Intended for internal use, mainly when type checkers are not being used.
[`unzipwalk()`](#function-unzipwalk) validates all the results it returns.

* **Returns:**
  The object itself, for method chaining.

### *class* unzipwalk.ReadOnlyBinary(\*args, \*\*kwargs)

Interface for the file handle (file object) used in [`UnzipWalkResult`](#unzipwalk.UnzipWalkResult).

The interface is the intersection of [`typing.BinaryIO`](https://docs.python.org/3/library/typing.html#typing.BinaryIO), [`gzip.GzipFile`](https://docs.python.org/3/library/gzip.html#gzip.GzipFile), and [`zipfile.ZipExtFile`](https://docs.python.org/3/library/zipfile.html#module-zipfile).
Because [`gzip.GzipFile`](https://docs.python.org/3/library/gzip.html#gzip.GzipFile) doesn’t implement `.tell()`, that method isn’t available here.
Whether the handle supports seeking depends on the underlying library.

Note [`unzipwalk()`](#function-unzipwalk) automatically closes files.

#### *property* name *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

#### close()

#### *property* closed *: [bool](https://docs.python.org/3/library/functions.html#bool)*

#### readable()

#### read(n: [int](https://docs.python.org/3/library/functions.html#int) = -1)

#### readline(limit: [int](https://docs.python.org/3/library/functions.html#int) = -1)

#### seekable()

#### seek(offset: [int](https://docs.python.org/3/library/functions.html#int), whence: [int](https://docs.python.org/3/library/functions.html#int) = 0)

### *class* unzipwalk.FileType(value)

Used in [`UnzipWalkResult`](#unzipwalk.UnzipWalkResult) to indicate the type of the file.

#### FILE *= 0*

A regular file.

#### ARCHIVE *= 1*

An archive file, will be descended into.

#### DIR *= 2*

A directory.

#### SYMLINK *= 3*

A symbolic link.

#### OTHER *= 4*

Some other file type (e.g. FIFO).

### unzipwalk.recursive_open(fns: [Sequence](https://docs.python.org/3/library/collections.abc.html#collections.abc.Sequence)[[str](https://docs.python.org/3/library/stdtypes.html#str) | [PathLike](https://docs.python.org/3/library/os.html#os.PathLike)], encoding=None, errors=None, newline=None)

This context manager allows opening files nested inside archives directly.

[`unzipwalk()`](#function-unzipwalk) automatically closes files as it iterates through directories and archives;
this function exists to allow you to open the returned files after the iteration.

If *any* of `encoding`, `errors`, or `newline` is specified, the returned
file is wrapped in [`io.TextIOWrapper`](https://docs.python.org/3/library/io.html#io.TextIOWrapper)!

If the last file in the list of files is an archive file, then it won’t be decompressed,
instead you’ll be able to read the archive’s raw compressed data from the handle.

```pycon
>>> from unzipwalk import recursive_open
>>> with recursive_open(('bar.zip', 'test.tar.gz', 'test/cool.txt.gz', 'test/cool.txt'), encoding='UTF-8') as fh:
...     print(fh.read())
Hi, I'm a compressed file!
```

## Command-Line Interface

```default
usage: unzipwalk [-h] [-a] [-d | -c ALGO] [PATH ...]

Recursively walk into directories and archives

positional arguments:
  PATH                  paths to process (default is current directory)

optional arguments:
  -h, --help            show this help message and exit
  -a, --all-files       also list dirs, symlinks, etc.
  -d, --dump            also dump file contents
  -c ALGO, --checksum ALGO
                        generate a checksum for each file

Possible values for ALGO: blake2b, blake2s, md5, md5-sha1, sha1, sha224,
sha256, sha384, sha3_224, sha3_256, sha3_384, sha3_512, sha512, sha512_224,
sha512_256, shake_128, shake_256, sm3
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
