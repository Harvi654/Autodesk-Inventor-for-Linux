{
  description = "Declarative Autodesk Inventor 2026 and 2027 environment for NixOS";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/b25309931cfda5f0b8805f462a29897eeae50168";
    nix-overlayfs = {
      url = "github:krokosik/nix-overlayfs/006dd3b3f1f973a60e394747e500c5cfb5721599";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    # winum releases, named by their signed tags. Only patches/series and the
    # patches it lists are used. There are two inputs so that the launcher can
    # move to a newer release while the installation layers stay as they are
    # (a new install Wine reinstalls Inventor):
    # - winum-install: the Wine that builds the installation layers;
    # - winum: the Wine that runs Inventor, and the source of wineCandidates.
    #   To test candidates from a winum checkout, use `--override-input winum
    #   path:/path/to/winum` (this rebuilds only the launch Wine and the launcher).
    winum-install = {
      url = "github:Harvi654/winum/winum-11.22-3";
      flake = false;
    };
    winum = {
      url = "github:Harvi654/winum/winum-11.22-3";
      flake = false;
    };
  };

  outputs =
    inputs@{ self, nixpkgs, ... }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs {
        inherit system;
        # This flake explicitly packages proprietary Autodesk and WebView2 inputs.
        config.allowUnfree = true;
        overlays = [
          (final: prev: {
            # libgsf 1.14.59 rejects valid empty OLE streams, crashing msitools.
            libgsf = prev.libgsf.overrideAttrs (old: {
              patches = (old.patches or [ ]) ++ [ ./patches/libgsf/libgsf-empty-stream.patch ];
            });
          })
          inputs.nix-overlayfs.overlays.default
        ];
      };
      # winum candidates (topics under its patches/candidates/) to test. They go
      # into the Wine Inventor runs, not the one that builds the layers, so
      # trying one rebuilds Wine and the launcher only (the WebView2, .NET and
      # Inventor installations stay). A candidate that must be present while
      # installing goes into installWineCandidates; that rebuilds the layers.
      # A candidate that changes prefix contents (wine.inf, registration, modules
      # added or removed; see nix/wine-prefix.nix) must go into
      # installWineCandidates: the launch Wine is refused otherwise.
      wineCandidates = [ ];
      installWineCandidates = [ ];
      overlayfsLib = pkgs.nix-overlayfs.lib;
      scope = pkgs.nix-overlayfs;
      mediaSources2026 = import ./nix/media.nix {
        inherit pkgs;
        year = "2026";
      };
      mediaSources2027 = import ./nix/media.nix {
        inherit pkgs;
        year = "2027";
      };
      # Wines, module scopes and the Inventor packages for a choice of winum
      # candidates; the outputs below and the checks are built with it.
      mkReleases =
        {
          wineCandidates ? [ ],
          installWineCandidates ? [ ],
          winum ? inputs.winum,
          installWinum ? inputs.winum-install,
          candidatesSource ? winum,
        }:
        let
          inherit (pkgs) lib;
          launchCandidates = lib.unique (installWineCandidates ++ wineCandidates);
          # Builds the base environment, WebView2, .NET Framework and Inventor.
          installWine = pkgs.callPackage ./nix/wine.nix {
            inherit candidatesSource;
            winum = installWinum;
            candidates = lib.unique installWineCandidates;
          };
          # Runs Inventor: the `winum` release plus the candidates under test.
          # With the same release and candidates as installWine it is the same
          # derivation, built once.
          wine = pkgs.callPackage ./nix/wine.nix {
            inherit winum candidatesSource;
            candidates = launchCandidates;
          };
          modules = scope.moduleScopes.makeNativeModules {
            wine = installWine;
            windowsArch = "wow64";
          };
          launchModules = scope.moduleScopes.makeNativeModules {
            inherit wine;
            windowsArch = "wow64";
          };
          mkInventor =
            args:
            import ./nix/inventor.nix {
              inherit
                pkgs
                overlayfsLib
                modules
                launchModules
                ;
            } args;
        in
        {
          inherit
            installWine
            wine
            modules
            launchModules
            mkInventor
            ;
          inventor2027 = mkInventor {
            year = "2027";
            inherit (mediaSources2027) media;
            updates = [ mediaSources2027.update ];
            version = "2027.2";
          };
          inventor2026 = mkInventor {
            year = "2026";
            inherit (mediaSources2026) media;
            updates = [ mediaSources2026.update ];
            version = "2026.4";
          };
        };
      releases = mkReleases { inherit wineCandidates installWineCandidates; };
      inherit (releases)
        wine
        modules
        inventor2026
        inventor2027
        ;
    in
    {
      packages.${system} = {
        inherit wine;
        inventor-2026 = inventor2026;
        inventor-2027 = inventor2027;
        inventor-2026-media = mediaSources2026.media;
        inventor-2027-media = mediaSources2027.media;
        default = inventor2027;
      };
      apps.${system} = {
        default = self.apps.${system}.inventor-2027;
        inventor-2027 = {
          type = "app";
          program = "${inventor2027}/bin/inventor-2027";
          meta.description = "Autodesk Inventor Professional 2027.2";
        };
        inventor-2026 = {
          type = "app";
          program = "${inventor2026}/bin/inventor";
          meta.description = "Autodesk Inventor Professional 2026.4";
        };
      };
      checks.${system} = {
        # Each winum input names its release by tag, and the source it points to
        # must be that release (winum's own wine/version.env, read by
        # nix/wine.nix). This checks the committed flake.lock, not an
        # --override-input.
        winum-pin =
          let
            locked = (builtins.fromJSON (builtins.readFile ./flake.lock)).nodes;
            release = package: "winum-${package.wineVersion}-${package.winumBuild}";
          in
          assert locked.winum.original.ref == release wine;
          assert locked.winum-install.original.ref == release releases.installWine;
          pkgs.runCommand "inventor-winum-pin" { } ''
            touch "$out"
          '';
        # A winum candidate changes the Wine Inventor runs, not the installation;
        # checked on the same mkReleases the packages come from. Evaluation only.
        launch-wine-candidates =
          let
            inherit (pkgs) lib;
            plain = builtins.unsafeDiscardStringContext;
            drv = package: package.drvPath;
            launchTools = package: drv package.launchRuntime.toolsPackage;
            # A code-only and a wine.inf candidate of the same release.
            fixture = ./tests/fixtures/fake-winum;
            # The documented workflow: candidates from another source than the
            # pinned release (here a fixture with a code-only and a wine.inf
            # candidate), compared with the production packages.
            fromFixture = args: mkReleases ({ candidatesSource = fixture; } // args);
            codeOnly = fromFixture { wineCandidates = [ "code-only" ]; };
            infChange = fromFixture { wineCandidates = [ "inf-change" ]; };
            infAtInstall = fromFixture {
              installWineCandidates = [ "inf-change" ];
              wineCandidates = [
                "inf-change"
                "code-only"
              ];
            };
            evaluates = package: (builtins.tryEval (builtins.deepSeq package.drvPath true)).success;
            prefixChange = import ./nix/wine-prefix.nix { inherit lib; };
            checks = {
              # This must also hold on a warm store, where an accidentally
              # copied fixture could hide an evaluation-only failure.
              "local candidate patches remain paths" =
                builtins.isPath (lib.last codeOnly.wine.patches)
                && builtins.isPath (lib.last infAtInstall.installWine.patches);
              # The production packages run on the flake's launch Wine.
              "packages use the launch Wine" =
                launchTools inventor2027 == drv releases.launchModules.runtime.toolsPackage;
              "a code-only candidate from another source leaves the installation as it is" =
                drv codeOnly.inventor2027.basePackage == drv inventor2027.basePackage
                && drv codeOnly.installWine == drv releases.installWine;
              "a code-only candidate changes the launcher" = drv codeOnly.inventor2027 != drv inventor2027;
              "the launcher runs the candidate Wine" =
                launchTools codeOnly.inventor2027 == drv codeOnly.launchModules.runtime.toolsPackage
                && launchTools codeOnly.inventor2027 != launchTools inventor2027;
              "the generated wrapper runs the candidate Wine" =
                lib.hasInfix (plain "${codeOnly.launchModules.runtime.toolsPackage}/bin/wine") (
                  plain codeOnly.inventor2027.launchWine.text
                );
              "the installation is built with the release Wine" =
                drv codeOnly.inventor2027.runtime.toolsPackage == drv releases.modules.runtime.toolsPackage;
              "a wine.inf candidate is refused at launch" = !(evaluates infChange.inventor2027);
              "a wine.inf candidate is accepted at installation" = evaluates infAtInstall.inventor2027;
              "candidates in both lists are applied once" =
                infAtInstall.wine.candidates == [
                  "inf-change"
                  "code-only"
                ];
              # A winum checkout given as `winum` (the documented way to test
              # candidates) that has the install release's name. A changed
              # code patch in its series is accepted, and a changed wine.inf
              # patch is refused.
              "a checkout whose series changes only code is accepted" =
                evaluates
                  (mkReleases {
                    winum = ./tests/fixtures/fake-winum-checkout-code;
                    installWinum = fixture;
                  }).inventor2027;
              "a checkout whose series changes the prefix is refused" =
                !(evaluates
                  (mkReleases {
                    winum = ./tests/fixtures/fake-winum-checkout-inf;
                    installWinum = fixture;
                  }).inventor2027
                );
              "the same candidates reuse the install Wine" =
                drv
                  (mkReleases {
                    candidatesSource = fixture;
                    installWineCandidates = [ "code-only" ];
                    wineCandidates = [ "code-only" ];
                  }).wine == drv
                  (mkReleases {
                    candidatesSource = fixture;
                    installWineCandidates = [ "code-only" ];
                  }).installWine;
              "prefix changes are detected" =
                prefixChange.changesPrefix "--- a/loader/wine.inf.in\n+++ b/loader/wine.inf.in\n"
                && prefixChange.changesPrefix "--- a/dlls/x/x.rgs\n+++ b/dlls/x/x.rgs\n"
                && prefixChange.changesPrefix "--- /dev/null\n+++ b/dlls/newdll/Makefile.in\n"
                && prefixChange.changesPrefix "--- a/programs/old/Makefile.in\n+++ /dev/null\n"
                && !(prefixChange.changesPrefix "--- a/dlls/ole32/storage32.c\n+++ b/dlls/ole32/storage32.c\n")
                && !(prefixChange.changesPrefix "--- a/dlls/ole32/Makefile.in\n+++ b/dlls/ole32/Makefile.in\n");
            };
            failed = lib.attrNames (lib.filterAttrs (_: passed: !passed) checks);
          in
          assert lib.assertMsg (failed == [ ]) "launch-wine-candidates: ${lib.concatStringsSep "; " failed}";
          pkgs.runCommand "inventor-launch-wine-candidates" { } "touch $out";
        module-empty-versions =
          let
            moduleConfig =
              settings:
              (nixpkgs.lib.nixosSystem {
                inherit system;
                modules = [
                  self.nixosModules.default
                  {
                    system.stateVersion = "26.05";
                    programs.autodesk-inventor = settings;
                  }
                ];
              }).config;
            cfg = moduleConfig { enable = true; };
            selectionWarnings =
              config:
              builtins.filter (nixpkgs.lib.hasPrefix "programs.autodesk-inventor.versions is empty;") config.warnings;
          in
          assert cfg.programs.autodesk-inventor.versions == [ ];
          assert
            selectionWarnings cfg == [
              ''programs.autodesk-inventor.versions is empty; select [ "2026" ] and/or [ "2027" ] to install Inventor.''
            ];
          assert
            selectionWarnings (moduleConfig {
              enable = false;
            }) == [ ];
          assert
            selectionWarnings (moduleConfig {
              enable = true;
              versions = [ "2027" ];
            }) == [ ];
          assert !(cfg.xdg.mime.defaultApplications ? "x-scheme-handler/adskidmgr");
          assert builtins.all (
            package: !(nixpkgs.lib.hasPrefix "inventor" (package.pname or package.name))
          ) cfg.environment.systemPackages;
          pkgs.runCommand "inventor-module-empty-versions" { } ''
            touch "$out"
          '';
        runtime-state =
          pkgs.runCommand "inventor-runtime-state-tests"
            {
              nativeBuildInputs = [
                pkgs.python3
                pkgs.bash
                pkgs.coreutils
                pkgs.findutils
                pkgs.gnugrep
                pkgs.util-linux
              ];
            }
            ''
              mkdir -p tests nix
              cp ${./tests/test_runtime_state.py} tests/test_runtime_state.py
              cp ${./nix/launch-state.sh} nix/launch-state.sh
              cp ${./nix/launch-services.sh} nix/launch-services.sh
              python3 tests/test_runtime_state.py
              touch "$out"
            '';
        installer =
          pkgs.runCommand "inventor-installer-tests"
            {
              nativeBuildInputs = [
                pkgs.python3
                pkgs.bash
                # Process-liveness tests set sleep's argv[0] to a Windows
                # image name; multicall coreutils would dispatch on it.
                (pkgs.coreutils.override { singleBinary = false; })
                pkgs.findutils
                pkgs.gnugrep
                pkgs.gnused
                pkgs.gawk
                pkgs.util-linux
                pkgs.glibc.bin # iconv for the synthetic .NET setup logs
              ];
            }
            ''
              export PYTHONPYCACHEPREFIX="$TMPDIR/pycache"
              cp -R ${./tests} tests
              cp -R ${./scripts} scripts
              cp -R ${./tools} tools
              cp -R ${./nix} nix
              cp -R ${./wine} wine
              mkdir registry
              chmod -R u+w tests scripts tools nix wine
              for script in scripts/*.sh scripts/lib/*.sh; do
                bash -n "$script"
              done
              python3 -m compileall -q scripts tools tests
              python3 -m unittest discover -s tests
              touch "$out"
            '';
        # Runs the adskidmgr dispatcher with stub launchers.
        url-dispatcher =
          let
            inherit (pkgs) lib;
            stub =
              name:
              pkgs.writeShellScript "stub-inventor-${name}" ''
                printf '%s %s\n' ${name} "$*" >> "$LOG"
                if [ "''${1:-}" = --nix-overlayfs-forward-url ]; then
                  # SEQ_<name>="4 4 0": one status per call, in order
                  if [ -n "''${SEQ_${name}:-}" ]; then
                    n=$(( $(cat "$LOG.${name}.n" 2>/dev/null || echo 0) + 1 ))
                    echo "$n" > "$LOG.${name}.n"
                    set -- ''${SEQ_${name}}
                    eval "exit \''${$n:-0}"
                  fi
                  exit "''${STATUS_${name}:-3}"
                fi
              '';
            dispatcher = import ./nix/url-dispatcher.nix { inherit (pkgs) lib writeShellScript; } [
              {
                name = "2027";
                exe = stub "2027";
              }
              {
                name = "2026";
                exe = stub "2026";
              }
            ];
            url = "adskidmgr://login?code=a b&state='x'";
          in
          pkgs.runCommand "inventor-url-dispatcher-tests" { } ''
            set -euo pipefail
            run() { LOG="$PWD/$1.log"; export LOG; : > "$LOG"; shift; "$@" ${dispatcher} ${lib.escapeShellArg url}; }
            lib_url=${lib.escapeShellArg url}

            # 2026 runs, 2027 does not: the callback goes to 2026, nothing starts.
            run forward env STATUS_2027=3 STATUS_2026=0
            test "$(cat forward.log)" = "2027 --nix-overlayfs-forward-url $lib_url
            2026 --nix-overlayfs-forward-url $lib_url"

            # Neither runs: the newest starts with the callback.
            run start env
            test "$(tail -1 start.log)" = "2027 $lib_url"

            # 2027 runs but cannot take it: stop, do not try 2026 or start one.
            status=0
            run failing env STATUS_2027=1 || status=$?
            test "$status" -eq 1
            test "$(cat failing.log)" = "2027 --nix-overlayfs-forward-url $lib_url"

            # 2027 is starting (4), then ready: the dispatcher asks again until
            # 2027 takes the callback. 2026 is never asked, and nothing starts.
            run starting env SEQ_2027="4 4 0"
            test "$(cat starting.log)" = "2027 --nix-overlayfs-forward-url $lib_url
            2027 --nix-overlayfs-forward-url $lib_url
            2027 --nix-overlayfs-forward-url $lib_url"

            # 2027 stays starting or closing: after the retries the dispatch
            # stops with 4 instead of handing the callback to 2026.
            status=0
            run busy env SEQ_2027="4 4 4 4 4 4" STATUS_2026=0 2>/dev/null || status=$?
            test "$status" -eq 4
            test "$(grep -c '^2027 ' busy.log)" -eq 4
            ! grep -q '^2026 ' busy.log

            # 2027 was closing (4) and then gone (3): the callback was its
            # own, so 2027 starts with it. 2026 is not asked.
            run closed env SEQ_2027="4 3" STATUS_2026=0
            test "$(cat closed.log)" = "2027 --nix-overlayfs-forward-url $lib_url
            2027 --nix-overlayfs-forward-url $lib_url
            2027 $lib_url"

            # 2027's session ended before taking the callback (5): 2027 starts
            # with it.
            run ended env SEQ_2027="5" STATUS_2026=0
            test "$(cat ended.log)" = "2027 --nix-overlayfs-forward-url $lib_url
            2027 $lib_url"

            # No URL.
            ! LOG=/dev/null ${dispatcher} 2>/dev/null
            touch "$out"
          '';
        # DXVK and vkd3d-proton are separate layers, not in the installation.
        # Builds only the two layers; the installation is compared by evaluation.
        graphics-layers =
          let
            inherit (pkgs) lib;
            drv = package: package.drvPath;
            otherDxvk = modules.dxvk_2_6_2;
            withOtherDxvk = releases.mkInventor {
              year = "2027";
              inherit (mediaSources2027) media;
              updates = [ mediaSources2027.update ];
              version = "2027.2";
              dxvkLayer = otherDxvk;
            };
            withUpstreamVkd3d = releases.mkInventor {
              year = "2027";
              inherit (mediaSources2027) media;
              updates = [ mediaSources2027.update ];
              version = "2027.2";
              vkd3dLayer = modules.vkd3d-proton;
            };
            # The layers the launcher mounts (passthru of nix-overlayfs).
            mounted = map drv inventor2027.overlayDependencies;
            graphics = lib.filter (
              layer: lib.hasPrefix "dxvk" layer.name || lib.hasPrefix "vkd3d-proton" layer.name
            ) inventor2027.overlayDependencies;
            checks = {
              "another DXVK leaves the installation as it is" =
                drv withOtherDxvk.basePackage == drv inventor2027.basePackage;
              "another DXVK changes the launcher" = drv withOtherDxvk != drv inventor2027;
              "the launcher mounts the other DXVK" = lib.elem (drv otherDxvk) (
                map drv withOtherDxvk.overlayDependencies
              );
              "the launcher mounts one DXVK and one vkd3d-proton layer" =
                map (layer: lib.head (lib.splitString "-2" (lib.removeSuffix "-3.0.1-winum-1" layer.name))) graphics
                == [
                  "dxvk"
                  "vkd3d-proton"
                ];
              "the default vkd3d-proton is winum's build" = lib.any (
                layer: layer.name == "vkd3d-proton-3.0.1-winum-1"
              ) graphics;
              "another vkd3d-proton leaves the installation as it is" =
                drv withUpstreamVkd3d.basePackage == drv inventor2027.basePackage
                && drv withUpstreamVkd3d != drv inventor2027;
              "both layers are mounted" = lib.all (layer: lib.elem (drv layer) mounted) graphics;
            };
            failed = lib.attrNames (lib.filterAttrs (_: passed: !passed) checks);
          in
          assert lib.assertMsg (failed == [ ]) "graphics-layers: ${lib.concatStringsSep "; " failed}";
          pkgs.runCommand "inventor-graphics-layers" { } "touch $out";
        # The installation layer and what it is built from. Evaluation only.
        installation =
          let
            inherit (pkgs) lib;
            drv = package: package.drvPath;
            built = inventor2027.installation;
            # scripts/lib/bsdtar.env as install-from-image.py reads it.
            env = import ./nix/env-file.nix { inherit lib; } ./scripts/lib/bsdtar.env;
            checks = {
              "the launcher starts from the installation layer" =
                drv inventor2027.basePackage == drv built.layer.basePackage;
              # The same expectations as in tests/test_bsdtar.py for Python's
              # read_env_file, so that both readers agree on the format.
              "nix/env-file.nix reads like install-from-image.py" =
                import ./nix/env-file.nix { inherit lib; } ./tests/fixtures/env-file.env == {
                  PLAIN = "value";
                  INDENTED = "spaced value";
                  QUOTED = "quoted value";
                  EMPTY = "";
                  WITH_EQUALS = "a=b";
                  DUP = "last";
                };
              "the bsdtar archive is fetched as bsdtar.env names it" =
                lib.elem env.BSDTAR_URL built.bsdtarArchive.urls
                && built.bsdtarArchive.outputHash == env.BSDTAR_SHA256
                && built.bsdtarArchive.name == env.BSDTAR_ZIP;
            };
            failed = lib.attrNames (lib.filterAttrs (_: passed: !passed) checks);
          in
          assert lib.assertMsg (failed == [ ]) "installation: ${lib.concatStringsSep "; " failed}";
          pkgs.runCommand "inventor-installation" { } "touch $out";
        # Every script migration has an entry in nix/migrations.nix that says
        # where the Nix package has it. The Nix build does not run migrations.
        migration-parity =
          let
            inherit (pkgs) lib;
            table = import ./nix/migrations.nix;
            files = builtins.attrNames (builtins.readDir ./scripts/lib/migrations);
            ids = map (lib.removeSuffix ".sh") (
              builtins.filter (name: builtins.match "[0-9]{4}-.*[.]sh" name != null) files
            );
            kinds = [
              "post-install"
              "config-layer"
              "installer"
              "launcher"
              "layers"
              "not-applicable"
            ];
            missing = lib.subtractLists (builtins.attrNames table) ids;
            stale = lib.subtractLists ids (builtins.attrNames table);
            badKinds = lib.filter (
              id: table.${id}.nix == [ ] || !(lib.all (k: lib.elem k kinds) table.${id}.nix)
            ) (builtins.attrNames table);
          in
          # A new or removed migration gives a warning, not a failure: migrations
          # come from the script installer's side, and its commits should not
          # turn the Nix checks red. A malformed entry is a mistake in
          # nix/migrations.nix itself, so it fails.
          assert lib.assertMsg (
            badKinds == [ ]
          ) "migration-parity: unknown or empty kinds for ${lib.concatStringsSep ", " badKinds}";
          lib.warnIf (missing != [ ])
            "migration-parity: the Nix package does not have ${lib.concatStringsSep ", " missing} yet - port it (nix/post-install.sh, nix/config-layer.sh) or say why it is not needed, in nix/migrations.nix"
            (
              lib.warnIf (stale != [ ])
                "migration-parity: nix/migrations.nix names migrations that do not exist: ${lib.concatStringsSep ", " stale}"
                (pkgs.runCommand "inventor-migration-parity" { } "touch $out")
            );
        # Evaluates the module with both releases; builds nothing from Autodesk.
        nixos-module =
          let
            inherit (pkgs) lib;
            config =
              (nixpkgs.lib.nixosSystem {
                modules = [
                  self.nixosModules.default
                  {
                    nixpkgs.hostPlatform = system;
                    system.stateVersion = "26.05";
                    programs.autodesk-inventor = {
                      enable = true;
                      versions = [
                        "2026"
                        "2027"
                      ];
                    };
                  }
                ];
              }).config;
            packages = config.environment.systemPackages;
            named = name: lib.findFirst (package: package.name == name) null packages;
            handler = named "autodesk-inventor-url-handler.desktop";
            plain = string: builtins.unsafeDiscardStringContext string;
            launcher = year: plain (lib.getExe self.packages.${system}."inventor-${year}");
            moduleLauncher =
              year:
              plain (
                lib.getExe (
                  self.packages.${system}."inventor-${year}".withArgs { registerHostUrlHandlers = false; }
                )
              );
            checks = {
              "adskidmgr goes to the dispatcher" =
                config.xdg.mime.defaultApplications."x-scheme-handler/adskidmgr"
                == "autodesk-inventor-url-handler.desktop";
              "the dispatcher entry is installed" = handler != null;
              "release entries do not claim adskidmgr" =
                lib.all (name: !(lib.hasInfix "adskidmgr" (plain (named name).text)))
                  [
                    "autodesk-inventor.desktop"
                    "autodesk-inventor-2027.desktop"
                  ];
              # The dispatcher's behaviour is checked by url-dispatcher.
              "the dispatcher uses the module's launchers, newest first" =
                map (launcher: plain launcher.exe) handler.urlHandler.launchers == [
                  (moduleLauncher "2027")
                  (moduleLauncher "2026")
                ];
              "the desktop-entry check runs in the user's graphical session" =
                let
                  service = config.systemd.user.services.autodesk-inventor-desktop-check;
                in
                lib.elem "graphical-session.target" service.wantedBy
                && lib.hasInfix "autodesk-inventor-desktop-check" (plain service.serviceConfig.ExecStart);
              # WantedBy orders the target after the unit, so an After= on the
              # target as well would make an ordering cycle.
              "the desktop-entry check is not ordered after its own target" =
                !(lib.elem "graphical-session.target" (
                  config.systemd.user.services.autodesk-inventor-desktop-check.after or [ ]
                ));
              "the module's launchers do not register handlers at runtime" =
                moduleLauncher "2026" != launcher "2026";
            };
            failed = lib.attrNames (lib.filterAttrs (_: passed: !passed) checks);
          in
          assert lib.assertMsg (failed == [ ]) "nixos-module: ${lib.concatStringsSep "; " failed}";
          pkgs.runCommand "inventor-nixos-module-tests" { } ''
            touch "$out"
          '';
      };
      formatter.${system} = pkgs.nixfmt;
      nixosModules.default = import ./nix/nixos-module.nix { inherit self; };
      devShells.${system}.default = pkgs.mkShell {
        packages = [
          wine
          pkgs.python3
          pkgs._7zz
          pkgs.cabextract
          pkgs.unzip
          pkgs.jq
          pkgs.shellcheck
        ];
      };
      # Consumers supply hash-pinned original installation media, never a personal prefix.
      lib.mkInventor = releases.mkInventor;
    };
}
