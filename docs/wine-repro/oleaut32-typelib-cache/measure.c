/*
 * MEASURE: what happens to a type library when the last reference goes, and
 * how expensive typelib-marshaled proxies for new objects are.
 *
 * Own test program (no Microsoft code). It builds its own large type library
 * with ICreateTypeLib2, registers it for the current user, measures, and
 * removes everything again. Only text comes back.
 *
 *   A  LoadTypeLib -> Release to 0 -> LoadTypeLib again: time of each load
 *      (a cache keeps the second one fast), and with a reference held.
 *   B  reference counts of the ITypeLib / ITypeInfo while a typelib-marshaled
 *      proxy and stub exist, and after they are gone.
 *   C  a new object marshaled from an MTA to an STA thread, one call, release -
 *      repeated: time per round when the program holds no reference to the
 *      type library, and when it holds one.
 *
 * Build (MinGW):
 *   x86_64-w64-mingw32-gcc -O2 -o measure64.exe measure.c -lole32 -loleaut32 -luuid
 *   i686-w64-mingw32-gcc   -O2 -o measure32.exe measure.c -lole32 -loleaut32 -luuid
 * Run: measure64.exe [interfaces] [functions] [rounds]   (default 3000 10 20)
 *
 * Written with AI help (Claude) for the Inventor-on-Linux project, LGPL 2.1+.
 */
#define COBJMACROS
#include <windows.h>
#include <ole2.h>
#include <oleauto.h>
#include <stdio.h>

/* {6C1F0A10-3B2E-4D7A-9A51-0F2C5EA10000}: library; interfaces ...0001 upwards */
static const GUID LIBID_Measure = {0x6c1f0a10, 0x3b2e, 0x4d7a, {0x9a, 0x51, 0x0f, 0x2c, 0x5e, 0xa1, 0x00, 0x00}};

static GUID iface_guid(unsigned int i)
{
    GUID g = LIBID_Measure;
    g.Data4[6] = (BYTE)((i + 1) >> 8);
    g.Data4[7] = (BYTE)(i + 1);
    return g;
}

/* not declared by every MinGW header version: load them at run time */
typedef HRESULT (WINAPI *register_for_user_fn)(ITypeLib *, OLECHAR *, OLECHAR *);
typedef HRESULT (WINAPI *unregister_for_user_fn)(REFGUID, WORD, WORD, LCID, SYSKIND);

static int n_ifaces = 3000, n_funcs = 10, n_rounds = 20;
static WCHAR tlb_path[MAX_PATH];
static GUID iid_measure;
static LARGE_INTEGER freq;

static double now_ms(void)
{
    LARGE_INTEGER t;
    QueryPerformanceCounter(&t);
    return (double)t.QuadPart * 1000.0 / (double)freq.QuadPart;
}

/* ---- the object: interface 0, IUnknown + n_funcs methods "Ping(long, long*)" */

typedef struct { void **vtbl; LONG ref; } measure_obj;
static void **obj_vtbl;

static HRESULT STDMETHODCALLTYPE obj_QueryInterface(measure_obj *This, REFIID iid, void **out)
{
    if (IsEqualIID(iid, &IID_IUnknown) || IsEqualIID(iid, &iid_measure))
    {
        *out = This;
        InterlockedIncrement(&This->ref);
        return S_OK;
    }
    *out = NULL;
    return E_NOINTERFACE;
}

static ULONG STDMETHODCALLTYPE obj_AddRef(measure_obj *This)
{
    return InterlockedIncrement(&This->ref);
}

static ULONG STDMETHODCALLTYPE obj_Release(measure_obj *This)
{
    LONG ref = InterlockedDecrement(&This->ref);
    if (!ref) HeapFree(GetProcessHeap(), 0, This);
    return ref;
}

static HRESULT STDMETHODCALLTYPE obj_Ping(measure_obj *This, LONG x, LONG *y)
{
    *y = x + 1;
    return S_OK;
}

static IUnknown *new_object(void)
{
    measure_obj *o = HeapAlloc(GetProcessHeap(), 0, sizeof(*o));
    o->vtbl = obj_vtbl;
    o->ref = 1;
    return (IUnknown *)o;
}

typedef HRESULT (STDMETHODCALLTYPE *ping_fn)(IUnknown *, LONG, LONG *);

/* ---- the type library */

