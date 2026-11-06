/* Check the texture metadata handoff used by Inventor's GPU renderer.
 * The same DXGI adapter is used for the D3D12 producer and D3D11 consumer. */
#define COBJMACROS
#define INITGUID
#include <windows.h>
#include <dxgi1_6.h>
#include <d3d11_1.h>
#include <d3d12.h>
#include <stdio.h>
#define CHECK(call) do { HRESULT hr_ = (call); printf("%s=%08lx\n", #call, (unsigned long)hr_); if (FAILED(hr_)) return 1; } while(0)
int main(void) {
    HMODULE dxgi = LoadLibraryA("dxgi.dll"), d12 = LoadLibraryA("d3d12.dll"), d11 = LoadLibraryA("d3d11.dll");
    typedef HRESULT (WINAPI *factory_fn)(REFIID, void **);
    typedef HRESULT (WINAPI *device12_fn)(IUnknown *, D3D_FEATURE_LEVEL, REFIID, void **);
    typedef HRESULT (WINAPI *device11_fn)(IDXGIAdapter *, D3D_DRIVER_TYPE, HMODULE, UINT, const D3D_FEATURE_LEVEL *, UINT, UINT, ID3D11Device **, D3D_FEATURE_LEVEL *, ID3D11DeviceContext **);
    factory_fn factory = (factory_fn)(void *)GetProcAddress(dxgi, "CreateDXGIFactory1");
    device12_fn create12 = (device12_fn)(void *)GetProcAddress(d12, "D3D12CreateDevice");
    device11_fn create11 = (device11_fn)(void *)GetProcAddress(d11, "D3D11CreateDevice");
    if (!factory || !create12 || !create11) return 2;
    IDXGIFactory1 *f = NULL; IDXGIAdapter1 *adapter = NULL;
    CHECK(factory(&IID_IDXGIFactory1, (void **)&f));
    CHECK(IDXGIFactory1_EnumAdapters1(f, 0, &adapter));
    ID3D12Device *device12 = NULL;
    CHECK(create12((IUnknown *)adapter, D3D_FEATURE_LEVEL_11_0, &IID_ID3D12Device, (void **)&device12));
    D3D12_HEAP_PROPERTIES heap = {0}; heap.Type = D3D12_HEAP_TYPE_DEFAULT;
    D3D12_RESOURCE_DESC desc = {0}; desc.Dimension = D3D12_RESOURCE_DIMENSION_TEXTURE2D;
    desc.Width = 32; desc.Height = 32; desc.DepthOrArraySize = 1; desc.MipLevels = 1;
    desc.Format = DXGI_FORMAT_R8G8B8A8_UNORM; desc.SampleDesc.Count = 1;
    desc.Flags = D3D12_RESOURCE_FLAG_ALLOW_RENDER_TARGET;
    ID3D12Resource *resource = NULL;
    CHECK(ID3D12Device_CreateCommittedResource(device12, &heap, D3D12_HEAP_FLAG_SHARED, &desc, D3D12_RESOURCE_STATE_COMMON, NULL, &IID_ID3D12Resource, (void **)&resource));
    HANDLE handle = NULL;
    CHECK(ID3D12Device_CreateSharedHandle(device12, (ID3D12DeviceChild *)resource, NULL, GENERIC_ALL, NULL, &handle));
    ID3D11Device *device11 = NULL; ID3D11DeviceContext *context = NULL;
    CHECK(create11((IDXGIAdapter *)adapter, D3D_DRIVER_TYPE_UNKNOWN, NULL, 0, NULL, 0, D3D11_SDK_VERSION, &device11, NULL, &context));
    ID3D11Device1 *device11_1 = NULL;
    CHECK(ID3D11Device_QueryInterface(device11, &IID_ID3D11Device1, (void **)&device11_1));
    ID3D11Texture2D *texture = NULL;
    CHECK(ID3D11Device1_OpenSharedResource1(device11_1, handle, &IID_ID3D11Texture2D, (void **)&texture));
    D3D11_TEXTURE2D_DESC imported = {0}; ID3D11Texture2D_GetDesc(texture, &imported);
    printf("IMPORTED_TEXTURE=%ux%u FORMAT=%u\n", imported.Width, imported.Height, imported.Format);
    int success = imported.Width == 32 && imported.Height == 32 && imported.Format == desc.Format;
    ID3D11Texture2D_Release(texture); ID3D11Device1_Release(device11_1);
    ID3D11DeviceContext_Release(context); ID3D11Device_Release(device11);
    CloseHandle(handle); ID3D12Resource_Release(resource); ID3D12Device_Release(device12);
    IDXGIAdapter1_Release(adapter); IDXGIFactory1_Release(f);
    return success ? 0 : 1;
}
