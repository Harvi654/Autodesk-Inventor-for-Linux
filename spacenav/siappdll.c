/*
 * siappdll.dll for Wine: the 3Dconnexion SIAPP (SpaceWare) client library,
 * fed by spacenavd instead of 3DxWare.
 *
 * Inventor (and other CAD programs) look for siappdll.dll at start and, when
 * it is there, drive their own 3D mouse navigation through it. Under Wine the
 * device belongs to spacenavd on the Linux side; Windows programs can't open
 * its UNIX socket (Wine has no AF_UNIX in ws2_32), so the launcher relays it
 * to 127.0.0.1 (scripts/launch-inventor.sh, socat) and this library reads the
 * relay: 8 x int32 per event (type, x, y, z, rx, ry, rz, period or button).
 *
 * Events reach the application the way the SIAPP API defines it: a message
 * registered as "SpaceWareMessage00" is posted to the window given to SiOpen,
 * and the application hands every message to SiGetEvent, which says whether
 * it is ours and decodes it.
 *
 * Buttons: on Windows 3DxWare runs the button commands itself and the
 * application ignores button events (Inventor does), so this library does it
 * too. A button press runs an action from spacemouse.ini (see
 * spacenav/spacemouse.ini): a view, an Inventor command, keys or a radial
 * menu. Views and commands go through Inventor's public COM API, on the
 * application's own thread (a message-only window created in SiOpen). The
 * file is read at every press, so changes apply at once.
 *
 * Environment (Windows side; Wine passes the Linux environment through):
 *   SIAPPDLL_PORT     relay port on 127.0.0.1 (default 17462)
 *   SIAPPDLL_LOG      write a log to this Windows path
 *   SIAPPDLL_CONFIG   button file (default %APPDATA%\inventor-on-linux\spacemouse.ini;
 *                     the launcher sets it to ~/.config/... as a \\?\unix\ path)
 *   SIAPPDLL_BUTTONS  V3DK codes in the button events, e.g. "0:fit,1:menu"
 *                     (see v3dk_names; for applications that read them)
 *   SIAPPDLL_SCALE    motion scale in percent (default 100)
 *
 * Only interface facts (exported names and signatures, struct layouts,
 * constant and event values) were taken, for ABI compatibility, from the
 * headers of SpaceNavigatorEmulator (GPLv3, github.com/lukenuttall/
 * SpaceNavigatorEmulator, siappdll/src/sidef.h, siappdll.h, syncapi.h).
 * No code or header text was copied; no 3Dconnexion or Autodesk binaries
 * were examined.
 *
 * SPDX-License-Identifier: MIT
 */

#define COBJMACROS
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <ole2.h>
#include <oleauto.h>
#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SPWAPI WINAPI

enum spw_ret
{
    SPW_NO_ERROR, SPW_ERROR, SI_BAD_HANDLE, SI_BAD_ID, SI_BAD_VALUE, SI_IS_EVENT,
    SI_SKIP_EVENT, SI_NOT_EVENT, SI_NO_DRIVER, SI_NO_RESPONSE, SI_UNSUPPORTED,
    SI_UNINITIALIZED, SI_WRONG_DRIVER, SI_INTERNAL_ERROR
};

enum
{
    SI_BUTTON_EVENT = 1, SI_MOTION_EVENT, SI_COMBO_EVENT, SI_ZERO_EVENT, SI_EXCEPTION_EVENT,
    SI_OUT_OF_BAND, SI_ORIENTATION_EVENT, SI_KEYBOARD_EVENT, SI_LPFK_EVENT, SI_APP_EVENT,
    SI_SYNC_EVENT, SI_BUTTON_PRESS_EVENT, SI_BUTTON_RELEASE_EVENT, SI_DEVICE_CHANGE_EVENT,
    SI_MOUSE_EVENT, SI_JOYSTICK_EVENT
};

#define SI_STRSIZE 128
#define SI_SPACEMOUSE_PRO 0xc62b

/* Only the event and info structures are written for the caller; Windows
 * "long" is 32 bit on x64 too, so their layout does not depend on packing. */
typedef struct { ULONG last, current, pressed, released; } SiButtonData;
typedef struct { SiButtonData button; LONG motion[6]; ULONG period; } SiSpwData;
typedef struct
{
    int type;
    union
    {
        SiSpwData spw;
        ULONG button_number;     /* SI_BUTTON_PRESS/RELEASE_EVENT: a V3DK code */
        char ex_data[128];
    } u;
} SiSpwEvent;
typedef struct { int dev_type, num_buttons, num_degrees; LONG can_beep; char firmware[SI_STRSIZE]; } SiDevInfo;
typedef struct { int major, minor, build; char version[SI_STRSIZE]; char date[SI_STRSIZE]; } SiVerInfo;
typedef struct { char name[SI_STRSIZE]; } SiName;

/* SiOpenData and SiGetEventData are filled by our own *WinInit functions and
 * read back by SiOpen/SiGetEvent, but allocated by the caller with its own
 * idea of their size (32/64 bit SDKs differ). Only the first 8 bytes are used,
 * which every variant has. */

/* V3DK virtual keys: what a button means to the application. */
static const struct { const char *name; ULONG code; } v3dk_names[] =
{
    { "menu", 1 }, { "fit", 2 }, { "top", 3 }, { "left", 4 }, { "right", 5 }, { "front", 6 },
    { "bottom", 7 }, { "back", 8 }, { "cw", 9 }, { "ccw", 10 }, { "iso1", 11 }, { "iso2", 12 },
};

#define MAX_BUTTONS 32
#define QUEUE_SIZE 64

static CRITICAL_SECTION cs;
static HWND app_hwnd;
static UINT spw_msg;
static HANDLE reader_thread;
static volatile LONG stopping;
static SOCKET sock = INVALID_SOCKET;
static int initialized, opened, connected;
static ULONG buttons, button_map[MAX_BUTTONS];
static int scale = 100;
static volatile LONG rotation_locked;   /* "lockrot": only pan and zoom */

static SiSpwEvent queue[QUEUE_SIZE];
static int q_head, q_tail;
static SiSpwEvent motion;           /* latest motion, coalesced */
static int motion_pending;

static FILE *log_file;
static HWND action_hwnd;            /* message-only, on the thread that called SiOpen */

#define WM_SPNAV_BUTTON (WM_APP + 1)   /* wparam: button, lparam: 1 press, 0 release */
#define WM_SPNAV_RUN    (WM_APP + 2)   /* run pending_action (chosen in the menu) */

__declspec(dllexport) enum spw_ret SpwErrorVal;

static void trace(const char *fmt, ...)
{
    va_list args;
    SYSTEMTIME t;

    if (!log_file) return;
    GetLocalTime(&t);
    fprintf(log_file, "%02u:%02u:%02u.%03u ", t.wHour, t.wMinute, t.wSecond, t.wMilliseconds);
    va_start(args, fmt);
    vfprintf(log_file, fmt, args);
    va_end(args);
    fflush(log_file);
}

