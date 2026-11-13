# AutoCAD 2027 / 2026 experiment, 2026-11-12/13

Moved here from `docs/arch-hyprland.md` on `main` (2026-11-13), so the
AutoCAD work stays on this branch. Commits on `main` that wrote it:
a1df42f .. 1fb74f3, the last part 54d3fca (not on main). Installer and
Wine changes it led to are on `main` / in winum: 2695dd9 (`quirk_key`),
winum candidate `wldap32-winsock-cleanup`.

## Result log entry

**2026-11-12 - AutoCAD 2027 experiment:** on a 2012 MacBook (Arch, Intel
HD 4000) with winum-11.20-2, `install-from-image.py --app acad.en-US`
installs AutoCAD 2027 completely, including .NET Framework 4.8, after the
licensing quirk was matched by installer file (2695dd9). AutoCAD opens its
main window and a drawing, then stops with "License manager is not
functioning" before sign-in. Best hypothesis: it checks the service through
the service manager, where Wine shows it stopped; started as a real service
under Wine it times out (no `StartServiceCtrlDispatcher` call seen; not
fixed by a longer `ServicesPipeTimeout` or by starting RpcSs and SamSs
first). Stopped there as planned.
Continued 2026-11-13: the real first blocker was a Wine defect - wldap32
releases WinSock references it never took (winum candidate
`wldap32-winsock-cleanup`; with it AutoCAD's sign-in reaches Identity
Manager). AutoCAD still stops at licensing for a reason not yet found.
Section "AutoCAD 2027 experiment".

## AutoCAD 2027 experiment (2026-11-12, stops at licensing)

A quick test of how far the installer and winum get with another Autodesk
program, on a 2012 MacBook running Arch Linux (x86_64, Intel HD 4000, 7.7 GB
RAM), winum-11.20-2, a separate prefix `~/.wine-autocad2027`. Not supported;
recorded so the next attempt starts here.

**Installation works.** The downloaded `ACD_2027_..._001_002.exe` holds only
the bootstrapper; the install image is in `..._002_002.7z` (extract it with
7z, `manifest/app.acad.en-US.xml`). Then:

```bash
python3 scripts/install-from-image.py "$IMG" --prefix ~/.wine-autocad2027 --app acad.en-US
```

All 30 package steps finish, and so does the .NET Framework 4.8 step
(about 30 minutes on this machine, most of it native image generation).
AutoCAD's manifest names the licensing package differently from Inventor's
(`x86/Licensing/pkg.licensing.xml`), so the known exit-84 quirk of
`AdskLicensing-installer.exe` is now matched by the installer file
(`quirk_key()`, commit 2695dd9). The MSI log shows the product registered
with the licensing service (`licIsSvcUpgraded`, `licRegister` return 1; the
service log: `Feature Register done for 001S1 2027.0.0.F`).

**Start: main window, then "License Error".** `finish-install.sh` was not
run (it is Inventor-specific), so the prefix has no DXVK and Wine draws with
OpenGL (wined3d). Started by hand like `launch-inventor.sh` does: Identity
Manager, `AdskLicensingService.exe` as a process, then `acad.exe`. AutoCAD
opens its main window with `Drawing1.dwg` (ribbon, grid, status bar), then
shows "The License manager is not functioning or is improperly installed.
AutoCAD will shut down now." - before any sign-in prompt.

What was seen:
- the service log shows a licensing agent (`AdskLicensingAgent.exe -i
  securesite-...`) launched, registered and shut down normally within
  about 0.1 s, no error lines;
- `sc query AdskLicensingService`: `STOPPED`, exit code 1077 - the service
  manager does not know about the service running as a plain process;
- `CurrentSDK` is missing: expected, licensing 16.x has no
  `AdskLicensingSDK` folder;
- adding the licensing agent's SSO plugin and
  `IDSDKVersionCompatibility.config` (what `cfg_sso_plugin` does for
  Inventor) did not change the error.

**Best hypothesis (unconfirmed):** unlike Inventor, AutoCAD checks the
licensing service through the Windows service manager, where the service
shows as stopped. Started as a real service it does not get there under
Wine - measured the same night:

- `wine net start AdskLicensingService` ends with "Service request
  timeout"; `sc query`: `STOPPED`, 1077, no process left. The service is
  auto-start, so the same failure also shows at every prefix start
  (`scmdatabase_autostart_services ... failed to start: 1053`) - the same
  cause as the installer's exit 84.
