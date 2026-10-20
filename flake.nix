{
  description = "Declarative Autodesk Inventor 2026 environment for NixOS";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/b25309931cfda5f0b8805f462a29897eeae50168";
    nix-overlayfs = {
      url = "github:krokosik/nix-overlayfs/9342964a7344d93d75fdda0adcbbbba1a36994c7";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    inputs@{ self, nixpkgs, ... }:
    let
      system = "x86_64-linux";
      bootstrapPkgs = import nixpkgs { inherit system; };
      overlayfsSource = bootstrapPkgs.applyPatches {
        name = "nix-overlayfs-inventor-source";
        src = inputs.nix-overlayfs;
        patches = [ ./nix/nix-overlayfs-wine-11.20.patch ];
      };
      pkgs = import nixpkgs {
        inherit system;
        overlays = [
          (final: prev: {
            # libgsf 1.14.59 rejects valid empty OLE streams, crashing msitools.
            libgsf = prev.libgsf.overrideAttrs (old: {
              patches = (old.patches or [ ]) ++ [ ./nix/libgsf-empty-stream.patch ];
            });
          })
          (final: prev: {
            nix-overlayfs = import "${overlayfsSource}/pkgs/top-level" {
              pkgs = final;
              inputs = inputs.nix-overlayfs.inputs;
            };
          })
        ];
      };
      wine = pkgs.callPackage ./nix/wine.nix { };
      overlayfsLib = pkgs.nix-overlayfs.lib;
      scope = pkgs.nix-overlayfs;
      modules = scope.moduleScopes.makeNativeModules {
        inherit wine;
        windowsArch = "wow64";
      };
      mediaSources = import ./nix/media.nix { inherit pkgs; };
      inventor = self.lib.mkInventor {
        inherit (mediaSources) media;
        updates = [ mediaSources.update ];
        version = "2026.4";
      };
    in
    {
      packages.${system} = {
        inherit wine inventor;
        inventor-media = mediaSources.media;
        default = inventor;
      };
      apps.${system} = {
        default = self.apps.${system}.inventor;
        inventor = {
          type = "app";
          program = "${inventor}/bin/inventor";
          meta.description = "Autodesk Inventor Professional 2026.4";
        };
      };
      checks.${system}.installer =
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
