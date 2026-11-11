{
  description = "Declarative Autodesk Inventor 2026 and 2027 environment for NixOS";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/b25309931cfda5f0b8805f462a29897eeae50168";
    nix-overlayfs = {
      url = "github:krokosik/nix-overlayfs/587ec313b81dc1937f127c887bd2c45f79ebd365";
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
      wine = pkgs.callPackage ./nix/wine.nix { inherit (inputs) winum; };
      overlayfsLib = pkgs.nix-overlayfs.lib;
      scope = pkgs.nix-overlayfs;
      modules = scope.moduleScopes.makeNativeModules {
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
            script = plain handler.urlHandler.text;
            launcher = year: plain (lib.getExe self.packages.${system}."inventor-${year}");
            moduleLauncher =
              year:
              plain (
                lib.getExe (
                  self.packages.${system}."inventor-${year}".withArgs { registerHostUrlHandlers = false; }
                )
              );
            position = needle: builtins.stringLength (builtins.head (lib.splitString needle script));
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
              "the module's launchers do not register handlers at runtime" =
                moduleLauncher "2026" != launcher "2026" && lib.hasInfix (moduleLauncher "2026") script;
              "a running 2027 session is tried first" =
                position "${moduleLauncher "2027"} --nix-overlayfs-forward-url"
                < position "${moduleLauncher "2026"} --nix-overlayfs-forward-url";
              "the newest release starts when none runs" =
                lib.hasInfix "exec ${moduleLauncher "2027"} \"$url\"" script;
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
          inherit pkgs overlayfsLib modules;
        } args;
    };
}
