
.PHONY: all installdeps clean

all: output/markdown/index.md

# Regarding "WARNING: unknown node type: desc_returns", see:
# https://github.com/liran-funaro/sphinx-markdown-builder/issues/19
# Note on Windows the first command should be `PYTHONPATH="..;_ext" ...`
output/markdown/index.md: requirements.txt conf.py index.rst ../unzipwalk/__init__.py
	PYTHONPATH=..:_ext sphinx-build -M markdown . output
	perl fixlinks.pl output/markdown/index.md

clean:
	rm -rf output