static HRESULT build_typelib(void)
{
    ICreateTypeLib2 *ctl;
    ICreateTypeInfo *cti;
    ITypeLib *stdole;
    ITypeInfo *unk;
    HREFTYPE href;
    HRESULT hr;
    WCHAR name[64], fname[64];
    int i, j;

    hr = LoadTypeLib(L"stdole2.tlb", &stdole);
    if (FAILED(hr)) { printf("LoadTypeLib(stdole2) failed %#lx\n", hr); return hr; }
    hr = ITypeLib_GetTypeInfoOfGuid(stdole, &IID_IUnknown, &unk);
    ITypeLib_Release(stdole);
    if (FAILED(hr)) { printf("no IUnknown typeinfo %#lx\n", hr); return hr; }

#ifdef _WIN64
    hr = CreateTypeLib2(SYS_WIN64, tlb_path, &ctl);
#else
    hr = CreateTypeLib2(SYS_WIN32, tlb_path, &ctl);
#endif
    if (FAILED(hr)) { printf("CreateTypeLib2 failed %#lx\n", hr); return hr; }
    ICreateTypeLib2_SetGuid(ctl, &LIBID_Measure);
    ICreateTypeLib2_SetName(ctl, (LPOLESTR)L"MeasureTlCache");
    ICreateTypeLib2_SetVersion(ctl, 1, 0);
    ICreateTypeLib2_SetLcid(ctl, LOCALE_NEUTRAL);

    for (i = 0; i < n_ifaces; i++)
    {
        GUID g = iface_guid(i);
        _snwprintf(name, 64, L"IMeasure%d", i);
        hr = ICreateTypeLib2_CreateTypeInfo(ctl, name, TKIND_INTERFACE, &cti);
        if (FAILED(hr)) { printf("CreateTypeInfo %d failed %#lx\n", i, hr); return hr; }
        ICreateTypeInfo_SetGuid(cti, &g);
        ICreateTypeInfo_SetTypeFlags(cti, TYPEFLAG_FOLEAUTOMATION);
        ICreateTypeInfo_AddRefTypeInfo(cti, unk, &href);
        ICreateTypeInfo_AddImplType(cti, 0, href);
        for (j = 0; j < n_funcs; j++)
        {
            FUNCDESC fd;
            ELEMDESC params[2];
            TYPEDESC i4 = {{0}, VT_I4};
            LPOLESTR names[3];

            memset(&fd, 0, sizeof(fd));
            memset(params, 0, sizeof(params));
            params[0].tdesc.vt = VT_I4;
            params[0].paramdesc.wParamFlags = PARAMFLAG_FIN;
            params[1].tdesc.vt = VT_PTR;
            params[1].tdesc.lptdesc = &i4;
            params[1].paramdesc.wParamFlags = PARAMFLAG_FOUT | PARAMFLAG_FRETVAL;
            fd.memid = 0x60020000 + j;
            fd.funckind = FUNC_PUREVIRTUAL;
            fd.invkind = INVOKE_FUNC;
            fd.callconv = CC_STDCALL;
            fd.cParams = 2;
            fd.lprgelemdescParam = params;
            fd.elemdescFunc.tdesc.vt = VT_HRESULT;
            hr = ICreateTypeInfo_AddFuncDesc(cti, j, &fd);
            if (FAILED(hr)) { printf("AddFuncDesc %d/%d failed %#lx\n", i, j, hr); return hr; }
            _snwprintf(fname, 64, L"Ping%d", j);
            names[0] = fname; names[1] = (LPOLESTR)L"x"; names[2] = (LPOLESTR)L"y";
            ICreateTypeInfo_SetFuncAndParamNames(cti, j, names, 3);
        }
        hr = ICreateTypeInfo_LayOut(cti);
        if (FAILED(hr)) { printf("LayOut %d failed %#lx\n", i, hr); return hr; }
        ICreateTypeInfo_Release(cti);
    }
    ITypeInfo_Release(unk);
    hr = ICreateTypeLib2_SaveAllChanges(ctl);
    ICreateTypeLib2_Release(ctl);
    if (FAILED(hr)) printf("SaveAllChanges failed %#lx\n", hr);
    return hr;
}

static ULONG refcount(IUnknown *unk)
{
    IUnknown_AddRef(unk);
    return IUnknown_Release(unk);
}

/* ---- client thread (STA): unmarshal, call, release */

static HANDLE ev_ready, ev_done, ev_quit;
static IStream *shared_stream;
static IUnknown *kept_proxy;
static volatile int keep_proxy, client_hr, client_result;

