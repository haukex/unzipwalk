import argparse
from docutils import nodes
from docutils.parsers.rst import Directive
from sphinx.application import Sphinx
import unzipwalk.__main__

class UnzipWalkCli(Directive):
    def run(self) -> list[nodes.Node]:
        parser = unzipwalk.__main__._arg_parser()  # pyright: ignore [reportPrivateUsage]  # pylint: disable=protected-access
        parser.formatter_class = lambda prog: argparse.HelpFormatter(prog, width=78)
        return [nodes.literal_block(text=parser.format_help())]

def setup(app :Sphinx) -> dict[str, object]:
    app.add_directive('unzipwalk_clidoc', UnzipWalkCli)
    return {
        'version': '0.1',
        'parallel_read_safe': True,
        'parallel_write_safe': True,
    }
