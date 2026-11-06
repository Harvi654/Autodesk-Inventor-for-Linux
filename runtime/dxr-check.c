/* Build as a Windows console executable; usable with any configured Wine prefix. */
#define COBJMACROS
#define INITGUID
#include <windows.h>
#include <dxgi1_6.h>
#include <d3d12.h>
#include <stdio.h>
#include <string.h>
#include <GL/gl.h>

static void check_opengl(const char *bin)
{
    WNDCLASSA cls = {0};
    PIXELFORMATDESCRIPTOR format = {0};
    HWND window;
    HDC dc;
    HGLRC context;
    cls.lpfnWndProc = DefWindowProcA;
    cls.hInstance = GetModuleHandleA(NULL);
    cls.lpszClassName = "InventorDxrProbe";
    RegisterClassA(&cls);
    window = CreateWindowA(cls.lpszClassName, "OpenGL diagnostic", WS_OVERLAPPED,
                          0, 0, 64, 64, NULL, NULL, cls.hInstance, NULL);
    dc = GetDC(window);
    format.nSize = sizeof(format);
    format.nVersion = 1;
    format.dwFlags = PFD_DRAW_TO_WINDOW | PFD_SUPPORT_OPENGL | PFD_DOUBLEBUFFER;
    format.iPixelType = PFD_TYPE_RGBA;
    format.cColorBits = 32;
    format.cDepthBits = 24;
    if (!window || !dc || !SetPixelFormat(dc, ChoosePixelFormat(dc, &format), &format) ||
        !(context = wglCreateContext(dc))) {
        printf("OPENGL_CONTEXT_ERROR=%lu\n", GetLastError());
    } else {
        if (wglMakeCurrent(dc, context)) {
            const char *version = (const char *)glGetString(GL_VERSION);
            printf("OPENGL_VERSION=%s\n", version ? version : "unavailable");
            SetDllDirectoryA(bin);
            HMODULE glf = LoadLibraryA("usd_glf.dll");
            typedef void (WINAPI *init_fn)(void);
            typedef const int *(WINAPI *caps_fn)(void);
            init_fn init = (init_fn)GetProcAddress(glf,
                "?InitInstance@GlfContextCaps@pxrInternal_adsk_v0_24__pxrReserved__@@SAXXZ");
            caps_fn caps = (caps_fn)GetProcAddress(glf,
                "?GetInstance@GlfContextCaps@pxrInternal_adsk_v0_24__pxrReserved__@@SAAEBV12@XZ");
            if (init && caps) {
                init();
                printf("USD_OPENGL_VERSION=%d\n", *caps());
            }
            wglMakeCurrent(NULL, NULL);
        } else printf("OPENGL_CURRENT_ERROR=%lu\n", GetLastError());
        wglDeleteContext(context);
    }
    if (dc) ReleaseDC(window, dc);
    if (window) DestroyWindow(window);
}

typedef HRESULT (WINAPI *create_factory_fn)(REFIID, void **);
typedef HRESULT (WINAPI *create_device_fn)(IUnknown *, D3D_FEATURE_LEVEL, REFIID, void **);

