# One installer for several Autodesk products (plan, 2026-11-22)

The installer in this repository (`install-from-image.py`, `odis.py`, the
migration runner, the prefix setup) installs Inventor as Autodesk's own
installer does on Windows (`docs/installer-completeness-review.md`).
AutoCAD 2027 already installs with it (Autodesk-AutoCAD-for-Linux,
`docs/autocad-experiment-2026-11.md`, 2026-11-17) and Revit is next. This
plan keeps one installer instead of a copy per product, and adds the checks
that stop a change for one product, or one release, from breaking another.

## Decision

- **One shared core, thin product repositories.** The core (installation
  from the image, the migration runner, the common prefix setup: Wine,
  DXVK and vkd3d-proton, fonts, WebView2, isolation, licensing and the
  sign-in callback) stays in this repository for now. Each product gets a
  **profile**: default prefix, the executable, which setup steps it needs,
  extra skipped packages, default add-ins, its own migrations. What only
  Inventor needs (add-ins, Content Center, COM registration) lives in
  Inventor's profile.
- **The AutoCAD and Revit repositories pin a release of the core**, as the
  products pin a winum release, and hold only their profile, migrations,
  tools and docs. A new core is taken after that product's own test.
- The core moves to its own repository only once two products are stable
  on it.
- Not chosen: a copy of the scripts per product. Every fix of the last
  weeks (INSTALLDIR from `setup.xml`, ODIS MSI properties, bsdtar, the
  Access/ODIS names, migration 0012) would have had to be ported by hand,
  and a bug like 0010's would repeat in each copy.

## Safety net

1. **Release checklist per product:** a fresh install from the image; an
   **upgrade of a copy of the previous release's prefix** (this would have
   caught 0010 before v0.4.0); an old prefix without .NET Framework 4.8
   kept as a test fixture.
2. **Golden plans:** the `odis-plan.py` output for each product image
   (package names, versions, INSTALLDIR values, what is skipped and why)
   kept as text in the repository and compared before a release; every
   difference is explained. Names only, no Autodesk files.
3. **Comparison with Windows** (`tools/compare-reference.py`) for the
   newest release of each product: done for Inventor 2027 and 2027.2,
   AutoCAD 2027 next.
4. **Every migration is tested with and without .NET Framework 4.8** and on
   an old prefix.

## Work items, in order

1. Shared fixes in the core:
   - Access/ODIS under other manifest names (#32);
   - robustness: atomic state, stamped unpack cache, the licensing
     service's address from its `.data` file (#34);
   - the sign-in callback uses the running session's Wine, not
     `select_wine`'s (AutoCAD notes 2026-11-17, finding 2);
   - DXVK and vkd3d-proton as a common setup step, not only in Inventor's
     `finish-install.sh` (finding 3);
   - **Autodesk's terms before installing** (below);
   - release checklist and golden plans for Inventor.
2. Product profiles, without changing what Inventor gets (proved by its
   golden plan and the tests).
3. AutoCAD: profile, comparison with Windows in the offline VM, the gaps
   closed, then an AutoCAD release.
4. Revit after that: it stops in DataIntegrity, which is Wine work first.

## Autodesk's terms before installing

On Windows, Autodesk's installer (ODIS) shows the terms and goes on only
after the user agrees. Our installer runs the packages directly; the
manifests themselves pass `ADSK_EULA_STATUS=#1` to the MSI packages (the
project's code does not set it), so the terms are never shown. Autodesk's
general terms are also accepted at account registration and by using the
products, but the website's terms say software that comes with a licence
agreement may not be installed before agreeing to it. The project does
what ODIS does:

- `install.sh` says, before anything is installed, that Autodesk software
  is installed under Autodesk's terms, links them
  (`https://www.autodesk.com/company/terms-of-use/en/general-terms`) and
  asks for `yes`; `--accept-autodesk-terms` for unattended runs.
- The GUI installer: a checkbox with the link; Install stays off until it
  is ticked.
- README: one sentence in the installation section.
- The terms' text is not copied into the repository, only linked.
- Nix: the flag in its configuration, at @krokosik's next batch update.

## Not part of the installer

- **Autodesk Genuine Service** stays optional (`--with ags`): AutoCAD 2027
  started on Windows with its folder moved away and reported nothing
  (maintainer, 2026-11-22), and its installer fails under Wine (its custom
  action needs Windows PowerShell).
- **Licensing service and Identity Manager updates** come on Windows
  through Autodesk Access, not with the product updates (Inventor 2027.2
  had neither; the AutoCAD VM had Identity Manager 1.19.2.0 where the
  prefix has 1.16.5.1). Open: an optional step that installs Autodesk's
  standalone installers the user downloads (the project never downloads
  Autodesk files itself).
