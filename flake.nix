{
  description = "Declarative Autodesk Inventor 2026 and 2027 environment for NixOS";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/b25309931cfda5f0b8805f462a29897eeae50168";
    nix-overlayfs = {
      url = "github:krokosik/nix-overlayfs/d3e19c4807c5b86f6dd20677a72138aeace782f5";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    # winum-11.20-1 (signed tag), the Wine release wine/version.env names.
    # Only its patches/series and the patches it lists are used.
    winum = {
      url = "github:Harvi654/winum/6d437d1e992e152eeec58b93ba85dce9c5f6a23d";
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
      wineCandidates = [ ];
      installWineCandidates = [ ];
      # Builds the base environment, WebView2, .NET Framework and Inventor.
      installWine = pkgs.callPackage ./nix/wine.nix {
        inherit (inputs) winum;
        candidates = installWineCandidates;
      };
      # Runs Inventor: the same winum release plus the candidates under test.
      wine =
        if wineCandidates == installWineCandidates then
          installWine
        else
          pkgs.callPackage ./nix/wine.nix {
            inherit (inputs) winum;
            candidates = installWineCandidates ++ wineCandidates;
          };
      overlayfsLib = pkgs.nix-overlayfs.lib;
      scope = pkgs.nix-overlayfs;
      modules = scope.moduleScopes.makeNativeModules {
        wine = installWine;
        windowsArch = "wow64";
      };
      launchModules = scope.moduleScopes.makeNativeModules {
        inherit wine;
        windowsArch = "wow64";
      };
      mediaSources2026 = import ./nix/media.nix {
        inherit pkgs;
        year = "2026";
      };
      mediaSources2027 = import ./nix/media.nix {
        inherit pkgs;
        year = "2027";
      };
      inventor2027 = self.lib.mkInventor {
        year = "2027";
        inherit (mediaSources2027) media;
        updates = [ mediaSources2027.update ];
        version = "2027.1";
      };
      inventor2026 = self.lib.mkInventor {
        year = "2026";
        inherit (mediaSources2026) media;
        updates = [ mediaSources2026.update ];
        version = "2026.4";
      };
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
          meta.description = "Autodesk Inventor Professional 2027.1";
        };
        inventor-2026 = {
          type = "app";
          program = "${inventor2026}/bin/inventor";
          meta.description = "Autodesk Inventor Professional 2026.4";
        };
      };
      checks.${system} = {
        # wine/version.env (get-wine.sh) and the flake input (nix/wine.nix)
        # must name the same winum release.
        winum-pin =
          let
            env = builtins.readFile ./wine/version.env;
            value =
              key:
              let
                m = builtins.match ".*\n${key}=([^\n]*)\n.*" ("\n" + env + "\n");
              in
              if m == null then throw "wine/version.env has no ${key}" else builtins.head m;
          in
          assert value "WINUM_VERSION" == wine.wineVersion;
          assert value "WINUM_BUILD" == wine.winumBuild;
          pkgs.runCommand "inventor-winum-pin" { } ''
            touch "$out"
          '';
        # A winum candidate changes the Wine Inventor runs, not the installation.
        launch-wine-candidates =
          let
            inherit (pkgs) lib;
            topics = lib.attrNames (
              lib.filterAttrs (_: type: type == "directory") (
                builtins.readDir "${inputs.winum}/patches/candidates"
              )
            );
            candidateModules = scope.moduleScopes.makeNativeModules {
              wine = pkgs.callPackage ./nix/wine.nix {
                inherit (inputs) winum;
                candidates = lib.take 1 topics;
              };
              windowsArch = "wow64";
            };
            withCandidate =
              import ./nix/inventor.nix
                {
                  inherit pkgs overlayfsLib modules;
                  launchModules = candidateModules;
                }
                {
                  year = "2027";
                  inherit (mediaSources2027) media;
                  updates = [ mediaSources2027.update ];
                  version = "2027.1";
                };
          in
          if topics == [ ] then
            builtins.trace "launch-wine-candidates: winum has no candidates; nothing to compare" (
              pkgs.runCommand "inventor-launch-wine-candidates" { } "touch $out"
            )
          else
            assert withCandidate.basePackage.drvPath == inventor2027.basePackage.drvPath;
            assert withCandidate.drvPath != inventor2027.drvPath;
            assert
              withCandidate.launchRuntime.toolsPackage.drvPath == candidateModules.runtime.toolsPackage.drvPath;
            assert withCandidate.runtime.toolsPackage.drvPath == modules.runtime.toolsPackage.drvPath;
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
              cp ${./nix/launch-lock.sh} nix/launch-lock.sh
              cp ${./nix/launch-services.sh} nix/launch-services.sh
              cp ${./nix/launch-fonts.sh} nix/launch-fonts.sh
              python3 tests/test_runtime_state.py
              touch "$out"
            '';
        installer =
          pkgs.runCommand "inventor-installer-tests"
            {
              nativeBuildInputs = [
                pkgs.python3
                pkgs.bash
              ];
            }
            ''
              export PYTHONPYCACHEPREFIX="$TMPDIR/pycache"
              mkdir -p tests
              cp ${./tests/test_declarative_installer.py} tests/test_declarative_installer.py
              cp -R ${./scripts} scripts
              python3 tests/test_declarative_installer.py
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

            # No URL.
            ! LOG=/dev/null ${dispatcher} 2>/dev/null
            touch "$out"
          '';
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
      lib.mkInventor =
        args:
        import ./nix/inventor.nix {
          inherit
            pkgs
            overlayfsLib
            modules
            launchModules
            ;
        } args;
    };
}