- `WINEDEBUG=+service`: no `StartServiceCtrlDispatcher` call from
  `AdskLicensingService.exe` (the 32-bit process that reports RUNNING in the
  trace is `clr_optimization_v4.0.30319_32`, the .NET ngen service).
  `services.exe` gives up in `process_send_start_message` ("failed to
  start", 1053) when the control pipe is not connected within
  `service_pipe_timeout` (10 s by default in Wine; read from
  `HKLM\System\CurrentControlSet\Control\ServicesPipeTimeout`, as REG_SZ).
  The service's own log meanwhile shows it running ("HTTP server running",
  agent launched).
- `ServicesPipeTimeout` = 60000: still the timeout.
- While the service starts, `RpcSs` and `SamSs` fail to start
  (`err:ole:start_rpcss`, `err:secur32:start_samss`): Wine starts services
  one at a time (`scmdatabase_lock_startup`), and a start request waits
  only 3 s for that lock. The service uses COM/WMI at start-up. But with
  `wineserver -p`, `RpcSs` and `SamSs` started first (both `RUNNING`), the
  licensing service still timed out - so this is not the whole cause.

Next step for whoever continues: a `+service,+timestamp` trace of only
`net start AdskLicensingService` with RpcSs and SamSs already running,
looking for when (or whether) the service calls
`StartServiceCtrlDispatcher`, and a MEASURE program on Windows 10 for the
service-start timing Wine should match. The fix, if any, belongs in winum.

**2026-11-13, continued: the service-manager hypothesis was wrong.** With
the prefix prepared by the non-Inventor parts of `finish-install.sh`
(`cfg_wine_mode`, licensing service on manual start, the `adskidmgr://`
handler, `cfg_sso_plugin`, `webview2_reg`, `linux-fonts.sh`,
`cfg_isolation`) and started like `launch-inventor.sh`, AutoCAD shows its
full ribbon but the same error. A `+service` trace of `acad.exe` shows no
service-manager calls at all. The licensing agent seen in the service log is
started by the service itself at its own start-up ("silent mode"), not by
AutoCAD; AutoCAD never contacts the service.

What was found instead: AutoCAD's sign-in component (`IdSDKPlugin`) could not
create a socket to Identity Manager (`IdServices.log`: `Failed to connect
to server at port 45321 ... system_error:10093`, WSANOTINITIALISED). A
`+pid,+winsock` trace and a `+relay` trace limited to
`ws2_32.WSAStartup;ws2_32.WSACleanup` showed AutoCAD loading and unloading
`wldap32.dll` eight times, and Wine's wldap32 (the bundled OpenLDAP) calling
`WSACleanup()` at every unload without ever calling `WSAStartup()`, so the
process's WinSock count reached 0. Fix: winum candidate
`wldap32-winsock-cleanup` (branch `topic/wldap32-winsock-cleanup`, page
`docs/patches/wldap32-winsock-cleanup.md` there). With its test build the
10093 errors are gone and AutoCAD completes `Handshake` and `IsLoggedIn`
(false) with Identity Manager - but it still stops with "License manager
is not functioning", and its licensing SDK (`AdskLicensingSDK_10.dll` in the
AutoCAD folder) still never contacts the licensing service. A `+relay`
trace from that DLL was far too large (12 GB before reaching the error);
next time try the lighter `+reg` and `+file` channels to see what it looks
for and does not find.

**2026-11-13, the second blocker (with the wldap32 fix), not solved.**
Ruled out with Wine's own channels, each filtered while running:
- registry and files (`+reg`, `+file`, all threads of `acad.exe`): nothing
  missing; AutoCAD reads its `*LICENSETYPE`, `*LICENSEUSAGE`,
  `*LICENSEUSAGESUBMODEL`, `*LICENSEMODEL` variables (all `UNKNOWN`, written
  by the installer), then the licensing SDK writes its own log
  (`AppData\Local\Autodesk\Logs\AdlSdk-<pid>.log`, two lines, encoded -
  not decoded, an `[E]` line one millisecond after the first) and the error
  box follows. AutoCAD never opens anything of the licensing service
  (`...\Autodesk Shared\AdskLicensing\...`,
  `ProgramData\Autodesk\AdskLicensingService`) and makes no connection to
  its port 44447 (`+winsock`, `+winhttp`, `+wininet`); it only talks to
  Identity Manager, which now works;
- network adapters: Wine reports the wired adapter with its MAC address
  (Wi-Fi as "Unknown adapter"); with Wi-Fi off and `virbr0` down, the same
  error;
