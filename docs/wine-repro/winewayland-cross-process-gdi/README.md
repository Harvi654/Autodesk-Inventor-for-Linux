# Cross-process child GDI painting

Original synthetic C reproducer, written with AI assistance; LGPL 2.1 or later.
No Autodesk or Microsoft code, binaries, symbols or disassembly were used.

The parent paints a red background and a green child panel. A second process
creates a blue child panel under the same parent and handles its own WM_PAINT.
Both processes log their paint calls. This exercises GDI painting into a
top-level window owned by another process, independently of WebView2.

Build with the matching Wine development package:

```sh
winegcc -m64 -o /tmp/cross-process-paint.exe child-paint.c -lgdi32 -luser32
```

Run only in a separate disposable prefix, never the Inventor prefix. Create
the prefix directory as the runtime user before launching Wine. An initial
Mono installation offer can be cancelled: this program does not use .NET.
In an isolated workspace, configure `HKCU\Software\Wine\Drivers`, value
`Graphics`, to `x11` or `wayland`. Unset DISPLAY for the Wayland run. Run
the generated `.exe.so` with the matching Wine loader. Stop that prefix's
Wine server before changing drivers. Capture screenshots through the
workspace screenshot tool. Send pointer input inside the right panel before
comparing: X11 can initially buffer the foreign child's drawing.

## Observations, 2026-10-26

Patched Wine 11.20, Agent Workspace Linux 0.5.1 with its Nix wrapper
authorization fix, private KWin, physical output 1920x1200, scale 1.5:

| Driver | Green same-process panel | Blue other-process panel |
|---|---|---|
| X11/XWayland | Visible | Visible after pointer input |
| Native Wayland | Visible | Missing, including after GdiFlush and pointer input |

Both processes logged WM_PAINT on both drivers. Both drivers were rechecked
with the final source including explicit GdiFlush. X11 displayed both panels
after input; Wayland still omitted the blue one. The final screenshot paths
used locally were `/tmp/gdi-x11-flush.png` and `/tmp/gdi-wayland-flush.png`.

The screenshot checker reads an unmodified workspace screenshot through FFmpeg:

```sh
python3 check-screenshot.py /tmp/gdi-x11-flush.png
python3 check-screenshot.py /tmp/gdi-wayland-flush.png --expect-foreign missing
```

Measured baseline: X11 had 48,018 green and 48,028 blue pixels; Wayland had
47,613 green and zero blue pixels. By default the checker requires both panels,
so the unpatched native Wayland screenshot fails that regression check.

In Wine 11.20, `dlls/win32u/dce.c:update_visible_region` only obtains
`win->surface` for a local top-level window, not WND_OTHER_PROCESS. It calls
the display driver's GetDC hook first. Wine's X11 driver has a separate GDI
drawing path; the Wayland driver does not provide that fallback.

This is diagnostic evidence, not a Wine test-suite assertion or a validated
fix. Real Windows x86_64/i686 execution, automated pixel checks, lifetime,
resize, clipping and concurrent paint coverage are still needed. No Wine
patch or validation level is claimed. A future bug report can contain this
program and its public API calls, without proprietary traces.

