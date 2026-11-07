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
 * Environment (Windows side; Wine passes the Linux environment through):
 *   SIAPPDLL_PORT     relay port on 127.0.0.1 (default 17462)
 *   SIAPPDLL_LOG      write a log to this Windows path
 *   SIAPPDLL_BUTTONS  button map, e.g. "0:fit,1:menu" (see v3dk_names)
 *   SIAPPDLL_SCALE    motion scale in percent (default 100)
 *
 * Interface facts (function names, struct layouts, constants) follow the
 * public SIAPP API as other open implementations use it; the code is new.
 *
 * SPDX-License-Identifier: MIT
 */

#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
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

static SiSpwEvent queue[QUEUE_SIZE];
static int q_head, q_tail;
static SiSpwEvent motion;           /* latest motion, coalesced */
static int motion_pending;

static FILE *logf;

__declspec(dllexport) enum spw_ret SpwErrorVal;

static void trace(const char *fmt, ...)
{
    va_list args;
    SYSTEMTIME t;

    if (!logf) return;
    GetLocalTime(&t);
    fprintf(logf, "%02u:%02u:%02u.%03u ", t.wHour, t.wMinute, t.wSecond, t.wMilliseconds);
    va_start(args, fmt);
    vfprintf(logf, fmt, args);
    va_end(args);
    fflush(logf);
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
        for (i = 0; i < 6; i++) if (p[i + 1]) zero = 0;
        EnterCriticalSection(&cs);
        post = !motion_pending;
        memset(&motion, 0, sizeof(motion));
        motion.type = zero ? SI_ZERO_EVENT : SI_MOTION_EVENT;
        for (i = 0; i < 6; i++) motion.u.spw.motion[i] = p[i + 1] * scale / 100;
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

/* --- library ---------------------------------------------------------- */

__declspec(dllexport) enum spw_ret SPWAPI SiInitialize(void)
{
    char path[MAX_PATH], buf[16];
    WSADATA wsa;

    if (initialized) return SpwErrorVal = SPW_NO_ERROR;
    if (!logf && GetEnvironmentVariableA("SIAPPDLL_LOG", path, sizeof(path))) logf = fopen(path, "a");
    if (GetEnvironmentVariableA("SIAPPDLL_SCALE", buf, sizeof(buf))) scale = atoi(buf);
    trace("SiInitialize\n");
    parse_button_map();
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
    static const char * const strings[] =
    {
        "no error", "function failed", "invalid handle", "invalid device ID", "invalid argument",
        "is an event", "skip this event", "not an event", "spacenavd relay not running",
        "no response", "unsupported", "not initialized", "wrong driver", "internal error"
    };
    return (unsigned)err < sizeof(strings) / sizeof(strings[0]) ? strings[err] : "unknown error";
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