static void parse_button_map(void)
{
    char buf[512], *tok, *ctx = NULL;
    unsigned int i;

    /* default: like 3DxWare's two-button SpaceMouse, left = menu, right = fit */
    button_map[0] = 1;
    button_map[1] = 2;
    if (!GetEnvironmentVariableA("SIAPPDLL_BUTTONS", buf, sizeof(buf))) return;
    for (tok = strtok_s(buf, ",", &ctx); tok; tok = strtok_s(NULL, ",", &ctx))
    {
        char *colon = strchr(tok, ':');
        int b = atoi(tok);

        if (!colon || b < 0 || b >= MAX_BUTTONS) continue;
        button_map[b] = strtoul(colon + 1, NULL, 0);
        for (i = 0; i < sizeof(v3dk_names) / sizeof(v3dk_names[0]); i++)
            if (!_stricmp(colon + 1, v3dk_names[i].name)) button_map[b] = v3dk_names[i].code;
        trace("button %d -> V3DK %lu\n", b, button_map[b]);
    }
}

static void post_event(void)
{
    HWND hwnd = app_hwnd;
    if (hwnd) PostMessageA(hwnd, spw_msg, 0, 0);
}

static void push_event(const SiSpwEvent *ev)
{
    EnterCriticalSection(&cs);
    if ((q_tail + 1) % QUEUE_SIZE != q_head)
    {
        queue[q_tail] = *ev;
        q_tail = (q_tail + 1) % QUEUE_SIZE;
    }
    LeaveCriticalSection(&cs);
    post_event();
}

static void handle_packet(const int *p)
{
    SiSpwEvent ev;
    int i, zero = 1, post;

    memset(&ev, 0, sizeof(ev));
    switch (p[0])
    {
    case 0: /* motion */
        for (i = 0; i < 6; i++) if (p[i + 1] && !(i >= 3 && rotation_locked)) zero = 0;
        EnterCriticalSection(&cs);
        post = !motion_pending;
        memset(&motion, 0, sizeof(motion));
        motion.type = zero ? SI_ZERO_EVENT : SI_MOTION_EVENT;
        for (i = 0; i < 6; i++) motion.u.spw.motion[i] = (i >= 3 && rotation_locked) ? 0 : p[i + 1] * scale / 100;
        motion.u.spw.period = p[7];
        motion.u.spw.button.current = motion.u.spw.button.last = buttons;
        motion_pending = 1;
        LeaveCriticalSection(&cs);
        if (post) post_event();
        break;

    case 1: /* button press */
    case 2: /* button release */
    {
        int b = p[1];
        ULONG bit = (b >= 0 && b < 31) ? 1ul << (b + 1) : 0;   /* SIAPP buttons are 1-based */

        trace("button %d %s\n", b, p[0] == 1 ? "press" : "release");
        ev.type = SI_BUTTON_EVENT;
        ev.u.spw.button.last = buttons;
        if (p[0] == 1) buttons |= bit; else buttons &= ~bit;
        ev.u.spw.button.current = buttons;
        ev.u.spw.button.pressed = p[0] == 1 ? bit : 0;
        ev.u.spw.button.released = p[0] == 2 ? bit : 0;
        push_event(&ev);
        if (action_hwnd) PostMessageA(action_hwnd, WM_SPNAV_BUTTON, b, p[0] == 1);

        if (b >= 0 && b < MAX_BUTTONS && button_map[b])
        {
            memset(&ev, 0, sizeof(ev));
            ev.type = p[0] == 1 ? SI_BUTTON_PRESS_EVENT : SI_BUTTON_RELEASE_EVENT;
            ev.u.button_number = button_map[b];
            push_event(&ev);
        }
        break;
    }
    }
}

static DWORD WINAPI reader_proc(void *arg)
{
    char portbuf[16];
    unsigned short port = 17462;

    if (GetEnvironmentVariableA("SIAPPDLL_PORT", portbuf, sizeof(portbuf))) port = atoi(portbuf);

    while (!stopping)
    {
        struct sockaddr_in addr = { AF_INET };
        int packet[8], got = 0, n;

        addr.sin_port = htons(port);
        addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        sock = socket(AF_INET, SOCK_STREAM, 0);
        if (sock == INVALID_SOCKET || connect(sock, (struct sockaddr *)&addr, sizeof(addr)))
        {
            if (sock != INVALID_SOCKET) closesocket(sock);
            sock = INVALID_SOCKET;
            Sleep(2000);
            continue;
        }
        connected = 1;
        trace("connected to spacenavd relay 127.0.0.1:%u\n", port);
        while (!stopping && (n = recv(sock, (char *)packet + got, sizeof(packet) - got, 0)) > 0)
        {
            if ((got += n) < (int)sizeof(packet)) continue;
            handle_packet(packet);
            got = 0;
        }
        connected = 0;
        trace("relay connection closed\n");
        closesocket(sock);
        sock = INVALID_SOCKET;
        if (!stopping) Sleep(2000);
    }
    return 0;
}

/* --- button actions --------------------------------------------------- */

#define MENU_MAX 8
#define ACTION_SIZE 256

static char config_path[MAX_PATH];
static char pending_action[ACTION_SIZE];

static void run_action(const char *action);

static void init_config_path(void)
{
    char dir[MAX_PATH];

    if (GetEnvironmentVariableA("SIAPPDLL_CONFIG", config_path, sizeof(config_path))) return;
    if (!GetEnvironmentVariableA("APPDATA", dir, sizeof(dir))) strcpy(dir, ".");
    snprintf(config_path, sizeof(config_path), "%s\\inventor-on-linux\\spacemouse.ini", dir);
}

static char *trim(char *s)
{
    char *end;

    while (*s == ' ' || *s == '\t') s++;
    end = s + strlen(s);
    while (end > s && (end[-1] == ' ' || end[-1] == '\t' || end[-1] == '\r' || end[-1] == '\n')) *--end = 0;
    return s;
}

/* what a button does when spacemouse.ini says nothing: like 3DxWare's
 * two-button SpaceMouse, left = menu, right = fit */
static const char *default_button(int b)
{
    return b == 0 ? "menu:views" : b == 1 ? "fit" : "";
}

/* the built-in "views" menu, clockwise from the top */
static const char *default_views[] =
{
    "Top|view:top", "Iso|view:iso", "Right|view:right", "Front|view:front",
    "Bottom|view:bottom", "Back|view:back", "Left|view:left", "Home|home",
};

/* --- Inventor through its COM API (late bound, IDispatch) */

static WCHAR *wide(const char *s, WCHAR *buf, int len)
{
    MultiByteToWideChar(CP_UTF8, 0, s, -1, buf, len);
    return buf;
}

/* argv is in reverse order, as DISPPARAMS wants it */
static HRESULT invoke(IDispatch *obj, const WCHAR *name, WORD flags, VARIANT *out, UINT argc, VARIANT *argv)
{
    DISPID id, put = DISPID_PROPERTYPUT;
    DISPPARAMS params = { argv, NULL, argc, 0 };
    LPOLESTR n = (LPOLESTR)name;
    VARIANT ignored;
    HRESULT hr;

    if (!obj) return E_POINTER;
    if (FAILED(hr = IDispatch_GetIDsOfNames(obj, &IID_NULL, &n, 1, LOCALE_USER_DEFAULT, &id)))
    {
        trace("COM: no member %ls (%08lx)\n", name, hr);
        return hr;
    }
    if (flags & DISPATCH_PROPERTYPUT)
    {
        params.rgdispidNamedArgs = &put;
        params.cNamedArgs = 1;
    }
    if (!out) out = &ignored;
    VariantInit(out);
    hr = IDispatch_Invoke(obj, id, &IID_NULL, LOCALE_USER_DEFAULT, flags, &params, out, NULL, NULL);
    if (FAILED(hr)) trace("COM: %ls failed (%08lx)\n", name, hr);
    if (out == &ignored) VariantClear(&ignored);
    return hr;
}