static DWORD WINAPI client_thread(void *arg)
{
    HANDLE evs[2];
    CoInitializeEx(NULL, COINIT_APARTMENTTHREADED);
    evs[0] = ev_ready; evs[1] = ev_quit;
    for (;;)
    {
        IUnknown *proxy = NULL;
        LONG y = 0;
        DWORD w = WaitForMultipleObjects(2, evs, FALSE, INFINITE);
        if (w != WAIT_OBJECT_0) break;
        client_hr = CoGetInterfaceAndReleaseStream(shared_stream, &iid_measure, (void **)&proxy);
        if (SUCCEEDED(client_hr))
        {
            client_hr = ((ping_fn)(*(void ***)proxy)[3])(proxy, 41, &y);
            client_result = y;
            if (keep_proxy) kept_proxy = proxy;
            else IUnknown_Release(proxy);
        }
        SetEvent(ev_done);
    }
    if (kept_proxy) { IUnknown_Release(kept_proxy); kept_proxy = NULL; }
    CoUninitialize();
    return 0;
}

/* one round on the server (MTA) side: a new object to the client */
static double round_trip(void)
{
    IUnknown *obj = new_object();
    double t = now_ms();
    HRESULT hr = CoMarshalInterThreadInterfaceInStream(&iid_measure, obj, &shared_stream);
    IUnknown_Release(obj);
    if (FAILED(hr)) { printf("CoMarshalInterThreadInterfaceInStream failed %#lx\n", hr); return -1; }
    SetEvent(ev_ready);
    WaitForSingleObject(ev_done, INFINITE);
    t = now_ms() - t;
    if (FAILED(client_hr) || client_result != 42)
        printf("  round failed: hr %#x, result %d\n", client_hr, client_result);
    return t;
}

