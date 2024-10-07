#!/bin/bash
set -euo pipefail
cd "$( dirname "${BASH_SOURCE[0]}" )"/..

##### Run tests locally
# The intention of this script is to allow the user to run the same
# actions as are run by the GitHub Actions in the local environment,
# i.e. across multiple Python versions.
# The `-e VENV_PATH` option allows the user to have the `.venv*`
# paths to be created elsewhere.
# This script assumes you've set up `python3.X` aliases to the various Python versions!
# See also: https://github.com/haukex/toolshed/blob/main/notes/Python.md
###
# Reminder: Keep these checks in sync with `.github/workflows/tests.yml`.

VENV_PATH=.
usage() { echo "Usage: $0 [-e VENV_PATH]" 1>&2; exit 1; }
while getopts "e:" OPT; do
    case "${OPT}" in
        e)
            VENV_PATH="${OPTARG}"
            test -e "$VENV_PATH" || usage
            ;;
        *)
            usage
            ;;
    esac
done
shift $((OPTIND-1))

activate_venv () {
    echo "+ . $VENV_PATH/.venv$1/{Scripts,bin}/activate"
    # Remember venv may only set up the `python` alias, not necessarily `python3`
    if [ -e "$VENV_PATH/.venv$1/Scripts" ]; then
        # shellcheck source=/dev/null
        . "$VENV_PATH/.venv$1/Scripts/activate"
    else
        # shellcheck source=/dev/null
        . "$VENV_PATH/.venv$1/bin/activate"
    fi
    # Double-check:
    PYTHON_VERSION="$(python --version)"
    if [[ ! "$PYTHON_VERSION" =~ ^Python\ $1\. ]]; then
        echo "ERROR: python isn't Python $1.*, but $PYTHON_VERSION"
        exit 1
    else
        echo "# $PYTHON_VERSION at $( python -c 'import sys; print(sys.executable)' )"
    fi
}

# Reminder: Keep version list in sync with `.github/workflows/tests.yml`.
for PY_VER in 3.9 3.10 3.11 3.12 3.13; do
    echo -e "\e[1;33m====================================================> Python $PY_VER <====================================================\e[0m"

    if [ -e "$VENV_PATH/.venv$PY_VER" ]; then
        activate_venv $PY_VER
    else
        python$PY_VER -m venv "$VENV_PATH/.venv$PY_VER"
        activate_venv $PY_VER
        make installdeps
    fi

    make test

    echo -e "\e[1;32m*** Done with Python $PY_VER\e[0m"
done
