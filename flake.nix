{
  description = "Declarative Autodesk Inventor 2026 and 2027 environment for NixOS";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/b25309931cfda5f0b8805f462a29897eeae50168";
    nix-overlayfs = {
      url = "github:krokosik/nix-overlayfs/8bf7c5cfa2541cf1478b87b519dcdc4c75831407";
      inputs.nixpkgs.follows = "nixpkgs";
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
      wine = pkgs.callPackage ./nix/wine.nix { };
      overlayfsLib = pkgs.nix-overlayfs.lib;
      scope = pkgs.nix-overlayfs;
      modules = scope.moduleScopes.makeNativeModules {
        inherit wine;
        windowsArch = "wow64";
      };
      mediaSources = import ./nix/media.nix { inherit pkgs; };
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
      inventor = self.lib.mkInventor {
        inherit (mediaSources) media;
        updates = [ mediaSources.update ];
        version = "2026.4";
      };
      inventor-rt = self.lib.mkInventor {
        inherit (mediaSources) media;
        updates = [ mediaSources.update ];
        version = "2026.4";
        gpuRayTracing = true;
      };
      inventor2027rt = self.lib.mkInventor {
        year = "2027";
        inherit (mediaSources2027) media;
        updates = [ mediaSources2027.update ];
        version = "2027.1";
        gpuRayTracing = true;
      };
      gpu = import ./nix/gpu-ray-tracing.nix {
        inherit pkgs overlayfsLib modules wine;
      };
    in
    {
      packages.${system} = {
        inherit wine inventor inventor-rt;
        inventor-2026-rt = inventor-rt;
        inventor-2027-rt = inventor2027rt;
        vkd3d-proton-windows = gpu.vkd3d;
        dxr-check = gpu.check;
        pixel-format-check = gpu.checkPixelFormat;
        shared-texture-check = gpu.checkSharedTexture;
        dxr-check-inventor = gpu.checkApplication inventor;
        inventor-2026 = inventor;
        inventor-2027 = inventor2027;
        inventor-media = mediaSources.media;
        default = inventor;
      };
      apps.${system} = {
        inventor-2026-rt = self.apps.${system}.inventor-rt;
        inventor-2027-rt = {
          type = "app";
          program = "${inventor2027rt}/bin/inventor-2027-rt";
          meta.description = "Inventor 2027 with experimental DirectX ray tracing";
        };
        inventor-rt = {
          type = "app";
          program = "${inventor-rt}/bin/inventor-rt";
          meta.description = "Inventor with experimental DirectX ray tracing";
        };
        dxr-check = {
          type = "app";
          program = "${gpu.check}/bin/inventor-dxr-check";
          meta.description = "Check Direct3D 12 ray tracing capabilities under Wine";
        };
        pixel-format-check = {
          type = "app";
          program = "${gpu.checkPixelFormat}/bin/inventor-pixel-format-check";
          meta.description = "Check Inventor's legacy and ARB OpenGL pixel-format selection";
        };
        shared-texture-check = {
          type = "app";
          program = "${gpu.checkSharedTexture}/bin/inventor-shared-texture-check";
          meta.description = "Check D3D12-to-D3D11 shared texture interoperability";
        };

        default = self.apps.${system}.inventor;
        inventor-2026 = self.apps.${system}.inventor;
        inventor-2027 = {
          type = "app";
          program = "${inventor2027}/bin/inventor-2027";
          meta.description = "Autodesk Inventor Professional 2027.1";
        };
        inventor = {
          type = "app";
          program = "${inventor}/bin/inventor";
          meta.description = "Autodesk Inventor Professional 2026.4";
        };
      };
      checks.${system} = {
        ray-payload = import ./nix/dxil-spirv-check.nix {
          inherit pkgs;
          vkd3d = gpu.vkd3d;
        };
        gpu-layers =
          pkgs.runCommand "inventor-gpu-layer-checks"
            {
              nativeBuildInputs = [ pkgs.python3 ];
            }
            ''
              python3 ${./tests/check_gpu_layers.py} ${(gpu.withRuntime inventor).basePackage} ${gpu.probe} ${gpu.runtime.toolsPackage} ${wine}
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
          inherit pkgs overlayfsLib modules wine;
        } args;
    };
}