- modules (`+module`, `+loaddll`, `warn+seh`): `AdskLicensingSDK_10.dll`
  (AutoCAD's folder) is loaded on the line right before the error box, with
  no failed load, missing export, stub or exception in between.
So the decision is made inside the licensing SDK without any call that Wine
logs as failing. What is left needs a comparison with a working system, all
from outside: Process Monitor on the Windows VM with AutoCAD 2027 installed
(what the SDK opens and connects to right after it is loaded), and Inventor
on the main PC with the same `+winsock` filter (whether Inventor's licensing
SDK connects to 127.0.0.1:44447 when it works).

**2026-11-13, AutoCAD 2026 for comparison:** same machine, own prefix
`~/.wine-autocad2026`, the wldap32 test build. Installs the same way (steps
1-30; licensing service 15.1.0.12339 finished by the exit-84 quirk). New in
2026: the `Autodesk CER Service` MSI fails because Wine cannot start the
service (`ITERATE_StartService ... (1053)`, MSI returns 1627, rolled back);
skipped, it is only crash reporting. Result: the same "License manager is
not functioning" error after the main window. A second Autodesk service
(after the licensing service) that times out with 1053 when started as a
real Windows service under Wine - worth one look in winum some day.

**2026-11-13, afternoon - more ruled out (AutoCAD 2027, wldap32 build):**
- the licensing service itself works under Wine: Autodesk's admin tool
  `AdskLicensingInstHelper.exe list` (in the licensing `helper` folder)
  connects to 127.0.0.1:44447 and lists AutoCAD (`ACD`, `001S1`,
  `2027.0.0.F`); `change -pk 001S1 -pv 2027.0.0.F -lm USER` sets the
  licence type (`lic_method` 4) - AutoCAD still shows the same error;
- early in start-up AutoCAD tries `upi2.dll` by name, fails (c0000135,
  delay-load exception c06d007e); the DLL is in
  `Common Files\Autodesk\AdpDesktopSDK\bin`. With that folder in
  `WINEPATH` it loads (and unloads) - same error, so not the cause. No
  `App Paths\acad.exe` key exists in the prefix;
- the rest of the start-up `fixme`/`warn` lines are the usual ones (.NET
  probing the program folder, ETW, themes, `WNetGetUniversalNameW`).
How the sign-in window comes about (as seen with Inventor): the program's
licensing SDK asks the licensing service; the service starts the Licensing
Agent (licence-type choice, WebView2) and asks Identity Manager, which opens
the Autodesk sign-in in the browser; `adskidmgr://` returns to Identity
Manager. With AutoCAD the first step never happens, so nothing asks for a
sign-in. Left: compare with a working system (Inventor's licensing SDK on
the main PC under `+winsock`; AutoCAD on Windows under Process Monitor).

Also checked the same afternoon, no change: the Shared Components registry
of migration 0001 (`HKLM\SOFTWARE\Autodesk\SharedComponents\2027` and
`Components\2027\2.0.2` in the system `Path`), and FlexNet: the prefix
starts `FNPLicensingService64.exe` by itself (a FlexNet service AutoCAD's
licensing installs; its service name is not `FNPLicensingService64`, `sc`
answers 1060) - running, same error. All package actions of the AutoCAD
manifests ran; one ran with an unexpanded variable: `AcNGEN.exe install ...
%ACAD_INSTALL_PATH%` (.NET native images for AutoCAD; speed only).

Last trace of the day: `+relay` limited (`RelayInclude`) to the calls a
licensing SDK would need to find a service running as a plain process or to
check it - process lists (`CreateToolhelp32Snapshot`, `Process32*`,
`EnumProcesses`), `OpenProcess`, `QueryFullProcessImageNameW`,
`ProcessIdToSessionId`, tokens, the service manager, sockets, named
objects and pipes, files, registry - over the whole start of AutoCAD 2027.
Between the load of `AdskLicensingSDK_10.dll` and the error box the SDK only
resolves `Local AppData` and the profile folder, opens its log file and
writes it; no process, token, service, network or licensing-registry call
at all. The failing calls just before the load are AutoCAD's usual lookups
(`*LICENSE...` variables found on the third try, `SHOWNEWSTATE`, `res`
resource values, `DisableAdConnect`). So "the service runs as a process,
not as a Windows service" is not what AutoCAD trips over, and the decision
is made before or at the SDK's first call without anything Wine reports.
The experiment stops here; the comparison with Inventor's licensing SDK on
the main PC is the next step.

**Why Autodesk's services time out (1053) under Wine - hypothesis, from
code, not yet measured in the service.** A `+relay` of
`AdskLicensingService.exe` started with `net start` shows a Go program
(`GODEBUG`, `GOPROTODEBUG`, `DEBUG_HTTP2_GOROUTINES`, `BBOLT_VERIFY`, Go heap
addresses). Go's `golang.org/x/sys/windows/svc.IsWindowsService()` decides
"I am a Windows service" only if the parent process is `services.exe` **and
has session ID 0** (it reads both with `NtQuerySystemInformation
(SystemProcessInformation)`; .NET's `WindowsServiceHelpers.IsWindowsService`
does the same). In Wine every process, `services.exe` included, is in
session 1 (`server/process.h`: `default_session_id = 1`; the session comes
from the token). So the service concludes it is not a service, runs as a
console program, never calls `StartServiceCtrlDispatcher`, and Wine's
`services.exe` gives up after the pipe timeout with 1053 - the licensing
installer's exit 84. That matches all measurements (longer
`ServicesPipeTimeout`, RpcSs/SamSs started first: no change).
Confirm next time with `RelayInclude=ntdll.NtQuerySystemInformation;
ntdll.NtQueryInformationProcess` on the service under `net start`. A fix
would be in winum: services started by `services.exe` (and `services.exe`
itself) in session 0, as on Windows - medium size (wineserver or
services.exe), needs a Windows measurement (L1) and care for services with
windows. Not needed for Inventor (the service runs as a process); for
AutoCAD probably not the cause either (AutoCAD never looks for the service);
it would remove the exit-84 quirk and let CER and similar services install.