/* a property (or a method with these arguments) that returns an object */
static IDispatch *get_object(IDispatch *obj, const WCHAR *name, UINT argc, VARIANT *argv)
{
    VARIANT v;

    if (FAILED(invoke(obj, name, DISPATCH_METHOD | DISPATCH_PROPERTYGET, &v, argc, argv))) return NULL;
    if (V_VT(&v) == VT_DISPATCH && V_DISPATCH(&v)) return V_DISPATCH(&v);
    VariantClear(&v);
    return NULL;
}

static IDispatch *inventor(void)
{
    static IDispatch *app;
    IUnknown *unk;
    CLSID clsid;
    HRESULT hr;

    if (app) return app;
    if (FAILED(hr = CLSIDFromProgID(L"Inventor.Application", &clsid)) ||
        FAILED(hr = GetActiveObject(&clsid, NULL, &unk)))
    {
        trace("COM: Inventor.Application not found (%08lx)\n", hr);
        return NULL;
    }
    hr = IUnknown_QueryInterface(unk, &IID_IDispatch, (void **)&app);
    IUnknown_Release(unk);
    return SUCCEEDED(hr) ? app : NULL;
}

/* the value of an enum constant such as kFrontViewOrientation, from the type
 * library the object comes from, so no number is written down here */
static BOOL enum_value(IDispatch *obj, const WCHAR *name, LONG *value)
{
    ITypeInfo *info;
    ITypeLib *lib;
    UINT index, i, count;
    BOOL found = FALSE;

    if (FAILED(IDispatch_GetTypeInfo(obj, 0, LOCALE_USER_DEFAULT, &info))) return FALSE;
    if (FAILED(ITypeInfo_GetContainingTypeLib(info, &lib, &index)))
    {
        ITypeInfo_Release(info);
        return FALSE;
    }
    ITypeInfo_Release(info);
    count = ITypeLib_GetTypeInfoCount(lib);
    for (i = 0; i < count && !found; i++)
    {
        TYPEKIND kind;
        TYPEATTR *attr;
        WORD j;

        if (FAILED(ITypeLib_GetTypeInfoType(lib, i, &kind)) || kind != TKIND_ENUM) continue;
        if (FAILED(ITypeLib_GetTypeInfo(lib, i, &info))) continue;
        if (SUCCEEDED(ITypeInfo_GetTypeAttr(info, &attr)))
        {
            for (j = 0; j < attr->cVars && !found; j++)
            {
                VARDESC *var;
                BSTR var_name;

                if (FAILED(ITypeInfo_GetVarDesc(info, j, &var))) continue;
                if (SUCCEEDED(ITypeInfo_GetDocumentation(info, var->memid, &var_name, NULL, NULL, NULL)))
                {
                    VARIANT v;

                    VariantInit(&v);
                    if (var->varkind == VAR_CONST && !_wcsicmp(var_name, name) &&
                        SUCCEEDED(VariantChangeType(&v, var->lpvarValue, 0, VT_I4)))
                    {
                        *value = V_I4(&v);
                        found = TRUE;
                    }
                    SysFreeString(var_name);
                }
                ITypeInfo_ReleaseVarDesc(info, var);
            }
            ITypeInfo_ReleaseTypeAttr(info, attr);
        }
        ITypeInfo_Release(info);
    }
    ITypeLib_Release(lib);
    return found;
}

static IDispatch *active_view(void)
{
    IDispatch *view = get_object(inventor(), L"ActiveView", 0, NULL);
    if (!view) trace("no active view (no document open?)\n");
    return view;
}

/* View.Fit, View.GoHome, ... */
static void view_call(const WCHAR *method)
{
    IDispatch *view = active_view();

    if (!view) return;
    invoke(view, method, DISPATCH_METHOD, NULL, 0, NULL);
    IDispatch_Release(view);
}

static void set_view(const char *name)
{
    static const struct { const char *name; const WCHAR *orientation; } views[] =
    {
        { "front", L"kFrontViewOrientation" }, { "back", L"kBackViewOrientation" },
        { "top", L"kTopViewOrientation" }, { "bottom", L"kBottomViewOrientation" },
        { "left", L"kLeftViewOrientation" }, { "right", L"kRightViewOrientation" },
        { "iso", L"kIsoTopRightViewOrientation" }, { "iso1", L"kIsoTopRightViewOrientation" },
        { "iso2", L"kIsoTopLeftViewOrientation" },
    };
    WCHAR buf[64];
    const WCHAR *orientation = wide(name, buf, 64);  /* or a ViewOrientationTypeEnum name */
    IDispatch *view, *camera;
    VARIANT arg;
    LONG value;
    unsigned int i;

    for (i = 0; i < sizeof(views) / sizeof(views[0]); i++)
        if (!_stricmp(name, views[i].name)) orientation = views[i].orientation;
    if (!(view = active_view())) return;
    if ((camera = get_object(view, L"Camera", 0, NULL)))
    {
        if (!enum_value(camera, orientation, &value)) trace("unknown view orientation %ls\n", orientation);
        else
        {
            V_VT(&arg) = VT_I4;
            V_I4(&arg) = value;
            if (SUCCEEDED(invoke(camera, L"ViewOrientationType", DISPATCH_PROPERTYPUT, NULL, 1, &arg)))
            {
                invoke(camera, L"Fit", DISPATCH_METHOD, NULL, 0, NULL);
                invoke(camera, L"Apply", DISPATCH_METHOD, NULL, 0, NULL);
            }
        }
        IDispatch_Release(camera);
    }
    IDispatch_Release(view);
}

/* --- camera: saved views (V1-V3) and rotating the view by 90 degrees */

static IDispatch *saved_view[10][3];   /* Eye, Target, UpVector of each slot */

static double get_double(IDispatch *obj, const WCHAR *name)
{
    VARIANT v;
    double d = 0;

    if (SUCCEEDED(invoke(obj, name, DISPATCH_PROPERTYGET, &v, 0, NULL)) &&
        SUCCEEDED(VariantChangeType(&v, &v, 0, VT_R8))) d = V_R8(&v);
    VariantClear(&v);
    return d;
}

/* Camera.Eye = point: a put with an object, or a putref where only that exists */
static HRESULT put_object(IDispatch *obj, const WCHAR *name, IDispatch *value)
{
    VARIANT arg;
    HRESULT hr;

    V_VT(&arg) = VT_DISPATCH;
    V_DISPATCH(&arg) = value;
    if (FAILED(hr = invoke(obj, name, DISPATCH_PROPERTYPUT, NULL, 1, &arg)))
        hr = invoke(obj, name, DISPATCH_PROPERTYPUTREF, NULL, 1, &arg);
    return hr;
}

static IDispatch *active_camera(IDispatch **view)
{
    IDispatch *camera;

    if (!(*view = active_view())) return NULL;
    if (!(camera = get_object(*view, L"Camera", 0, NULL)))
    {
        IDispatch_Release(*view);
        *view = NULL;
    }
    return camera;
}

static void save_view(int slot)
{
    static const WCHAR *names[3] = { L"Eye", L"Target", L"UpVector" };
    IDispatch *view, *camera;
    int i;

    if (slot < 0 || slot > 9 || !(camera = active_camera(&view))) return;
    for (i = 0; i < 3; i++)
    {
        if (saved_view[slot][i]) IDispatch_Release(saved_view[slot][i]);
        saved_view[slot][i] = get_object(camera, names[i], 0, NULL);
    }
    trace("view %d saved\n", slot);
    IDispatch_Release(camera);
    IDispatch_Release(view);
}

