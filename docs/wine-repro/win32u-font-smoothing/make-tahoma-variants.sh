#!/usr/bin/env bash
# Builds renamed variants of Wine's own Tahoma (LGPL) for tahoma-ppem.c:
#   TTR20/TTR22  wine-11.20 / wine-11.22 tahoma.ttf unchanged
#   TTRNB        11.22 without embedded bitmaps (EBDT/EBLC/BDF)
#   TTRSG        11.22 with gasp = smooth + grid-fit at every size (15)
#   TTRBO        both;  TTB22 / TTBBO the same for tahomabd.ttf
# Needs curl and fonttools' ttx (e.g. `nix shell nixpkgs#python3Packages.fonttools`).
set -euo pipefail
out=${1:-.}; mkdir -p "$out"; cd "$out"
for v in 11.20 11.22; do for f in tahoma tahomabd; do
    curl -sfL -o "$f-$v.ttf" "https://gitlab.winehq.org/wine/wine/-/raw/wine-$v/fonts/$f.ttf"
done; done
mk() { # source tag drop-bitmaps smooth-gasp
    local x=(); [ "$3" = 1 ] && x=(-x EBDT -x EBLC -x BDF)
    ttx -q "${x[@]}" -o "v-$2.ttx" "$1.ttf"
    sed -i "s/Tahoma/TT$2/g" "v-$2.ttx"
    [ "$4" = 1 ] && perl -0pi -e 's/<gasp>.*?<\/gasp>/<gasp>\n    <gaspRange rangeMaxPPEM="65535" rangeGaspBehavior="15"\/>\n  <\/gasp>/s' "v-$2.ttx"
    ttx -q -o "v-$2.ttf" "v-$2.ttx"
}
mk tahoma-11.20 R20 0 0; mk tahoma-11.22 R22 0 0; mk tahoma-11.22 RNB 1 0
mk tahoma-11.22 RSG 0 1; mk tahoma-11.22 RBO 1 1
mk tahomabd-11.22 B22 0 0; mk tahomabd-11.22 BBO 1 1
ls v-*.ttf