int main(int argc, char **argv)
{
    if (argc > 1) {
        check_opengl(argv[1]);
        HMODULE aurora;
        DWORD load_error;
        SetDllDirectoryA(argv[1]);
        aurora = LoadLibraryA("aurora.dll");
        load_error = GetLastError();
        printf("AURORA_LOAD=%s\n", aurora ? "success" : "failed");
        if (!aurora) printf("AURORA_LOAD_ERROR=%lu\n", load_error);
        if (argc <= 2 || strcmp(argv[2], "discover") != 0) {
            const char *plugins[] = { "agp_hydra_bridge.dll", "usd\\hdAurora.dll" };
            unsigned i;
            for (i = 0; i < sizeof(plugins) / sizeof(plugins[0]); ++i) {
                HMODULE plugin = LoadLibraryA(plugins[i]);
                DWORD error = GetLastError();
                printf("PLUGIN=%s LOAD=%s ERROR=%lu\n", plugins[i], plugin ? "success" : "failed", plugin ? 0 : error);
            }
        }
        if (aurora && argc > 2) {
            /* Query USD's actual renderer selection as well as loading the DLL.
             * These exports belong to Inventor 2026's Autodesk USD build. */
            HMODULE hd = LoadLibraryA("usd_hd.dll");
            HMODULE tf = LoadLibraryA("usd_tf.dll");
            typedef void *(WINAPI *registry_fn)(void);
            typedef void *(WINAPI *default_plugin_fn)(void *, void *, unsigned char);
            typedef void *(WINAPI *token_fn)(void *, const char *);
            registry_fn registry = (registry_fn)GetProcAddress(hd,
                "?GetInstance@HdRendererPluginRegistry@pxrInternal_adsk_v0_24__pxrReserved__@@SAAEAV12@XZ");
            default_plugin_fn default_plugin = (default_plugin_fn)GetProcAddress(hd,
                "?GetDefaultPluginId@HdRendererPluginRegistry@pxrInternal_adsk_v0_24__pxrReserved__@@QEAA?AVTfToken@2@_N@Z");
            token_fn token = (token_fn)GetProcAddress(tf,
                "??0TfToken@pxrInternal_adsk_v0_24__pxrReserved__@@QEAA@PEBD@Z");
            if (registry && default_plugin && token) {
                ULONG_PTR selected = 0, expected = 0;
                puts("USD_SELECTING_RENDERER=1");
                fflush(stdout);
                token(&expected, "HdAuroraRendererPlugin");
                default_plugin(registry(), &selected, 1);
                printf("USD_DEFAULT_RENDERER=%s\n", !selected ? "none" :
                    (selected & ~(ULONG_PTR)1) == (expected & ~(ULONG_PTR)1) ? "Aurora" : "other");
            } else puts("USD_DEFAULT_RENDERER=unknown API version");
            /* MSVC x64 returns std::shared_ptr through a hidden output pointer.
             * This diagnostic only checks initialization; process exit reclaims it. */
            struct { void *object; void *control; } renderer = {0};
            typedef void *(WINAPI *create_renderer_fn)(void *, int, unsigned);
            create_renderer_fn create_renderer = (create_renderer_fn)GetProcAddress(aurora,
                "?createRenderer@Aurora@@YA?AV?$shared_ptr@VIRenderer@Aurora@@@std@@W4Backend@IRenderer@1@I@Z");
            if (strcmp(argv[2], "discover") == 0) {
                puts("AURORA_INITIALIZATION=skipped (plugin discovery only)");
            } else if (create_renderer) {
                puts("AURORA_INITIALIZING=1");
                fflush(stdout);
                create_renderer(&renderer, 1, 1);
                printf("AURORA_RENDERER=%s\n", renderer.object ? "available" : "unavailable");
            } else puts("AURORA_RENDERER=unknown API version");
        }
    }
    HMODULE dxgi = LoadLibraryA("dxgi.dll"), d3d12 = LoadLibraryA("d3d12.dll");
    create_factory_fn create_factory;
    create_device_fn create_device;
    IDXGIFactory1 *factory = NULL;
    UINT index;
    int supported = 0;
    HRESULT hr;
    if (!dxgi || !d3d12) {
        fprintf(stderr, "Could not load DXGI/D3D12 (Windows error %lu)\n", GetLastError());
        return 2;
    }
    create_factory = (create_factory_fn)GetProcAddress(dxgi, "CreateDXGIFactory1");
    create_device = (create_device_fn)GetProcAddress(d3d12, "D3D12CreateDevice");
    if (!create_factory || !create_device) {
        fprintf(stderr, "Required DXGI/D3D12 exports are missing\n");
        return 2;
    }
    hr = create_factory(&IID_IDXGIFactory1, (void **)&factory);
    if (FAILED(hr)) {
        fprintf(stderr, "CreateDXGIFactory1 failed: %#lx\n", (unsigned long)hr);
        return 2;
    }
    for (index = 0; ; ++index) {
        IDXGIAdapter1 *adapter = NULL;
        DXGI_ADAPTER_DESC1 desc;
        ID3D12Device *device = NULL;
        ID3D12Device5 *ray_device = NULL;
        D3D12_FEATURE_DATA_D3D12_OPTIONS5 options = {0};
        char name[256];
        hr = IDXGIFactory1_EnumAdapters1(factory, index, &adapter);
        if (hr == DXGI_ERROR_NOT_FOUND) break;
        if (FAILED(hr)) break;
        IDXGIAdapter1_GetDesc1(adapter, &desc);
        WideCharToMultiByte(CP_UTF8, 0, desc.Description, -1, name, sizeof(name), NULL, NULL);
        printf("ADAPTER=%s\nVENDOR_ID=%#x\nDEVICE_ID=%#x\n", name, desc.VendorId, desc.DeviceId);
        hr = create_device((IUnknown *)adapter, D3D_FEATURE_LEVEL_12_0, &IID_ID3D12Device, (void **)&device);
        if (FAILED(hr)) {
            printf("D3D12_DEVICE_ERROR=%#lx\n", (unsigned long)hr);
        } else {
            hr = ID3D12Device_CheckFeatureSupport(device, D3D12_FEATURE_D3D12_OPTIONS5, &options, sizeof(options));
            if (SUCCEEDED(hr)) {
                printf("DXR_TIER=%s\n", options.RaytracingTier >= D3D12_RAYTRACING_TIER_1_1 ? "1.1" :
                       options.RaytracingTier >= D3D12_RAYTRACING_TIER_1_0 ? "1.0" : "unsupported");
                hr = ID3D12Device_QueryInterface(device, &IID_ID3D12Device5, (void **)&ray_device);
                printf("D3D12_DEVICE5=%s\n", SUCCEEDED(hr) ? "available" : "unavailable");
                if (ray_device && options.RaytracingTier >= D3D12_RAYTRACING_TIER_1_0) supported = 1;
                if (ray_device) ID3D12Device5_Release(ray_device);
            } else printf("DXR_QUERY_ERROR=%#lx\n", (unsigned long)hr);
            ID3D12Device_Release(device);
        }
        IDXGIAdapter1_Release(adapter);
    }
    IDXGIFactory1_Release(factory);
    puts(supported ? "DXR_AVAILABLE=1" : "DXR_AVAILABLE=0");
    return supported ? 0 : 1;
}