static void restore_view(int slot)
{
    static const WCHAR *names[3] = { L"Eye", L"Target", L"UpVector" };
    IDispatch *view, *camera;
    int i;

    if (slot < 0 || slot > 9 || !saved_view[slot][0])
    {
        trace("view %d: nothing saved\n", slot);
        return;
    }
    if (!(camera = active_camera(&view))) return;
    for (i = 0; i < 3; i++) put_object(camera, names[i], saved_view[slot][i]);
    invoke(camera, L"Apply", DISPATCH_METHOD, NULL, 0, NULL);
    IDispatch_Release(camera);
    IDispatch_Release(view);
}

/* turn the picture by 90 degrees about the viewing direction: the up vector
 * becomes (direction x up), or (up x direction) for -90 */
static void roll_view(int degrees)
{
    IDispatch *view, *camera, *eye, *target, *up, *geometry, *new_up;
    double d[3], u[3], r[3], len;
    VARIANT args[3];

    if (!(camera = active_camera(&view))) return;
    eye = get_object(camera, L"Eye", 0, NULL);
    target = get_object(camera, L"Target", 0, NULL);
    up = get_object(camera, L"UpVector", 0, NULL);
    geometry = get_object(inventor(), L"TransientGeometry", 0, NULL);
    if (eye && target && up && geometry)
    {
        d[0] = get_double(target, L"X") - get_double(eye, L"X");
        d[1] = get_double(target, L"Y") - get_double(eye, L"Y");
        d[2] = get_double(target, L"Z") - get_double(eye, L"Z");
        len = sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2]);
        u[0] = get_double(up, L"X");
        u[1] = get_double(up, L"Y");
        u[2] = get_double(up, L"Z");
        if (len > 0)
        {
            int i;

            for (i = 0; i < 3; i++) d[i] /= len;
            r[0] = d[1] * u[2] - d[2] * u[1];
            r[1] = d[2] * u[0] - d[0] * u[2];
            r[2] = d[0] * u[1] - d[1] * u[0];
            if (degrees < 0) for (i = 0; i < 3; i++) r[i] = -r[i];
            /* arguments in reverse order */
            for (i = 0; i < 3; i++)
            {
                V_VT(&args[2 - i]) = VT_R8;
                V_R8(&args[2 - i]) = r[i];
            }
            if ((new_up = get_object(geometry, L"CreateUnitVector", 3, args)))
            {
                if (SUCCEEDED(put_object(camera, L"UpVector", new_up)))
                    invoke(camera, L"Apply", DISPATCH_METHOD, NULL, 0, NULL);
                IDispatch_Release(new_up);
            }
        }
    }
    if (eye) IDispatch_Release(eye);
    if (target) IDispatch_Release(target);
    if (up) IDispatch_Release(up);
    if (geometry) IDispatch_Release(geometry);
    IDispatch_Release(camera);
    IDispatch_Release(view);
}

static IDispatch *control_definitions(void)
{
    IDispatch *manager = get_object(inventor(), L"CommandManager", 0, NULL), *defs;

    if (!manager) return NULL;
    defs = get_object(manager, L"ControlDefinitions", 0, NULL);
    IDispatch_Release(manager);
    return defs;
}

/* a command by its internal name, as Inventor's ControlDefinitions list it */
static void run_command(const char *name)
{
    IDispatch *defs = control_definitions(), *def;
    WCHAR buf[128];
    VARIANT arg;

    if (!defs) return;
    V_VT(&arg) = VT_BSTR;
    V_BSTR(&arg) = SysAllocString(wide(name, buf, 128));
    if ((def = get_object(defs, L"Item", 1, &arg)))
    {
        invoke(def, L"Execute", DISPATCH_METHOD, NULL, 0, NULL);
        IDispatch_Release(def);
    }
    else trace("no command %s\n", name);
    VariantClear(&arg);
    IDispatch_Release(defs);
}

/* write every command's internal and display name next to spacemouse.ini */
static void dump_commands(void)
{
    IDispatch *defs = control_definitions();
    char path[MAX_PATH], *slash;
    VARIANT count, arg;
    FILE *f;
    LONG i;

    if (!defs) return;
    strcpy(path, config_path);
    if ((slash = strrchr(path, '\\'))) strcpy(slash + 1, "inventor-commands.txt");
    if (SUCCEEDED(invoke(defs, L"Count", DISPATCH_PROPERTYGET, &count, 0, NULL)) &&
        SUCCEEDED(VariantChangeType(&count, &count, 0, VT_I4)) && (f = fopen(path, "w")))
    {
        for (i = 1; i <= V_I4(&count); i++)
        {
            IDispatch *def;
            VARIANT internal, display;

            V_VT(&arg) = VT_I4;
            V_I4(&arg) = i;
            if (!(def = get_object(defs, L"Item", 1, &arg))) continue;
            if (SUCCEEDED(invoke(def, L"InternalName", DISPATCH_PROPERTYGET, &internal, 0, NULL)))
            {
                if (SUCCEEDED(invoke(def, L"DisplayName", DISPATCH_PROPERTYGET, &display, 0, NULL)) &&
                    V_VT(&display) == VT_BSTR && V_VT(&internal) == VT_BSTR)
                    fprintf(f, "%ls\t%ls\n", V_BSTR(&internal), V_BSTR(&display));
                VariantClear(&display);
                VariantClear(&internal);
            }
            IDispatch_Release(def);
        }
        fclose(f);
        trace("wrote %ld commands to %s\n", V_I4(&count), path);
    }
    IDispatch_Release(defs);
}

/* --- keys: "ctrl+z", "esc", "f6", "shift+tab" */

/* virtual keys of "ctrl+z" into vks (up to 8), their number or 0 */
static int parse_keys(const char *keys, WORD *vks)
{
    static const struct { const char *name; WORD vk; } names[] =
    {
        { "ctrl", VK_CONTROL }, { "shift", VK_SHIFT }, { "alt", VK_MENU }, { "win", VK_LWIN },
        { "esc", VK_ESCAPE }, { "enter", VK_RETURN }, { "tab", VK_TAB }, { "space", VK_SPACE },
        { "backspace", VK_BACK }, { "del", VK_DELETE }, { "delete", VK_DELETE }, { "ins", VK_INSERT },
        { "home", VK_HOME }, { "end", VK_END }, { "pgup", VK_PRIOR }, { "pgdn", VK_NEXT },
        { "left", VK_LEFT }, { "right", VK_RIGHT }, { "up", VK_UP }, { "down", VK_DOWN },
    };
    char buf[64], *tok, *ctx = NULL;
    int n = 0;
    unsigned int j;

    snprintf(buf, sizeof(buf), "%s", keys);
    for (tok = strtok_s(buf, "+", &ctx); tok && n < 8; tok = strtok_s(NULL, "+", &ctx))
    {
        WORD vk = 0;

        tok = trim(tok);
        for (j = 0; j < sizeof(names) / sizeof(names[0]); j++)
            if (!_stricmp(tok, names[j].name)) vk = names[j].vk;
        if (!vk && (tok[0] == 'f' || tok[0] == 'F') && atoi(tok + 1) >= 1 && atoi(tok + 1) <= 24)
            vk = VK_F1 + atoi(tok + 1) - 1;
        if (!vk && tok[0] && !tok[1])
        {
            SHORT scan = VkKeyScanA(tok[0]);
            if (scan != -1)
            {
                if ((scan & 0x100) && n < 7) vks[n++] = VK_SHIFT;
                vk = scan & 0xff;
            }
        }
        if (!vk)
        {
            trace("unknown key \"%s\"\n", tok);
            return 0;
        }
        vks[n++] = vk;
    }
    return n;
}

