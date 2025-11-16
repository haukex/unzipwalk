"""
Internal Utilities for :mod:`unzipwalk`
=======================================

Author, Copyright, and License
------------------------------

Copyright (c) 2022-2025 Hauke Dämpfling (haukex@zero-g.net)
at the Leibniz Institute of Freshwater Ecology and Inland Fisheries (IGB),
Berlin, Germany, https://www.igb-berlin.de/

This library is free software: you can redistribute it and/or modify it under
the terms of the GNU Lesser General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your option) any
later version.

This library is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public License for more
details.

You should have received a copy of the GNU Lesser General Public License
along with this program. If not, see https://www.gnu.org/licenses/
"""
import ast

# spell-checker: ignore elts

def decode_tuple(code :str) -> tuple[str, ...]:
    """Helper function to parse a string as produced by :func:`repr` from a :class:`tuple` of one or more :class:`str`.

    :param code: The Python code to parse.
    :return: The :class:`tuple` that was parsed.
    :raises ValueError: If the code could not be parsed or it was not a tuple.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as ex:
        raise ValueError() from ex
    if not len(tree.body)==1 or not isinstance(tree.body[0], ast.Expr) or not isinstance(tree.body[0].value, ast.Tuple) \
            or not isinstance(tree.body[0].value.ctx, ast.Load) or len(tree.body[0].value.elts)<1:
        raise ValueError(f"failed to decode tuple {code!r}")
    elements :list[str] = []
    for e in tree.body[0].value.elts:
        if not isinstance(e, ast.Constant) or not isinstance(e.value, str):
            raise ValueError(f"failed to decode tuple {code!r}")
        elements.append(e.value)
    return tuple(elements)
