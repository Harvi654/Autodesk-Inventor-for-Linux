"""Ensure the runtime layer contains x64 Windows binaries, not Linux libraries."""
from pathlib import Path
import hashlib
import struct
import sys


def check_pe(path):
    data = path.read_bytes()
    assert data[:2] == b"MZ", f"not a Windows executable: {path}"
    offset = struct.unpack_from("<I", data, 0x3C)[0]
    assert data[offset:offset + 4] == b"PE\0\0", f"invalid PE signature: {path}"
    machine = struct.unpack_from("<H", data, offset + 4)[0]
    assert machine == 0x8664, f"expected x64 PE, got {machine:#x}: {path}"
    print(f"Verified x64 PE: {path.name} ({len(data)} bytes)")


def check_d3dkmt_imports(path):
    # MinGW's DXGI import library also advertises these APIs, while native
    # DXVK DXGI does not export them. Linking them there compiles but aborts
    # at runtime. They must resolve to Wine's GDI32 implementation.
    data = path.read_bytes()
    nt = struct.unpack_from("<I", data, 0x3C)[0]
    optional = nt + 24
    sections = optional + struct.unpack_from("<H", data, nt + 20)[0]
    section_count = struct.unpack_from("<H", data, nt + 6)[0]

    def offset(rva):
        for i in range(section_count):
            size, address, raw_size, raw = struct.unpack_from("<IIII", data, sections + 40 * i + 8)
            if address <= rva < address + max(size, raw_size):
                return raw + rva - address
        raise AssertionError(f"unmapped PE address {rva:#x}")

    def string(rva):
        start = offset(rva)
        return data[start:data.index(0, start)].decode("ascii")

    descriptor = offset(struct.unpack_from("<I", data, optional + 120)[0])
    found = set()
    while any(data[descriptor:descriptor + 20]):
        original, _, _, module, first = struct.unpack_from("<IIIII", data, descriptor)
        dll = string(module).lower()
        thunk = offset(original or first)
        while (entry := struct.unpack_from("<Q", data, thunk)[0]):
            if entry < 2**63:
                name = string(entry + 2)
                if name.startswith("D3DKMT"):
                    assert dll == "gdi32.dll", f"{name} imported from {dll}, expected GDI32"
                    found.add(name)
            thunk += 8
        descriptor += 20
    assert "D3DKMTCreateDevice" in found, "missing D3DKMT resource-sharing imports"
    print(f"Verified {len(found)} D3DKMT imports resolve to GDI32")


layer, probe, runtime, original_wine = map(Path, sys.argv[1:])
for name in ["d3d12.dll", "d3d12core.dll", "dxgi.dll", "d3d11.dll"]:
    check_pe(layer / "drive_c/windows/system32" / name)
check_d3dkmt_imports(layer / "drive_c/windows/system32/d3d11.dll")
check_pe(probe / "drive_c/dxr-check.exe")
check_pe(probe / "drive_c/pixel-format-check.exe")
check_pe(probe / "drive_c/shared-texture-check.exe")
check_pe(runtime / "lib/wine/x86_64-windows/opengl32.dll")

# Wine resolves its builtin directory from the real bootstrap paths. Symlinks
# here silently select the original Wine and bypass the patched OpenGL DLL.
for relative in [
    "bin/.wine",
    "lib/wine/x86_64-unix/wine",
    "lib/wine/x86_64-unix/wine-preloader",
    "lib/wine/x86_64-unix/ntdll.so",
]:
    path = runtime / relative
    assert path.is_file() and not path.is_symlink(), f"bootstrap must be copied: {relative}"
    assert hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256(
        (original_wine / relative).read_bytes()
    ).digest(), f"unexpected bootstrap binary modification: {relative}"
    print(f"Verified unchanged copied bootstrap: {relative}")