/* down (press) or up (release) only, for keys held with a button */
static void key_events(const WORD *vks, int n, BOOL up)
{
    INPUT in[8];
    int i;

    memset(in, 0, sizeof(in));
    for (i = 0; i < n; i++)
    {
        in[i].type = INPUT_KEYBOARD;
        in[i].ki.wVk = vks[up ? n - 1 - i : i];
        in[i].ki.dwFlags = up ? KEYEVENTF_KEYUP : 0;
    }
    SendInput(n, in, sizeof(INPUT));
}

static void send_keys(const char *keys)
{
    INPUT in[16];
    WORD vks[8];
    int n = parse_keys(keys, vks), i;

    memset(in, 0, sizeof(in));
    for (i = 0; i < n; i++)
    {
        in[i].type = in[2 * n - 1 - i].type = INPUT_KEYBOARD;
        in[i].ki.wVk = in[2 * n - 1 - i].ki.wVk = vks[i];
        in[2 * n - 1 - i].ki.dwFlags = KEYEVENTF_KEYUP;
    }
    SendInput(2 * n, in, sizeof(INPUT));
}

/* --- radial menu: a round popup at the mouse pointer. Point at an item (or
 * just move towards it) and click, or press the menu button again; Esc, a
 * right click or a click in the middle closes it. */

static struct { char label[64]; char action[ACTION_SIZE]; } menu_items[MENU_MAX];
static int menu_count, menu_hot = -1, menu_radius, menu_inner, menu_closing;
static char menu_title[64];
static HWND menu_hwnd, menu_prev_focus;
static HFONT menu_font;

static BOOL load_menu(const char *name)
{
    char section[96], key[8], value[ACTION_SIZE + 64], probe[8];
    int i;

    menu_count = 0;
    snprintf(section, sizeof(section), "menu:%s", name);
    GetPrivateProfileStringA(section, "title", name, menu_title, sizeof(menu_title), config_path);
    for (i = 1; i <= MENU_MAX; i++)
    {
        char *bar;

        snprintf(key, sizeof(key), "%d", i);
        if (!GetPrivateProfileStringA(section, key, "", value, sizeof(value), config_path)) continue;
        if (!(bar = strchr(value, '|'))) continue;
        *bar = 0;
        snprintf(menu_items[menu_count].label, sizeof(menu_items[0].label), "%s", trim(value));
        snprintf(menu_items[menu_count].action, sizeof(menu_items[0].action), "%s", trim(bar + 1));
        menu_count++;
    }
    /* the views menu needs no file; a [menu:views] section replaces it */
    if (!menu_count && !GetPrivateProfileSectionA(section, probe, sizeof(probe), config_path) &&
        !_stricmp(name, "views"))
    {
        strcpy(menu_title, "Views");
        for (i = 0; i < MENU_MAX; i++)
        {
            const char *bar = strchr(default_views[i], '|');
            snprintf(menu_items[i].label, sizeof(menu_items[0].label), "%.*s",
                     (int)(bar - default_views[i]), default_views[i]);
            snprintf(menu_items[i].action, sizeof(menu_items[0].action), "%s", bar + 1);
        }
        menu_count = MENU_MAX;
    }
    if (!menu_count) trace("menu %s: no items in %s\n", name, config_path);
    return menu_count > 0;
}

/* item i is centred at i * 360/n degrees, clockwise from the top */
static int menu_item_at(int x, int y)
{
    double dx = x - menu_radius, dy = menu_radius - y, angle, step = 2 * M_PI / menu_count;

    if (dx * dx + dy * dy < (double)menu_inner * menu_inner) return -1;
    angle = atan2(dx, dy) + step / 2;
    if (angle < 0) angle += 2 * M_PI;
    return (int)(angle / step) % menu_count;
}

static POINT menu_point(double angle, int r)
{
    POINT pt = { menu_radius + (LONG)lround(r * sin(angle)), menu_radius - (LONG)lround(r * cos(angle)) };
    return pt;
}

static void menu_paint(HDC hdc)
{
    static const COLORREF back = RGB(0x2b, 0x2f, 0x36), hot = RGB(0x2f, 0x6f, 0xcf),
                          line = RGB(0x55, 0x5b, 0x66), text = RGB(0xf0, 0xf0, 0xf0);
    int size = 2 * menu_radius, i;
    double step = 2 * M_PI / menu_count;
    HDC mem = CreateCompatibleDC(hdc);
    HBITMAP bmp = CreateCompatibleBitmap(hdc, size, size), old_bmp = SelectObject(mem, bmp);
    HPEN pen = CreatePen(PS_SOLID, 1, line), old_pen = SelectObject(mem, pen);
    HBRUSH back_brush = CreateSolidBrush(back), hot_brush = CreateSolidBrush(hot);
    HFONT old_font = SelectObject(mem, menu_font);
    RECT rc = { 0, 0, size, size };

    FillRect(mem, &rc, back_brush);
    for (i = 0; i < menu_count; i++)
    {
        double centre = i * step;
        POINT from = menu_point(centre + step / 2, menu_radius), to = menu_point(centre - step / 2, menu_radius);
        POINT label = menu_point(centre, (menu_radius + menu_inner) / 2);
        RECT text_rc = { label.x - menu_radius / 2, label.y - menu_radius / 6,
                         label.x + menu_radius / 2, label.y + menu_radius / 6 };

        SelectObject(mem, i == menu_hot ? hot_brush : back_brush);
        if (menu_count == 1) Ellipse(mem, 0, 0, size, size);
        else Pie(mem, 0, 0, size, size, from.x, from.y, to.x, to.y);
        SetBkMode(mem, TRANSPARENT);
        SetTextColor(mem, text);
        DrawTextA(mem, menu_items[i].label, -1, &text_rc, DT_CENTER | DT_VCENTER | DT_SINGLELINE | DT_END_ELLIPSIS);
    }
    SelectObject(mem, back_brush);
    Ellipse(mem, menu_radius - menu_inner, menu_radius - menu_inner, menu_radius + menu_inner, menu_radius + menu_inner);
    rc.left = menu_radius - menu_inner;
    rc.right = menu_radius + menu_inner;
    rc.top = menu_radius - menu_inner;
    rc.bottom = menu_radius + menu_inner;
    SetTextColor(mem, line);
    DrawTextA(mem, menu_title, -1, &rc, DT_CENTER | DT_VCENTER | DT_SINGLELINE | DT_END_ELLIPSIS);
    BitBlt(hdc, 0, 0, size, size, mem, 0, 0, SRCCOPY);

    SelectObject(mem, old_font);
    SelectObject(mem, old_pen);
    SelectObject(mem, old_bmp);
    DeleteObject(pen);
    DeleteObject(back_brush);
    DeleteObject(hot_brush);
    DeleteObject(bmp);
    DeleteDC(mem);
}

