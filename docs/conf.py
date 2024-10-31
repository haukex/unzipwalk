# Configuration file for the Sphinx documentation builder.
from pathlib import Path
import tomli

# pylint: disable=invalid-name

def _get_props() -> tuple[str, str, str]:
    with (Path(__file__).parent.parent/'pyproject.toml').open('rb') as fh:
        data = tomli.load(fh)
    proj = data['project']
    return proj['name'], proj['authors'][0]['name'], proj['version']

project, author, version = _get_props()
copyright = '2024 Hauke Dämpfling at the IGB'  # pylint: disable=redefined-builtin

nitpicky = True

extensions = ['sphinx.ext.autodoc', 'sphinx.ext.intersphinx', 'sphinx_markdown_builder', 'unzipwalk_clidoc']

autodoc_member_order = 'bysource'

intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'py7zr': ('https://py7zr.readthedocs.io/en/stable/', None),
}
