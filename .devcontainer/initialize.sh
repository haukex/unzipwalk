#!/bin/bash
set -euxo pipefail
cd "$( dirname "${BASH_SOURCE[0]}" )"/..

python -m venv .venv
# shellcheck source=/dev/null
source .venv/bin/activate
make installdeps
simple-perms -mr .