static void close_menu(int item)
{
    HWND hwnd = menu_hwnd;

    if (!hwnd || menu_closing) return;
    menu_closing = 1;
    if (GetCapture() == hwnd) ReleaseCapture();
    DestroyWindow(hwnd);
    menu_hwnd = NULL;
    menu_closing = 0;
    if (menu_prev_focus) SetForegroundWindow(menu_prev_focus);
    if (item >= 0 && item < menu_count)
    {
        trace("menu: %s\n", menu_items[item].label);
        strcpy(pending_action, menu_items[item].action);
        /* after the menu is gone and the application has the focus again */
        PostMessageA(action_hwnd, WM_SPNAV_RUN, 0, 0);
    }
}

static LRESULT CALLBACK menu_proc(HWND hwnd, UINT msg, WPARAM wparam, LPARAM lparam)
{
    PAINTSTRUCT ps;
    int item;

    switch (msg)
    {
    case WM_MOUSEMOVE:
        item = menu_item_at((short)LOWORD(lparam), (short)HIWORD(lparam));
        if (item != menu_hot)
        {
            menu_hot = item;
            InvalidateRect(hwnd, NULL, FALSE);
        }
        return 0;
    case WM_LBUTTONDOWN:
        return 0;
    case WM_LBUTTONUP:
        close_menu(menu_item_at((short)LOWORD(lparam), (short)HIWORD(lparam)));
        return 0;
    case WM_RBUTTONUP:
        close_menu(-1);
        return 0;
    case WM_KEYDOWN:
        if (wparam == VK_ESCAPE) close_menu(-1);
        else if (wparam == VK_RETURN) close_menu(menu_hot);
        return 0;
    case WM_ACTIVATE:
        if (LOWORD(wparam) == WA_INACTIVE) close_menu(-1);
        return 0;
    case WM_CAPTURECHANGED:
        if ((HWND)lparam != hwnd) close_menu(-1);
        return 0;
    case WM_ERASEBKGND:
        return 1;
    case WM_PAINT:
        menu_paint(BeginPaint(hwnd, &ps));
        EndPaint(hwnd, &ps);
        return 0;
    }
    return DefWindowProcA(hwnd, msg, wparam, lparam);
}

static void show_menu(const char *name)
{
    static ATOM cls;
    MONITORINFO mi = { sizeof(mi) };
    NONCLIENTMETRICSA ncm = { sizeof(ncm) };
    POINT pt;
    HDC hdc;
    int dpi, x, y, size;

    if (menu_hwnd) close_menu(-1);
    if (!load_menu(name)) return;
    if (!cls)
    {
        WNDCLASSA wc = { CS_DROPSHADOW, menu_proc, 0, 0, GetModuleHandleA(NULL), NULL, LoadCursorA(NULL, (LPCSTR)IDC_ARROW),
                         NULL, NULL, "siappdll_radial_menu" };
        cls = RegisterClassA(&wc);
    }
    hdc = GetDC(NULL);
    dpi = GetDeviceCaps(hdc, LOGPIXELSY);
    ReleaseDC(NULL, hdc);
    menu_radius = MulDiv(130, dpi, 96);
    menu_inner = MulDiv(34, dpi, 96);
    if (!menu_font && SystemParametersInfoA(SPI_GETNONCLIENTMETRICS, sizeof(ncm), &ncm, 0))
        menu_font = CreateFontIndirectA(&ncm.lfMessageFont);
    size = 2 * menu_radius;

    GetCursorPos(&pt);
    GetMonitorInfoA(MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST), &mi);
    x = max(mi.rcWork.left, min(pt.x - menu_radius, mi.rcWork.right - size));
    y = max(mi.rcWork.top, min(pt.y - menu_radius, mi.rcWork.bottom - size));
    menu_hot = -1;
    menu_prev_focus = GetForegroundWindow();
    menu_hwnd = CreateWindowExA(WS_EX_TOPMOST | WS_EX_TOOLWINDOW, "siappdll_radial_menu", menu_title, WS_POPUP,
                                x, y, size, size, menu_prev_focus, NULL, GetModuleHandleA(NULL), NULL);
    if (!menu_hwnd) return;
    SetWindowRgn(menu_hwnd, CreateEllipticRgn(0, 0, size + 1, size + 1), FALSE);
    ShowWindow(menu_hwnd, SW_SHOW);
    SetForegroundWindow(menu_hwnd);
    SetFocus(menu_hwnd);
    SetCapture(menu_hwnd);
    trace("menu %s: %d items at %ld,%ld\n", name, menu_count, pt.x, pt.y);
}

/* --- dispatch */

static void run_action(const char *action)
{
    char buf[ACTION_SIZE], *a;
    unsigned int i;

    snprintf(buf, sizeof(buf), "%s", action);
    a = trim(buf);
    if (!*a || !_stricmp(a, "none")) return;
    trace("action \"%s\"\n", a);
    if (!_stricmp(a, "menu")) show_menu("views");
    else if (!_strnicmp(a, "menu:", 5)) show_menu(trim(a + 5));
    else if (!_strnicmp(a, "key:", 4)) send_keys(a + 4);
    else if (!_strnicmp(a, "view:", 5)) set_view(trim(a + 5));
    else if (!_strnicmp(a, "cmd:", 4)) run_command(trim(a + 4));
    else if (!_stricmp(a, "fit")) view_call(L"Fit");
    else if (!_stricmp(a, "home")) view_call(L"GoHome");
    else if (!_stricmp(a, "dumpcmds")) dump_commands();
    else if (!_strnicmp(a, "saveview:", 9)) save_view(atoi(a + 9));
    else if (!_strnicmp(a, "restoreview:", 12)) restore_view(atoi(a + 12));
    else if (!_strnicmp(a, "roll:", 5)) roll_view(atoi(a + 5));
    else if (!_stricmp(a, "cw")) roll_view(90);
    else if (!_stricmp(a, "ccw")) roll_view(-90);
    else if (!_stricmp(a, "lockrot"))
    {
        rotation_locked = !rotation_locked;
        trace("rotation %s\n", rotation_locked ? "locked" : "unlocked");
    }
    else
    {
        /* the V3DK names: "front", "top", ... */
        for (i = 0; i < sizeof(v3dk_names) / sizeof(v3dk_names[0]); i++)
            if (!_stricmp(a, v3dk_names[i].name) && v3dk_names[i].code >= 3 && v3dk_names[i].code != 9 &&
                v3dk_names[i].code != 10)
            {
                set_view(a);
                return;
            }
        trace("unknown action\n");
    }
}

/* "hold:ctrl": the keys stay down while the button is, like 3DxWare's
 * Ctrl/Alt/Shift buttons (Ctrl+click, Shift+click work) */
static struct { WORD vks[8]; int n; } held[MAX_BUTTONS];

/* "<n>.long = action": what a button does when held (default 500 ms, [settings]
 * long_ms); its short action then runs on release instead of on press */
#define LONG_TIMER 0x100
static char short_action[MAX_BUTTONS][ACTION_SIZE], long_action[MAX_BUTTONS][ACTION_SIZE];

static void button_long(int b)
{
    char action[ACTION_SIZE];

    KillTimer(action_hwnd, LONG_TIMER + b);
    short_action[b][0] = 0;
    strcpy(action, long_action[b]);
    trace("button %d long\n", b);
    run_action(action);
}

