Changelog for unzipwalk
=======================

1.4.0 - Mon, Jun 17 2024
------------------------

- Made requirements more lenient to avoid dependency conflicts

1.3.0 - Mon, Jun  3 2024
------------------------

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
