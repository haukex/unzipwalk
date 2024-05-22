#!/usr/bin/env perl
use warnings;
use strict;
$^I = ""; # -i command line switch, edit file inplace
while (<>) {
    s{\Q[`unzipwalk()`](#\E\Kmodule-unzipwalk\)} {function-unzipwalk)}g;
    s{^\Q### unzipwalk.unzipwalk(\E} {<a id="function-unzipwalk"></a>\n\n$&};
} continue { print }