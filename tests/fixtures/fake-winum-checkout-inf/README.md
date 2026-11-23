A winum checkout as `--override-input winum` would give it, used by flake
checks that evaluate (never build) `nix/wine.nix`. It has the same release
name as `fake-winum` and a release-series patch that changes `wine.inf`. The
launcher refuses it with an installation built from `fake-winum`.
