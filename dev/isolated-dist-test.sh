#!/bin/bash
set -euxo pipefail

##### Test distribution in an isolated environment
# This test takes a built .tar.gz distribution (must be passed as first argument)
# and runs the test suite on it in an isolated venv.
###

test -n "$1"
DISTFILE="$(realpath "$1")"
test -f "$DISTFILE"

cd "$( dirname "${BASH_SOURCE[0]}" )"/..

TEMPDIR="$( mktemp --directory )"
trap 'set +e; popd; rm -rf "$TEMPDIR"' EXIT

rsync -a tests "$TEMPDIR" --exclude=__pycache__

pushd "$TEMPDIR"
python -m venv venv
venv/bin/python -m pip -q install --upgrade pip
venv/bin/python -m pip -q install "$DISTFILE"
venv/bin/python -Im unittest -v
