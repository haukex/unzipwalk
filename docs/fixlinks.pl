#!/usr/bin/env perl
use warnings;
use strict;
$^I = ""; # -i command line switch, edit file inplace
my %PFX = (
    '### unzipwalk.unzipwalk(' => 'function-unzipwalk',
    '### *class* unzipwalk.UnzipWalkResult(' => 'unzipwalk.UnzipWalkResult',
    '#### checksum_line(' => 'unzipwalk.UnzipWalkResult.checksum_line',
    '#### *classmethod* from_checksum_line(' => 'unzipwalk.UnzipWalkResult.from_checksum_line',
    '### *class* unzipwalk.ReadOnlyBinary(' => 'unzipwalk.ReadOnlyBinary',
    '### *class* unzipwalk.FileType(' => 'unzipwalk.FileType',
    '### unzipwalk.recursive_open(' => 'unzipwalk.recursive_open',
);
my ($regex) = map { qr/$_/ } join '|', map {quotemeta} sort { length $b <=> length $a or $a cmp $b } keys %PFX;
while (<>) {
    s{\Q[`unzipwalk()`](#\E\Kmodule-unzipwalk\)} {function-unzipwalk)}g;
    s{($regex)} {<a id="$PFX{$1}"></a>\n\n$&}g;
} continue { print }
