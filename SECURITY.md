# Security policy

## Reporting a problem

Please report security problems **privately**: on this repository's
**Security** tab choose **Report a vulnerability** (GitHub's private
vulnerability reporting). Only the maintainer sees the report. Please don't
open a public issue for them.

You get an answer within a few days. Once a fix is published, the report can
be made public with credit to you if you like.

## What counts

Anything that could harm the people who run this project, for example:

- `get.sh` or the installer doing something other than what they say, or
  something an attacker could make them do
- the scripts' use of `sudo` (they only install your distribution's packages)
- this project's Wine builds: the build workflow, the releases, the checksums
  in `wine/SHA256SUMS` or the provenance attestations not matching
- downloads that are not checked (DXVK, Wine and the rest are pinned and
  checked by SHA-256)
- files written outside the places the README names (the Wine prefix,
  `~/Inventor`, `~/.local/share/inventor-on-linux`, `~/.cache/inventor-on-linux`,
  app-menu entries)
- personal data or credentials ending up in logs or in `report.sh` output

Problems in Autodesk's software or in Wine itself belong to Autodesk or to
[WineHQ](https://bugs.winehq.org/); tell us anyway if this project makes them
worse.

## What not to send

**Never put Autodesk credentials, sign-in links or tokens in a report** - not
in issues, not in private reports. Some Autodesk files and logs contain
session tokens (for example ODIS `.info` files and Identity Manager logs);
leave them out or remove the tokens first. `report.sh` collects what is needed
for most problems - read its output before you share it.

## Supported versions

The newest release and the `main` branch. Update with
`bash scripts/update-project.sh` or the installer's **Update** button.
