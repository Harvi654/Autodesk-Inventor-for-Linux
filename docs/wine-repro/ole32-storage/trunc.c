/* Standalone version of test_transacted_truncate() from
 * patches/ole32-transacted-truncate-dirty.patch: a stream truncated to zero in
 * a transacted storage must survive Commit. Prints "0 failures" when fixed. */
#define COBJMACROS
#include <windows.h>
#include <ole2.h>
#include <stdio.h>

static int failures;
#define ok(c, ...) do { if (!(c)) { failures++; printf("FAIL line %d: ", __LINE__); printf(__VA_ARGS__); } } while (0)

static WCHAR filename[MAX_PATH] = L"trunc.stg";

static void check_tree(const char *what, BOOL nested, ULONG expect_a, ULONG expect_b)
{
    static const WCHAR stgname[] = L"SUB", stmname_a[] = L"A", stmname_b[] = L"B";
    IStorage *stg, *stg2;
    IEnumSTATSTG *e;
    STATSTG st;
    int count = 0, seen_a = 0, seen_b = 0;
    HRESULT hr;

    hr = StgOpenStorage(filename, NULL, STGM_READ | STGM_SHARE_EXCLUSIVE, NULL, 0, &stg);
    ok(hr == S_OK, "%s: StgOpenStorage failed, hr %#lx\n", what, hr);
    if (FAILED(hr)) return;
    stg2 = stg;
    if (nested)
    {
        hr = IStorage_OpenStorage(stg, stgname, NULL, STGM_READ | STGM_SHARE_EXCLUSIVE, NULL, 0, &stg2);
        ok(hr == S_OK, "%s: OpenStorage failed, hr %#lx\n", what, hr);
        if (FAILED(hr)) { IStorage_Release(stg); return; }
    }
    hr = IStorage_EnumElements(stg2, 0, NULL, 0, &e);
    ok(hr == S_OK, "%s: EnumElements failed, hr %#lx\n", what, hr);
    while (hr == S_OK && IEnumSTATSTG_Next(e, 1, &st, NULL) == S_OK && count < 10)
    {
        count++;
        if (!lstrcmpW(st.pwcsName, stmname_a))
        {
            seen_a++;
            ok(st.cbSize.QuadPart == expect_a, "%s: A has size %lu\n", what, (ULONG)st.cbSize.QuadPart);
        }
        else if (!lstrcmpW(st.pwcsName, stmname_b))
        {
            seen_b++;
            ok(st.cbSize.QuadPart == expect_b, "%s: B has size %lu\n", what, (ULONG)st.cbSize.QuadPart);
        }
        else
            ok(0, "%s: unexpected element %ls\n", what, st.pwcsName);
        CoTaskMemFree(st.pwcsName);
    }
    if (hr == S_OK) IEnumSTATSTG_Release(e);
    ok(count == 2 && seen_a == 1 && seen_b == 1, "%s: got %d elements, A %d, B %d\n", what, count, seen_a, seen_b);
    if (nested) IStorage_Release(stg2);
    IStorage_Release(stg);
}

/* write_again: write to B in the second transaction before truncating it, so
 * its data is in the scratch file rather than in the parent */
static void test_truncate(BOOL nested, BOOL write_again)
{
    static const WCHAR stgname[] = L"SUB", stmname_a[] = L"A", stmname_b[] = L"B";
    static BYTE buffer[8192];
    IStorage *stg, *stg2;
    IStream *stm_a, *stm_b;
    ULARGE_INTEGER size;
    char what[64];
    HRESULT hr;

    sprintf(what, "nested %d, write_again %d", nested, write_again);
    DeleteFileW(filename);

    hr = StgCreateDocfile(filename, STGM_CREATE | STGM_READWRITE | STGM_SHARE_EXCLUSIVE | STGM_TRANSACTED, 0, &stg);
    ok(hr == S_OK, "StgCreateDocfile failed, hr %#lx\n", hr);
    stg2 = stg;
    if (nested)
    {
        hr = IStorage_CreateStorage(stg, stgname, STGM_READWRITE | STGM_SHARE_EXCLUSIVE | STGM_TRANSACTED, 0, 0, &stg2);
        ok(hr == S_OK, "CreateStorage failed, hr %#lx\n", hr);
    }

    hr = IStorage_CreateStream(stg2, stmname_a, STGM_READWRITE | STGM_SHARE_EXCLUSIVE, 0, 0, &stm_a);
    ok(hr == S_OK, "CreateStream failed, hr %#lx\n", hr);
    hr = IStream_Write(stm_a, buffer, 6000, NULL);
    ok(hr == S_OK, "Write failed, hr %#lx\n", hr);
    hr = IStorage_CreateStream(stg2, stmname_b, STGM_READWRITE | STGM_SHARE_EXCLUSIVE, 0, 0, &stm_b);
    ok(hr == S_OK, "CreateStream failed, hr %#lx\n", hr);
    hr = IStream_Write(stm_b, buffer, 7000, NULL);
    ok(hr == S_OK, "Write failed, hr %#lx\n", hr);

    hr = IStorage_Commit(stg2, 0);
    ok(hr == S_OK, "Commit failed, hr %#lx\n", hr);

    if (write_again)
    {
        hr = IStream_Write(stm_b, buffer, 100, NULL);
        ok(hr == S_OK, "Write failed, hr %#lx\n", hr);
    }
    size.QuadPart = 0;
    hr = IStream_SetSize(stm_b, size);
    ok(hr == S_OK, "SetSize failed, hr %#lx\n", hr);

    hr = IStorage_Commit(stg2, 0);
    ok(hr == S_OK, "Commit failed, hr %#lx\n", hr);
    if (nested)
    {
        hr = IStorage_Commit(stg, 0);
        ok(hr == S_OK, "Commit failed, hr %#lx\n", hr);
    }

    IStream_Release(stm_a);
    IStream_Release(stm_b);
    if (nested) IStorage_Release(stg2);
    IStorage_Release(stg);

    check_tree(what, nested, 6000, 0);
    DeleteFileW(filename);
}

int main(void)
{
    CoInitialize(NULL);
    test_truncate(FALSE, FALSE);
    test_truncate(FALSE, TRUE);
    test_truncate(TRUE, FALSE);
    test_truncate(TRUE, TRUE);
    printf("%d failures\n", failures);
    return !!failures;
}