Related reports: [Wine 35456](https://bugs.winehq.org/show_bug.cgi?id=35456)
describes missing cross-process software drawing on the Mac driver, including
a later Wine 11.20 observation; [Wine 41161](https://bugs.winehq.org/show_bug.cgi?id=41161)
describes separate-process plugin UI repaint loss on X11. The latter's test
attachment forces direct X drawing and is not a native Wayland solution.

## Draft runtime result

With `patches/drafts/win32u-foreign-process-gdi.patch` and
`WINE_WAYLAND_GDI_BRIDGE=1`, the native Wayland screenshot has 47,613 green
pixels and 47,619 blue pixels. `check-screenshot.py` passes, and the test exits
normally. The full flake-derived Wine build passed for its WoW64 configuration;
the independent review read the draft in full. The explicit flake output is
`wine-wayland-gdi-experimental`; the maintainer later included the draft
in `nix/wine.nix` for follow-up testing.

The Inventor experiment restores initial Home visibility and opens New;
focused Cancel returns to Home and focused close exits with status 0. White
edges on focused controls and a detached small control remain. This is not
validation of transparent drawing, destination-dependent ROPs, dynamic
clipping, resize/DPI changes, reentrant message waits or general application
use. See [draft notes](../../../patches/drafts/README.md) before experimenting.

## Inventor and isolated workspace investigation

## Isolated native Wayland comparison at 133% (2026-10-26)

Inventor 2027.1 reaches its Home page under the isolated X11 workspace:
the ribbon, project selector, Open/New buttons, recent files and help links
are visible. This is a baseline observation, not native Wayland validation.

The requested Hyprland comparison is blocked before Inventor launches.
Agent Workspace Linux 0.5.1 starts Hyprland, but its private headless output
reports width/height zero and startup times out. Both 1920x1200 and
1995x1197 with scale 1.33 fail. The latter dimensions divide evenly by 1.33.
The compositor log reports `GBM: Failed to allocate a GBM buffer: bo null`
and rejects even its initial 1280x720 XR24 buffers. The only exposed render
node has NVIDIA vendor ID `0x10de`. The workspace backend guide documents
that NVIDIA GBM cannot allocate its headless buffers; its alternative-device
selection requires another GPU vendor's render node.

Reproduce with the workspace MCP `workspace_start`, setting
`acknowledge_hidden_workspace: true`, a purpose, width 1995, height 1197,
and `session: {backend: "hyprland", scale: 1.33}`. Inspect
`output-config.json` and `hypr/*/hyprland.log` in that workspace's runtime
directory. No host desktop input or capture is needed.

Open: restore a working isolated Hyprland renderer, then compare Wine's
`x11` and `wayland` drivers sequentially at the same output scale using
workspace screenshots. No Inventor/Wine cause has been established, no Wine
fix was attempted, and no Wine validation level was reached. There is no
Wine bug report evidence from the failed compositor startup.

A follow-up with the KWin backend got past output creation: `scale: 1.33`
was quantized to 1.325 and rejected by the workspace's scale check, but
`scale: 1.3333333333333333` produced a verified 1920x1200 output with logical
size 1440x900. Startup then failed with `KWin fake-input v6 is unavailable
(advertised version 0)`. The private desktop entry had the requested
`X-KDE-Wayland-Interfaces=org_kde_kwin_fake_input` declaration, and its
service-cache build reported no error. The authorization/interface failure
remains undiagnosed. Inventor was not launched in that KWin session, so this
provides no native Wayland application rendering result.

## Native Wayland Home content is blank on KWin at 150% (2026-10-26)

With the corrected Agent Workspace Linux 0.5.1 Nix wrapper, KWin starts and
captures screenshots at 1920x1200, scale 1.5. Inventor 2027.1 launched with
the same existing user state, sequentially, renders the ribbon, project
selector, Open/New, recent files and help links under X11. Native Wayland
renders the ribbon and status bar but leaves the Home content blank. Its
small child-window controls appear detached in the middle of the window.
These are observations from workspace screenshots, not a scaling fix.

An original [cross-process GDI test](#observations-2026-10-26)
in a separate disposable prefix reproduces a relevant Wine limitation:
same-process child painting is visible, while painting by a second process
is absent under Wayland despite WM_PAINT executing. X11 displays both panels
after pointer input flushes buffered drawing. Explicit GdiFlush and input do
not restore the missing Wayland panel.

In the pinned Wine 11.20 source, `win32u!update_visible_region` in `dce.c`
does not obtain a window surface when the top-level WND is WND_OTHER_PROCESS.
The display driver's GetDC hook is called first; X11 has a fallback drawing
path, while Wayland does not. This explains the synthetic result and is a
strong hypothesis for the software-rendered WebView2 Home page. It is not
yet proof that every missing Inventor element has that cause. No Microsoft
internals were inspected or traced for this investigation.

Reproduce the application comparison through workspace_start with
`session: {backend: "kwin", scale: 1.5}` and the dimensions above. Use the
installed launcher sequentially with INVENTOR_WINE_DRIVER=x11 and wayland;
close the first application and wait for its Wine session to exit before
switching. The KWin workspace supplies private XDG data/config/cache paths,
overriding launch env entries; use an explicit env command in the launched
argv to select the existing Inventor state in place. Never copy an
authenticated prefix. Keep the private display and runtime variables.

Open: implement and validate cross-process drawing/composition, measure the
synthetic test on Windows, and retest Inventor. No fix or Wine validation
level is claimed. A Wine bug report can use the synthetic public API test;
do not submit AI-generated code as a Wine contribution. Local application
screenshots contain account information and remain outside the repository.

## Native Wayland summary: not ready for Inventor (2026-10-26)

Wine's native Wayland driver is not ready for Inventor yet, especially its
embedded WebView2 Home page and authentication screens. Use Wine's X11 driver
through XWayland on a Wayland desktop. This conclusion concerns the tested
Inventor workflow, not every application using Wine's Wayland driver.

The draft cross-process GDI bridge below helped render the WebView2 Home
content, but the maintainer's follow-up test found it **terribly slow and
glitchy**. Rendering the controls did not make the application usable. Focus
artifacts and a detached control were also observed in the isolated test.
Text remained blurry at fractional scaling; the bridge does not fix DPI or
text sharpness. Its synchronous tile transfers and per-tile presentation are
a likely source of overhead, but no profiling established how much of the
slowdown comes from the bridge versus other Wine/WebView2 limitations.

Pause this workaround and wait for proper upstream support before retrying
native Wayland. Track these reports:

- [Wine #58921: WebView2 does not work with Windows version setting 8.1 or newer](https://bugs.winehq.org/show_bug.cgi?id=58921)
  tracks broader WebView2 compatibility, rather than only Wayland.
- [Wine #59370: WebView2 blank windows / Chromium compositor](https://bugs.winehq.org/show_bug.cgi?id=59370)
  was closed as a duplicate of #58921. The
  [official discussion mirror](https://list.winehq.org/hyperkitty/list/wine-bugs%40list.winehq.org/thread/UDZKZTMP5WYISOAUDGEOMFOSU7X73JND/)
  records missing DirectComposition, multiprocess surface and sandbox support.
  Closing the duplicate does not mean the rendering problem was fixed.
- [Wine #35456: child windows from a separate process do not display](https://bugs.winehq.org/show_bug.cgi?id=35456)
  is the closest match to the cross-process GDI failure reproduced here.
- [Wine #41161: OpenMPT cross-process plugin window repaint failure](https://bugs.winehq.org/show_bug.cgi?id=41161)
  covers a related symptom; the proposed X11 direct-drawing change does not
  supply Wayland support.
- [WebView2Feedback #5720](https://github.com/MicrosoftEdge/WebView2Feedback/issues/5720)
  contains related reporter analysis of software output and Wine's missing
  cross-process GDI drawing. It is not confirmation of a Microsoft fix.

WineHQ's anti-bot page prevented direct verification of current Bugzilla
statuses; the #59370 duplicate resolution was verified through the official
mailing-list mirror. No upstream fix or delivery date is claimed.

## Draft bridge restores Home content, but is unusably slow (2026-10-26)

`patches/drafts/win32u-foreign-process-gdi.patch` adds an opt-in experiment in
Win32u. For drivers without direct GDI image drawing, a foreign DC draws to a
private surface. Its flush sends bounded opaque pixel tiles through a new
marshalled internal message; the top-level window's owning process copies
those tiles into its own surface and presents them. Initial visible-region
rectangles constrain the transfer, including the core's rounded dirty bounds.
It is original AI-assisted code, reviewed independently in full. No vendor
implementation code was inspected. It is not submitted to Wine.

The full flake-derived Wine 11.20 WoW64 build passed with the regular patch set
plus the draft, x86_64 and i386 PE outputs, and no patch-hunk fuzz: **L0 for
that Nix configuration**. The final corrected source was built as an explicit
override of the flake's Wine derivation. The separate experimental flake
output exposes the same code; its evaluation was checked. To build it:

```sh
nix build .#wine-wayland-gdi-experimental
```

The flag `WINE_WAYLAND_GDI_BRIDGE=1` is required to enable forwarding. At the
time of the isolated test, regular outputs did not include the draft; the
maintainer subsequently added it to `nix/wine.nix` for the follow-up test.
That local inclusion does not make it a validated fix. The initial experiment
used temporary copies of the installed declarative launcher's shell scripts,
replacing their Wine runtime paths with the diagnostic build, while retaining
the existing application layers and user state in place. It did not install
another program into the Inventor prefix or change the installed launcher.

The two-process screenshot test now finds 47,613 same-process green pixels
and **47,619 foreign-process blue pixels**, compared with zero blue pixels on
unpatched native Wayland. The test exits with status 0. Inventor 2027.1 under
KWin at 1920x1200, scale 1.5, now shows the same initial Home controls seen
under X11: project selector, Open/New, recent files and help links, together
with the ribbon and status bar. New opens Create New File. Explicitly focusing
the dialog and clicking Cancel returns to Home; explicitly focused close
exits with status 0. A prior run timed out after unfocused modal-close input;
that alone did not establish a bridge deadlock. The focused repeat succeeded.

This remains a draft: focused controls can acquire white-edge artifacts,
and the small detached control remains. The bridge does not yet preserve
transparent or destination-dependent drawing, changes to DC clipping, or
surface identity across resize/DPI changes. Synchronous transfers and
per-tile presentation also need redesign and regression testing. The review
identified these limitations; a receiver-side mutex wait is still possible
under reentrant drawing and has not been ruled out by the small tests.
Windows x86_64/i686 measurements, neighbouring Wine suites and the full
Inventor smoke test are outstanding. No L1/L2/L4/L5 result is claimed. Keep
the patch in drafts; the normal WINE_BUILD is unchanged.

Local evidence: `/tmp/gdi-wayland-patched.png`,
`/tmp/inventor-wayland-bridge.png` and
`/tmp/inventor-wayland-bridge-home-return.png`. Screenshots remain outside
Git because the application displays account information. The original C
program and screenshot checker are public synthetic evidence suitable for
a report about [Wine 35456](https://bugs.winehq.org/show_bug.cgi?id=35456).

## Investigation result log

**2026-10-26 - Native Wayland remains unusable:** the maintainer confirmed
that the draft bridge renders WebView2 content, but it is terribly slow and
glitchy; fractional-scale text remains blurry. Keep X11/XWayland as the usable
path and defer native Wayland until upstream support improves. Track Wine
#58921 (including duplicate #59370), #35456 and the related reports above.
The earlier screenshot success establishes rendering only, not usability.

**2026-10-26 - Draft cross-process GDI bridge:** full flake-derived Wine
build passes; the native Wayland reproducer's missing blue panel renders.
Inventor 2027.1 Home controls appear under KWin at 150%, New/Cancel works
with explicitly focused input, and the repeat run exits with status 0.
Focus-edge artifacts and broader correctness/validation remain open; the
patch stays in drafts and has an explicit experimental Wine flake output.

**2026-10-26 - KWin at 150% reproduces the blank Home page:** corrected
workspace packaging permits launch and screenshots. X11 renders Home;
native Wayland renders its frame/ribbon but omits Home controls. A standalone
two-process C program reproduces missing foreign-process GDI child painting
on Wayland. No fix yet; see the native Wayland Home section and reproducer.

**2026-10-26 - Native Wayland menu parity investigation:** Inventor 2027.1
Home page captured under isolated X11. Hyprland at 133% could not initialize
its workspace output because NVIDIA GBM buffer allocation failed, before
Inventor could launch there. Native Wayland parity remains unverified; see
"Isolated native Wayland comparison at 133%".

**2026-10-26 - KWin comparison follow-up:** KWin configured a 1920x1200
output at four-thirds scaling, but workspace startup failed because its
required fake-input interface was unavailable. Application parity remains
unverified; no Wine change.
