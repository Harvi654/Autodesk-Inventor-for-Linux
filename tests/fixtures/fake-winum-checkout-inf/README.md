A winum checkout as `--override-input winum` would give it, for flake checks
that evaluate (never build) `nix/wine.nix`: the same release name as
`fake-winum`, with a release-series patch that changes `wine.inf`. The
launcher refuses it with an installation built from `fake-winum`.