static void button_released(int b)
{
    if (b < 0 || b >= MAX_BUTTONS) return;
    if (short_action[b][0])
    {
        char action[ACTION_SIZE];

        KillTimer(action_hwnd, LONG_TIMER + b);
        strcpy(action, short_action[b]);
        short_action[b][0] = 0;
        run_action(action);
    }
    if (!held[b].n) return;
    key_events(held[b].vks, held[b].n, TRUE);
    held[b].n = 0;
}

static void button_pressed(int b)
{
    char key[16], action[ACTION_SIZE], *a;

    /* the menu button again: take the item under the pointer, or close */
    if (menu_hwnd)
    {
        close_menu(menu_hot);
        return;
    }
    snprintf(key, sizeof(key), "%d", b);
    GetPrivateProfileStringA("buttons", key, default_button(b), action, sizeof(action), config_path);
    a = trim(action);
    snprintf(key, sizeof(key), "%d.long", b);
    if (b >= 0 && b < MAX_BUTTONS &&
        GetPrivateProfileStringA("buttons", key, "", long_action[b], sizeof(long_action[b]), config_path))
    {
        snprintf(short_action[b], sizeof(short_action[b]), "%s", a);
        if (!short_action[b][0]) strcpy(short_action[b], "none");
        SetTimer(action_hwnd, LONG_TIMER + b, GetPrivateProfileIntA("settings", "long_ms", 500, config_path), NULL);
        return;
    }
    if (!_strnicmp(a, "hold:", 5))
    {
        if (b < 0 || b >= MAX_BUTTONS) return;
        button_released(b);
        if ((held[b].n = parse_keys(a + 5, held[b].vks))) key_events(held[b].vks, held[b].n, FALSE);
        trace("hold \"%s\"\n", a + 5);
        return;
    }
    run_action(a);
}

static LRESULT CALLBACK action_proc(HWND hwnd, UINT msg, WPARAM wparam, LPARAM lparam)
{
    switch (msg)
    {
    case WM_TIMER:
        if (wparam >= LONG_TIMER && wparam < LONG_TIMER + MAX_BUTTONS)
        {
            button_long((int)(wparam - LONG_TIMER));
            return 0;
        }
        break;
    case WM_SPNAV_BUTTON:
        if (lparam) button_pressed((int)wparam);
        else button_released((int)wparam);
        return 0;
    case WM_SPNAV_RUN:
    {
        char action[ACTION_SIZE];

        strcpy(action, pending_action);
        run_action(action);
        return 0;
    }
    }
    return DefWindowProcA(hwnd, msg, wparam, lparam);
}

static void create_action_window(void)
{
    static ATOM cls;

    if (action_hwnd) return;
    if (!cls)
    {
        WNDCLASSA wc = { 0, action_proc, 0, 0, GetModuleHandleA(NULL), NULL, NULL, NULL, NULL, "siappdll_actions" };
        cls = RegisterClassA(&wc);
    }
    action_hwnd = CreateWindowExA(0, "siappdll_actions", "", 0, 0, 0, 0, 0, HWND_MESSAGE, NULL,
                                  GetModuleHandleA(NULL), NULL);
    trace("actions from %s\n", config_path);
}

/* --- library ---------------------------------------------------------- */

__declspec(dllexport) enum spw_ret SPWAPI SiInitialize(void)
{
    char path[MAX_PATH], buf[16];
    WSADATA wsa;

    if (initialized) return SpwErrorVal = SPW_NO_ERROR;
    if (!log_file && GetEnvironmentVariableA("SIAPPDLL_LOG", path, sizeof(path))) log_file = fopen(path, "a");
    if (GetEnvironmentVariableA("SIAPPDLL_SCALE", buf, sizeof(buf))) scale = atoi(buf);
    trace("SiInitialize\n");
    parse_button_map();
    init_config_path();
    WSAStartup(MAKEWORD(2, 2), &wsa);
    spw_msg = RegisterWindowMessageA("SpaceWareMessage00");
    stopping = 0;
    reader_thread = CreateThread(NULL, 0, reader_proc, NULL, 0, NULL);
    initialized = 1;
    return SpwErrorVal = SPW_NO_ERROR;
}

__declspec(dllexport) LONG SPWAPI SiIsInitialized(void)
{
    return initialized;
}

__declspec(dllexport) void SPWAPI SiTerminate(void)
{
    trace("SiTerminate\n");
    if (!initialized) return;
    stopping = 1;
    if (sock != INVALID_SOCKET) closesocket(sock);
    if (reader_thread)
    {
        WaitForSingleObject(reader_thread, 3000);
        CloseHandle(reader_thread);
        reader_thread = NULL;
    }
    WSACleanup();
    initialized = 0;
}

__declspec(dllexport) void SPWAPI SiGetLibraryInfo(SiVerInfo *info)
{
    trace("SiGetLibraryInfo\n");
    if (!info) return;
    memset(info, 0, sizeof(*info));
    info->major = 4;
    strcpy(info->version, "4.0.0 spacenavd");
}

__declspec(dllexport) enum spw_ret SPWAPI SiGetDriverInfo(SiVerInfo *info)
{
    trace("SiGetDriverInfo\n");
    if (!info) return SpwErrorVal = SI_BAD_VALUE;
    memset(info, 0, sizeof(*info));
    info->major = 10;
    strcpy(info->version, "10.0.0 spacenavd");
    return SpwErrorVal = SPW_NO_ERROR;
}

__declspec(dllexport) int SPWAPI SiGetNumDevices(void)
{
    trace("SiGetNumDevices\n");
    return 1;
}

__declspec(dllexport) int SPWAPI SiDeviceIndex(int idx)
{
    trace("SiDeviceIndex %d\n", idx);
    return idx == 0 ? 1 : -1;
}

__declspec(dllexport) void SPWAPI SiOpenWinInit(void *data, HWND hwnd)
{
    trace("SiOpenWinInit hwnd %p\n", hwnd);
    if (data) *(HWND *)data = hwnd;
}

__declspec(dllexport) void * SPWAPI SiOpen(const char *app, int devid, void *mask, int mode, void *data)
{
    trace("SiOpen app \"%s\" dev %d mode %d hwnd %p\n", app ? app : "", devid, mode, data ? *(HWND *)data : NULL);
    if (!initialized) { SpwErrorVal = SI_UNINITIALIZED; return NULL; }
    if (data) app_hwnd = *(HWND *)data;
    create_action_window();
    opened = 1;
    SpwErrorVal = SPW_NO_ERROR;
    return &opened;     /* a single device; any non-NULL handle */
}

__declspec(dllexport) void * SPWAPI SiOpenPort(const char *app, const void *port, int mode, void *data)
{
    trace("SiOpenPort\n");
    return SiOpen(app, 0, NULL, mode, data);
}

__declspec(dllexport) enum spw_ret SPWAPI SiClose(void *hdl)
{
    trace("SiClose\n");
    app_hwnd = NULL;
    if (menu_hwnd) close_menu(-1);
    if (action_hwnd) DestroyWindow(action_hwnd);
    action_hwnd = NULL;
    opened = 0;
    return SpwErrorVal = SPW_NO_ERROR;
}

__declspec(dllexport) int SPWAPI SiGetDeviceID(void *hdl)
{
    trace("SiGetDeviceID\n");
    return SI_SPACEMOUSE_PRO;
}

