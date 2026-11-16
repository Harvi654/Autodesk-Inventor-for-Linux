# Small UI fonts without smoothing

This original synthetic diagnostic queries system menu/status fonts and renders
sample text into a 32-bit DIB with default, antialiased and ClearType quality.
It counts pixels between black and white, and pixels with unequal RGB channels.
It is a diagnostic, not a Windows regression test: DIB rendering does not cover
every application drawing path, and no Windows reference measurements exist yet.

Build with MinGW:

```sh
x86_64-w64-mingw32-gcc -Wall -O2 font-probe.c -o font-probe.exe -lgdi32 -luser32
WINEDEBUG=+font wine font-probe.exe > font-probe.txt 2> font-trace.log
```

Use the application's Wine and prefix. With the Nix launcher, commands must run
in the active application's user and mount namespaces; using the same prefix
pathname outside those namespaces can start a separate Wine server. Obtain the
actual Linux Inventor PID and composed prefix path first, then use:

```sh
nsenter --target "$inventor_pid" --user --mount --preserve-credentials \
  env WINEPREFIX="$inventor_prefix" WINEDEBUG=+font \
  "$inventor_wine" /tmp/font-probe.exe > /tmp/font-probe.txt 2> /tmp/font-trace.log
```

On 2026-11-10, Wine 11.20, NixOS/Hyprland, Inventor 2027: the actual application
session reported smoothing enabled, type 2, and Tahoma for menu/status text.
At height -15, Tahoma and Liberation Sans produced zero intermediate pixels;
Segoe UI produced 1149, Noto Sans 1027. These numbers describe this machine's
fonts, not portable expected results. Wine's `+font` trace reported
`aa disabled by GASP` for Tahoma and Liberation Sans. The relevant source is
`freetype_get_aa_flags()` in `dlls/win32u/freetype.c`: grayscale rendering can be
disabled by the selected font's `gasp` table. No Microsoft DLL was traced or
disassembled; this uses public GDI APIs and Wine's own diagnostic channels.

A local follow-up experiment sets
`HKLM\Software\Microsoft\Windows NT\CurrentVersion\FontSubstitutes`,
string value `Tahoma=Segoe UI`, then restarts Inventor. Segoe UI was already
available through this user's mounted Windows fonts. No font files were copied
or added to the package. Delete that value and restart to undo it (it was absent
before this experiment). After restart, the probe reported Segoe UI as both
system menu/status fonts, with 1149 intermediate pixels in their samples.
Explicit Tahoma requests still produced zero intermediate pixels, so this
does not replace every application font request. The user confirmed that
Inventor looked better. The Nix launcher now applies this substitution only
when the real Segoe UI family is available in host fonts or prefix files.
No Wine patch or L0–L5 validation claim. (Replaced on 2026-11-16, below.)

## Tahoma by pixel size, Wine vs Windows (2026-11-16)

`tahoma-ppem.c` draws the same string with `Tahoma`, `Segoe UI` and renamed
copies of Wine's Tahoma at 11, 12, 13, 15, 16, 17, 19, 21 and 24 px, with
default, non-antialiased, antialiased and ClearType quality. For each it prints
the face, partly covered pixels, coloured pixels, grey levels and width.
`make-tahoma-variants.sh` builds the copies from Wine's `fonts/` at the
wine-11.20 and wine-11.22 tags with fonttools' `ttx`: `TTR20`/`TTR22`
unchanged, `TTRNB` without bitmaps, `TTRSG` with `gasp` smooth at every size,
`TTRBO` both, `TTB22`/`TTBBO` bold. Pass the `.ttf` files as arguments.

```sh
./make-tahoma-variants.sh out
x86_64-w64-mingw32-gcc -Wall -O2 -static tahoma-ppem.c -o tahoma-ppem.exe -lgdi32 -luser32
wine tahoma-ppem.exe out/v-*.ttf                        # host fontconfig
FONTCONFIG_FILE=rgb.conf wine tahoma-ppem.exe out/v-*.ttf  # rgba=rgb added
```

Results: on Windows 10 22H2 (ClearType on) Tahoma, Windows' and Wine's, is
smoothed with ClearType at every size and has no greyscale up to 16 px. Under
winum-11.20-2 with this host's fontconfig (`rgba` none) nothing up to 16 px is
smoothed, in any quality; with a fontconfig file that sets `rgba=rgb` the
pattern matches Windows. Cause and fix: `docs/arch-hyprland.md`, section
"Small Tahoma text without smoothing (ClearType)". These runs used a
throwaway prefix and host MinGW, not a flake output.