Also to fix in the installer before AutoCAD is attempted again: a dry run
creates an empty prefix that blocks the real run, and the skip list does not
know AutoCAD's names for the ODIS installer and Autodesk Access packages. `%ACAD_INSTALL_PATH%` in AutoCAD's `AcNGEN.exe` action is not expanded, and
2026's `Autodesk CER Service` is not on the skip list.

## 2026-11-13 evening: Inventor 2027 on the same MacBook, side by side

Inventor 2027 installed with `install.sh --no-content` (INV_VKD3D=off) on the
same machine and Wine as AutoCAD. Sign-in works; Inventor's window needs
wined3d there (DXVK: "Device does not support Vulkan 1.3", HD 4000), i.e.
the DXVK overrides removed. Comparison (all from outside):

- **Same licensing SDK**: `AdskLicensingSDK_10.dll`, 2409304 bytes, in both.
- Identity Manager log: with Inventor, `AdskLicensingAgent` sends `GetServer`,
  `IsLoginValid` and `Login`; with AutoCAD the agent never appears.
- Licensing service log: about 120 ms after Inventor's SDK opens its log,
  the service shows `SDK monitor starting`, `Launching Agent via SDK`,
  `Features in service`, `LicenseWorkflowData`, workflow nodes. Nothing
  from AutoCAD.
