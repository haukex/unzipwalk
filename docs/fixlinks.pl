#!/usr/bin/env perl
use warnings;
use strict;
$^I = ""; # -i command line switch, edit file inplace
while (<>) {
    s{\Q[`unzipwalk()`](#\E\Kmodule-unzipwalk\)} {function-unzipwalk)}g;
    s{^\Q### unzipwalk.unzipwalk(\E} {<a id="function-unzipwalk"></a>\n\n$&};
    s{^\Q### unzipwalk.recursive_open(\E} {<a id="unzipwalk.recursive_open"></a>\n\n$&};
} continue { print }
