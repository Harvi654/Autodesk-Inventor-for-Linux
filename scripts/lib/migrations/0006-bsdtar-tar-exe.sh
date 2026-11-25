# shellcheck shell=bash
# Step 0006: tar.exe in system32 (and syswow64): libarchive's own signed
# Windows build of bsdtar 3.5.3, pinned and SHA-256 checked
# (scripts/lib/bsdtar.env), its license text in
# <prefix>/.inventor-on-linux/doc/libarchive-3.5.3/. Windows 10 ships
# bsdtar as System32\tar.exe (3.5.2 in the maintainer's VM); Wine has none,
# and the Electrical Catalog Browser's library package unzips with it
# during its install (docs/installer-completeness-review.md, run 2).
# install-from-image.py puts it in place before the packages for a new
# installation; this step is for an existing prefix (a repair run of
# install.sh then installs the Catalog Browser).
MIG_DESC="tar.exe: libarchive's bsdtar (as on Windows 10) for installers that unpack with it"
MIG_BACKUP="drive_c/windows/system32/tar.exe drive_c/windows/syswow64/tar.exe .inventor-on-linux/doc"

mig_needed() { ! bsdtar_ok; }

mig_apply() { install_bsdtar; }
