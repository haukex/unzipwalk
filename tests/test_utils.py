"""
Tests for :mod:`unzipwalk.utils`
================================

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
import unittest
import unzipwalk.utils as uut

class TestUtils(unittest.TestCase):

    def setUp(self):
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_decode_tuple(self):
        self.assertEqual( uut.decode_tuple(repr(('hi',))), ('hi',) )
        self.assertEqual( uut.decode_tuple(repr(('hi','there'))), ('hi','there') )
        self.assertEqual( uut.decode_tuple('( "foo" , \'bar\' ) '), ('foo','bar') )
        self.assertEqual( uut.decode_tuple("('hello',)"), ('hello',) )
        self.assertEqual( uut.decode_tuple('"foo","bar"'), ('foo','bar') )
        with self.assertRaises(ValueError):
            uut.decode_tuple('')
        with self.assertRaises(ValueError):
            uut.decode_tuple('X=("foo",)')
        with self.assertRaises(ValueError):
            uut.decode_tuple('(')
        with self.assertRaises(ValueError):
            uut.decode_tuple('()')
        with self.assertRaises(ValueError):
            uut.decode_tuple('("foo")')
        with self.assertRaises(ValueError):
            uut.decode_tuple('("foo","bar",3)')
        with self.assertRaises(ValueError):
            uut.decode_tuple('("foo","bar",str)')
        with self.assertRaises(ValueError):
            uut.decode_tuple('("foo","bar","x"+"y")')
        with self.assertRaises(ValueError):
            uut.decode_tuple('["foo","bar"]')