__declspec(dllexport) enum spw_ret SPWAPI SiGetDeviceInfo(void *hdl, SiDevInfo *info)
{
    trace("SiGetDeviceInfo\n");
    if (!info) return SpwErrorVal = SI_BAD_VALUE;
    memset(info, 0, sizeof(*info));
    info->dev_type = SI_SPACEMOUSE_PRO;
    info->num_buttons = 15;
    info->num_degrees = 6;
    strcpy(info->firmware, "spacenavd");
    return SpwErrorVal = SPW_NO_ERROR;
}

__declspec(dllexport) enum spw_ret SPWAPI SiGetDeviceName(void *hdl, SiName *name)
{
    trace("SiGetDeviceName\n");
    if (name) strcpy(name->name, "SpaceMouse (spacenavd)");
    return SpwErrorVal = SPW_NO_ERROR;
}

__declspec(dllexport) enum spw_ret SPWAPI SiGetButtonName(void *hdl, ULONG b, SiName *name)
{
    trace("SiGetButtonName %lu\n", b);
    if (name) sprintf(name->name, "Button %lu", b);
    return SpwErrorVal = SPW_NO_ERROR;
}

__declspec(dllexport) void SPWAPI SiGetEventWinInit(void *data, UINT msg, WPARAM wparam, LPARAM lparam)
{
    if (data) *(UINT *)data = msg;
}

static enum spw_ret get_event(const void *data, SiSpwEvent *ev, BOOL remove)
{
    enum spw_ret ret = SI_SKIP_EVENT;

    if (!data || !spw_msg || *(const UINT *)data != spw_msg) return SpwErrorVal = SI_NOT_EVENT;
    EnterCriticalSection(&cs);
    if (q_head != q_tail)
    {
        if (ev) *ev = queue[q_head];
        if (remove) q_head = (q_head + 1) % QUEUE_SIZE;
        ret = SI_IS_EVENT;
    }
    else if (motion_pending)
    {
        if (ev) *ev = motion;
        if (remove) motion_pending = 0;
        ret = SI_IS_EVENT;
    }
    LeaveCriticalSection(&cs);
    if (ret == SI_IS_EVENT && ev && ev->type != SI_MOTION_EVENT)
        trace("event type %d buttons %lx/%lx v3dk %lu\n", ev->type, ev->u.spw.button.pressed,
              ev->u.spw.button.released, ev->u.button_number);
    return SpwErrorVal = ret;
}

__declspec(dllexport) enum spw_ret SPWAPI SiGetEvent(void *hdl, int flags, const void *data, SiSpwEvent *ev)
{
    return get_event(data, ev, TRUE);
}

__declspec(dllexport) enum spw_ret SPWAPI SiPeekEvent(void *hdl, int flags, const void *data, SiSpwEvent *ev)
{
    return get_event(data, ev, FALSE);
}

__declspec(dllexport) LONG SPWAPI SiIsSpaceWareEvent(const void *data, void *hwnd)
{
    return data && spw_msg && *(const UINT *)data == spw_msg;
}

static int lowest_bit(ULONG mask)
{
    int i;
    for (i = 0; i < 32; i++) if (mask & (1ul << i)) return i;
    return 0;
}

__declspec(dllexport) int SPWAPI SiButtonPressed(SiSpwEvent *ev)
{
    return ev && ev->type == SI_BUTTON_EVENT ? lowest_bit(ev->u.spw.button.pressed) : 0;
}

__declspec(dllexport) int SPWAPI SiButtonReleased(SiSpwEvent *ev)
{
    return ev && ev->type == SI_BUTTON_EVENT ? lowest_bit(ev->u.spw.button.released) : 0;
}

__declspec(dllexport) int SPWAPI SiDispatch(void *hdl, void *data, SiSpwEvent *ev, void *handlers)
{
    trace("SiDispatch (unsupported)\n");
    return 0;
}

__declspec(dllexport) const char * SPWAPI SpwErrorString(enum spw_ret err)
{
    switch (err)
    {
    case SPW_NO_ERROR:      return "ok";
    case SPW_ERROR:         return "call failed";
    case SI_BAD_HANDLE:     return "handle not from SiOpen";
    case SI_BAD_ID:         return "unknown device";
    case SI_BAD_VALUE:      return "bad parameter";
    case SI_IS_EVENT:       return "message is a 3D mouse event";
    case SI_SKIP_EVENT:     return "message is the library's own, ignore it";
    case SI_NOT_EVENT:      return "message is not a 3D mouse event";
    case SI_NO_DRIVER:      return "spacenavd relay on 127.0.0.1 not listening";
    case SI_NO_RESPONSE:    return "spacenavd did not answer";
    case SI_UNSUPPORTED:    return "not implemented by this library";
    case SI_UNINITIALIZED:  return "SiInitialize was not called";
    case SI_WRONG_DRIVER:   return "driver version not supported";
    case SI_INTERNAL_ERROR: return "bug in siappdll";
    }
    return "unknown error";
}

/* Calls the library accepts and ignores. Logged, so a trace shows what an
 * application expects beyond navigation. */
#define STUB(name) \
    __declspec(dllexport) enum spw_ret SPWAPI name(void) { trace(#name " (stub)\n"); return SpwErrorVal = SPW_NO_ERROR; }

STUB(SiGrabDevice)
STUB(SiReleaseDevice)
STUB(SiRezero)
STUB(SiBeep)
STUB(SiSetLEDs)
STUB(SiSetUiMode)
STUB(SiSetTypeMask)
STUB(SiGetDevicePort)
STUB(SiGetDeviceImageFileName)
STUB(SiGetCompanyLogoFileName)
STUB(SiSyncSendQuery)
STUB(SiSyncGetVersion)
STUB(SiSyncGetNumberOfFunctions)
STUB(SiSyncGetFunction)
STUB(SiSyncGetButtonAssignment)
STUB(SiSyncSetButtonAssignment)
STUB(SiSyncSetButtonAssignmentAbsolute)
STUB(SiSyncSetButtonName)
STUB(SiSyncGetAxisLabel)
STUB(SiSyncSetAxisLabel)
STUB(SiSyncGetOrientation)
STUB(SiSyncSetOrientation)
STUB(SiSyncGetFilter)
STUB(SiSyncSetFilter)
STUB(SiSyncGetAxesState)
STUB(SiSyncSetAxesState)
STUB(SiSyncSetInfoLine)
STUB(SiSyncGetScaleOverall)
STUB(SiSyncSetScaleOverall)
STUB(SiSyncGetScaleTx)
STUB(SiSyncSetScaleTx)
STUB(SiSyncGetScaleTy)
STUB(SiSyncSetScaleTy)
STUB(SiSyncGetScaleTz)
STUB(SiSyncSetScaleTz)
STUB(SiSyncGetScaleRx)
STUB(SiSyncSetScaleRx)
STUB(SiSyncGetScaleRy)
STUB(SiSyncSetScaleRy)
STUB(SiSyncGetScaleRz)
STUB(SiSyncSetScaleRz)
STUB(SiSyncInvokeAbsoluteFunction)
STUB(SiSyncSetButtonState)
STUB(SiAppCmdWriteActionSet)
STUB(SiAppCmdActivateActionSet)
STUB(SiAppCmdWriteActionImages)

__declspec(dllexport) void * SPWAPI SiGetCompanyIcon(void)
{
    trace("SiGetCompanyIcon\n");
    return NULL;
}

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, void *reserved)
{
    if (reason == DLL_PROCESS_ATTACH)
    {
        DisableThreadLibraryCalls(inst);
        InitializeCriticalSection(&cs);
    }
    return TRUE;
}