- The SDK log's `[O]` + `[E]` pair at `AdlSdkLogger.cpp:147/155` is written by
  Inventor too: it is the log header, **not** an error (the notes above
  that read it as AutoCAD's error were wrong).
- `ADLSDK_LOG_LEVEL=T` (documented in Autodesk's Nastran Linux manual) makes
  the SDK log more lines; only level, source file and line are readable.
  Inventor: 57 lines - `AdlSdkSession.cpp:52`, `AdlSdkAdlsAdapter`,
  `AdlSdkSocket`, `easywsclient` (a WebSocket to the service), ...
  AutoCAD: 3 lines - `AdlSdkLogger.cpp:147`, `AdlSdkWinUI.cpp:158`,
  `AdlSdkWinUI.cpp:168`, then AutoCAD's own message box. AutoCAD never
  reaches a session.
- A `+relay` of window, DPI, language, resource and module functions: between
  the SDK load and the message box no call comes from the SDK's address
  range at all.
- Inventor's SDK first checks `<exe folder>\upi\upiconfig.xml`
  (`GetFileAttributesW`); AutoCAD's SDK never gets that far.
- Not the difference: the `.pit` path in the registration (`M:\...` for both;
  M: is gone after the install), the ASR files
  (`ProgramData\Autodesk\Adlm\ASR`, both). Small difference: the
  registration's serial field (`000-00000000;0;0` for Inventor, `-` for
  AutoCAD). AutoCAD's registry has
  `ADLMInfoPath = C:\ProgramData\Autodesk\AutoCAD 2027\R26.0\enu\Adlm\`, a
  folder that does not exist in the prefix (Inventor has no such value).

Reading: AutoCAD loads the SDK late (after its main window) and its first use
is the SDK's UI part, then its own "License manager is not functioning" box -
as if AutoCAD had decided earlier that licensing failed and uses the SDK only
to report it. Where to look next: what AutoCAD does before it loads the SDK
(the early failed `upi2.dll` delay-load, the missing `ADLMInfoPath` folder),
and the same `ADLSDK_LOG_LEVEL=T` log of AutoCAD on Windows for comparison.

Tried the same evening, no change (SDK log still 3 lines, same error): the
`ADLMInfoPath` folder created empty, then with `AutoCADConfig.pit` from the
image (`x64/acadprivate/`) in it, both with `upi2.dll` reachable through
`WINEPATH` (`Common Files\Autodesk\AdpDesktopSDK\bin`). Stopped here.

## 2026-11-13: Autodesk's own web installer (ODIS) under winum

`Autodesk_AutoCAD_2027_1_English_en-US_setup_webinstall.exe`, fresh prefix
`~/.wine-acadweb`, the wldap32 test build, `wineboot -i` with
`mscoree,mshtml=` (no Mono/Gecko), Windows 10.

- The 7-Zip self-extractor starts `Setup.exe`, which fails to load
  `wxbase332u_vc_x64_custom.dll`, `wxmsw332u_core_vc_x64_custom.dll` and
  `AdHttpLib.dll` (c0000135). They are in `ODIS\odis.bs.wx\` and
  `ODIS\odis.bs.win\`, each with its own `<name>.manifest` - private
  side-by-side assemblies that Wine does not resolve for `Setup.exe` (to be
  looked at in winum). Work-around for the test: unpack with 7z and add both
  folders to `WINEPATH`.
- Then the ODIS window works, downloads, installs some packages (Autodesk
  Access Connector), and stops with "Install error: AutoCAD 2027 - Error
  4005" on "AutoCAD Shared 2027" (an ADIX package), rolling back.
  `Install.log`: `MsixCoreLib::PopulatePackageInfo::GetPackageInfoFromPackage
  ... appxFactory->CreatePackageReader(...) error code: -1951596478`
  = 0x8BAD0042, MSIX Core's `CertNotTrusted`: the package signature does not
  chain to a trusted root in Wine's certificate store. Hypothesis: a
  code-signing root that the Linux (TLS-oriented) CA bundle Wine imports
  does not contain. Not pursued; this project's own installer unpacks ADIX
  packages itself.

## 2026-11-13 evening: native Windows 10 first run compared with Wine

AutoCAD 2027 installed on the MacBook's own Windows 10 (dual boot) from the
same image, first start recorded with Process Monitor; the capture, registry
exports (`HKLM\SOFTWARE\Autodesk`, its WOW6432Node, `HKCU\Software\Autodesk`),
file lists and logs were copied to Linux and stay local (never committed:
they hold user names, the machine's SID and a sign-in callback). Read with
the open `procmon-parser` library and the three scripts in
[autocad-tools/](autocad-tools/) (output masks user names and SIDs):

```
python -m venv venv; venv/bin/pip install procmon-parser
venv/bin/python -I pml-summary.py first-run.PML out     # process tree, acad.exe around the SDK load, licensing paths
venv/bin/python -I pml-sdk-window.py first-run.PML <index of the SDK Load_Image> > sdk.txt
python3 -I regdiff.py hklm-autodesk.reg PREFIX/system.reg   # key/value NAMES Windows has and the prefix lacks
```

What Windows does (the AdlSdk log with `ADLSDK_LOG_LEVEL=T`: 157 lines,
`AdlSdkSession.cpp` right after the logger, where Wine goes to
`AdlSdkWinUI.cpp:158/168`):

- **In the same thread, right after its own log, the SDK opens a second
  log, `C:\ProgramData\Autodesk\Adlm\AdlSdk-ACD2027EN-<pid>.log`** - it
  already knows the product (`ACD2027EN`) before any other I/O. Then it
  finds `Common Files (x86)`, opens
  `ProgramData\Autodesk\AdskLicensingService\AdskLicensingService.data`,
  reads `MachineGuid`, runs a signature check (WinTrust policy keys, maps
  its own DLL several times), connects to a local port, and AutoCAD later
  starts `AdskLicensingAgent.exe -i <guid> -c 2` (the licence window) and
  several `--no-gui` analytics agents. Under Wine `AdlSdk-ACD2027EN-*.log`
  is never created: the product is not known at the SDK's first call, so
  the decision is in what AutoCAD passes, not in anything the SDK reads.
- Long before the SDK, `acad.exe` uses Autodesk Access / ODIS: reads
  `HKLM\SOFTWARE\Autodesk\ODIS\ODISSDKLocation`, loads
  `AdODIS\V1\Setup\ODISSDK.dll`, talks over `\\.\pipe\adsk_odis_sdk`
  (served by `AdskAccessServiceHost.exe`, a session-0 service) and writes
  `AppData\Local\Autodesk\ODIS\ODIS_APIWrapper.log`. Just before the SDK
  it opens two ADP (analytics) pipes, `adsk_adp_ipm_ipc_channel_<SID>` and
  `adsk_adp_sdk_ipc_channel_<SID>`, and runs `CER\upi.exe
  --cmd=get-device-id`.
- Genuine Autodesk Service runs on its own (not a child of `acad.exe`) and
  only calls `AdskLicensingInstHelper list` - not involved.

Tried on a copy of the prefix (`~/.wine-autocad2027-odis`), each with the
same result (SDK log 3 lines, "License manager is not functioning"):

1. **ODIS and Access installed.** The AutoCAD prefix had neither: the plan
   lists them (steps 31/32, `ODIS/AdODIS-installer.exe`,
   `x64/Access/AdAccess-installer.exe`, `--mode unattended`), but the run
   on 2026-11-12 never executed them (the log goes from step 30 to .NET 4.8;
   cause not found yet). Both are VMware InstallBuilder installers; started
   from the image drive they fail with "Installer payload initialization
   failed" (InstallBuilder's Tcl VFS gets confused by the path - known from
   Wine bug 38803's discussion); copied to `C:\` they install (exit 0,
   `--useService` left out, it is not in `--help`). `ODISSDK.dll` and the
   `ODIS` registry key then match Windows, and `ODIS_APIWrapper.log` under
   Wine shows the same sessions as on Windows (ASC 2027, DVPTS 2.0 twice,
   each with a session id). ODIS works and is not the cause.
2. **UPI2 registrations added.** `regdiff.py` found, besides
   `HKLM\SOFTWARE\Autodesk\AdskLicensing` (only `Version`; Inventor's
   working prefix has no such key either) and three extra
   `HKLM\SOFTWARE\Autodesk\UPI` upiconfig entries (`acaoe`,
   `en-US\acadlp`, `globupi`), 13 keys under `HKLM\SOFTWARE\Autodesk\UPI2`
   that the prefix lacks - the ADIX packages ("AutoCAD 2027", "Autodesk
   AutoCAD 2027 - English", "AutoCAD Shared 2027", ...: on Windows ODIS
   writes them, this project's installer unpacks ADIX itself and does not;
   MSI packages write their own). Values: build, category, GUID, INSTALLDIR,
   versions, product code/line, release, unit type, upgrade code - no serial
   or personal data. The 11 that are not CER or Genuine Service imported
   with `regedit` (verified in `system.reg` before the start). No change.

Same for both: the files in `ProgramData\Autodesk\Adlm\ASR` (six `.asr`)
and the rest of the `HKLM\SOFTWARE\Autodesk` values match Windows.

**State (three-rounds rule reached, stopped):** AutoCAD under Wine reaches
the SDK without a product, Windows with `ACD2027EN`. Not the cause: the
service-vs-process question, `upiconfig.xml`, `ADLMInfoPath`, `upi2.dll`,
`/product` arguments, ODIS/Access, UPI2 registry, ASR files. Best
hypothesis: something `acad.exe` reads or calls earlier fails silently
under Wine (or returns a different value), and AutoCAD then calls only the
SDK's UI part to report the failure. Next step if resumed: a list of
`acad.exe`'s registry and file operations before the SDK load on Windows
(unique path + result from the PML, about 217,000 events) against a
`+reg,+file` trace of the same window under Wine, looking for what Windows
finds and Wine does not.

For the installer (when AutoCAD is picked up again): steps 31/32 not run;
InstallBuilder installers must run from `C:\`, not from the image drive;
UPI2 keys of ADIX packages are not written (the `upi2` GUID is in each
package's manifest line).