int main(int argc, char **argv)
{
    ITypeLib *tl, *tl2;
    ITypeInfo *ti;
    HMODULE ntdll = GetModuleHandleA("ntdll.dll");
    const char *(CDECL *wine_get_version)(void) = (void *)GetProcAddress(ntdll, "wine_get_version");
    double t0, t_first, t_second, t_held, sum;
    ULONG rc;
    HANDLE th;
    HRESULT hr;
    int i;

    HMODULE oleaut = GetModuleHandleA("oleaut32.dll");
    register_for_user_fn pRegisterTypeLibForUser =
        (register_for_user_fn)GetProcAddress(oleaut, "RegisterTypeLibForUser");
    unregister_for_user_fn pUnRegisterTypeLibForUser =
        (unregister_for_user_fn)GetProcAddress(oleaut, "UnRegisterTypeLibForUser");

    if (!pRegisterTypeLibForUser || !pUnRegisterTypeLibForUser)
    {
        printf("RegisterTypeLibForUser / UnRegisterTypeLibForUser not found\n");
        return 1;
    }
    if (argc > 1) n_ifaces = atoi(argv[1]);
    if (argc > 2) n_funcs = atoi(argv[2]);
    if (argc > 3) n_rounds = atoi(argv[3]);
    if (n_ifaces < 1 || n_funcs < 1 || n_rounds < 1) { printf("bad arguments\n"); return 1; }
    QueryPerformanceFrequency(&freq);

    printf("system: %s, %d-bit\n", wine_get_version ? "Wine" : "Windows", (int)sizeof(void *) * 8);
    if (wine_get_version) printf("wine: %s\n", wine_get_version());
    printf("type library: %d interfaces x %d functions, %d rounds\n", n_ifaces, n_funcs, n_rounds);

    iid_measure = iface_guid(0);
    obj_vtbl = HeapAlloc(GetProcessHeap(), 0, (3 + n_funcs) * sizeof(void *));
    obj_vtbl[0] = (void *)obj_QueryInterface;
    obj_vtbl[1] = (void *)obj_AddRef;
    obj_vtbl[2] = (void *)obj_Release;
    for (i = 0; i < n_funcs; i++) obj_vtbl[3 + i] = (void *)obj_Ping;

    GetTempPathW(MAX_PATH, tlb_path);
    lstrcatW(tlb_path, sizeof(void *) == 8 ? L"measure_tlcache64.tlb" : L"measure_tlcache32.tlb");
    DeleteFileW(tlb_path);

    CoInitializeEx(NULL, COINIT_MULTITHREADED);

    t0 = now_ms();
    if (FAILED(build_typelib())) return 1;
    {
        WIN32_FILE_ATTRIBUTE_DATA fa;
        GetFileAttributesExW(tlb_path, GetFileExInfoStandard, &fa);
        printf("created in %.0f ms, file size %lu bytes\n", now_ms() - t0, fa.nFileSizeLow);
    }

    /* A: loads */
    t0 = now_ms();
    hr = LoadTypeLib(tlb_path, &tl);
    t_first = now_ms() - t0;
    if (FAILED(hr)) { printf("LoadTypeLib failed %#lx\n", hr); return 1; }
    rc = ITypeLib_Release(tl);
    printf("A first load: %.2f ms, Release -> %lu\n", t_first, rc);
    t0 = now_ms();
    hr = LoadTypeLib(tlb_path, &tl2);
    t_second = now_ms() - t0;
    printf("A load after Release to 0: %.2f ms, same pointer: %s\n", t_second, tl2 == tl ? "yes" : "no");
    t0 = now_ms();
    hr = LoadTypeLib(tlb_path, &tl);
    t_held = now_ms() - t0;
    printf("A load while a reference is held: %.2f ms, same pointer: %s\n", t_held, tl == tl2 ? "yes" : "no");
    ITypeLib_Release(tl);
    rc = ITypeLib_Release(tl2);
    printf("A last Release -> %lu\n", rc);

    hr = LoadTypeLib(tlb_path, &tl);
    hr = pRegisterTypeLibForUser(tl, tlb_path, NULL);
    ITypeLib_Release(tl);
    if (FAILED(hr)) { printf("RegisterTypeLibForUser failed %#lx\n", hr); return 1; }

    ev_ready = CreateEventW(NULL, FALSE, FALSE, NULL);
    ev_done = CreateEventW(NULL, FALSE, FALSE, NULL);
    ev_quit = CreateEventW(NULL, TRUE, FALSE, NULL);
    th = CreateThread(NULL, 0, client_thread, NULL, 0, NULL);

    /* B: reference counts around one proxy/stub pair */
    LoadTypeLib(tlb_path, &tl);
    ITypeLib_GetTypeInfoOfGuid(tl, &iid_measure, &ti);
    printf("B before: ITypeLib refs %lu, ITypeInfo refs %lu\n",
           refcount((IUnknown *)tl), refcount((IUnknown *)ti));
    keep_proxy = 1;
    round_trip();
    printf("B proxy and stub alive: ITypeLib refs %lu, ITypeInfo refs %lu\n",
           refcount((IUnknown *)tl), refcount((IUnknown *)ti));
    keep_proxy = 0;
    /* the next round releases nothing kept; release the kept proxy on its thread */
    SetEvent(ev_quit);
    WaitForSingleObject(th, INFINITE);
    CloseHandle(th);
    printf("B proxy and stub released: ITypeLib refs %lu, ITypeInfo refs %lu\n",
           refcount((IUnknown *)tl), refcount((IUnknown *)ti));
    ITypeInfo_Release(ti);
    rc = ITypeLib_Release(tl);
    printf("B our last ITypeLib Release -> %lu\n", rc);

    /* C: rounds without and with a reference held by the program */
    ResetEvent(ev_quit);
    th = CreateThread(NULL, 0, client_thread, NULL, 0, NULL);
    round_trip();   /* warm up: proxy/stub code paths, apartments */
    for (sum = 0, i = 0; i < n_rounds; i++) sum += round_trip();
    printf("C no reference held: %.2f ms per round (%d rounds)\n", sum / n_rounds, n_rounds);
    LoadTypeLib(tlb_path, &tl);
    round_trip();
    for (sum = 0, i = 0; i < n_rounds; i++) sum += round_trip();
    printf("C reference held: %.2f ms per round (%d rounds)\n", sum / n_rounds, n_rounds);
    ITypeLib_Release(tl);
    SetEvent(ev_quit);
    WaitForSingleObject(th, INFINITE);
    CloseHandle(th);

#ifdef _WIN64
    hr = pUnRegisterTypeLibForUser(&LIBID_Measure, 1, 0, LOCALE_NEUTRAL, SYS_WIN64);
#else
    hr = pUnRegisterTypeLibForUser(&LIBID_Measure, 1, 0, LOCALE_NEUTRAL, SYS_WIN32);
#endif
    printf("unregistered: %#lx\n", hr);
    CoUninitialize();
    printf("file deleted: %s\n", DeleteFileW(tlb_path) ? "yes" : "no (still in use?)");
    return 0;
}
