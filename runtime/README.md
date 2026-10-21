# Experimental GPU ray tracing

These helpers are kept outside the Nix expressions so a manually configured
Wine launcher can reuse them. The full GPU viewport path has rendered the sample part on an RTX 3060.
A successful diagnostic alone does not establish that another system can render
inside Inventor.

- `install-vkd3d.sh DIRECTORY WINEPREFIX` installs the x64 Windows builds of
  `d3d12.dll` and `d3d12core.dll`. Use vkd3d-proton's Windows binaries, rather
  than its native Linux libraries, with ordinary Wine.
- Source `gpu-ray-tracing.sh` after choosing the prefix and host graphics
  stack. It selects native D3D12 DLLs and configures logs and shader caching.
  Supply a compatible DXGI implementation, such as the existing DXVK layer.
- Source `enable-gpu-renderer.sh` before starting Inventor to set its
  `Driver\EnableHydra` preference to `1`. This changes writable user state.
  To undo it, use the same `wine reg add` command with `/d 0` while Inventor
  is closed. The helper currently targets Inventor 2026's registry version.
- `assemble-wine-opengl.sh WINE_ROOT PATCHED_OPENGL_DLL OUTPUT` builds a
  runtime tree using a matching Wine OpenGL DLL. Its physical bootstrap copies
  ensure Wine loads that DLL from the new tree. `gpu-ray-tracing.sh` enables
  the opt-in alpha pixel-format selection fix needed by Autodesk's OpenGL
  context initialization; normal Wine behavior is unchanged without the flag.
- `pixel-format-check.c` reproduces Autodesk's legacy-to-ARB pixel-format
  selection on one window. `nix run .#pixel-format-check` fails if the second
  `SetPixelFormat` call is rejected.
- `shared-texture-check.c` exports a 32×32 RGBA texture from D3D12 and opens
  it with D3D11, checking the imported descriptor. Run it with
  `nix run .#shared-texture-check` to check the renderer's texture handoff.
- `wine-session.sh` runs a console diagnostic and terminates its prefix's
  Wine server afterward. It is intended for isolated diagnostic sessions.

`dxr-check.c` builds a Windows console executable. Without arguments it
enumerates DXGI adapters and checks D3D12 ray-tracing support and the
`ID3D12Device5` interface. Its exit status describes these checks only.

With Inventor's Windows `Bin` path as the first argument, it also checks
Autodesk DLL loading. A second argument of `init` checks USD's selected
renderer and initializes Aurora's DirectX backend. `discover` checks USD's
automatic renderer selection without preloading the Hydra plugin or directly
initializing Aurora. These optional diagnostics use Inventor 2026's exported
C++ ABI; they may need adjustment for other Autodesk versions.

For example, from the flake checkout:

```sh
nix run .#dxr-check
nix build .#dxr-check-inventor
./result/bin/inventor-dxr-check 'C:\Program Files\Autodesk\Inventor 2026\Bin' discover
```

The Nix diagnostic launcher creates ephemeral state and reuses the immutable
application layer. It does not run Inventor's licensing services or use the
normal authenticated user prefix. The experimental `inventor-rt` launcher
does use the normal Inventor state.

The compatibility patches address separate startup paths:

- DXVK uses an estimated 60 Hz vblank period when a virtual display reports no
  refresh rate, without changing the modes exposed to the application.
- The opt-in Wine pixel-format fix chooses an alpha-capable legacy format so
  Autodesk can reuse that format for its ARB OpenGL context on the same window.
- The vkd3d-proton shader patch uses known ray-payload storage classes before
  querying unmaterialized instructions. Long-vector matrix copies use legal
  arrays and component reshaping instead of invalid 12-component SPIR-V
  vectors or aggregate bitcasts. This covers logical matrix copies, not general
  physical structure-padding conversions.

`nix build .#checks.x86_64-linux.ray-payload` compiles the original HLSL fixture
in `tests/shaders/` and validates every entry point with the patched translator.
Autodesk shader dumps used for local investigation are not included in this
repository.

Shared textures use Wine's existing D3DKMT runtime descriptor channel, with the
legacy Proton IOCTL implementation retained as a fallback. The DXVK changes
backport [upstream PR #5257](https://github.com/doitsujin/dxvk/pull/5257) to the
pinned Nixpkgs version. The matching vkd3d-proton exporter writes the D3D11
texture descriptor without replacing Vulkan's allocation data.

Imported textures keep the caller-owned shared handle for D3DKMT bookkeeping;
they are not re-exported through Vulkan. Runtime descriptor buffers are queried
before opening a resource so existing metadata is retained.

The RT launcher selects GLX for Inventor on X11. On the tested NVIDIA/Xwayland
stack, Wine’s EGL path cannot supply the alpha-capable window format needed by
the capability probe; GLX passes both pixel-format selections with OpenGL 4.6.
