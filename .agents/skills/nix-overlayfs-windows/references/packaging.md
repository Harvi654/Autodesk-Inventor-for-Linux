# Packaging patterns

Examples assume pkgs, overlayfsLib, and modules are bound as in SKILL.md. Illustrative source URLs and hashes must be replaced with actual versioned upstream artifacts and verified hashes before building.

## Portable archive

```nix
let
  pname = "example-app";
  version = "1.2.3";
  src = pkgs.fetchurl {
    url = "https://vendor.example/releases/${version}/app-x64.zip";
    hash = pkgs.lib.fakeHash; # Replace with verified source hash.
  };
  installPath = "drive_c/Program Files/Example App";
  basePackage = pkgs.runCommand "${pname}-${version}" {
    inherit pname version;
    nativeBuildInputs = [ pkgs.unzip ];
  } ''
    mkdir -p "$out/${installPath}"
    unzip -qq "${src}" -d "$out/${installPath}"
  '';
in overlayfsLib.composeWindowsLayers {
  inherit (modules) runtime;
  packageName = "ExampleVendor/ExampleApp";
  baseLayer = {
    inherit basePackage;
    overlayDependencies = [ ];
    runtimeEnvVars = { };
  };
  executableName = "example-app";
  executablePath = "${modules.runtime.programFilesPath}/Example App/app.exe";
  workingDirectory = installPath;
  # If required: overlayDependencies = [ modules.vcrun2022 ];
}
```

Inspect archive nesting before choosing the output layout. When moving contents use cp -R source/. destination/ to retain hidden files. The layer's basePackage contains prefix contents directly, without another basePackage/ or prefix directory. Wine's .update-timestamp belongs to the base environment; application installer deltas omit it. The explicit baseLayer record needs all three fields shown; a bare derivation is insufficient.

## Installer

```nix
let
  src = pkgs.fetchurl {
    url = "https://vendor.example/releases/1.2.3/setup.exe";
    hash = pkgs.lib.fakeHash; # Replace with verified source hash.
  };
in overlayfsLib.mkWindowsPackage {
  inherit src;
  inherit (modules) runtime;
  pname = "example-app";
  version = "1.2.3";
  packageName = "ExampleVendor/ExampleApp";
  executableName = "example-app";
  executablePath = "${modules.runtime.programFilesPath}/Example App/app.exe";
  silentFlags = "/S"; # Only if confirmed for this installer.
  overlayDependencies = [ modules.vcrun2022 ];
}
```

The default command runs session.commands.wine with src and silentFlags. It does not infer msiexec for an MSI. For MSI replace the default installation sequence with this attribute (src must be bound in the surrounding let):

```nix
unshareInstall = { session, ... }: ''
  set -euo pipefail
  ${session.commands.wine} msiexec /i "${src}" /qn /norestart
  ${session.commands.wineserver} --wait
'';
```

A custom unshareInstall replaces the default installer/postInstall/wait sequence; include required follow-up steps yourself. Use session.commands.wine and session.commands.wineserver instead of host Wine or an assumed bin/wine64. WoW64 can use a single Wine launcher. Handle documented reboot-success exit statuses only where required; do not discard arbitrary installation failures. See packages/wine-modules/vcrun2022/default.nix for a multi-installer callback.

Prefer verified unattended flags. ahkScript supports AutoHotkey automation when no unattended install exists and adds the AutoHotkey layer automatically. launchVncServer is an optional build debugging aid. wineserverWaitTimeout bounds default post-install waiting. Fetch all required payloads as Nix sources rather than relying on installer downloads inside the sandbox.

Reusable components can omit executable fields when only their installation layer is needed. mkWindowsPackage results expose basePackage, dependency information, and runtime environment metadata for composition.

## Runtime upgrades and build failures

Check dlls/appwiz.cpl/addons.c in the selected Wine source for its required Mono and Gecko versions. Wine 11.20 requires Mono 11.3.0; the fork needed both a verified download/version mapping and an extension of its existing MSI CREATELINKS/CREATELINKS64 workaround before that base environment built successfully. Extend such a workaround only when the actual failing action matches; do not suppress unrelated MSI failures. Build the corrected base-env with the application's exact Wine and Nixpkgs before retrying the full application.

When a Nixpkgs dependency fails its own tests, inspect the retained test output before disabling tests or changing versions. For example, libgsf 1.14.59 treated a valid zero-length OLE stream's NULL allocation result as an out-of-memory error, causing msitools to crash. A focused allocation fix passed all 29 msitools tests. Keep third-party dependency fixes distinct from nix-overlayfs library changes.

