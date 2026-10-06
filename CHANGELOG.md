Changelog for unzipwalk
=======================

2.0.0 - *not yet released*
------------------------

- **Possibly incompatible API change:** Added `UnzipWalkResult.raw_names` to preserve exact archive
  member names; `UnzipWalkResult` is therefore now a 5-tuple `(names, raw_names, typ, hnd, size)`.
  This was necessary because `pathlib` objects, as they are used in `names`, do some basic
  normalization, for example if an archive has a member named exactly `./file.txt`, `pathlib`
  normalizes this to `file.txt`, and so `recursive_open` can no longer open it. `raw_names` is now
  used in more places, such as in "matchers" and in the CLI.
  - CLI `--exclude` now matches the full final raw name, including directory components, instead of
    only the basename. For archive members, this is the path within the innermost archive.
  - `recursive_open` was overhauled in terms of its pathname handling in general.
- Improved CLI `--outfile` handling: It can no longer clobber existing files, and if the output is
  in the input files, it is skipped automatically.
- Fixed physical directory exclusions in `matcher` and CLI `--exclude`: excluded directories are
  no longer descended into, including directories passed as input paths.
- Directory traversal errors now respect `raise_errors`: they are raised by default, or when
  `raise_errors=False`, they are reported as `ERROR` results and traversal continues.
- `from_checksum_line` now defaults to the current platform's pathname format. Its `windows`
  argument affects the physical pathname and derived compression paths.
- Duplicate names in 7z archives are now yielded as separate results with their individual contents.
- Extracted 7z member buffers are now closed when iteration advances or is closed, and when
  `recursive_open` exits, including error paths.
- 7z symlinks and other special entries are now reported as `SYMLINK` and `OTHER`, respectively,
  instead of being processed as regular files.
- Walking 7z archives now extracts selected files in a single pass to temporary storage,
  avoiding repeated decompression of earlier members in solid archives.
- Returned binary handles are now annotated as `IO[bytes]` instead of `ReadOnlyBinary` so usage in
  iteration and `TextIOWrapper` work with type checkers.
  `ReadOnlyBinary` remains the runtime validation protocol and now includes iteration.

1.9.2 - Sat, Oct  3 2026
------------------------

- Fixed an issue extracting 7z archives with more than one member.

1.9.1 - Fri, Aug 28 2026
------------------------

- Added more type annotations and added `py.typed` marker

1.9.0 - Thu, Aug 20 2026
------------------------

- Added `unzipwalk.ARCHIVE_RE`
- `recursive_open` now handles invalid arguments better
- `py7zr` now supports Python 3.14, so that combination is now tested

1.8.1 - Sun, Nov 16 2025
------------------------

- Just a rebuild of 1.8.0 with proper permissions in the `.tar.gz` release file.

1.8.0 - Sun, Nov 16 2025
------------------------

- **Removed** `ReadOnlyBinary.name`
- **Added** `UnzipWalkResult.size`
- Drop testing for Python 3.9 and add Python 3.14
- More robust and uniform exception handling
- More tar file extensions are now recognized (e.g. `.txz` and `.tbz2`)
- Documentation improvements

1.7.0 - Thu, Oct 31 2024
------------------------

- Added support for `.bz2`, `.xz`, and `.7z` files (the latter requires the module `py7zr` to be installed)
- **Warning: Deprecated** `ReadOnlyBinary.name` property; will be removed in the next release.

1.6.0 - Wed, Jun 19 2024
------------------------

- Added `--outfile` CLI option

1.5.0 - Wed, Jun 19 2024
------------------------

`commit 43e2481c8ae71733d84b930ad989db67ce6cb5d2`

- Added `raise_errors` option that can be turned off so that errors during iteration don't abort the walk,
  and instead a `UnzipWalkResult` of type `FileType.ERROR` is yielded.
- **Warning: Potentially incompatible changes**
  - When `matcher` is used, previously the results would be entirely suppressed, now a `UnzipWalkResult` of type `FileType.SKIP` is yielded.
  - The CLI tool now defaults to `raise_errors` being off; you must specify `--raise-errors` to get the previous behavior.
  - The CLI tool now defaults to reporting `ERROR` and `FILE` results instead of just `FILE` results.
- Package `unzipwalk` now has a `__main__.py` so you can invoke the CLI tool with `python3 -m unzipwalk` as well

1.4.0 - Mon, Jun 17 2024
------------------------

`commit c0069e6c6cc20438b70865777b8ca97e8e0dca96`

- Made requirements more lenient to avoid dependency conflicts

1.3.0 - Mon, Jun  3 2024
------------------------

`commit 11e5d41703e50348f68410121b078afdcbe30f43`

- Further improved escaping of filenames with `--checksum` CLI option,
  and provided `UnzipWalkResult.from_checksum_line()` to parse the output.

1.2.1 - Fri, May 31 2024
------------------------

`commit e3f8275b7150fd84c7e2a5ca7d7d45c991f6fcee`

- Improved escaping of filenames with `--checksum` CLI option.

1.2.0 - Fri, May 31 2024
------------------------

`commit b9fd55222886dd3e074ea374dbd901f9024ee497`

- Added `matcher` argument to `unzipwalk()` and corresponding `--exclude` CLI option.

1.1.0 - Fri, May 31 2024
------------------------

`commit 5dbcf68c5107ec50ccee76a9e7f9e1ede27e593c`

- Added `unzipwalk.recursive_open()`.
- Updated documentation.

1.0.0 - Wed, May 22 2024
------------------------

`commit 111c8e0b92ace40c7c5f4f2d01f6cbd75748ff83`

- Initial release, based on the `unzipwalk` that was part of <https://github.com/haukex/igbdatatools>.
  - **WARNING: Incompatible Changes**
    - The `onlyfiles` argument of the `unzipwalk` function was removed and its return type has changed!
    - The output of the `unzipwalk` command line-tool has changed!

<!-- spell: ignore onlyfiles pathlib -->