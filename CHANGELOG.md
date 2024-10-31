Changelog for unzipwalk
=======================

1.8.0 - *not yet released*
--------------------------

- **Removed** `ReadOnlyBinary.name`
- More robust and uniform exception handling
- ...

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
