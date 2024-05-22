import argparse
from docutils import nodes
from docutils.parsers.rst import Directive
from sphinx.application import Sphinx
import unzipwalk

class UnzipWalkCli(Directive):
    def run(self):
        parser = unzipwalk._arg_parser()  # pyright: ignore [reportPrivateUsage]  # pylint: disable=protected-access
        # monkey patch this ArgumentParser to fix the output width
        parser._get_formatter = lambda: argparse.HelpFormatter(parser.prog, width=78)  # pylint: disable=protected-access
        return [nodes.literal_block(text=parser.format_help())]

def setup(app: Sphinx):
    app.add_directive('unzipwalk_clidoc', UnzipWalkCli)
    return {
        'version': '0.1',
        'parallel_read_safe': True,
        'parallel_write_safe': True,
    }
