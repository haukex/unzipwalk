
.PHONY: all installdeps clean

all: output/markdown/index.md

PATHSEP := :
ifeq ($(OS),Windows_NT)
PATHSEP := ;
endif

output/markdown/index.md: requirements.txt conf.py index.rst ../unzipwalk/__init__.py
	PYTHONPATH="..$(PATHSEP)_ext" sphinx-build -M markdown . output
	perl fixlinks.pl output/markdown/index.md

clean:
	rm -rf output
