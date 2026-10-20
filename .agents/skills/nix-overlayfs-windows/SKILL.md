---
name: nix-overlayfs-windows
description: Package and run Windows programs on Linux with nix-overlayfs using declarative Wine prefix layers, reusable dependencies, and Nix launchers. Use for reproducible Wine setup or conversion of a manual prefix into a Nix application package.
---

# Windows applications with nix-overlayfs

Produce a versioned Nix definition whose launcher combines an immutable Wine base, reusable dependency layers, and an application layer with writable user state. Put installation and compatibility fixes in the package definition so rebuilding does not depend on a hand-prepared prefix.

## Locate the implementation

For Autodesk-Inventor-for-Nix, a local nix-overlayfs checkout is available at `~/work/nix-overlayfs` (on this machine, `/home/wkrokosz/work/nix-overlayfs`). It is cloned from the fork `https://github.com/krokosik/nix-overlayfs`, with `https://github.com/conroy-cheers/nix-overlayfs` as upstream. Check its current remotes, revision, working tree, and project input wiring before making changes; do not assume a published upstream revision includes the local fork's capabilities.

This is a niche project: missing functionality and implementation bugs may need work in nix-overlayfs itself. Implement fixes or new features needed for the Windows application setup in the local fork rather than maintaining consumer-side patches to the library or stopping at a workaround proposal. Keep changes focused on the application requirements, preserve unrelated work, validate the affected behavior, and update the consuming project to use the corrected implementation. Distinguish temporary local-path development from a reproducible pinned revision. When the user authorizes pushing library fixes, commit only the intended changes, push to the authorized remote, and pin the resulting published revision in the consumer. Without that authorization, keep the changes local and report the remaining publication dependency; do not silently publish or change remotes.

Use the user's checkout or pinned flake input. Without one, start discovery at https://github.com/krokosik/nix-overlayfs and pin the selected revision in the consumer's flake lock. This skill describes that fork; check the actual revision before copying APIs from another fork.

Read README.md, pkgs/top-level/default.nix, packages/runtime-catalog.nix, and the relevant lib constructor. The current API uses composeWindowsLayers and a runtime argument; older composeWineLayers and wine arguments are incompatible. Preserve existing input versions unless the task requires an update.

Determine Linux host architecture, Windows binary architecture, portable archive versus installer, executable location, and required components. Use versioned sources and verified fixed-output hashes. An existing prefix is evidence about dependencies and registry settings, not an opaque payload to redistribute with user data.

## Select a coherent runtime

In a consuming flake, bind:

```nix
overlayfsLib = inputs.nix-overlayfs.lib.${system};
scope = inputs.nix-overlayfs.legacyPackages.${system}.nix-overlayfs;
modules = scope.moduleScopes.nativeModules;
```

With the repository overlay applied, the equivalents are pkgs.nix-overlayfs.lib and pkgs.nix-overlayfs.moduleScopes. Follow the consumer's existing Nixpkgs integration.

- On x86_64 Linux, nativeModules targets ordinary Windows x64 apps. Use nativeWin32Modules when a Win32 prefix is required; nativeWin32HeadlessModules is available for lean CLI workloads.
- On aarch64 Linux, nativeModules targets Windows ARM64 binaries. Use x64FexModules for Windows x64 via native ARM64EC Wine and FEX WoA DLLs. x64FexModules is not exposed on x86_64 Linux.
- Keep modules.runtime and all component layers from the same scope. Do not independently swap Wine binaries or change WINEARCH on existing writable state.

For a custom patched Wine, use scope.moduleScopes.makeNativeModules { wine = patchedWine; windowsArch = "wow64"; } on x86_64 Linux. Check the selected Wine source's required Mono/Gecko versions and the fork's base-environment mappings before starting an application build. A successful Wine compilation does not prove the base prefix can bootstrap. For runtime upgrades and installer integration pitfalls, read the corresponding sections in [references/packaging.md](references/packaging.md).

## Choose a package constructor

Read [references/packaging.md](references/packaging.md) for examples and installer caveats.

- Portable distribution: extract a prefix-shaped derivation and pass an explicit baseLayer record to composeWindowsLayers.
- Installer: use mkWindowsPackage with a pinned source and verified unattended command. Use its unshareInstall callback for MSI or custom sequences.
- WinGet manifest: mkWinpkgsPackage is convenient when its selection and forwarded options fit. Pin version and inspect its implementation: extra arguments can be silently ignored.

Use overlayDependencies for components needed during installation; mkWindowsPackage retains those dependencies in its launcher. composeWindowsLayers can add runtime layers without rerunning an installer. Reuse components such as vcrun2022, fonts, dxvk, and dotnet-framework-4-8 only when required. Define missing reusable components with the selected module scope's callPackage. Avoid leaving the final setup dependent on Winetricks mutations to the user's live prefix.

Keep packageName stable: persistent state lives at $XDG_DATA_HOME/<packageName>, defaulting to ~/.local/share/<packageName>. executableName names the Linux launcher. executablePath addresses the Windows program in the composed prefix; runtime.programFilesPath is /drive_c/Program Files. Output directories use relative drive_c/... paths.

For desktop applications retain persistent state and host integration. For one-shot CLI workloads without managed runtime requirements, consider hostIntegration = false; managedRuntime = "disabled"; stateMode = "ephemeral"; on composeWindowsLayers or mkWindowsPackage. Disabled managed runtime suppresses Mono/Gecko loaders; ephemeral mode discards writable application state after exit.

## Expose and verify

When editing nix-overlayfs itself, register binary variants in apps/catalog.nix; apps/default.nix derives flat packages/apps and runtime variants. In a consumer such as Autodesk-Inventor-for-Nix, expose the derivation under packages.${system}, with an optional flat apps.${system} entry pointing at bin/<executableName>.

Evaluate and build the exact package. Inspect its basePackage for the expected executable, then smoke-test the launcher using temporary XDG data/cache directories so existing state cannot hide missing dependencies. For CLI apps check argument forwarding and exit status; for GUI apps verify the window, essential functions, and clean exit. Report what evaluated, built, and actually ran separately. Evaluation alone does not establish runtime compatibility.

Keep namespace modes at auto initially. If user namespaces are denied, the launcher can fall back to rootless fuse-overlayfs and the build to a materialized prefix. namespaceMode = "direct" and buildNamespaceMode = "direct" select those paths explicitly; NIX_OVERLAYFS_NAMESPACE_MODE=direct overrides the launcher. Investigate FUSE or host policy failures without disabling security settings. For graphics problems inspect mkGraphicsBootstrap and its opt-in NIX_OVERLAYFS_GRAPHICS_STACK=system support.

Preserve user state while diagnosing upgrades; use isolated test state instead of deleting prefixes. Deliver the Nix definition, build/run commands, runtime choice, and remaining application-specific limitations.