Preserve Wine registry key metadata through both JSON conversion and runtime layer merging. Dropping the #link marker while retaining SymbolicLinkValue turns aliases such as CurrentControlSet into ordinary keys; symptoms include missing RpcSs/SamSs services and unregistered COM classes. Verify registry-link round trips and merges, not only ordinary registry values. Fix the converters and merger in the library instead of adding application-specific duplicate registry keys.

For Wine installers that fail creating directory junctions or symbolic links, inspect the vendor log and test both link creation and traversal. Newer Wine stores directory links in `user.WINEREPARSE` xattrs and renames placeholders with a `?` suffix. Nix builds can deny xattr writes, NAR does not preserve that metadata, and kernel overlayfs can reject the directory rename even when Wine reports successful creation. Selecting direct mode alone does not solve the xattr problem.

The fork's `mkWindowsPackage { portableReparsePoints = true; ... }` provides a prefix-scoped build adapter and selects materialized mode. It converts supported directory reparse records into relative Unix symlinks before layer capture. Call `${session.commands.normalizeReparsePoints} "$WINEPREFIX"` before native Linux postprocessing needs to follow installer-created links. Verify Windows traversal with the exact runtime and inspect captured links. Unsupported targets and nonempty placeholders fail rather than lose data. Keep host security policy unchanged.

When installing DXVK or other replacements for stock Wine DLLs inside `mkWindowsPackage`, retain their `windows/system32/...` and `windows/syswow64/...` paths with `extraPathsToInclude`; the library prunes a stock-DLL path list without comparing replacement contents. Inspect the captured layer, since successful installation alone does not prove the replacements survived. Keep per-application registry overrides effective: global `WINEDLLOVERRIDES` can override WebView2's builtin graphics settings.

Runtime service helpers must share the application's user mapping. Running hooks as namespace root and Wine as a mapped user creates separate Wine servers for the same prefix; compare process namespaces and add a prelaunch/application UID regression in the library. The fork now drops namespace root after mounting and runs hooks, callbacks, the application, and cleanup together. Mutable databases captured during installation need writable copies in the user layer; a targeted `chmod u+w` through the mounted prefix copies them up without altering immutable sources. Preserve the source launcher's transient IPC cleanup when adapting persistent service startup.

Use --keep-failed for expensive installer builds when retained logs will help diagnose failures. Keep and poll an existing live build handle rather than launching additional builds just to observe progress. Prefer bounded log excerpts over streaming an entire Wine compilation into the conversation.

## Integrating existing installer scripts

Scripts may assume a writable checkout, distro font paths, a new empty prefix, or a fixed Wine architecture. Give build logs and extraction caches writable temporary paths; explicitly opt into prepared build prefixes while preserving normal personal-prefix safeguards. Preserve the runtime's WINEARCH, support the actual packaged extraction executable (Nix's _7zz exposes 7zz), and follow font symlinks when searching symlinkJoin outputs. Package required tools and use explicit paths rather than assuming the launcher inherits Wine in PATH.

Custom unshareInstall callbacks replace the normal installer/wait sequence. Enable failure propagation and include all required follow-up checks; otherwise a failed install can be hidden by a later successful command. Verify the expected executable and required components, not merely a successful shell exit.

For GUI applications with persistent licensing or SSO helpers, check that closing the main application also allows the composed session to finish and unmount. Restrict cleanup to that application's Wine prefix/session. Desktop callback entries must invoke nix-overlayfs's --nix-overlayfs-open-url protocol or explicitly translate the URI into it; forwarding a login URI as an ordinary application argument does not validate the callback path.

## WinGet convenience wrapper

mkWinpkgsPackage takes a manifest identifier such as Notepad++/Notepad++, selects a compatible non-ZIP installer, and derives source metadata and silent flags. Pin version instead of using its latest default. Its manifest lookup uses import-from-derivation, which matters in evaluation-restricted consumers.

Inspect lib/mkWinpkgsPackage.nix before using optional arguments. At the inspected revision its variadic arguments accept but do not forward stateMode, hostIntegration, managedRuntime, unshareInstall, and buildNamespaceMode. Its MSI flag table also does not change the default command to msiexec. Use mkWindowsPackage directly when those details matter.

## Source map

- lib/mkWindowsPackage.nix: installer callback and layer delta capture.
- lib/composeWindowsLayers.nix: composition and runtime environment merging.
- lib/mkOverlayfsPackage.nix: writable state, namespaces, launch and cleanup.
- packages/wine-modules/default.nix: available components and scope callPackage.
- packages/runtime-catalog.nix: architecture and runtime selection.
- apps/notepad-plus-plus/default.nix and apps/vlc/default.nix: portable layouts.

The selected revision's source is authoritative; forks may expose different APIs.
