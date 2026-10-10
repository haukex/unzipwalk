Changelog for unzipwalk
=======================

2.0.0 - Wed, Oct  7 2026
------------------------

`commit f38f54cd02541d2f65bc2a583a5696d1a62e1812`

- **Possibly incompatible API change:** Added `UnzipWalkResult.raw_names` to preserve exact archive
  member names; `UnzipWalkResult` is therefore now a 5-tuple `(names, raw_names, typ, hnd, size)`.
  This was necessary because `pathlib` objects, as they are used in `names`, do some basic
  normalization, for example if an archive has a member named exactly `./file.txt`, `pathlib`
  normalizes this to `file.txt`, and so `recursive_open` can no longer open it. `raw_names` is now
  used in several places, such as in "matchers" and in the CLI.
  - CLI `--exclude` now matches the full final raw name, including directory components, instead of
    only the basename. For archive members, this is the path within the innermost archive.
  - `recursive_open` was overhauled in terms of its pathname handling in general, allowing opening
    of "uncommonly" named archive members. (If more than one archive member has the *exact* same
    name, it is still not supported to open a specific one of those members.)
- Fixed physical directory exclusions in `matcher` and CLI `--exclude`: excluded directories are
  no longer descended into, including directories passed as input paths.
- Input paths are now matched before filesystem metadata is accessed, so missing or inaccessible
  excluded paths are reported as `SKIP` instead of causing errors.
- Physical symlinks supplied as input paths are now reported as `SYMLINK` without following their
  targets, including directory symlinks, dangling links, and cyclic links.
- Improved handling of inaccessible files:
  - Directory traversal errors now respect `raise_errors`: they are raised by default, or when
    `raise_errors=False`, they are reported as `ERROR` results and traversal continues.
  - File type detection now respects `raise_errors` on Python 3.14 instead of reporting
    inaccessible filesystem entries as `OTHER`.
- Returned binary handles are now annotated as `IO[bytes]` instead of `ReadOnlyBinary` so usage in
  iteration and `TextIOWrapper` work with type checkers.
  `ReadOnlyBinary` remains the runtime validation protocol and now includes iteration.
- Improvements to 7z handling:
  - Walking 7z archives now extracts selected files in a single pass to temporary storage,
    avoiding repeated decompression of earlier members in solid archives.
  - Duplicate names in archives are now yielded as separate results with their individual contents.
  - Extracted 7z member buffers are now closed when iteration advances or is closed, and when
    `recursive_open` exits, including error paths.
  - 7z symlinks and other special entries are now reported as `SYMLINK` and `OTHER`, respectively,
    instead of being processed as regular files.
  - With `raise_errors=False`, the remaining members of archives containing errors can now be
    processed.
- Improved CLI `--outfile` handling: It can no longer clobber existing files, and if the output is
  in the input files, it is skipped automatically.
  Dangling symlinks no longer cause errors when comparing input paths with the output file,
  and can still be reported or excluded normally.
- Fixed infinite recursion for files named exactly `.gz`, `.bz2`, or `.xz`: their derived
  basename is now `noname`, preserving any directory prefix.
- `from_checksum_line` now defaults to the current platform's pathname format. Its `windows`
  argument affects the physical pathname and derived compression paths.
  Both LF and CRLF line endings are now accepted on all platforms.

1.9.2 - Sat, Oct  3 2026
------------------------

`commit d634b6ee4c0b9616a6b8736e849b3b77a7cb4939`

- Fixed an issue extracting 7z archives with more than one member.

1.9.1 - Fri, Aug 28 2026
------------------------

`commit 327d95d965f34df85284db0fbc361b86edc4fda8`

- Added more type annotations and added `py.typed` marker

1.9.0 - Thu, Aug 20 2026
------------------------

`commit 48fe372a5db9628d41381330810071ce4824580f`

- Added `unzipwalk.ARCHIVE_RE`
- `recursive_open` now handles invalid arguments better
- `py7zr` now supports Python 3.14, so that combination is now tested

1.8.1 - Sun, Nov 16 2025
------------------------

`commit 36a0d0e1d0d41efa09a86154b877becf747afd75`

- Just a rebuild of 1.8.0 with proper permissions in the `.tar.gz` release file.

1.8.0 - Sun, Nov 16 2025
------------------------

`commit 680a45485f6273a66bf4a386c4fbccd221bea48d`

- **Removed** `ReadOnlyBinary.name`
- **Added** `UnzipWalkResult.size`
- Drop testing for Python 3.9 and add Python 3.14
- More robust and uniform exception handling
- More tar file extensions are now recognized (e.g. `.txz` and `.tbz2`)
- Documentation improvements

1.7.0 - Thu, Oct 31 2024
------------------------

`commit 70de03bc4d7a85d397caead032c69f32b2a53cc3`

- Added support for `.bz2`, `.xz`, and `.7z` files (the latter requires the module `py7zr` to be installed)
- **Warning: Deprecated** `ReadOnlyBinary.name` property; will be removed in the next release.

1.6.0 - Wed, Jun 19 2024
------------------------

`commit 243afeab7ff21f5e96eee9986099a1dd331d19e4`

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

<!-- spell: ignore onlyfiles pathlib noname -->